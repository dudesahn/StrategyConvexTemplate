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
import "./interfaces/yearn.sol";
import {IUniswapV2Router02} from "./interfaces/uniswap.sol";
import {
    BaseStrategy,
    StrategyParams
} from "@yearnvaults/contracts/BaseStrategy.sol";

contract StrategyCurveEURtVoterProxy is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;

    address public constant gauge =
        address(0xF5194c3325202F456c95c1Cf0cA36f8475C1949F); // Curve Iron Bank Gauge contract, v2 is tokenized, held by Yearn's voter
    ICurveStrategyProxy public proxy =
        ICurveStrategyProxy(
            address(0xA420A63BbEFfbda3B147d0585F1852C358e2C152)
        ); // Yearn's Updated v4 StrategyProxy

    uint256 public optimal;

    ICurveFi public constant curve =
        ICurveFi(address(0x2dded6Da1BF5DBdF597C45fcFaa3194e53EcfeAF)); // Curve Iron Bank Pool
    address public constant voter =
        address(0xF147b8125d2ef93FB6965Db97D6746952a133934); // Yearn's veCRV voter
    address public constant crvRouter =
        address(0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F); // default to sushiswap, more CRV liquidity there
    address[] public crvPath;

    // Swap stuff
    uint256 public keepCRV = 1000; // the percentage of CRV we re-lock for boost (in basis points)
    uint256 public constant FEE_DENOMINATOR = 10000; // with this and the above, sending 10% of our CRV yield to our voter

    ICrvV3 public constant crv =
        ICrvV3(0xD533a949740bb3306d119CC777fa900bA034cd52);
    IERC20 public constant weth =
        IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    IERC20 public constant usdt =
        IERC20(0xdAC17F958D2ee523a2206206994597C13D831ec7);
    IERC20 public constant eurt =
        IERC20(0xC581b735A1688071A1746c968e0798D642EDE491);

    constructor(address _vault) public BaseStrategy(_vault) {
        // You can set these parameters on deployment to whatever you want
        maxReportDelay = 504000; // 140 hours in seconds
        debtThreshold = 400 * 1e18; // we shouldn't ever have debt, but set a bit of a buffer
        profitFactor = 4000; // in this strategy, profitFactor is only used for telling keep3rs when to move funds from vault to strategy

        // want = crvIB, Curve's Iron Bank pool (ycDai+ycUsdc+ycUsdt)
        want.safeApprove(address(proxy), type(uint256).max);

        // add approvals for crv on sushiswap and uniswap due to weird crv approval issues for setCrvRouter
        // add approvals on all tokens
        crv.approve(crvRouter, type(uint256).max);
        dai.safeApprove(address(curve), type(uint256).max);
        usdc.safeApprove(address(curve), type(uint256).max);
        usdt.safeApprove(address(curve), type(uint256).max);

        crvPath = new address[](3);
        crvPath[0] = address(crv);
        crvPath[1] = address(weth);
        crvPath[2] = address(usdt);
    }

    function name() external view override returns (string memory) {
        return "StrategyCurveEURtVoterProxy";
    }
	
    function _stakedBalance() public view returns (uint256) {
        return proxy.balanceOf(gauge);
    }

    function _balanceOfWant() public view returns (uint256) {
        return want.balanceOf(address(this));
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
        // if we have anything in the gauge, then harvest CRV from the gauge
        if (_stakedBalance() > 0) {
            proxy.harvest(gauge);
            uint256 crvBalance = crv.balanceOf(address(this));
            // if we claimed any CRV, then sell it
            if (crvBalance > 0) {
            	
            	// keep some of our CRV to increase our boost
                uint256 _keepCRV = crvBalance.mul(keepCRV).div(FEE_DENOMINATOR);
                IERC20(address(crv)).safeTransfer(voter, _keepCRV);
                uint256 crvRemainder = crvBalance.sub(_keepCRV);
                
                // sell the rest of our CRV
                _sell(crvRemainder);
                
                // convert our USDT to EURt
                uint256 usdtBalance = IERC20(usdt).balanceOf(address(this));
                _sell_v3(usdtBalance);
                
                // deposit our EURt to Curve
                uint256 eurtBalance = eurt.balanceOf(address(this));
                curve.add_liquidity([eurtBalance, 0], 0);

            }
        }

        // serious loss should never happen, but if it does (for instance, if Curve is hacked), let's record it accurately
        uint256 assets = estimatedTotalAssets();
        uint256 debt = vault.strategies(address(this)).totalDebt;

        // if assets are greater than debt, things are working great!
        if (assets > debt) {
            _profit = want.balanceOf(address(this));
        }
        // if assets are less than debt, we are in trouble
        else {
            _loss = debt.sub(assets);
        }

        // debtOustanding will only be > 0 in the event of revoking or lowering debtRatio of a strategy
        if (_debtOutstanding > 0) {
            proxy.withdraw(
                gauge,
                address(want),
                Math.min(_stakedBalance(), _debtOutstanding)
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
        // Send all of our Iron Bank pool tokens to the proxy and deposit to the gauge if we have any
        uint256 _toInvest = want.balanceOf(address(this));
        if (_toInvest > 0) {
            want.safeTransfer(address(proxy), _toInvest);
            proxy.deposit(gauge, address(want));
        }
    }

    function liquidatePosition(uint256 _amountNeeded)
        internal
        override
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        uint256 wantBal = want.balanceOf(address(this));
        if (_amountNeeded > wantBal) {
            proxy.withdraw(
                gauge,
                address(want),
                Math.min(_stakedBalance(), _amountNeeded - wantBal)
            );
            uint256 withdrawnBal = want.balanceOf(address(this));
            _liquidatedAmount = Math.min(_amountNeeded, withdrawnBal);

            _loss = _amountNeeded.sub(_liquidatedAmount);
        } else {
            // we have enough balance to cover the liquidation available
            return (_amountNeeded, 0);
        }
    }

    // Sells our harvested CRV into the selected output (DAI, USDC, or USDT).
    function _sell(uint256 _amount) internal {
        IUniswapV2Router02(crvRouter).swapExactTokensForTokens(
            _amount,
            uint256(0),
            crvPath,
            address(this),
            now
        );
    }

    // Sells our harvested CRV into the selected output (DAI, USDC, or USDT).
    function _sell_v3(uint256 _amount) internal {
        UniV3(uniswapv3).exactInput(UniV3.ExactInputParams(
            abi.encodePacked(
                usdt, 
                uint24(500), 
                eurt
            ),
            address(this),
            now,
            _amount,
            uint256(0)
        ));
    }

    function prepareMigration(address _newStrategy) internal override {
        if (_stakedBalance() > 0) {
            proxy.withdraw(gauge, address(want), _stakedBalance());
        }
    }

    function protectedTokens()
        internal
        view
        override
        returns (address[] memory)
    {
        address[] memory protected = new address[](1);
        protected[0] = gauge;

        return protected;
    }

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

        // Trigger if it makes sense for the vault to send funds idle funds from the vault to the strategy
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
                IUniswapV2Router02(crvRouter).getAmountsOut(
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

    // Use to update Yearn's StrategyProxy contract as needed in case of upgrades.
    function setProxy(address _proxy) external onlyGovernance {
        proxy = ICurveStrategyProxy(_proxy);
    }

    // Set the amount of CRV to be locked in Yearn's veCRV voter from each harvest. Default is 10%.
    function setKeepCRV(uint256 _keepCRV) external onlyAuthorized {
        keepCRV = _keepCRV;
    }

}
