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

contract StrategyCurveEURtVoterProxy is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;

    /* ========== STATE CONSTANTS ========== */
    // these should stay the same across different wants.

    // curve infrastructure contracts
    ICurveStrategyProxy public proxy =
        ICurveStrategyProxy(0xA420A63BbEFfbda3B147d0585F1852C358e2C152); // Yearn's Updated v4 StrategyProxy
    address public constant voter =
        address(0xF147b8125d2ef93FB6965Db97D6746952a133934); // Yearn's veCRV voter

    // state variables used for swapping
    address public constant sushiswap =
        address(0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F); // default to sushiswap, more CRV liquidity there
    address public constant uniswapv3 =
        address(0xE592427A0AEce92De3Edee1F18E0157C05861564);
    address[] public crvPath;
    uint256 public keepCRV = 1000; // the percentage of CRV we re-lock for boost (in basis points)
    uint256 public constant FEE_DENOMINATOR = 10000; // with this and the above, sending 10% of our CRV yield to our voter
    IERC20 public constant crv =
        IERC20(0xD533a949740bb3306d119CC777fa900bA034cd52);
    IERC20 public constant weth =
        IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);

    /* ========== STATE VARIABLES ========== */
    // these will likely change across different wants.

    address public constant gauge =
        address(0xe8060Ad8971450E624d5289A10017dD30F5dA85F); // Curve EURt Gauge contract, tokenized, held by Yearn's voter
    ICurveFi public constant curve =
        ICurveFi(address(0xFD5dB7463a3aB53fD211b4af195c5BCCC1A03890)); // Curve EURt Pool

    // here are any additional tokens used in the swap path
    IERC20 public constant usdt =
        IERC20(0xdAC17F958D2ee523a2206206994597C13D831ec7);
    IERC20 public constant eurt =
        IERC20(0xC581b735A1688071A1746c968e0798D642EDE491);

    /* ========== CONSTRUCTOR ========== */

    constructor(address _vault) public BaseStrategy(_vault) {
        /* ========== CONSTRUCTOR CONSTANTS ========== */
        // these should stay the same across different wants.

        // You can set these parameters on deployment to whatever you want
        minReportDelay = 0;
        maxReportDelay = 504000; // 140 hours in seconds
        debtThreshold = 5 * 1e18; // we shouldn't ever have debt, but set a bit of a buffer
        profitFactor = 10000; // in this strategy, profitFactor is only used for telling keep3rs when to move funds from vault to strategy
        healthCheck = address(0xDDCea799fF1699e98EDF118e0629A974Df7DF012); // health.ychad.eth

        // these are our standard approvals. want = Curve LP token
        want.safeApprove(address(proxy), type(uint256).max);
        crv.approve(sushiswap, type(uint256).max);

        /* ========== CONSTRUCTOR VARIABLES ========== */
        // these will likely change across different wants.

        // these are our approvals and path specific to this contract
        eurt.safeApprove(address(curve), type(uint256).max);
        weth.safeApprove(uniV3, type(uint256).max);

        crvPath = new address[](2);
        crvPath[0] = address(crv);
        crvPath[1] = address(weth);
    }

    /* ========== VIEWS ========== */

    function name() external view override returns (string memory) {
        return "StrategyCurveEURtVoterProxy";
    }

    function _stakedBalance() internal view returns (uint256) {
        return proxy.balanceOf(gauge);
    }

    function _balanceOfWant() internal view returns (uint256) {
        return want.balanceOf(address(this));
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        return _balanceOfWant().add(_stakedBalance());
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
        // if we have anything in the gauge, then harvest CRV from the gauge
        if (_stakedBalance() > 0) {
            proxy.harvest(gauge);
            uint256 _crvBalance = crv.balanceOf(address(this));
            // if we claimed any CRV, then sell it
            if (_crvBalance > 0) {
                // keep some of our CRV to increase our boost
                uint256 _keepCRV =
                    _crvBalance.mul(keepCRV).div(FEE_DENOMINATOR);
                crv.safeTransfer(voter, _keepCRV);
                uint256 _crvRemainder = _crvBalance.sub(_keepCRV);

                // sell the rest of our CRV
                _sell(_crvRemainder);

                // convert our WETH to EURt, but don't want to swap dust
                uint256 _wethBalance = IERC20(weth).balanceOf(address(this));
                if (_wethBalance > 0) _sellWethForEurt(_wethBalance);

                // deposit our EURt to Curve
                uint256 _eurtBalance = eurt.balanceOf(address(this));
                curve.add_liquidity([_eurtBalance, 0], 0);
            }
        }

        // serious loss should never happen, but if it does (for instance, if Curve is hacked), let's record it accurately
        uint256 assets = estimatedTotalAssets();
        uint256 debt = vault.strategies(address(this)).totalDebt;

        // if assets are greater than debt, things are working great!
        if (assets > debt) {
            _profit = assets.sub(debt);
        }
        // if assets are less than debt, we are in trouble
        else {
            _loss = debt.sub(assets);
        }

        // debtOustanding will only be > 0 in the event of revoking or lowering debtRatio of a strategy
        if (_debtOutstanding > 0) {
            if (_stakedBalance() > 0) {
                // don't bother withdrawing if we don't have staked funds
                proxy.withdraw(
                    gauge,
                    address(want),
                    Math.min(_stakedBalance(), _debtOutstanding)
                );
            }
            uint256 withdrawnBal = _balanceOfWant();
            _debtPayment = Math.min(_debtOutstanding, withdrawnBal);
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

    // Sells our harvested CRV into the selected output.
    function _sell(uint256 _amount) internal {
        IUniswapV2Router02(sushiswap).swapExactTokensForTokens(
            _amount,
            uint256(0),
            crvPath,
            address(this),
            now
        );
    }

    // Sells our USDT for EURt
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

    /* ========== CONSTANT FUNCTIONS ========== */
    // these should stay the same across different wants.

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }
        // Send all of our LP tokens to the proxy and deposit to the gauge if we have any
        uint256 _toInvest = _balanceOfWant();
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
        if (_amountNeeded > _balanceOfWant()) {
            // check if we have enough free funds to cover the withdrawal
            if (_stakedBalance() > 0) {
                proxy.withdraw(
                    gauge,
                    address(want),
                    Math.min(_stakedBalance(), _amountNeeded - _balanceOfWant())
                );
            }
            uint256 _withdrawnBal = _balanceOfWant();
            _liquidatedAmount = Math.min(_amountNeeded, _withdrawnBal);
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
            proxy.withdraw(gauge, address(want), _stakedBalance());
        }
        return _balanceOfWant();
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
        address[] memory protected = new address[](0);
        return protected;
    }

    /* ========== KEEP3RS ========== */

    // our main trigger is regarding our DCA since there is low liquidity for $XYZ
    function harvestTrigger(uint256 callCostinEth)
        public
        view
        override
        returns (bool)
    {
        return super.harvestTrigger(callCostinEth);
    }

    // since we can't pull claimable crv from gauge on chain, no need for this
    function ethToWant(uint256 _amtInWei)
        public
        view
        override
        returns (uint256)
    {
        return _amtInWei;
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
