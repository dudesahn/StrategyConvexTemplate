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
import {BaseStrategy} from "@yearnvaults/contracts/BaseStrategy.sol";

interface ITradeFactory {
    function enable(address, address) external;
    function disable(address, address) external;
}

interface IBaseFee {
    function isCurrentBaseFeeAcceptable() external view returns (bool);
}
interface ICurveGauge {
    function deposit(uint256) external;
    function balanceOf(address) external view returns (uint256);
    function withdraw(uint256) external;
    function claim_rewards() external;
    function reward_tokens(uint256) external view returns(address);//v2
    function rewarded_token() external view returns(address);//v1
    function lp_token() external view returns(address);
    function reward_count() external view returns(uint256);
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

interface ICurveStrategyProxy {
    function proxy() external returns (address);

    function balanceOf(address _gauge) external view returns (uint256);

    function deposit(address _gauge, address _token) external;

    function withdraw(
        address _gauge,
        address _token,
        uint256 _amount
    ) external returns (uint256);

    function withdrawAll(address _gauge, address _token)
        external
        returns (uint256);

    function harvest(address _gauge) external;

    function lock() external;

    function approveStrategy(address) external;

    function revokeStrategy(address) external;

    function claimRewards(address _gauge, address _token) external;
}

interface IDetails {
    // get details from curve
    function name() external view returns (string memory);
}

contract StrategyCurveFactoryClonable is BaseStrategy  {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;

    /* ========== STATE VARIABLES ========== */
    // these should stay the same across different wants.

    
    uint256 public localKeepCRV;

    address public constant voter = 0xF147b8125d2ef93FB6965Db97D6746952a133934; // Yearn's veCRV voter, we send some extra CRV here
    uint256 internal constant FEE_DENOMINATOR = 10000; // this means all of our fee values are in basis points

    address internal constant sushiswap =
        0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F; // default to sushiswap, more CRV and CVX liquidity there

    IERC20 internal constant crv =
        IERC20(0xD533a949740bb3306d119CC777fa900bA034cd52);
    IERC20 internal constant weth =
        IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    IERC20 internal constant usdt =
        IERC20(0xdAC17F958D2ee523a2206206994597C13D831ec7);

    // keeper stuff
    uint256 public harvestProfitMin; // minimum size in USDT that we want to harvest
    uint256 public harvestProfitMax; // maximum size in USDT that we want to harvest
    bool internal forceHarvestTriggerOnce; // only set this to true when we want to trigger our keepers to harvest for us

    string internal stratName; // we use this to be able to adjust our strategy's name

    // convex-specific variables
    bool public claimRewards; // boolean if we should always claim rewards when withdrawing, usually withdrawAndUnwrap (generally this should be false)

    /* ========== STATE VARIABLES ========== */
    // these will likely change across different wants.

    // Curve stuff
    address public gauge;

    bool public skipClaim;
    bool public tradesEnabled;
    address public tradeFactory;

    // rewards token info. we can have more than 1 reward token but this is rare, so we don't include this in the template
    address[] public rewardsTokens;
    bool public hasRewards;

    address public proxy; // our proxy

    // check for cloning
    bool internal isOriginal = true;

    /* ========== CONSTRUCTOR ========== */

    constructor(
        address _vault,
        address _tradeFactory,
        address _gauge
    ) public BaseStrategy(_vault) {
        _initializeStrat(_gauge, _tradeFactory);
    }

    /* ========== CLONING ========== */

    event Cloned(address indexed clone);

    // we use this to clone our original strategy to other vaults
    function cloneStrategyCurve(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _gauge,
        address _tradeFactory
    ) external returns (address newStrategy) {
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

        StrategyConvexFactoryClonable(newStrategy).initialize(
            _vault,
            _strategist,
            _rewards,
            _keeper,
            _gauge,
            _tradeFactory
        );

        emit Cloned(newStrategy);
    }

    // this will only be called by the clone function above
    function initialize(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _gauge,
        address _tradeFactory
    ) public {
        _initialize(_vault, _strategist, _rewards, _keeper);
        _initializeStrat(_gauge, _tradeFactory);
    }

    // this is called by our original strategy, as well as any clones
    function _initializeStrat(
        address _gauge, address _tradeFactory
    ) internal {
        // make sure that we haven't initialized this before
        require(address(tradeFactory) == address(0)); // already initialized.
        
        require(ICurveGauge(_gauge).lp_token() == want);
        gauge = _gauge;

        proxy = ICurveStrategyProxy(0xA420A63BbEFfbda3B147d0585F1852C358e2C152);

        // want = Curve LP
        want.approve(address(depositContract), type(uint256).max);

        // harvest profit max set to 25k usdt. will trigger harvest in this situation
        harvestProfitMax = 25_000 * 1e6;

        IConvexDeposit dp = IConvexDeposit(depositContract);
        pid = _pid;
        (address lptoken, , , address _rewardsContract, , ) = dp.poolInfo(_pid);
        rewardsContract = IConvexRewards(_rewardsContract);

        require(address(lptoken) == address(want));

        _updateRewards();

        tradeFactory = _tradeFactory;

        // set our strategy's name
        stratName = string(abi.encodePacked(IDetails(address(want)).name(), "Convex Strat"));
    }

    function _setUpTradeFactory() internal{
        //approve and set up trade factory
        address _tradeFactory = tradeFactory;

        ITradeFactory tf = ITradeFactory(_tradeFactory);
        crv.safeApprove(_tradeFactory, type(uint256).max);
        tf.enable(address(crv), address(want));

        //enable for all rewards tokens too
        for(uint256 i; i < rewardsTokens.length; i++){
            IERC20(rewardsTokens[i]).safeApprove(_tradeFactory, type(uint256).max);
            tf.enable(rewardsTokens[i], address(want));
        }
        
        convexToken.safeApprove(_tradeFactory, type(uint256).max);
        tf.enable(address(convexToken), address(want));
        tradesEnabled = true;
    }

    /* ========== VARIABLE FUNCTIONS ========== */
    // these will likely change across different wants.

    //anyone can call
    function claimRewards(address _token) external{
        ICurveStrategyProxy(proxy).claimRewards(gauge, _token);
    }

    function _claimAllRewards() internal{
        //get our rewards from the proxy
        ICurveStrategyProxy p = ICurveStrategyProxy(proxy);
        p.claimRewards(guage, crv);
        for(uint256 i = 0; i < rewardsTokens.length; i ++){
            p.claimRewards(guage, rewardsTokens[i]);
        }
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
        if(tradesEnabled == false && tradeFactory != address(0)){
            _setUpTradeFactory();
        }
        
        //allow normal ops if something is wrong
        if(!skipClaim){
            _claimAllRewards();
        }

        uint256 crvBalance = crv.balanceOf(address(this));
        uint256 keep = localKeepCRV;
        uint256 _sendToVoter = crvBalance.mul(keep).div(FEE_DENOMINATOR);
        if (_sendToVoter > 0) {
            crv.safeTransfer(voter, _sendToVoter);
        }
        _debtPayment = _debtOutstanding;

        // serious loss should never happen, but if it does (for instance, if Curve is hacked), let's record it accurately
        uint256 assets = estimatedTotalAssets();
        uint256 debt = vault.strategies(address(this)).totalDebt;

        // if assets are greater than debt, things are working great!
        if (assets >= debt) {
            _profit = assets.sub(debt);
            
            uint256 toFree = _profit.add(_debtPayment);

            //freed is math.min(wantBalance, toFree)
            (uint256 freed, ) = liquidatePosition(toFree);
            
            if (_profit.add(_debtPayment) > freed) {
                if(_debtPayment > freed){
                    _debtPayment = freed;
                    _profit = 0;
                }else{
                    _profit = freed - _debtPayment;
                }
            }
        }
        // if assets are less than debt, we are in trouble. should never happen. dont worry about withdrawing here just report profit
        else {
            _loss = debt.sub(assets);
        }

        // we're done harvesting, so reset our trigger if we used it
        forceHarvestTriggerOnce = false;
    }

    // migrate our want token to a new strategy if needed, make sure to check claimRewards first
    // also send over any CRV or CVX that is claimed; for migrations we definitely want to claim
    function prepareMigration(address _newStrategy) internal override {
        uint256 _stakedBal = stakedBalance();
        if (_stakedBal > 0) {
            ICurveStrategyProxy(proxy).withdraw(gauge, address(want), _stakedBal);
        }
    }

    /* ========== KEEP3RS ========== */
    // use this to determine when to harvest automagically
    function harvestTrigger(uint256 callCostinEth)
        public
        view
        override
        returns (bool)
    {
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

        // trigger if we want to manually harvest, but only if our gas price is acceptable
        if (forceHarvestTriggerOnce) {
            return true;
        }

        // harvest if we have a sufficient profit to claim, but only if our gas price is acceptable
        if (claimableProfit > harvestProfitMin) {
            return true;
        }

        // otherwise, we don't harvest
        return false;
    }

    // only checks crv and cvx
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

        address[] memory usd_path = new address[](3);
        usd_path[0] = address(crv);
        usd_path[1] = address(weth);
        usd_path[2] = address(usdt);

        uint256 crvValue;
        if (_claimableBal > 0) {
            uint256[] memory crvSwap =
                IUniswapV2Router02(sushiswap).getAmountsOut(
                    _claimableBal,
                    usd_path
                );
            crvValue = crvSwap[crvSwap.length - 1];
        }

        usd_path[0] = address(convexToken);
        uint256 cvxValue;
        if (mintableCvx > 0) {
            uint256[] memory cvxSwap =
                IUniswapV2Router02(sushiswap).getAmountsOut(
                    mintableCvx,
                    usd_path
                );
            cvxValue = cvxSwap[cvxSwap.length - 1];
        }

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

    // check if someone needs to earmark rewards on convex before keepers harvest again
    function needsEarmarkReward() public view returns (bool needsEarmark) {
        // check if there is any CRV we need to earmark
        uint256 crvExpiry = rewardsContract.periodFinish();
        if (crvExpiry < block.timestamp) {
            return true;
        } 
        // else {
        //     // check if there is any bonus reward we need to earmark
        //     uint256 rewardsExpiry =
        //         IConvexRewards(virtualRewardsPool).periodFinish();
        //     if (rewardsExpiry < block.timestamp) {
        //         return true;
        //     }
        // }
    }

    /* ========== SETTERS ========== */

    // These functions are useful for setting parameters of the strategy that may need to be adjusted.

    // Use to add or update rewards
    // Rebuilds tradefactory too
    function updateRewards() external onlyGovernance {
        address tf = tradeFactory;
        _removeTradeFactoryPermissions();
        _updateRewards();

        tradeFactory = tf;
        _setUpTradeFactory();
    }

    function _updateRewards() internal {

        delete rewardsTokens; //empty the rewardsTokens and rebuild
        ICurveGauge g = ICurveGauge(gauge);

        //we need to treat differently for different gauge versions. start with v2 as that is more likely
        if (IsV2()){
            for (uint256 i; i< g.reward_count(); i++){
                rewardsTokens.push(g.reward_tokens[i]);
            }
        }
        else if(IsV1()){
            //only one reward
            rewardsTokens.push(g.rewarded_token());
        }
        
        
    }

    function updateLocalKeepcrv(uint256 _keep) external onlyGovernance {
        
        require(_keep <= 10_000);
        if(_local){
            localKeepCRV = _keep;
        }
    }

    // Use to turn off extra rewards claiming and selling. set our allowance to zero on the router and set address to zero address.
    function turnOffRewards() external onlyGovernance {
        hasRewards = false;
        rewardsToken = address(0);
    }

    // determine whether we will check if our convex rewards need to be earmarked
    function setCheckEarmark(bool _checkEarmark) external onlyAuthorized {
        checkEarmark = _checkEarmark;
    }

    /* ========== VIEWS ========== */

    function name() external view override returns (string memory) {
        return stratName;
    }

    function stakedBalance() public view returns (uint256) {
        // how much want we have staked in Convex
        return ICurveStrategyProxy(proxy).balanceOf(gauge);
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

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }
        // Send all of our Curve pool tokens to be deposited
        uint256 _toInvest = balanceOfWant();
        // deposit into convex and stake immediately but only if we have something to invest
         if (_toInvest > 0) {
            want.safeTransfer(proxy, _toInvest);
            ICurveStrategyProxy(proxy).deposit(gauge, address(want));
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

    // We usually don't need to claim rewards on withdrawals, but might change our mind for migrations etc
    function setClaimRewards(bool _claimRewards) external onlyAuthorized {
        claimRewards = _claimRewards;
    }

    // This determines when we tell our keepers to start allowing harvests based on profit, and when to sell no matter what. this is how much in USDT we need to make. remember, 6 decimals!
    function setHarvestProfitNeeded(
        uint256 _harvestProfitMin,
        uint256 _harvestProfitMax
    ) external onlyAuthorized {
        harvestProfitMin = _harvestProfitMin;
        harvestProfitMax = _harvestProfitMax;
    }

    function updateTradeFactory(
        address _newTradeFactory
    ) external onlyGovernance {
        if(tradeFactory != address(0))
        {
            _removeTradeFactoryPermissions();
        }
        
        tradeFactory = _newTradeFactory;
        _setUpTradeFactory();
    }

    // once this is called setupTradefactory must be called to get things working again
    function removeTradeFactoryPermissions() external onlyEmergencyAuthorized{
        _removeTradeFactoryPermissions();
        
    }
    function _removeTradeFactoryPermissions() internal{

        address _tradeFactory = tradeFactory;
        ITradeFactory tf = ITradeFactory(_tradeFactory);

        crv.safeApprove(_tradeFactory, 0);
        tf.disable(convexToken, address(want));

        //disable for all rewards tokens too
        for(uint256 i; i < rewardsTokens.length; i++){
            IERC20(rewardsTokens[i]).safeApprove(_tradeFactory, 0);
            tf.disable(rewardsTokens[i], address(want));
        }
        
        convexToken.safeApprove(_tradeFactory, 0);
        tf.disable(convexToken, address(want));

        tradeFactory = address(0);
        
    }

    // This allows us to manually harvest with our keeper as needed
    function setForceHarvestTriggerOnce(bool _forceHarvestTriggerOnce)
        external
        onlyAuthorized
    {
        forceHarvestTriggerOnce = _forceHarvestTriggerOnce;
    }

    function setSkipClaim(bool _skipClaim)
        external
        onlyEmergencyAuthorized
    {
        skipClaim = _skipClaim;
    }


    bytes4 private constant rewarded_token = 0x16fa50b1; //rewarded_token()
    bytes4 private constant reward_tokens = 0x54c49fe9; //reward_tokens(uint256)

    function IsV1() private returns(bool){
        bytes memory data = abi.encode(rewarded_token);
        (bool success,) = gauge.call(data);
        return success;
    }

    function IsV2() private returns(bool){
        bytes memory data = abi.encodeWithSelector(reward_tokens,uint256(0));
        (bool success,) = gauge.call(data);
        return success;
    }
}

