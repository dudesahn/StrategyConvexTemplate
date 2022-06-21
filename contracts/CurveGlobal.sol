// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

enum VaultType {DEFAULT, AUTOMATED, FIXED_TERM, EXPERIMENTAL}

interface Registry {
    function newVault(
        address _token,
        address _governance,
        address _guardian,
        address _rewards,
        string calldata _name,
        string calldata _symbol,
        uint256 _releaseDelta,
        VaultType _type
    ) external returns (address);

    function isRegistered(address token) external view returns (bool);

    function latestVault(address token) external view returns (address);

    function latestVault(address token, VaultType _type)
        external
        view
        returns (address);

    function endorseVault(
        address _vault,
        uint256 _releaseDelta,
        VaultType _type
    ) external;
}

interface IPoolManager {
    function addPool(address _gauge) external returns (bool);
}

interface ICurveGauge {
    function deposit(uint256) external;

    function balanceOf(address) external view returns (uint256);

    function withdraw(uint256) external;

    function claim_rewards() external;

    function reward_tokens(uint256) external view returns (address); //v2

    function rewarded_token() external view returns (address); //v1

    function lp_token() external view returns (address);
}

interface IGaugeController {
    function get_gauge_weight(address _gauge) external view returns (uint256);

    function vote_user_slopes(address, address)
        external
        view
        returns (
            uint256,
            uint256,
            uint256
        ); //slope,power,end

    function vote_for_gauge_weights(address, uint256) external;

    function add_gauge(
        address,
        int128,
        uint256
    ) external;
}

interface IStrategy {
    function cloneStrategyConvex(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        uint256 _pid,
        address _tradeFactory,
        uint256 _harvestProfitMax
    ) external returns (address newStrategy);

    function setHealthCheck(address) external;
}

interface IConvexDeposit {
    function gaugeMap(address) external view returns (bool);

    // deposit into convex, receive a tokenized deposit.  parameter to stake immediately (we always do this).
    function deposit(
        uint256 _pid,
        uint256 _amount,
        bool _stake
    ) external returns (bool);

    // burn a tokenized deposit (Convex deposit tokens) to receive curve lp tokens back
    function withdraw(uint256 _pid, uint256 _amount) external returns (bool);

    function poolLength() external view returns (uint256);

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

interface Vault {
    function setGovernance(address) external;

    function setManagement(address) external;

    function managementFee() external view returns (uint256);

    function setManagementFee(uint256) external;

    function performanceFee() external view returns (uint256);

    function setPerformanceFee(uint256) external;

    function setDepositLimit(uint256) external;

    function addStrategy(
        address,
        uint256,
        uint256,
        uint256,
        uint256
    ) external;
}

interface ISharerV4 {
    function setContributors(
        address,
        address[] memory,
        uint256[] memory
    ) external;
}

contract CurveGlobal {
    event NewAutomatedCurveVault(
        address indexed lpToken,
        address indexed gauge,
        address indexed vault,
        address convexStrategy,
        uint256 timestamp
    );

    ///////////////////////////////////
    //
    //  Storage variables and setters
    //
    ////////////////////////////////////

    // always owned by ychad
    address owner = 0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52;

    function setOwner(address newOwner) external {
        require(msg.sender == owner);
        owner = newOwner;
    }

    address public convexPoolManager =
        0xD1f9b3de42420A295C33c07aa5C9e04eDC6a4447;

    function setConvexPoolManager(address _convexPoolManager) external {
        require(msg.sender == owner);
        convexPoolManager = _convexPoolManager;
    }

    Registry public registry; //= Registry(address(0x50c1a2eA0a861A967D9d0FFE2AE4012c2E053804));

    function setRegistry(address _registry) external {
        require(msg.sender == owner);
        registry = Registry(_registry);
    }

    IConvexDeposit public convexDeposit =
        IConvexDeposit(0xF403C135812408BFbE8713b5A23a04b3D48AAE31);

    function setConvexDeposit(address _convexDeposit) external {
        require(msg.sender == owner);
        convexDeposit = IConvexDeposit(_convexDeposit);
    }

    address public sms = 0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7;

    function setSms(address _sms) external {
        require(msg.sender == owner);
        sms = _sms;
    }

    address public devms = 0x846e211e8ba920B353FB717631C015cf04061Cc9;

    function setDevms(address _devms) external {
        require(msg.sender == owner);
        devms = _devms;
    }

    address public treasury = 0x93A62dA5a14C80f265DAbC077fCEE437B1a0Efde;

    function setTreasury(address _treasury) external {
        require(msg.sender == owner);
        treasury = _treasury;
    }

    address public keeper = 0x736D7e3c5a6CB2CE3B764300140ABF476F6CFCCF;

    function setKeeper(address _keeper) external {
        require(msg.sender == owner);
        keeper = _keeper;
    }

    address public rewardsStrat = 0xc491599b9A20c3A2F0A85697Ee6D9434EFa9f503;

    function setStratRewards(address _rewards) external {
        require(msg.sender == owner);
        rewardsStrat = _rewards;
    }

    address public healthCheck = 0xDDCea799fF1699e98EDF118e0629A974Df7DF012;

    function setHealthcheck(address _health) external {
        require(msg.sender == owner);
        healthCheck = _health;
    }

    address public tradeFactory = 0x99d8679bE15011dEAD893EB4F5df474a4e6a8b29;

    function setTradeFactory(address _tradeFactory) external {
        require(msg.sender == owner || msg.sender == sms);
        tradeFactory = _tradeFactory;
    }

    uint256 public depositLimit = 10_000_000 * 1e18; // some large number

    function setDepositLimit(uint256 _depositLimit) external {
        require(msg.sender == owner || msg.sender == sms);
        depositLimit = _depositLimit;
    }

    address public convexStratImplementation;

    function setConvexStratImplementation(address _convexStratImplementation)
        external
    {
        require(msg.sender == owner);
        convexStratImplementation = _convexStratImplementation;
    }

    bool public allConvex = true;

    function setAllConvex(bool _allConvex) external {
        require(msg.sender == owner || msg.sender == sms);
        allConvex = _allConvex;
    }

    uint256 public keepCRV = 0; // the percentage of CRV we re-lock for boost (in basis points).Default is 10%.

    // Set the amount of CRV to be locked in Yearn's veCRV voter from each harvest.
    function setKeepCRV(uint256 _keepCRV) external {
        require(msg.sender == owner);
        require(_keepCRV <= 10_000);
        keepCRV = _keepCRV;
    }

    uint256 public harvestProfitMaxInUsdt = 25_000 * 1e6; // what profit do we need to harvest

    // Set the amount of CRV to be locked in Yearn's veCRV voter from each harvest.
    function setHarvestProfitMaxInUsdt(uint256 _harvestProfitMaxInUsdt)
        external
    {
        require(msg.sender == owner || msg.sender == sms);
        harvestProfitMaxInUsdt = _harvestProfitMaxInUsdt;
    }

    uint256 public performanceFee = 1_000;

    function setPerformanceFee(uint256 _performanceFee) external {
        require(msg.sender == owner);
        require(_performanceFee <= 5_000);
        performanceFee = _performanceFee;
    }

    uint256 public managementFee = 0;

    function setManagementFee(uint256 _managementFee) external {
        require(msg.sender == owner);
        require(_managementFee <= 1_000);
        managementFee = _managementFee;
    }

    ///////////////////////////////////
    //
    // Functions
    //
    ////////////////////////////////////

    constructor(address _registry, address _convexStratImplementation) public {
        registry = Registry(_registry);
        convexStratImplementation = _convexStratImplementation;
    }

    function alreadyExistsFromGauge(address _gauge)
        public
        view
        returns (address)
    {
        address lptoken = ICurveGauge(_gauge).lp_token();
        return alreadyExistsFromToken(lptoken);
    }

    function alreadyExistsFromToken(address lptoken)
        public
        view
        returns (address)
    {
        if (!registry.isRegistered(lptoken)) {
            return address(0);
        }

        // check default vault followed by automated
        bytes memory data =
            abi.encodeWithSignature("latestVault(address)", lptoken);
        (bool success, ) = address(registry).staticcall(data);
        if (success) {
            return registry.latestVault(lptoken);
        } else {
            return registry.latestVault(lptoken, VaultType.AUTOMATED);
        }
    }

    //very annoying
    function getPid(address _gauge) public view returns (uint256 pid) {
        pid = type(uint256).max;

        if (!convexDeposit.gaugeMap(_gauge)) {
            return pid;
        }

        for (uint256 i = convexDeposit.poolLength(); i > 0; i--) {
            //we start at the end and work back for most recent
            (, , address gauge, , , ) = convexDeposit.poolInfo(i - 1);

            if (_gauge == gauge) {
                return i - 1;
            }
        }
    }

    // only permissioned users can deploy if there is already one endorsed
    function createNewCurveVaultsAndStrategies(
        address _gauge,
        bool _allowDuplicate
    ) external returns (address vault, address convexStrategy) {
        require(msg.sender == owner || msg.sender == sms);

        return _createNewCurveVaultsAndStrategies(_gauge, _allowDuplicate);
    }

    function createNewCurveVaultsAndStrategies(address _gauge)
        external
        returns (address vault, address convexStrategy)
    {
        return _createNewCurveVaultsAndStrategies(_gauge, false);
    }

    function _createNewCurveVaultsAndStrategies(
        address _gauge,
        bool _allowDuplicate
    ) internal returns (address vault, address convexStrategy) {
        if (!_allowDuplicate) {
            require(
                alreadyExistsFromGauge(_gauge) == address(0),
                "Vault already exists"
            );
        }
        address lptoken = ICurveGauge(_gauge).lp_token();

        //get convex pid. if no pid create one
        uint256 pid = getPid(_gauge);
        if (pid == type(uint256).max) {
            //when we add the new pool it will be added to the end of the pools in convexDeposit.
            pid = convexDeposit.poolLength();
            //add pool
            require(
                IPoolManager(convexPoolManager).addPool(_gauge),
                "Unable to add pool to Convex"
            );
        }

        //now we create the vault, endorses it as well
        vault = registry.newVault(
            lptoken,
            address(this),
            devms,
            treasury,
            "",
            "",
            0,
            VaultType.AUTOMATED
        );
        Vault v = Vault(vault);
        v.setManagement(sms);
        //set governance to owner who needs to accept before it is finalised. until then governance is this factory
        v.setGovernance(owner);
        v.setDepositLimit(depositLimit);

        if (v.managementFee() != managementFee) {
            v.setManagementFee(managementFee);
        }
        if (v.performanceFee() != performanceFee) {
            v.setPerformanceFee(performanceFee);
        }

        Vault(vault).setDepositLimit(depositLimit);

        //now we create the convex strat
        convexStrategy = IStrategy(convexStratImplementation)
            .cloneStrategyConvex(
            vault,
            sms,
            rewardsStrat,
            keeper,
            pid,
            tradeFactory,
            harvestProfitMaxInUsdt
        );
        IStrategy(convexStrategy).setHealthCheck(healthCheck);

        Vault(vault).addStrategy(
            convexStrategy,
            10_000,
            0,
            type(uint256).max,
            0
        );

        emit NewAutomatedCurveVault(
            lptoken,
            _gauge,
            vault,
            convexStrategy,
            block.timestamp
        );
    }
}
