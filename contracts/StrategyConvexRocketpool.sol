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

interface IBaseFee {
    function isCurrentBaseFeeAcceptable() external view returns (bool);
}

interface IOracle {
    function latestAnswer() external view returns (uint256);
}

interface IstETH is IERC20 {
    function submit(address _referral) external payable returns (uint256);
}

interface IwstETH is IERC20 {
    function wrap(uint256 _amount) external returns (uint256);
}

interface IRocketPoolHelper {
    function getRocketDepositPoolAddress() external view returns (address);

    function getMinimumDepositSize() external view returns (uint256);

    function isRethFree(address _user) external view returns (bool);

    function rEthCanAcceptDeposit(uint256 _ethAmount)
        external
        view
        returns (bool);

    function deposit() external payable;
}

interface IRocketPoolDeposit {
    function deposit() external payable;
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

    // check if we have rewards on a pool
    function extraRewardsLength() external view returns (uint256);

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
    address public constant depositContract =
        0xF403C135812408BFbE8713b5A23a04b3D48AAE31; // this is the deposit contract that all pools use, aka booster
    IConvexRewards public rewardsContract; // This is unique to each curve pool
    uint256 public pid; // this is unique to each pool

    // keepCRV stuff
    uint256 public keepCRV; // the percentage of CRV we re-lock for boost (in basis points)
    address public constant voter = 0xF147b8125d2ef93FB6965Db97D6746952a133934; // Yearn's veCRV voter, we send some extra CRV here
    uint256 internal constant FEE_DENOMINATOR = 10000; // this means all of our fee values are in basis points

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
    bool internal harvestNow; // this tells us if we're currently harvesting or tending

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
        return rewardsContract.balanceOf(address(this));
    }

    function balanceOfWant() public view returns (uint256) {
        // balance of want sitting in our strategy
        return want.balanceOf(address(this));
    }

    function claimableBalance() public view returns (uint256) {
        // how much CRV we can claim from the staking contract
        return rewardsContract.earned(address(this));
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
                rewardsContract.withdrawAndUnwrap(
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
            rewardsContract.withdrawAndUnwrap(_stakedBal, claimRewards);
        }
        return balanceOfWant();
    }

    // in case we need to exit into the convex deposit token, this will allow us to do that
    // make sure to check claimRewards before this step if needed
    // plan to have gov sweep convex deposit tokens from strategy after this
    function withdrawToConvexDepositTokens() external onlyAuthorized {
        uint256 _stakedBal = stakedBalance();
        if (_stakedBal > 0) {
            rewardsContract.withdraw(_stakedBal, claimRewards);
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
    function setKeepCRV(uint256 _keepCRV) external onlyAuthorized {
        require(_keepCRV <= 10_000);
        keepCRV = _keepCRV;
    }

    // We usually don't need to claim rewards on withdrawals, but might change our mind for migrations etc
    function setClaimRewards(bool _claimRewards) external onlyAuthorized {
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

contract StrategyConvexRocketpool is StrategyConvexBase {
    /* ========== STATE VARIABLES ========== */
    // these will likely change across different wants.

    // Curve stuff
    ICurveFi public constant curve =
        ICurveFi(0x447Ddd4960d9fdBF6af9a790560d0AF76795CB08); // This is our pool specific to this vault.
    bool public checkEarmark; // this determines if we should check if we need to earmark rewards before harvesting

    bool public mintReth; // use this to determine if we are depositing wsteth or reth to our curve pool (we mint both directly from ETH)

    // use Curve to sell our CVX and CRV rewards to WETH
    ICurveFi internal constant crveth =
        ICurveFi(0x8301AE4fc9c624d1D396cbDAa1ed877821D7C511); // use curve's new CRV-ETH crypto pool to sell our CRV
    ICurveFi internal constant cvxeth =
        ICurveFi(0xB576491F1E6e5E62f1d8F26062Ee822B40B0E0d4); // use curve's new CVX-ETH crypto pool to sell our CVX

    // stETH and rETH token contracts
    IstETH internal constant steth =
        IstETH(0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84);
    IwstETH internal constant wsteth =
        IwstETH(0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0);
    IERC20 internal constant reth =
        IERC20(0xae78736Cd615f374D3085123A210448E74Fc6393);

    // rocketpool helper contract
    IRocketPoolHelper public constant rocketPoolHelper =
        IRocketPoolHelper(0x5943910C2e88480584092C7B95A3FD762cAbc699);

    address internal referral = 0xD20Eb2390e675b000ADb8511F62B28404115A1a4; // referral address, use EOA to claim on L2
    uint256 public lastTendTime; // this is the timestamp that our last tend was called

    /* ========== CONSTRUCTOR ========== */

    constructor(
        address _vault,
        uint256 _pid,
        string memory _name
    ) public StrategyConvexBase(_vault) {
        // want = Curve LP
        want.approve(address(depositContract), type(uint256).max);
        convexToken.approve(address(cvxeth), type(uint256).max);
        crv.approve(address(crveth), type(uint256).max);

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

        // these are our approvals and path specific to this contract
        wsteth.approve(address(curve), type(uint256).max);
        reth.approve(address(curve), type(uint256).max);
        steth.approve(address(wsteth), type(uint256).max);

        // set our last tend time on deployment
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

        if (!mintReth) {
            // go through the claim, sell, and deposit process for wstETH
            rewardsContract.getReward(address(this), true);

            uint256 crvBalance = crv.balanceOf(address(this));
            uint256 convexBalance = convexToken.balanceOf(address(this));

            uint256 sendToVoter = crvBalance.mul(keepCRV).div(FEE_DENOMINATOR);
            if (sendToVoter > 0) {
                crv.safeTransfer(voter, sendToVoter);
            }
            uint256 crvRemainder = crv.balanceOf(address(this));

            // sell the rest of our CRV and our CVX for ETH and mint wstETH with it
            uint256 ethBalance = _sellCrvAndCvx(crvRemainder, convexBalance);
            if (ethBalance > 0) {
                mintWsteth(ethBalance);
            }

            uint256 wstethBalance = wsteth.balanceOf(address(this));
            if (wstethBalance > 0) {
                curve.add_liquidity([0, wstethBalance], 0);
            }
        }

        uint256 rEthBalance = reth.balanceOf(address(this));
        // if we're depositing via rETH, we will have already minted it, but double-check that it's unlocked
        if (rEthBalance > 0 && isRethFree()) {
            curve.add_liquidity([rEthBalance, 0], 0);
        }

        // debtOustanding will only be > 0 in the event of revoking or if we need to rebalance from a withdrawal or lowering the debtRatio
        if (_debtOutstanding > 0) {
            uint256 _stakedBal = stakedBalance();
            if (_stakedBal > 0) {
                rewardsContract.withdrawAndUnwrap(
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
            if (mintReth) {
                // this is our tend call
                claimAndMintReth();
            }

            // update our variable for tracking last tend time
            lastTendTime = block.timestamp;

            // we're done harvesting, so reset our trigger if we used it
            forceTendTriggerOnce = false;
        }
    }

    // Sells our CRV and CVX for ETH on Curve
    function _sellCrvAndCvx(uint256 _crvAmount, uint256 _convexAmount)
        internal
        returns (uint256 ethBalance)
    {
        if (_convexAmount > 0) {
            cvxeth.exchange(1, 0, _convexAmount, 0, true);
        }

        if (_crvAmount > 0) {
            crveth.exchange(1, 0, _crvAmount, 0, true);
        }

        ethBalance = address(this).balance;
    }

    // mint wstETH from ETH
    function mintWsteth(uint256 _amount) internal {
        steth.submit{value: _amount}(referral);
        uint256 stethBalance = steth.balanceOf(address(this));
        wsteth.wrap(stethBalance);
    }

    // claim and swap our CRV and CVX for rETH
    function claimAndMintReth() internal {
        // this claims our CRV, CVX, and any extra tokens.
        IConvexRewards(rewardsContract).getReward(address(this), true);

        uint256 crvBalance = crv.balanceOf(address(this));
        uint256 convexBalance = convexToken.balanceOf(address(this));

        uint256 sendToVoter = crvBalance.mul(keepCRV).div(FEE_DENOMINATOR);
        if (sendToVoter > 0) {
            crv.safeTransfer(voter, sendToVoter);
        }
        uint256 crvRemainder = crv.balanceOf(address(this));

        // sell the rest of our CRV and our CVX for ETH
        uint256 toDeposit = _sellCrvAndCvx(crvRemainder, convexBalance);

        // deposit our rETH only if there's space, and if it's large enough. this will prevent keepers from tending as well if needed.
        require(
            rocketPoolHelper.rEthCanAcceptDeposit(toDeposit),
            "Can't accept this deposit!"
        );
        require(
            toDeposit > rocketPoolHelper.getMinimumDepositSize(),
            "Deposit too small."
        );

        // pull our most recent deposit contract address since it can be upgraded
        IRocketPoolDeposit rocketDepositPool =
            IRocketPoolDeposit(rocketPoolHelper.getRocketDepositPoolAddress());
        rocketDepositPool.deposit{value: toDeposit}();
    }

    // migrate our want token to a new strategy if needed, make sure to check claimRewards first
    // also send over any CRV or CVX that is claimed; for migrations we definitely want to claim
    function prepareMigration(address _newStrategy) internal override {
        uint256 _stakedBal = stakedBalance();
        if (_stakedBal > 0) {
            rewardsContract.withdrawAndUnwrap(_stakedBal, claimRewards);
        }
        crv.safeTransfer(_newStrategy, crv.balanceOf(address(this)));
        convexToken.safeTransfer(
            _newStrategy,
            convexToken.balanceOf(address(this))
        );
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

        if (!mintReth) {
            // only check if we need to earmark on vaults we know are problematic
            if (checkEarmark) {
                // don't harvest if we need to earmark convex rewards
                if (needsEarmarkReward()) {
                    return false;
                }
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

            // harvest if we have a sufficient profit to claim, but only if our gas price is acceptable
            if (claimableProfit > harvestProfitMin) {
                return true;
            }

            // pull our last harvest
            StrategyParams memory params = vault.strategies(address(this));

            // Should trigger if hasn't been called in a while.
            if (block.timestamp.sub(params.lastReport) >= maxReportDelay)
                return true;
        }

        // check if the base fee gas price is higher than we allow. if it is, block harvests.
        if (isBaseFeeAcceptable()) {
            // trigger if we want to manually harvest, but not if we also triggered a tend (should realistically never happen).
            if (forceHarvestTriggerOnce) {
                if (forceTendTriggerOnce) {
                    return false;
                } else {
                    return true;
                }
            }

            // harvest our strategy's credit if it's above our threshold
            if (vault.creditAvailable() > creditThreshold) {
                return true;
            }

            // if we're minting rETH, then we want to harvest as soon as it's free to deposit into our curve pool
            if (isRethFree() && reth.balanceOf(address(this)) > 0) {
                return true;
            }
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

        // only check if we need to tend if we're minting rETH
        if (mintReth) {
            // only check if we need to earmark on vaults we know are problematic
            if (checkEarmark) {
                // don't tend if we need to earmark convex rewards
                if (needsEarmarkReward()) {
                    return false;
                }
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
            if (block.timestamp.sub(lastTendTime) >= maxReportDelay)
                return true;
        }

        // otherwise, we don't harvest
        return false;
    }

    // we will need to add rewards token here if we have them
    function claimableProfitInUsdt() internal view returns (uint256) {
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

    // convert our keeper's eth cost into want, we don't need this anymore since we don't use baseStrategy harvestTrigger
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

    // this contains logic to check if it's been long enough since we minted our rETH to move it
    function isRethFree() public view returns (bool) {
        return rocketPoolHelper.isRethFree(address(this));
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

    function sweepETH() public onlyGovernance {
        (bool success, ) = governance().call{value: address(this).balance}("");
        require(success, "!FailedETHSweep");
    }

    /* ========== SETTERS ========== */

    // These functions are useful for setting parameters of the strategy that may need to be adjusted.
    // Set whether we mint rETH or wstETH
    function setMintReth(bool _mintReth) external onlyEmergencyAuthorized {
        mintReth = _mintReth;
    }

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

    // update our referral address as needed
    function setReferral(address _referral) external onlyEmergencyAuthorized {
        referral = _referral;
    }
}
