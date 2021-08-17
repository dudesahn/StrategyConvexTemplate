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

interface UniV3 {

    struct ExactInputParams {
        bytes path;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
    }

    function exactInput(
        ExactInputParams calldata params
    ) external payable returns (uint256 amountOut);
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
}

/* ========== CONTRACT ========== */

contract StrategyConvexsETH is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;

    ICurveFi public constant curve =
        ICurveFi(0xFD5dB7463a3aB53fD211b4af195c5BCCC1A03890); // Curve EURT Pool, need this for buying more pool tokens
    address public constant sushiswapRouter =
        0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F; // default to sushiswap, more CRV liquidity there
    address public constant uniswapv3 = 
        0xE592427A0AEce92De3Edee1F18E0157C05861564;
    address public constant voter = 
        0xF147b8125d2ef93FB6965Db97D6746952a133934; // Yearn's veCRV voter, we send some extra CRV here
    address[] public crvPath; // path to sell CRV
    address[] public convexTokenPath; // path to sell CVX

    address public constant depositContract =
        0xF403C135812408BFbE8713b5A23a04b3D48AAE31; // this is the deposit contract that all pools use, aka booster
    address public constant rewardsContract =
        0xD814BFC091111E1417a669672144aFFAA081c3CE; // This is unique to each curve pool, this one is for EURT pool
    uint256 public constant pid = 39; // this is unique to each pool, this is the one for EURT

    // Swap stuff
    uint256 public keepCRV = 1000; // the percentage of CRV we re-lock for boost (in basis points)
    uint256 public constant FEE_DENOMINATOR = 10000; // with this and the above, sending 10% of our CRV yield to our voter

    IERC20 public constant eurt =
        IERC20(0xC581b735A1688071A1746c968e0798D642EDE491);
    ICrvV3 public constant crv =
        ICrvV3(0xD533a949740bb3306d119CC777fa900bA034cd52);
    IERC20 public constant convexToken =
        IERC20(0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B);
    IERC20 public constant weth =
        IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    IERC20 public constant usdt =
        IERC20(0xdAC17F958D2ee523a2206206994597C13D831ec7);
    IERC20 public constant dai =
        IERC20(0x6B175474E89094C44Da98b954EedeAC495271d0F);

    // convex-specific variables
    bool public claimRewards = false; // boolean if we should always claim rewards when withdrawing, usually withdrawAndUnwrap (generally this should be false)

    constructor(address _vault) public BaseStrategy(_vault) {
        // You can set these parameters on deployment to whatever you want
        maxReportDelay = 324000; // 90 hours in seconds, if we hit this then harvestTrigger = True
        debtThreshold = 100000 * 1e18; // set a bit of a buffer
        profitFactor = 4000; // in this strategy, profitFactor is only used for telling keep3rs when to move funds from vault to strategy (what previously was an earn call)

        // want = Curve LP
        want.safeApprove(address(depositContract), type(uint256).max);
        IERC20(address(eurt)).safeApprove(address(curve), type(uint256).max);
        IERC20(address(crv)).safeApprove(sushiswapRouter, type(uint256).max);
        IERC20(address(weth)).safeApprove(uniswapv3, type(uint256).max);

        convexToken.safeApprove(sushiswapRouter, type(uint256).max);

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
        return "StrategyConvexsETH";
    }

    // total assets held by strategy. loose funds in strategy and all staked funds
    function estimatedTotalAssets() public view override returns (uint256) {
        return
            IConvexRewards(rewardsContract).balanceOf(address(this)).add(
                want.balanceOf(address(this))
            );
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
        uint256 claimableTokens =
            IConvexRewards(rewardsContract).earned(address(this));
        if (claimableTokens > 0) {
            // this claims our CRV, CVX, and any extra tokens like SNX or ANKR
            // if for some reason we don't want extra rewards, make sure we don't harvest them
            IConvexRewards(rewardsContract).getReward(address(this), false);

            uint256 crvBalance = crv.balanceOf(address(this));
            uint256 convexBalance = convexToken.balanceOf(address(this));

            uint256 _keepCRV = crvBalance.mul(keepCRV).div(FEE_DENOMINATOR);
            IERC20(address(crv)).safeTransfer(voter, _keepCRV);
            uint256 crvRemainder = crvBalance.sub(_keepCRV);

            if (crvRemainder > 0) _sellCrv(crvRemainder);
            if (convexBalance > 0) _sellConvex(convexBalance);

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
            uint256 stakedTokens =
                IConvexRewards(rewardsContract).balanceOf(address(this));
            IConvexRewards(rewardsContract).withdrawAndUnwrap(
                Math.min(stakedTokens, _debtOutstanding),
                claimRewards
            );

            _debtPayment = Math.min(
                _debtOutstanding,
                want.balanceOf(address(this))
            );
            // want to make sure we report losses properly here
            if (_debtPayment < _debtOutstanding) {
                _loss = _debtOutstanding.sub(_debtPayment);
                _profit = 0;
            }
        }
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }
        // Send all of our sETH pool tokens to be deposited
        uint256 _toInvest = want.balanceOf(address(this));
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
        uint256 wantBal = want.balanceOf(address(this));
        if (_amountNeeded > wantBal) {
            uint256 stakedTokens =
                IConvexRewards(rewardsContract).balanceOf(address(this));
            IConvexRewards(rewardsContract).withdrawAndUnwrap(
                Math.min(stakedTokens, _amountNeeded - wantBal),
                claimRewards
            );

            uint256 withdrawnBal = want.balanceOf(address(this));
            _liquidatedAmount = Math.min(_amountNeeded, withdrawnBal);

            _loss = _amountNeeded.sub(_liquidatedAmount);
        } else {
            // we have enough balance to cover the liquidation available
            return (_amountNeeded, 0);
        }
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
        _sellWethForEurt();
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
        _sellWethForEurt();
    }

    function _sellWethForEurt() internal {
        uint256 wethBalance = weth.balanceOf(address(this));
        if(wethBalance > 0){
            UniV3(uniswapv3).exactInput(UniV3.ExactInputParams(
                abi.encodePacked(
                    address(weth),
                    uint24(500),
                    address(usdt),
                    uint24(500),
                    address(eurt)
                ),
                address(this),
                now,
                wethBalance,
                uint256(0)
            ));
        }
    }

    // in case we need to exit into the convex deposit token, this will allow us to do that
    // make sure to check claimRewards before this step if needed
    // plan to have gov sweep convex deposit tokens from strategy after this
    function withdrawToConvexDepositTokens() external onlyAuthorized {
        uint256 stakedTokens =
            IConvexRewards(rewardsContract).balanceOf(address(this));
        IConvexRewards(rewardsContract).withdraw(stakedTokens, claimRewards);
    }

    // migrate our want token to a new strategy if needed, make sure to check claimRewards first
    // also send over any CRV or CVX that is claimed; for migrations we definitely want to claim
    function prepareMigration(address _newStrategy) internal override {
        uint256 stakedTokens =
            IConvexRewards(rewardsContract).balanceOf(address(this));
        if (stakedTokens > 0) {
            IConvexRewards(rewardsContract).withdrawAndUnwrap(
                stakedTokens,
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
        address[] memory protected = new address[](2);
        protected[0] = address(convexToken);
        protected[1] = address(crv);

        return protected;
    }

    /* ========== KEEP3RS ========== */

    function harvestTrigger(uint256 callCostinEth)
        public
        view
        override
        returns (bool)
    {
        StrategyParams memory params = vault.strategies(address(this));

        // Should not trigger if Strategy is not activated
        if (params.activation == 0) return false;

        // Should not trigger if we haven't waited long enough since previous harvest
        if (block.timestamp.sub(params.lastReport) < minReportDelay)
            return false;

        // Should trigger if hasn't been called in a while
        if (block.timestamp.sub(params.lastReport) >= maxReportDelay)
            return true;

        // If some amount is owed, pay it back
        // NOTE: Since debt is based on deposits, it makes sense to guard against large
        //       changes to the value from triggering a harvest directly through user
        //       behavior. This should ensure reasonable resistance to manipulation
        //       from user-initiated withdrawals as the outstanding debt fluctuates.
        uint256 outstanding = vault.debtOutstanding();
        if (outstanding > debtThreshold) return true;

        // Check for profits and losses
        uint256 total = estimatedTotalAssets();
        // Trigger if we have a loss to report
        if (total.add(debtThreshold) < params.totalDebt) return true;

        // Trigger if it makes sense for the vault to send funds idle funds from the vault to the strategy.
        uint256 profit = 0;
        if (total > params.totalDebt) profit = total.sub(params.totalDebt); // We've earned a profit!

        // calculate how much the call costs in dollars (converted from ETH)
        uint256 callCost = ethToDai(callCostinEth);

        // check if it makes sense to send funds from vault to strategy
        uint256 credit = vault.creditAvailable();
        if (profitFactor.mul(callCost) < credit.add(profit)) return true;
    }

    // convert our keeper's eth cost into dai
    function ethToDai(uint256 _ethAmount) internal view returns (uint256) {
        if (_ethAmount > 0) {
            address[] memory ethPath = new address[](2);
            ethPath[0] = address(weth);
            ethPath[1] = address(dai);
            uint256[] memory callCostInDai =
                IUniswapV2Router02(sushiswapRouter).getAmountsOut(
                    _ethAmount,
                    ethPath
                );

            return callCostInDai[callCostInDai.length - 1];
        } else {
            return 0;
        }
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
}
