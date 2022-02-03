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
import {
    BaseStrategy,
    StrategyParams
} from "@yearnvaults/contracts/BaseStrategy.sol";

// these are the libraries to use with synthetix
import "./interfaces/synthetix.sol";

interface IBaseFee {
    function isCurrentBaseFeeAcceptable() external view returns (bool);
}

interface IWeth {
    function withdraw(uint256 wad) external;
}

interface IOracle {
    function latestAnswer() external view returns (uint256);
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

    // if we have rewards, see what the address is
    function extraRewards(uint256 _reward) external view returns (address);

    // read our rewards token
    function rewardToken() external view returns (address);

    // check our reward period finish
    function periodFinish() external view returns (uint256);
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

    /* ========== STATE VARIABLES ========== */
    // these should stay the same across different wants.

    // convex stuff
    address internal constant depositContract =
        0xF403C135812408BFbE8713b5A23a04b3D48AAE31; // this is the deposit contract that all pools use, aka booster
    IConvexRewards public rewardsContract; // This is unique to each curve pool
    uint256 public pid; // this is unique to each pool

    // keepCRV stuff
    uint256 public keepCRV; // the percentage of CRV we re-lock for boost (in basis points)
    address internal constant voter =
        0xF147b8125d2ef93FB6965Db97D6746952a133934; // Yearn's veCRV voter, we send some extra CRV here
    uint256 internal constant FEE_DENOMINATOR = 10000; // this means all of our fee values are in bips

    // Swap stuff
    ICurveFi public curve; // Curve Pool, need this for depositing into our curve pool

    IERC20 internal constant crv =
        IERC20(0xD533a949740bb3306d119CC777fa900bA034cd52);
    IERC20 internal constant convexToken =
        IERC20(0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B);
    IERC20 internal constant weth =
        IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);

    // keeper stuff
    uint256 public harvestProfitMin; // minimum size in USDT that we want to harvest
    uint256 public harvestProfitMax; // maximum size in USDT that we want to harvest
    uint256 public creditThreshold; // amount of credit in underlying tokens that will automatically trigger a harvest
    bool internal forceHarvestTriggerOnce; // only set this to true when we want to trigger our keepers to harvest for us
    bool internal forceTendTriggerOnce; // only set this to true when we want to trigger our keepers to tend for us

    string internal stratName; // we use this to be able to adjust our strategy's name

    // convex-specific variables
    bool public claimRewards; // boolean if we should always claim rewards when withdrawing, usually withdrawAndUnwrap (generally this should be false)

    /* ========== CONSTRUCTOR ========== */

    constructor(address _vault) public BaseStrategy(_vault) {}

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

    // in case we need to exit into the convex deposit token, this will allow us to do that
    // make sure to check claimRewards before this step if needed
    // plan to have gov sweep convex deposit tokens from strategy after this
    function withdrawToConvexDepositTokens() external onlyEmergencyAuthorized {
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
    {}

    /* ========== SETTERS ========== */
    // These functions are useful for setting parameters of the strategy that may need to be adjusted.

    // Set the amount of CRV to be locked in Yearn's veCRV voter from each harvest. Default is 10%.
    function setKeepCRV(uint256 _keepCRV) external onlyGovernance {
        require(_keepCRV <= 10_000);
        keepCRV = _keepCRV;
    }

    // We usually don't need to claim rewards on withdrawals, but might change our mind for migrations etc
    function setClaimRewards(bool _claimRewards)
        external
        onlyEmergencyAuthorized
    {
        claimRewards = _claimRewards;
    }

    // This allows us to manually harvest or tend with our keeper as needed
    function setForceTriggerOnce(
        bool _forceTendTriggerOnce,
        bool _forceHarvestTriggerOnce
    ) external onlyEmergencyAuthorized {
        forceTendTriggerOnce = _forceTendTriggerOnce;
        forceHarvestTriggerOnce = _forceHarvestTriggerOnce;
    }
}

contract StrategyConvexFixedForexClonable is StrategyConvexBase {
    /* ========== STATE VARIABLES ========== */
    // these will likely change across different wants.

    // synthetix stuff
    IReadProxy public sTokenProxy; // this is the proxy for our synthetix token
    IERC20 internal constant sethProxy =
        IERC20(0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb); // this is the proxy for sETH
    IReadProxy internal constant readProxy =
        IReadProxy(0x4E3b31eB0E5CB73641EE1E65E7dCEFe520bA3ef2);

    ISystemStatus internal constant systemStatus =
        ISystemStatus(0x1c86B3CDF2a60Ae3a574f7f71d44E2C50BDdB87E); // this is how we check if our market is closed

    bytes32 public synthCurrencyKey;
    bytes32 internal constant sethCurrencyKey = "sETH";

    bytes32 internal constant TRACKING_CODE = "YEARN"; // this is our referral code for SNX volume incentives
    bytes32 internal constant CONTRACT_SYNTHETIX = "Synthetix";
    bytes32 internal constant CONTRACT_EXCHANGER = "Exchanger";

    // swap stuff
    address internal constant uniswapv3 =
        address(0xE592427A0AEce92De3Edee1F18E0157C05861564);
    bool internal harvestNow; // this tells us if we're currently harvesting or tending

    uint256 public lastTendTime; // this is the timestamp that our last tend was called
    bool public checkEarmark; // this determines if we should check if we need to earmark rewards before harvesting

    // use Curve to sell our CVX and CRV rewards to WETH
    ICurveFi internal constant crveth =
        ICurveFi(0x8301AE4fc9c624d1D396cbDAa1ed877821D7C511); // use curve's new CRV-ETH crypto pool to sell our CRV
    ICurveFi internal constant cvxeth =
        ICurveFi(0xB576491F1E6e5E62f1d8F26062Ee822B40B0E0d4); // use curve's new CVX-ETH crypto pool to sell our CVX
    ICurveFi internal constant setheth =
        ICurveFi(0xc5424B857f758E906013F3555Dad202e4bdB4567); // use curve's sETH-ETH crypto pool to swap our ETH to sETH

    // kp3r and rkp3r
    IERC20 internal constant rkpr =
        IERC20(0xEdB67Ee1B171c4eC66E6c10EC43EDBbA20FaE8e9);
    address internal constant kpr = 0x1cEB5cB57C4D4E2b2433641b95Dd330A33185A44;
    bool public sellRkpr; // bool for selling our rKP3R rewards on uniswap v3

    // check for cloning
    bool internal isOriginal = true;

    /* ========== CONSTRUCTOR ========== */

    constructor(
        address _vault,
        uint256 _pid,
        address _curvePool,
        address _sTokenProxy,
        string memory _name
    ) public StrategyConvexBase(_vault) {
        _initializeStrat(_pid, _curvePool, _sTokenProxy, _name);
    }

    /* ========== CLONING ========== */

    event Cloned(address indexed clone);

    // we use this to clone our original strategy to other vaults
    function cloneConvexibFF(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        uint256 _pid,
        address _curvePool,
        address _sTokenProxy,
        string memory _name
    ) external returns (address payable newStrategy) {
        require(isOriginal);
        // Copied from https://github.com/optionality/clone-factory/blob/master/contracts/CloneFactory.sol
        bytes20 addressBytes = bytes20(address(this));
        assembly {
            // EIP-1167 bytecode
            let clone_code := mload(0x40)
            mstore(
                clone_code,
                0x3d602d80600a3d3981f3363d3d373d3d3d363d73000000000000000000000000
            )
            mstore(add(clone_code, 0x14), addressBytes)
            mstore(
                add(clone_code, 0x28),
                0x5af43d82803e903d91602b57fd5bf30000000000000000000000000000000000
            )
            newStrategy := create(0, clone_code, 0x37)
        }

        StrategyConvexFixedForexClonable(newStrategy).initialize(
            _vault,
            _strategist,
            _rewards,
            _keeper,
            _pid,
            _curvePool,
            _sTokenProxy,
            _name
        );

        emit Cloned(newStrategy);
    }

    // this will only be called by the clone function above
    function initialize(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        uint256 _pid,
        address _curvePool,
        address _sTokenProxy,
        string memory _name
    ) public {
        _initialize(_vault, _strategist, _rewards, _keeper);
        _initializeStrat(_pid, _curvePool, _sTokenProxy, _name);
    }

    // this is called by our original strategy, as well as any clones
    function _initializeStrat(
        uint256 _pid,
        address _curvePool,
        address _sTokenProxy,
        string memory _name
    ) internal {
        // make sure that we haven't initialized this before
        require(address(curve) == address(0)); // already initialized.

        // You can set these parameters on deployment to whatever you want
        maxReportDelay = 21 days; // 21 days in seconds, if we hit this then harvestTrigger = True
        healthCheck = 0xDDCea799fF1699e98EDF118e0629A974Df7DF012; // health.ychad.eth

        // these are our standard approvals for swaps. want = Curve LP token
        want.approve(address(depositContract), type(uint256).max);
        convexToken.approve(address(cvxeth), type(uint256).max);
        crv.approve(address(crveth), type(uint256).max);
        weth.approve(uniswapv3, type(uint256).max);
        rkpr.approve(uniswapv3, type(uint256).max);

        // set our keepCRV
        keepCRV = 1000;

        // this is the pool specific to this vault, used for depositing
        curve = ICurveFi(_curvePool);

        // setup our rewards contract
        pid = _pid; // this is the pool ID on convex, we use this to determine what the reweardsContract address is
        (address lptoken, , , address _rewardsContract, , ) =
            IConvexDeposit(depositContract).poolInfo(_pid);

        // set up our rewardsContract
        rewardsContract = IConvexRewards(_rewardsContract);

        // check that our LP token based on our pid matches our want
        require(address(lptoken) == address(want));

        // set our strategy's name
        stratName = _name;

        // set our token to swap for and deposit with
        sTokenProxy = IReadProxy(_sTokenProxy);

        // these are our approvals and path specific to this contract
        sTokenProxy.approve(address(curve), type(uint256).max);

        // set our synth currency key
        synthCurrencyKey = ISynth(IReadProxy(_sTokenProxy).target())
            .currencyKey();

        // set our last tend time to the deployment block
        lastTendTime = block.timestamp;
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
        // turn on our toggle for harvests
        harvestNow = true;

        // deposit our sToken to Curve if we have any and if our trade has finalized
        uint256 _sTokenProxyBalance = sTokenProxy.balanceOf(address(this));
        if (_sTokenProxyBalance > 0 && checkWaitingPeriod()) {
            curve.add_liquidity([0, _sTokenProxyBalance], 0);
        }

        // debtOustanding will only be > 0 in the event of revoking or if we need to rebalance from a withdrawal or lowering the debtRatio
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
        forceHarvestTriggerOnce = false;
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }
        if (harvestNow) {
            // Send all of our Curve pool tokens to be deposited
            uint256 _toInvest = balanceOfWant();
            // deposit into convex and stake immediately but only if we have something to invest
            if (_toInvest > 0) {
                IConvexDeposit(depositContract).deposit(pid, _toInvest, true);
            }
            // we're done with our harvest, so we turn our toggle back to false
            harvestNow = false;
        } else {
            // this is our tend call
            claimAndSell();

            // update our variable for tracking last tend time
            lastTendTime = block.timestamp;

            // we're done harvesting, so reset our trigger if we used it
            forceTendTriggerOnce = false;
        }
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
        sethProxy.safeTransfer(
            _newStrategy,
            convexToken.balanceOf(address(this))
        );
    }

    // Sells our CRV and CVX to ETH on Curve
    function _sellCrvAndCvx(uint256 _crvAmount, uint256 _convexAmount)
        internal
    {
        if (_convexAmount > 0) {
            cvxeth.exchange(1, 0, _convexAmount, 0, true);
        }

        if (_crvAmount > 0) {
            crveth.exchange(1, 0, _crvAmount, 0, true);
        }
    }

    // Sells our rKP3R rewards for more want on uniV3
    function _sellRkpr(uint256 _amount) internal {
        IUniV3(uniswapv3).exactInput(
            IUniV3.ExactInputParams(
                abi.encodePacked(
                    address(rkpr),
                    uint24(500),
                    kpr,
                    uint24(10000),
                    address(weth)
                ),
                address(this),
                block.timestamp,
                _amount,
                uint256(1)
            )
        );

        uint256 wethBalance = weth.balanceOf(address(this));
        IWeth(address(weth)).withdraw(wethBalance);
    }

    /* ========== KEEP3RS ========== */

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

        // check if the 5-minute lock has elapsed yet
        if (!checkWaitingPeriod()) {
            return false;
        }

        // check if the base fee gas price is higher than we allow. if it is, block harvests.
        if (!isBaseFeeAcceptable()) {
            return false;
        }

        // trigger if we want to manually harvest, but only if our gas price is acceptable
        if (forceHarvestTriggerOnce) {
            if (forceTendTriggerOnce) {
                return false;
            } else {
                return true;
            }
        }

        // harvest our profit if we have tended since our last harvest
        StrategyParams memory params = vault.strategies(address(this));
        if (lastTendTime > params.lastReport) {
            return true;
        }

        // harvest our credit if it's above our threshold
        if (vault.creditAvailable() > creditThreshold) {
            return true;
        }

        // otherwise, we don't harvest
        return false;
    }

    function tendTrigger(uint256 callCostinEth)
        public
        view
        override
        returns (bool)
    {
        // Should not trigger if strategy is not active (no assets and no debtRatio). This means we don't need to adjust keeper job.
        if (!isActive()) {
            return false;
        }

        // only check if we need to earmark on vaults we know are problematic
        if (checkEarmark) {
            // don't harvest if we need to earmark convex rewards
            if (needsEarmarkReward()) {
                return false;
            }
        }

        // Should not tend if forex markets are closed.
        if (isMarketClosed()) {
            return false;
        }

        // harvest if we have a profit to claim at our upper limit without considering gas price
        uint256 claimableProfit = claimableProfitInUsdt();
        if (claimableProfit > harvestProfitMax) {
            return true;
        }

        // check if the base fee gas price is higher than we allow. if it is, block harvests.
        if (!isBaseFeeAcceptable()) {
            return false;
        }

        // trigger if we want to manually harvest, but only if our gas price is acceptable
        if (forceTendTriggerOnce) {
            return true;
        }

        // harvest if we have a sufficient profit to claim, but only if our gas price is acceptable
        if (claimableProfit > harvestProfitMin) {
            return true;
        }

        // Should trigger if hasn't been called in a while. Running this based on harvest even though this is a tend call since a harvest should run ~5 mins after every tend.
        if (block.timestamp.sub(lastTendTime) >= maxReportDelay) return true;
    }

    // we will need to add rewards token here if we have them
    function claimableProfitInUsdt() public view returns (uint256) {
        // calculations pulled directly from CVX's contract for minting CVX per CRV claimed
        uint256 totalCliffs = 1_000;
        uint256 maxSupply = 100 * 1_000_000 * 1e18; // 100mil
        uint256 reductionPerCliff = 100_000 * 1e18; // 100,000
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

        // our chainlink oracle returns prices normalized to 8 decimals, we convert it to 6
        IOracle ethOracle = IOracle(0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419);
        uint256 ethPrice = ethOracle.latestAnswer().div(1e2); // 1e8 div 1e2 = 1e6
        uint256 crvPrice = crveth.price_oracle().mul(ethPrice).div(1e18); // 1e18 mul 1e6 div 1e18 = 1e6
        uint256 cvxPrice = cvxeth.price_oracle().mul(ethPrice).div(1e18); // 1e18 mul 1e6 div 1e18 = 1e6

        uint256 crvValue = crvPrice.mul(_claimableBal).div(1e18); // 1e6 mul 1e18 div 1e18 = 1e6
        uint256 cvxValue = cvxPrice.mul(mintableCvx).div(1e18); // 1e6 mul 1e18 div 1e18 = 1e6

        return crvValue.add(cvxValue);
    }

    // convert our keeper's eth cost into want (too much of a pain for Fixed Forex, and doesn't give much use)
    function ethToWant(uint256 _ethAmount)
        public
        view
        override
        returns (uint256)
    {
        return _ethAmount;
    }

    // check if the current baseFee is below our external target
    function isBaseFeeAcceptable() internal view returns (bool) {
        return
            IBaseFee(0xb5e1CAcB567d98faaDB60a1fD4820720141f064F)
                .isCurrentBaseFeeAcceptable();
    }

    /* ========== SYNTHETIX ========== */

    // claim and swap our CRV for synths
    function claimAndSell() internal {
        // if we have anything in the gauge, then harvest CRV from the gauge
        if (claimableBalance() > 0) {
            // check if we have any CRV to claim
            // this claims our CRV, CVX, and any extra tokens.
            IConvexRewards(rewardsContract).getReward(address(this), true);

            uint256 _crvBalance = crv.balanceOf(address(this));
            uint256 _convexBalance = convexToken.balanceOf(address(this));

            uint256 _sendToVoter =
                _crvBalance.mul(keepCRV).div(FEE_DENOMINATOR);
            if (_sendToVoter > 0) {
                crv.safeTransfer(voter, _sendToVoter);
            }
            uint256 _crvRemainder = crv.balanceOf(address(this));

            // sell the rest of our CRV and our CVX for ETH
            _sellCrvAndCvx(_crvRemainder, _convexBalance);

            // sell any rKP3R we may have for WETH if our setter is true
            uint256 rkprBalance = rkpr.balanceOf(address(this));
            if (sellRkpr && rkprBalance > 0) {
                _sellRkpr(rkprBalance);
            }

            // convert our ETH into sETH
            uint256 ethBalance = address(this).balance;
            if (ethBalance > 0) {
                setheth.exchange{value: ethBalance}(0, 1, ethBalance, 0);
            }

            // check our output balance of sETH
            uint256 _sEthBalance = sethProxy.balanceOf(address(this));

            // swap our sETH for our underlying synth if the forex markets are open
            if (!isMarketClosed()) {
                exchangeSEthToSynth(_sEthBalance);
            }
        }
    }

    function exchangeSEthToSynth(uint256 amount) internal returns (uint256) {
        // swap amount of sETH for Synth
        if (amount == 0) {
            return 0;
        }

        return
            _synthetix().exchangeWithTracking(
                sethCurrencyKey,
                amount,
                synthCurrencyKey,
                address(this),
                TRACKING_CODE
            );
    }

    function _synthetix() internal view returns (ISynthetix) {
        return ISynthetix(resolver().getAddress(CONTRACT_SYNTHETIX));
    }

    function resolver() internal view returns (IAddressResolver) {
        return IAddressResolver(readProxy.target());
    }

    function _exchanger() internal view returns (IExchanger) {
        return IExchanger(resolver().getAddress(CONTRACT_EXCHANGER));
    }

    function checkWaitingPeriod() internal view returns (bool freeToMove) {
        return
            // check if it's been >5 mins since we traded our sETH for our synth
            _exchanger().maxSecsLeftInWaitingPeriod(
                address(this),
                synthCurrencyKey
            ) == 0;
    }

    function isMarketClosed() public view returns (bool) {
        // set up our arrays to use
        bool[] memory tradingSuspended;
        bytes32[] memory synthArray;

        // use our synth key
        synthArray = new bytes32[](1);
        synthArray[0] = synthCurrencyKey;

        // check if trading is open or not. true = market is closed
        (tradingSuspended, ) = systemStatus.getSynthExchangeSuspensions(
            synthArray
        );
        return tradingSuspended[0];
    }

    // check if someone needs to earmark rewards on convex before keepers harvest again
    function needsEarmarkReward() public view returns (bool needsEarmark) {
        // check if there is any CRV we need to earmark
        uint256 crvExpiry = rewardsContract.periodFinish();
        if (crvExpiry < block.timestamp) {
            return true;
        }
    }

    // include so our contract plays nicely with ether
    receive() external payable {}

    /* ========== SETTERS ========== */

    // Min profit to start checking for harvests if gas is good, max will harvest no matter gas (both in USDT, 6 decimals). Credit threshold is in want token, and will trigger a harvest if credit is large enough. check earmark to look at convex's booster.
    function setHarvestTriggerParams(
        uint256 _harvestProfitMin,
        uint256 _harvestProfitMax,
        uint256 _creditThreshold,
        bool _checkEarmark
    ) external onlyEmergencyAuthorized {
        harvestProfitMin = _harvestProfitMin;
        harvestProfitMax = _harvestProfitMax;
        creditThreshold = _creditThreshold;
        checkEarmark = _checkEarmark;
    }

    // turn this off if we don't want to automatically sell our rkp3r claimed
    function setSellRkpr(bool _sellRkpr) external onlyEmergencyAuthorized {
        sellRkpr = _sellRkpr;
    }
}
