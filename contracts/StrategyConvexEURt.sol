// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

// These are the core Yearn libraries
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/math/SafeMath.sol";
import "@openzeppelin/contracts/utils/Address.sol";
import "@openzeppelin/contracts/token/ERC20/SafeERC20.sol";
import "@openzeppelin/contracts/math/Math.sol";

import "./interfaces/curve.sol";
import {IUniswapV2Router02} from "./interfaces/uniswap.sol";
import {
    BaseStrategy,
    StrategyParams
} from "@yearnvaults/contracts/BaseStrategy.sol";

interface IUniV3 {
    struct ExactInputParams {
        bytes path;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
    }

    function exactInput(ExactInputParams calldata params)
        external
        payable
        returns (uint256 amountOut);
}

interface IOracle {
    function ethToAsset(
        uint256 _ethAmountIn,
        address _tokenOut,
        uint32 _twapPeriod
    ) external view returns (uint256 amountOut);
}

interface IConvexRewards {
    // strategy's staked balance in the synthetix staking contract
    function balanceOf(address account) external view returns (uint256);

    // read how much claimable CRV a strategy has
    function earned(address account) external view returns (uint256);

    // stake a convex tokenized deposit
    function stake(uint256 _amount) external returns (bool);

    // withdraw to a convex tokenized deposit, probably never need to use this
    function withdraw(uint256 _amount, bool _claim) external returns (bool);

    // withdraw directly to curve LP token, this is what we primarily use
    function withdrawAndUnwrap(uint256 _amount, bool _claim)
        external
        returns (bool);

    // claim rewards, with an option to claim extra rewards or not
    function getReward(address _account, bool _claimExtras)
        external
        returns (bool);
}

interface IConvexDeposit {
    // deposit into convex, receive a tokenized deposit.  parameter to stake immediately (we always do this).
    function deposit(
        uint256 _pid,
        uint256 _amount,
        bool _stake
    ) external returns (bool);

    // burn a tokenized deposit (Convex deposit tokens) to receive curve lp tokens back
    function withdraw(uint256 _pid, uint256 _amount) external returns (bool);

    // give us info about a pool based on its pid
    function poolInfo(uint256)
        external
        view
        returns (
            address,
            address,
            address,
            address,
            address,
            bool
        );
}

/* ========== CONTRACT ========== */

contract StrategyConvexEURt is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;

    address public constant depositContract =
        0xF403C135812408BFbE8713b5A23a04b3D48AAE31; // this is the deposit contract that all pools use, aka booster
    address public rewardsContract; // This is unique to each curve pool
    uint256 public pid; // this is unique to each pool
    address public constant sushiswapRouter =
        0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F; // default to sushiswap, more CRV liquidity there
    address public constant uniswapv3 =
        0xE592427A0AEce92De3Edee1F18E0157C05861564;
    address public constant uniswapQuoter =
        0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6;

    address public constant voter = 0xF147b8125d2ef93FB6965Db97D6746952a133934; // Yearn's veCRV voter, we send some extra CRV here
    address[] public crvPath; // path to sell CRV
    address[] public convexTokenPath; // path to sell CVX
    // Swap stuff
    uint256 public keepCRV = 1000; // the percentage of CRV we re-lock for boost (in basis points)
    uint256 public constant FEE_DENOMINATOR = 10000; // with this and the above, sending 10% of our CRV yield to our voter
    ICrvV3 public constant crv =
        ICrvV3(0xD533a949740bb3306d119CC777fa900bA034cd52);
    IERC20 public constant convexToken =
        IERC20(0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B);
    IERC20 public constant weth =
        IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    uint256 public harvestProfitNeeded;

    // convex-specific variables
    bool public claimRewards = false; // boolean if we should always claim rewards when withdrawing, usually withdrawAndUnwrap (generally this should be false)

    // specific variables for this contract
    ICurveFi public constant curve =
        ICurveFi(0xFD5dB7463a3aB53fD211b4af195c5BCCC1A03890); // Curve EURT Pool, need this for buying more pool tokens
    IERC20 public constant eurt =
        IERC20(0xC581b735A1688071A1746c968e0798D642EDE491);
    IERC20 public constant usdt =
        IERC20(0xdAC17F958D2ee523a2206206994597C13D831ec7);
    IOracle public oracle = IOracle(0x0F1f5A87f99f0918e6C81F16E59F3518698221Ff);

    constructor(address _vault, uint256 _pid) public BaseStrategy(_vault) {
        // You can set these parameters on deployment to whatever you want
        maxReportDelay = 60 * 60 * 24 * 7; // 7 days in seconds, if we hit this then harvestTrigger = True
        debtThreshold = 5 * 1e18; // set a bit of a buffer
        profitFactor = 10_000; // in this strategy, profitFactor is only used for telling keep3rs when to move funds from vault to strategy (what previously was an earn call)
        harvestProfitNeeded = 10_0000e18;

        // want = Curve LP
        want.safeApprove(address(depositContract), type(uint256).max);
        IERC20(address(crv)).safeApprove(sushiswapRouter, type(uint256).max);
        convexToken.safeApprove(sushiswapRouter, type(uint256).max);

        // setup our rewards contract
        pid = _pid;
        (, , , rewardsContract, , ) = IConvexDeposit(depositContract).poolInfo(
            pid
        );

        // strategy-specific approvals and paths
        IERC20(address(eurt)).safeApprove(address(curve), type(uint256).max);
        IERC20(address(weth)).safeApprove(uniswapv3, type(uint256).max);

        // crv token path
        crvPath = new address[](2);
        crvPath[0] = address(crv);
        crvPath[1] = address(weth);

        // convex token path
        convexTokenPath = new address[](2);
        convexTokenPath[0] = address(convexToken);
        convexTokenPath[1] = address(weth);
    }

    function name() external view override returns (string memory) {
        return "StrategyConvexEURt";
    }

    function _stakedBalance() internal view returns (uint256) {
        return IConvexRewards(rewardsContract).balanceOf(address(this));
    }

    function _balanceOfWant() internal view returns (uint256) {
        return want.balanceOf(address(this));
    }

    function claimableBalance() internal view returns (uint256) {
        return IConvexRewards(rewardsContract).earned(address(this)); // how much CRV we can claim from the staking contract
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        return _balanceOfWant().add(_stakedBalance());
    }

    function prepareReturn(uint256 _debtOutstanding)
        internal
        override
        returns (
            uint256 _profit,
            uint256 _loss,
            uint256 _debtPayment
        )
    {
        // if we have anything staked, then harvest CRV and CVX from the rewards contract
        if (claimableBalance() > 0) {
            // this claims our CRV, CVX, and any extra tokens like SNX or ANKR. set to false if these tokens don't exist, true if they do.
            IConvexRewards(rewardsContract).getReward(address(this), false);

            uint256 crvBalance = crv.balanceOf(address(this));
            uint256 convexBalance = convexToken.balanceOf(address(this));

            uint256 _keepCRV = crvBalance.mul(keepCRV).div(FEE_DENOMINATOR);
            IERC20(address(crv)).safeTransfer(voter, _keepCRV);
            uint256 crvRemainder = crvBalance.sub(_keepCRV);

            if (crvRemainder > 0) _sellCrv(crvRemainder);
            if (convexBalance > 0) _sellConvex(convexBalance);

            uint256 wethBalance = weth.balanceOf(address(this));
            if (wethBalance > 0) _sellWethForEurt(wethBalance);

            uint256 eurtBalance = eurt.balanceOf(address(this));
            if (eurtBalance > 0) {
                curve.add_liquidity([eurtBalance, 0], 0);
            }
        }

        // serious loss should never happen, but if it does (for instance, if Curve is hacked), let's record it accurately
        uint256 assets = estimatedTotalAssets();
        uint256 debt = vault.strategies(address(this)).totalDebt;

        // if assets are greater than debt, things are working great!
        if (assets > debt) {
            _profit = want.balanceOf(address(this));
        } else {
            // if assets are less than debt, we are in trouble
            _loss = debt.sub(assets);
        }

        // debtOustanding will only be > 0 in the event of revoking or lowering debtRatio of a strategy
        if (_debtOutstanding > 0) {
            if (_stakedBalance() > 0) {
                IConvexRewards(rewardsContract).withdrawAndUnwrap(
                    Math.min(_stakedBalance(), _debtOutstanding),
                    claimRewards
                );
            }
            _debtPayment = Math.min(
                _debtOutstanding,
                want.balanceOf(address(this))
            );
            // want to make sure we report losses properly here
            if (_debtPayment < _debtOutstanding) {
                _loss = _debtOutstanding.sub(_debtPayment);
                if (_profit > _loss) {
                    _profit = _profit.sub(_loss);
                    _loss = 0;
                } else {
                    _loss = _loss.sub(_profit);
                    _profit = 0;
                }
            }
        }
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }
        // Send all of our Curve pool tokens to be deposited
        uint256 _toInvest = _balanceOfWant();
        // deposit into convex and stake immediately but only if we have something to invest
        if (_toInvest > 0) {
            IConvexDeposit(depositContract).deposit(pid, _toInvest, true);
        }
    }

    function liquidatePosition(uint256 _amountNeeded)
        internal
        override
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        if (_amountNeeded > _balanceOfWant()) {
            if (_stakedBalance() > 0) {
                IConvexRewards(rewardsContract).withdrawAndUnwrap(
                    Math.min(
                        _stakedBalance(),
                        _amountNeeded - _balanceOfWant()
                    ),
                    claimRewards
                );
            }

            _liquidatedAmount = Math.min(_amountNeeded, _balanceOfWant());
            _loss = _amountNeeded.sub(_liquidatedAmount);
        } else {
            // we have enough balance to cover the liquidation available
            return (_amountNeeded, 0);
        }
    }

    // fire sale, get rid of it all!
    function liquidateAllPositions() internal override returns (uint256) {
        if (_stakedBalance() > 0) {
            // don't bother withdrawing zero
            IConvexRewards(rewardsContract).withdrawAndUnwrap(
                _stakedBalance(),
                claimRewards
            );
        }
        return _balanceOfWant();
    }

    // Sells our harvested CRV into the selected output (ETH).
    function _sellCrv(uint256 _crvAmount) internal {
        IUniswapV2Router02(sushiswapRouter).swapExactTokensForTokens(
            _crvAmount,
            uint256(0),
            crvPath,
            address(this),
            now
        );
    }

    // Sells our harvested CVX into the selected output (ETH).
    function _sellConvex(uint256 _convexAmount) internal {
        IUniswapV2Router02(sushiswapRouter).swapExactTokensForTokens(
            _convexAmount,
            uint256(0),
            convexTokenPath,
            address(this),
            now
        );
    }

    function _sellWethForEurt(uint256 _amount) internal {
        IUniV3(uniswapv3).exactInput(
            IUniV3.ExactInputParams(
                abi.encodePacked(
                    address(weth),
                    uint24(500),
                    address(usdt),
                    uint24(500),
                    address(eurt)
                ),
                address(this),
                now,
                _amount,
                uint256(1)
            )
        );
    }

    // in case we need to exit into the convex deposit token, this will allow us to do that
    // make sure to check claimRewards before this step if needed
    // plan to have gov sweep convex deposit tokens from strategy after this
    function withdrawToConvexDepositTokens() external onlyAuthorized {
        if (_stakedBalance() > 0) {
            IConvexRewards(rewardsContract).withdraw(
                _stakedBalance(),
                claimRewards
            );
        }
    }

    // migrate our want token to a new strategy if needed, make sure to check claimRewards first
    // also send over any CRV or CVX that is claimed; for migrations we definitely want to claim
    function prepareMigration(address _newStrategy) internal override {
        if (_stakedBalance() > 0) {
            IConvexRewards(rewardsContract).withdrawAndUnwrap(
                _stakedBalance(),
                claimRewards
            );
        }
        IERC20(address(crv)).safeTransfer(
            _newStrategy,
            crv.balanceOf(address(this))
        );
        IERC20(address(convexToken)).safeTransfer(
            _newStrategy,
            convexToken.balanceOf(address(this))
        );
    }

    // we don't want for these tokens to be swept out. We allow gov to sweep out cvx vault tokens; we would only be holding these if things were really, really rekt.
    function protectedTokens()
        internal
        view
        override
        returns (address[] memory)
    {
        address[] memory protected = new address[](0);

        return protected;
    }

    /* ========== KEEP3RS ========== */

    function harvestTrigger(uint256 callCostinEth)
        public
        view
        override
        returns (bool)
    {
        return
            super.harvestTrigger(callCostinEth) ||
            claimableProfitInUsd() > harvestProfitNeeded;
    }

    function claimableProfitInUsd() internal view returns (uint256) {
        // calculations pulled directly from CVX's contract for minting CVX per CRV claimed
        uint256 totalCliffs = 1000;
        uint256 maxSupply = 100 * 1000000 * 1e18; // 100mil
        uint256 reductionPerCliff = 100000000000000000000000; // 100,000
        uint256 supply = convexToken.totalSupply();
        uint256 mintableCvx;

        uint256 cliff = supply.div(reductionPerCliff);
        //mint if below total cliffs
        if (cliff < totalCliffs) {
            //for reduction% take inverse of current cliff
            uint256 reduction = totalCliffs.sub(cliff);
            //reduce
            mintableCvx = claimableBalance().mul(reduction).div(totalCliffs);

            //supply cap check
            uint256 amtTillMax = maxSupply.sub(supply);
            if (mintableCvx > amtTillMax) {
                mintableCvx = amtTillMax;
            }
        }

        address[] memory crv_usd_path = new address[](3);
        crv_usd_path[0] = address(crv);
        crv_usd_path[1] = address(weth);
        crv_usd_path[2] = address(usdt);

        address[] memory cvx_usd_path = new address[](3);
        cvx_usd_path[0] = address(convexToken);
        cvx_usd_path[1] = address(weth);
        cvx_usd_path[2] = address(usdt);

        uint256 crvValue;
        if (claimableBalance() > 0) {
            uint256[] memory crvSwap =
                IUniswapV2Router02(sushiswapRouter).getAmountsOut(
                    claimableBalance(),
                    crv_usd_path
                );
            crvValue = crvSwap[1];
        }

        uint256 cvxValue;
        if (mintableCvx > 0) {
            uint256[] memory cvxSwap =
                IUniswapV2Router02(sushiswapRouter).getAmountsOut(
                    mintableCvx,
                    cvx_usd_path
                );
            cvxValue = cvxSwap[1];
        }
        return crvValue.add(cvxValue);
    }

    // convert our keeper's eth cost into want
    function ethToWant(uint256 _ethAmount)
        public
        view
        override
        returns (uint256)
    {
        uint256 callCostInWant;
        if (_ethAmount > 0) {
            uint256 callCostInEur =
                oracle.ethToAsset(_ethAmount, address(eurt), 1800);
            callCostInWant = curve.calc_token_amount([callCostInEur, 0], true);
        }
        return callCostInWant;
    }

    /* ========== SETTERS ========== */

    // These functions are useful for setting parameters of the strategy that may need to be adjusted.

    // Set the amount of CRV to be locked in Yearn's veCRV voter from each harvest. Default is 10%.
    function setKeepCRV(uint256 _keepCRV) external onlyAuthorized {
        keepCRV = _keepCRV;
    }

    // We usually don't need to claim rewards on withdrawals, but might change our mind for migrations etc
    function setClaimRewards(bool _claimRewards) external onlyAuthorized {
        claimRewards = _claimRewards;
    }

    // This determines when we tell our keepers to harvest based on profit
    function setHarvestProfitNeeded(uint256 _harvestProfitNeeded)
        external
        onlyAuthorized
    {
        harvestProfitNeeded = _harvestProfitNeeded;
    }
}
