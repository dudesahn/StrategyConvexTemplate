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

abstract contract StrategyConvexBase is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;

    /* ========== STATE CONSTANTS ========== */
    // these should stay the same across different wants.

    address public constant depositContract =
        0xF403C135812408BFbE8713b5A23a04b3D48AAE31; // this is the deposit contract that all pools use, aka booster
    address public rewardsContract; // This is unique to each curve pool
    uint256 public pid; // this is unique to each pool
    address public constant sushiswap =
        0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F; // default to sushiswap, more CRV and CVX liquidity there
    address public constant uniswapv3 =
        0xE592427A0AEce92De3Edee1F18E0157C05861564;
    ICurveFi public curve; // Curve Pool, need this for buying more pool tokens

    address public constant voter = 0xF147b8125d2ef93FB6965Db97D6746952a133934; // Yearn's veCRV voter, we send some extra CRV here
    address[] public crvPath; // path to sell CRV
    address[] public convexTokenPath; // path to sell CVX

    // Swap stuff
    uint256 public keepCRV = 1000; // the percentage of CRV we re-lock for boost (in basis points)
    uint256 public constant FEE_DENOMINATOR = 10000; // with this and the above, sending 10% of our CRV yield to our voter
    IERC20 public constant crv =
        IERC20(0xD533a949740bb3306d119CC777fa900bA034cd52);
    IERC20 public constant convexToken =
        IERC20(0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B);
    IERC20 public constant weth =
        IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    uint256 public harvestProfitNeeded; // we use this to set our dollar target for harvest sells
    bool internal keeperHarvestNow = false; // only set this to true when we want to trigger our keepers to harvest for us
    string internal stratName; // we use this to be able to adjust our strategy's name

    // convex-specific variables
    bool public claimRewards; // boolean if we should always claim rewards when withdrawing, usually withdrawAndUnwrap (generally this should be false)

    constructor(
        address _vault,
        uint256 _pid,
        address _curvepool,
        string memory _name
    ) public BaseStrategy(_vault) {
        /* ========== CONSTRUCTOR CONSTANTS ========== */
        // You can set these parameters on deployment to whatever you want
        maxReportDelay = 60 * 60 * 24 * 7; // 7 days in seconds, if we hit this then harvestTrigger = True
        debtThreshold = 5 * 1e18; // set a bit of a buffer
        profitFactor = 10000; // in this strategy, profitFactor is only used for telling keep3rs when to move funds from vault to strategy (what previously was an earn call)
        harvestProfitNeeded = 20000 * 1e6; // this is how much in USDT we need to make. remember, 6 decimals!
        healthCheck = address(0xDDCea799fF1699e98EDF118e0629A974Df7DF012); // health.ychad.eth

        // want = Curve LP
        want.safeApprove(address(depositContract), type(uint256).max);
        crv.safeApprove(sushiswap, type(uint256).max);
        convexToken.safeApprove(sushiswap, type(uint256).max);

        // setup our rewards contract
        pid = _pid; // this is the pool ID on convex, we use this to determine what the reweardsContract address is
        (, , , rewardsContract, , ) = IConvexDeposit(depositContract).poolInfo(
            pid
        );

        // set our curve pool contract
        curve = ICurveFi(_curvepool);

        // set our strategy's name
        stratName = _name;
    }

    /* ========== VIEWS ========== */

    function name() external view override returns (string memory) {
        return stratName;
    }

    function stakedBalance() public view returns (uint256) {
        // how much want we have staked in Convex
        return IConvexRewards(rewardsContract).balanceOf(address(this));
    }

    function balanceOfWant() public view returns (uint256) {
        // balance of want sitting in our strategy
        return want.balanceOf(address(this));
    }

    function claimableBalance() public view returns (uint256) {
        // how much CRV we can claim from the staking contract
        return IConvexRewards(rewardsContract).earned(address(this));
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        return balanceOfWant().add(stakedBalance());
    }

    /* ========== CONSTANT FUNCTIONS ========== */
    // these should stay the same across different wants.

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }
        // Send all of our Curve pool tokens to be deposited
        uint256 _toInvest = balanceOfWant();
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
        uint256 _wantBal = balanceOfWant();
        if (_amountNeeded > _wantBal) {
            uint256 _stakedBal = stakedBalance();
            if (_stakedBal > 0) {
                IConvexRewards(rewardsContract).withdrawAndUnwrap(
                    Math.min(_stakedBal, _amountNeeded.sub(_wantBal)),
                    claimRewards
                );
            }
            uint256 _withdrawnBal = balanceOfWant();
            _liquidatedAmount = Math.min(_amountNeeded, _withdrawnBal);
            _loss = _amountNeeded.sub(_liquidatedAmount);
        } else {
            // we have enough balance to cover the liquidation available
            return (_amountNeeded, 0);
        }
    }

    // fire sale, get rid of it all!
    function liquidateAllPositions() internal override returns (uint256) {
        uint256 _stakedBal = stakedBalance();
        if (_stakedBal > 0) {
            // don't bother withdrawing zero
            IConvexRewards(rewardsContract).withdrawAndUnwrap(
                _stakedBal,
                claimRewards
            );
        }
        return balanceOfWant();
    }

    // Sells our harvested CRV into the selected output (ETH).
    function _sellCrv(uint256 _crvAmount) internal {
        IUniswapV2Router02(sushiswap).swapExactTokensForTokens(
            _crvAmount,
            uint256(0),
            crvPath,
            address(this),
            now
        );
    }

    // Sells our harvested CVX into the selected output (ETH).
    function _sellConvex(uint256 _convexAmount) internal {
        IUniswapV2Router02(sushiswap).swapExactTokensForTokens(
            _convexAmount,
            uint256(0),
            convexTokenPath,
            address(this),
            now
        );
    }

    // in case we need to exit into the convex deposit token, this will allow us to do that
    // make sure to check claimRewards before this step if needed
    // plan to have gov sweep convex deposit tokens from strategy after this
    function withdrawToConvexDepositTokens() external onlyAuthorized {
        uint256 _stakedBal = stakedBalance();
        if (_stakedBal > 0) {
            IConvexRewards(rewardsContract).withdraw(_stakedBal, claimRewards);
        }
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

    // This determines when we tell our keepers to harvest based on profit. this is how much in USDT we need to make. remember, 6 decimals!
    function setHarvestProfitNeeded(uint256 _harvestProfitNeeded)
        external
        onlyAuthorized
    {
        harvestProfitNeeded = _harvestProfitNeeded;
    }

    // This allows us to change the name of a strategy
    function setName(string calldata _stratName) external onlyAuthorized {
        stratName = _stratName;
    }

    // This allows us to manually harvest with our keeper as needed
    function setManualHarvest(bool _keeperHarvestNow) external onlyAuthorized {
        keeperHarvestNow = _keeperHarvestNow;
    }
}

contract StrategyConvexEURt is StrategyConvexBase {
    /* ========== STATE VARIABLES ========== */
    // these will likely change across different wants.
    // note that some strategies will require the "optimal" state variable here as well if we choose which token to sell into before depositing

    // specific variables for this contract
    IERC20 public constant eurt =
        IERC20(0xC581b735A1688071A1746c968e0798D642EDE491);
    IERC20 public constant usdt =
        IERC20(0xdAC17F958D2ee523a2206206994597C13D831ec7);
    IOracle public oracle = IOracle(0x0F1f5A87f99f0918e6C81F16E59F3518698221Ff); // this is only needed for strats that use uniV3 for swaps

    constructor(
        address _vault,
        uint256 _pid,
        address _curvePool,
        string memory _name
    ) public StrategyConvexBase(_vault, _pid, _curvePool, _name) {
        /* ========== CONSTRUCTOR VARIABLES ========== */
        // these will likely change across different wants.

        // strategy-specific approvals and paths
        eurt.safeApprove(address(curve), type(uint256).max);
        weth.safeApprove(uniswapv3, type(uint256).max);

        // crv token path
        crvPath = new address[](2);
        crvPath[0] = address(crv);
        crvPath[1] = address(weth);

        // convex token path
        convexTokenPath = new address[](2);
        convexTokenPath[0] = address(convexToken);
        convexTokenPath[1] = address(weth);
    }

    /* ========== VARIABLE FUNCTIONS ========== */
    // these will likely change across different wants.

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
            if (_keepCRV > 0) crv.safeTransfer(voter, _keepCRV);
            uint256 crvRemainder = crvBalance.sub(_keepCRV);

            if (crvRemainder > 0) _sellCrv(crvRemainder);
            if (convexBalance > 0) _sellConvex(convexBalance);

            // convert our WETH to EURt, but don't want to swap dust
            uint256 _wethBalance = weth.balanceOf(address(this));
            uint256 _eurtBalance = 0;
            if (_wethBalance > 0) {
                _eurtBalance = _sellWethForEurt(_wethBalance);
            }

            // deposit our EURt to Curve if we have any
            if (_eurtBalance > 0) {
                curve.add_liquidity([_eurtBalance, 0], 0);
            }
        }

        // debtOustanding will only be > 0 in the event of revoking or lowering debtRatio of a strategy
        if (_debtOutstanding > 0) {
            uint256 _stakedBal = stakedBalance();
            if (_stakedBal > 0) {
                IConvexRewards(rewardsContract).withdrawAndUnwrap(
                    Math.min(_stakedBal, _debtOutstanding),
                    claimRewards
                );
            }
            uint256 _withdrawnBal = balanceOfWant();
            _debtPayment = Math.min(_debtOutstanding, _withdrawnBal);
        }

        // serious loss should never happen, but if it does (for instance, if Curve is hacked), let's record it accurately
        uint256 assets = estimatedTotalAssets();
        uint256 debt = vault.strategies(address(this)).totalDebt;

        // if assets are greater than debt, things are working great!
        if (assets > debt) {
            _profit = assets.sub(debt);
            uint256 _wantBal = balanceOfWant();
            if (_profit.add(_debtPayment) > _wantBal) {
                // this should only be hit following donations to strategy
                liquidateAllPositions();
            }
        }
        // if assets are less than debt, we are in trouble
        else {
            _loss = debt.sub(assets);
        }

        // we're done harvesting, so reset our trigger if we used it
        if (keeperHarvestNow) keeperHarvestNow = false;
    }

    // migrate our want token to a new strategy if needed, make sure to check claimRewards first
    // also send over any CRV or CVX that is claimed; for migrations we definitely want to claim
    function prepareMigration(address _newStrategy) internal override {
        uint256 _stakedBal = stakedBalance();
        if (_stakedBal > 0) {
            IConvexRewards(rewardsContract).withdrawAndUnwrap(
                _stakedBal,
                claimRewards
            );
        }
        crv.safeTransfer(_newStrategy, crv.balanceOf(address(this)));
        convexToken.safeTransfer(
            _newStrategy,
            convexToken.balanceOf(address(this))
        );
    }

    // Sells our USDT for EURt
    function _sellWethForEurt(uint256 _amount) internal returns (uint256) {
        uint256 _eurtOutput =
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
        return _eurtOutput;
    }

    /* ========== KEEP3RS ========== */

    function harvestTrigger(uint256 callCostinEth)
        public
        view
        override
        returns (bool)
    {
        // trigger if we want to manually harvest
        if (keeperHarvestNow) return true;

        // harvest if we have a profit to claim
        if (claimableProfitInUsdt() > harvestProfitNeeded) return true;

        // Should not trigger if strategy is not active (no assets and no debtRatio). This means we don't need to adjust keeper job.
        if (!isActive()) return false;

        return super.harvestTrigger(callCostinEth);
    }

    // we will need to add rewards token here if we have them
    function claimableProfitInUsdt() internal view returns (uint256) {
        // calculations pulled directly from CVX's contract for minting CVX per CRV claimed
        uint256 totalCliffs = 1000;
        uint256 maxSupply = 100 * 1000000 * 1e18; // 100mil
        uint256 reductionPerCliff = 100000000000000000000000; // 100,000
        uint256 supply = convexToken.totalSupply();
        uint256 mintableCvx;

        uint256 cliff = supply.div(reductionPerCliff);
        uint256 _claimableBal = claimableBalance();
        //mint if below total cliffs
        if (cliff < totalCliffs) {
            //for reduction% take inverse of current cliff
            uint256 reduction = totalCliffs.sub(cliff);
            //reduce
            mintableCvx = _claimableBal.mul(reduction).div(totalCliffs);

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
        if (_claimableBal > 0) {
            uint256[] memory crvSwap =
                IUniswapV2Router02(sushiswap).getAmountsOut(
                    _claimableBal,
                    crv_usd_path
                );
            crvValue = crvSwap[crvSwap.length - 1];
        }

        uint256 cvxValue;
        if (mintableCvx > 0) {
            uint256[] memory cvxSwap =
                IUniswapV2Router02(sushiswap).getAmountsOut(
                    mintableCvx,
                    cvx_usd_path
                );
            cvxValue = cvxSwap[cvxSwap.length - 1];
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
}
