// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

// These are the core Yearn libraries
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/Address.sol";
import "@openzeppelin/contracts/math/Math.sol";

interface IGauge {
    struct VotedSlope {
        uint slope;
        uint power;
        uint end;
    }
    struct Point {
        uint bias;
        uint slope;
    }
    function vote_user_slopes(address, address) external view returns (VotedSlope memory);
    function last_user_vote(address, address) external view returns (uint);
    function points_weight(address, uint256) external view returns (Point memory);
    function checkpoint_gauge(address) external;
    function time_total() external view returns (uint);
}

interface IStrategy {
    function estimatedTotalAssets() external view returns (uint);
    function rewardsContract() external view returns (address);
}

interface IRewards {
    function getReward(address, bool) external;
}

interface IYveCRV {
    function deposit(uint) external;
}

contract Splitter {

    event Split(uint yearnAmount, uint keep, uint templAmount, uint period);
    event PeriodUpdated(uint period, uint globalSlope, uint userSlope);

    struct Yearn{
        address recipient;
        address voter;
        uint share;
        uint keepCRV;
    }
    struct Period{
        uint period;
        uint globalSlope;
        uint userSlope;
    }

    uint constant precision = 10_000;
    uint constant WEEK = 86400 * 7;
    IERC20 constant crv = IERC20(0xD533a949740bb3306d119CC777fa900bA034cd52);
    IYveCRV constant yvecrv = IYveCRV(0xc5bDdf9843308380375a611c18B50Fb9341f502A);
    IERC20 constant liquidityPool = IERC20(0xdaDfD00A2bBEb1abc4936b1644a3033e1B653228);
    IGauge constant gaugeController = IGauge(0x2F50D538606Fa9EDD2B11E2446BEb18C9D5846bB);
    address constant gauge = 0xdaDfD00A2bBEb1abc4936b1644a3033e1B653228;
    
    Yearn yearn;
    Period period;
    address public strategy;
    address templeRecipient = 0x5C8898f8E0F9468D4A677887bC03EE2659321012;
    address owner;
    
    constructor() public {
        owner = 0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52;
        crv.approve(address(yvecrv), type(uint256).max);
        yearn = Yearn(
            address(0xF147b8125d2ef93FB6965Db97D6746952a133934),
            address(0xF147b8125d2ef93FB6965Db97D6746952a133934),
            7_000,
            5_000
        );
    }

    function split() external {
        _split();
    }

    function claimAndSplit() external {
        IRewards(IStrategy(strategy).rewardsContract()).getReward(strategy, true);
        _split();
    }

    function _split() internal {
        uint256 crvBalance = crv.balanceOf(strategy);
        if (crvBalance == 0) return;
        if (block.timestamp / WEEK * WEEK > period.period) _updatePeriod();
        (uint yRatio, uint tRatio) = _computeSplitRatios();
        if (yRatio == 0) {
            crv.transferFrom(strategy, templeRecipient, crvBalance);
            emit Split(0, 0, crvBalance, period.period);
            return;
        }
        uint yearnAmount = crvBalance * yRatio / precision;
        uint templeAmount = crvBalance * tRatio / precision;
        uint keep = yearnAmount * yearn.keepCRV / precision;
        if (keep > 0) {
            crv.transferFrom(strategy, address(this), keep);
            yvecrv.deposit(keep);
        }
        crv.transferFrom(strategy, yearn.recipient, yearnAmount - keep);
        crv.transferFrom(strategy, templeRecipient, templeAmount);
        emit Split(yearnAmount, keep, templeAmount, period.period);
    }

    // @dev: updates all period data to present week
    function _updatePeriod() internal {
        uint _period = block.timestamp / WEEK * WEEK;
        period.period = _period;
        gaugeController.checkpoint_gauge(gauge);
        uint _userSlope = gaugeController.vote_user_slopes(yearn.voter, gauge).slope;
        uint _globalSlope = gaugeController.points_weight(gauge, _period).slope;
        period.userSlope = _userSlope;
        period.globalSlope = _globalSlope;
        emit PeriodUpdated(_period, _userSlope, _globalSlope);
    }

    function _computeSplitRatios() internal view returns (uint yRatio, uint tRatio) {
        uint _precision = precision; // @dev: Move value into memory
        uint userSlope = period.userSlope;
        if(period.userSlope == 0) return (0, 10_000);
        uint relativeSlope = userSlope * precision / period.globalSlope;
        uint lpSupply = liquidityPool.totalSupply();
        if (lpSupply == 0){
            return (10_000, 0);
        }
        uint gaugeDominance = 
            IStrategy(strategy).estimatedTotalAssets() 
            * _precision 
            / lpSupply;
        yRatio = relativeSlope 
            * _precision 
            / gaugeDominance;
        // Cannot return > 100%
        if (yRatio > 10_000){
            return (10_000, 0);
        }
        tRatio = _precision - yRatio;
    }

    // @dev: Estimate only. Only guaranteed to be accuarate when period data is not stale.
    function estimateSplit() external view returns (uint ySplit, uint tSplit) {
        (uint y, uint t) = _computeSplitRatios();
        uint bal = crv.balanceOf(strategy);
        ySplit = bal * y / precision;
        tSplit = bal - ySplit;
    }

    // @dev: Estimate only. Only guaranteed to be accuarate when period data is not stale.
    function estimateSplitRatios() external view returns (uint ySplit, uint tSplit) {
        (ySplit, tSplit) = _computeSplitRatios();
    }

    function setStrategy(address _strategy) external {
        require(msg.sender == owner);
        strategy = _strategy;
    }
}