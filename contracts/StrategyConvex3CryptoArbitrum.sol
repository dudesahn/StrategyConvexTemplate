// SPDX-License-Identifier: AGPL-3.0
pragma solidity ^0.8.15;

// These are the core Yearn libraries
import "@openzeppelin/contracts/utils/math/Math.sol";

import "./interfaces/curve.sol";
import "@yearnvaults/contracts/BaseStrategy.sol";

interface IOracle {
    function getPriceUsdcRecommended(address tokenAddress)
        external
        view
        returns (uint256);
}

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

interface IConvexRewards {
    // strategy's staked balance in the synthetix staking contract
    function balanceOf(address account) external view returns (uint256);

    // read how much claimable CRV and CVX a strategy has
    function claimable_reward(address asset, address account) external view returns (uint256);

    // on sidechains this replaces withdrawAndUnwrap
    function withdraw(uint256 _amount, bool _claim) external returns (bool);

    // claim rewards
    function getReward(address _account) external;
}

interface IConvexDeposit {
    // deposit into convex, receive a tokenized deposit. stakes automatically for sidechain implementation.
    function deposit(
        uint256 _pid,
        uint256 _amount
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
            bool,
            address
        );
}

abstract contract StrategyConvexBase is BaseStrategy {
    /* ========== STATE VARIABLES ========== */
    // these should stay the same across different wants.

    // convex stuff
    address internal constant depositContract =
        0xF403C135812408BFbE8713b5A23a04b3D48AAE31; // this is the deposit contract that all pools use, aka booster
    IConvexRewards public rewardsContract; // This is unique to each curve pool
    uint256 public pid; // this is unique to each pool

    IERC20 internal constant crv =
        IERC20(0x11cDb42B0EB46D95f990BeDD4695A6e3fA034978);
    IERC20 internal constant convexToken =
        IERC20(0xb952A807345991BD529FDded05009F5e80Fe8F45);
    IERC20 internal constant weth =
        IERC20(0x82aF49447D8a07e3bd95BD0d56f35241523fBab1);

    // keeper stuff
    uint256 public harvestProfitMin; // minimum size in USD (6 decimals) that we want to harvest
    uint256 public harvestProfitMax; // maximum size in USD (6 decimals) that we want to harvest
    uint256 internal constant FEE_DENOMINATOR = 10000; // this means all of our fee values are in basis points

    string internal stratName;

    // convex-specific variables
    bool public claimRewards; // boolean if we should always claim rewards when withdrawing (generally this should be false)

    /* ========== CONSTRUCTOR ========== */

    constructor(address _vault) BaseStrategy(_vault) {}

    /* ========== VIEWS ========== */

    function name() external view override returns (string memory) {
        return stratName;
    }

    /// @notice How much want we have staked in Convex
    function stakedBalance() public view returns (uint256) {
        return rewardsContract.balanceOf(address(this));
    }

    /// @notice Balance of want sitting in our strategy
    function balanceOfWant() public view returns (uint256) {
        return want.balanceOf(address(this));
    }

    /// @notice How much CRV and CVX we can claim from the staking contract
    function claimableBalance() public view returns (uint256, uint256) {
        uint256 crvRewards = rewardsContract.claimable_reward(address(crv), address(this));
        uint256 cvxRewards = rewardsContract.claimable_reward(address(convexToken), address(this));
        
        return (crvRewards, cvxRewards);
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        return balanceOfWant() + stakedBalance();
    }

    /* ========== MUTATIVE FUNCTIONS ========== */

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }
        // Send all of our Curve pool tokens to be deposited
        uint256 _toInvest = balanceOfWant();
        // deposit into convex and stake immediately (but only if we have something to invest)
        if (_toInvest > 0) {
            IConvexDeposit(depositContract).deposit(pid, _toInvest);
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
                rewardsContract.withdraw(
                    Math.min(_stakedBal, _amountNeeded - _wantBal),
                    claimRewards
                );
            }
            uint256 _withdrawnBal = balanceOfWant();
            _liquidatedAmount = Math.min(_amountNeeded, _withdrawnBal);
            _loss = _amountNeeded - _liquidatedAmount;
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
            rewardsContract.withdraw(_stakedBal, claimRewards);
        }
        return balanceOfWant();
    }

    // we don't want for these tokens to be swept out. We allow gov to sweep out cvx vault tokens; we would only be holding these if things were really, really rekt.
    function protectedTokens()
        internal
        view
        override
        returns (address[] memory)
    {}

    /* ========== SETTERS ========== */

    // These functions are useful for setting parameters of the strategy that may need to be adjusted.

    // We usually don't need to claim rewards on withdrawals, but might change our mind for migrations etc
    function setClaimRewards(bool _claimRewards) external onlyVaultManagers {
        claimRewards = _claimRewards;
    }
}

contract StrategyConvex3CryptoArbitrum is StrategyConvexBase {
    using SafeERC20 for IERC20;
    /* ========== STATE VARIABLES ========== */
    // these will likely change across different wants.

    // Curve stuff
    ICurveFi public curve; // Curve Pool, this is our pool specific to this vault

    // sell our crv to weth on uniV3
    address internal constant uniswapv3 = 0xE592427A0AEce92De3Edee1F18E0157C05861564;
    uint24 public crvFee;

    /* ========== CONSTRUCTOR ========== */

    constructor(
        address _vault,
        uint256 _pid,
        address _curvePool,
        string memory _name
    ) StrategyConvexBase(_vault) {
        // You can set these parameters on deployment to whatever you want
        maxReportDelay = 365 days; // 365 days in seconds, if we hit this then harvestTrigger = True
        healthCheck = 0x32059ccE723b4DD15dD5cb2a5187f814e6c470bC; // health check
        harvestProfitMin = 2_000e6;
        harvestProfitMax = 120000e6;
        creditThreshold = 10 * 1e18;

        // want = Curve LP
        want.approve(address(depositContract), type(uint256).max);
        crv.approve(uniswapv3, type(uint256).max);

        // this is the pool specific to this vault, but we only use it as an address
        curve = ICurveFi(_curvePool);

        // setup our rewards contract
        pid = _pid; // this is the pool ID on convex, we use this to determine what the reweardsContract address is
        (address lptoken, , address _rewardsContract, , ) =
            IConvexDeposit(depositContract).poolInfo(_pid);

        // set up our rewardsContract
        rewardsContract = IConvexRewards(_rewardsContract);

        // check that our LP token based on our pid matches our want
        require(address(lptoken) == address(want));

        // set our needed curve approvals
        weth.approve(address(curve), type(uint256).max);

        // set our strategy's name
        stratName = _name;

        // set our uniswap pool fees, 1%
        crvFee = 10_000;
    }

    /* ========== MUTATIVE FUNCTIONS ========== */

    function prepareReturn(uint256 _debtOutstanding)
        internal
        override
        returns (
            uint256 _profit,
            uint256 _loss,
            uint256 _debtPayment
        )
    {
        // this claims our CRV, CVX, and any extra tokens like SNX or ANKR
        if (stakedBalance() > 0) {
            rewardsContract.getReward(address(this));
        }
            
        // transfer CVX to gov for now, as there is currrently no liquidity on arbitrum
        convexToken.safeTransfer(governance(), convexToken.balanceOf(address(this)));
        
        // sell our crv for more weth
        _sellCrv(crv.balanceOf(address(this)));

        // check for balances of tokens to deposit
        uint256 wethBalance = weth.balanceOf(address(this));

        // deposit our euros to the pool
        if (wethBalance > 0) {
            curve.add_liquidity([0, 0, wethBalance], 0);
        }

        // debtOustanding will only be > 0 in the event of revoking or if we need to rebalance from a withdrawal or lowering the debtRatio
        if (_debtOutstanding > 0) {
            uint256 _stakedBal = stakedBalance();
            if (_stakedBal > 0) {
                rewardsContract.withdraw(
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
            unchecked {
                _profit = assets - debt;
            }
            uint256 _wantBal = balanceOfWant();
            if (_profit + _debtPayment > _wantBal) {
                // this should only be hit following donations to strategy
                liquidateAllPositions();
            }
        }
        // if assets are less than debt, we are in trouble
        else {
            unchecked {
                _loss = debt - assets;
            }
        }
    }

    // migrate our want token to a new strategy if needed, make sure to check claimRewards first
    // also send over any CRV or CVX that is claimed; for migrations we definitely want to claim
    function prepareMigration(address _newStrategy) internal override {
        uint256 _stakedBal = stakedBalance();
        if (_stakedBal > 0) {
            rewardsContract.withdraw(_stakedBal, claimRewards);
        }
        crv.safeTransfer(_newStrategy, crv.balanceOf(address(this)));
        convexToken.safeTransfer(_newStrategy,convexToken.balanceOf(address(this)));
    }

    // Sells our CRV for WETH on UniV3
    function _sellCrv(uint256 _crvAmount)
        internal
    {
        if (_crvAmount > 1e17) {
            IUniV3(uniswapv3).exactInput(
                IUniV3.ExactInputParams(
                    abi.encodePacked(
                        address(crv),
                        uint24(crvFee),
                        address(weth)
                    ),
                    address(this),
                    block.timestamp,
                    _crvAmount,
                    uint256(1)
                )
            );
        }
    }

    /* ========== KEEP3RS ========== */
    // use this to determine when to harvest
    function harvestTrigger(uint256 callCostinEth)
        public
        view
        override
        returns (bool)
    {
        // Should not trigger if strategy is not active (no assets and no debtRatio). This means we don't need to adjust keeper job.
        if (!isActive()) {
            return false;
        }

        // harvest if we have a profit to claim at our upper limit without considering gas price
        uint256 claimableProfit = claimableProfitInUsdc();
        if (claimableProfit > harvestProfitMax) {
            return true;
        }

        // check if the base fee gas price is higher than we allow. if it is, block harvests.
        if (!isBaseFeeAcceptable()) {
            return false;
        }

        // trigger if we want to manually harvest, but only if our gas price is acceptable
        if (forceHarvestTriggerOnce) {
            return true;
        }

        // harvest if we have a sufficient profit to claim, but only if our gas price is acceptable
        if (claimableProfit > harvestProfitMin) {
            return true;
        }

        StrategyParams memory params = vault.strategies(address(this));
        // harvest no matter what once we reach our maxDelay
        if (block.timestamp - params.lastReport > maxReportDelay) {
            return true;
        }

        // harvest our credit if it's above our threshold
        if (vault.creditAvailable() > creditThreshold) {
            return true;
        }

        // otherwise, we don't harvest
        return false;
    }

    /// @notice Calculates the profit if all claimable assets were sold for USDC (6 decimals).
    /// @return Total return in USDC from selling claimable CRV and CVX.
    function claimableProfitInUsdc() public view returns (uint256) {
        IOracle yearnOracle =
            IOracle(0x043518AB266485dC085a1DB095B8d9C2Fc78E9b9); // yearn lens oracle
        uint256 crvPrice = yearnOracle.getPriceUsdcRecommended(address(crv));
        uint256 convexTokenPrice =
            yearnOracle.getPriceUsdcRecommended(address(convexToken));
            
        // check how much CRV and CVX we can claim from our deposit contract
        (uint256 claimableCrv, uint256 claimableCvx) = claimableBalance();

        // Oracle returns prices as 6 decimals, so multiply by claimable amount and divide by token decimals (1e18)
        return
            (crvPrice * claimableCrv + convexTokenPrice * claimableCvx) / 1e18;
    }

    // convert our keeper's eth cost into want, we don't need this anymore since we don't use baseStrategy harvestTrigger
    function ethToWant(uint256 _ethAmount)
        public
        view
        override
        returns (uint256)
    {}

    /* ========== SETTERS ========== */

    // These functions are useful for setting parameters of the strategy that may need to be adjusted.

    /**
     * @notice
     * Here we set various parameters to optimize our harvestTrigger.
     * @param _harvestProfitMin The amount of profit (in USDC, 6 decimals)
     * that will trigger a harvest if gas price is acceptable.
     * @param _harvestProfitMax The amount of profit in USDC that
     * will trigger a harvest regardless of gas price.
     */
    function setHarvestTriggerParams(
        uint256 _harvestProfitMin,
        uint256 _harvestProfitMax
    ) external onlyVaultManagers {
        harvestProfitMin = _harvestProfitMin;
        harvestProfitMax = _harvestProfitMax;
    }

    /// @notice Set the fee pool we'd like to swap through on UniV3 (1% = 10_000)
    function setUniFees(uint24 _crvFee)
        external
        onlyVaultManagers
    {
        crvFee = _crvFee;
    }
}
