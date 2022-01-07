// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

import "./StrategyConvexFactoryClonable.sol";

interface Registry{
    function newExperimentalVault(address token, address governance, address guardian, address rewards, string memory name, string memory symbol) external returns (address);
}

interface Vault{
    
    function setGovernance(address) external;
    function addStrategy(address, uint, uint, uint, uint) external;
}

contract CurveGlobal{

    address owner = 0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52;
    Registry public registry = Registry(address(0x50c1a2eA0a861A967D9d0FFE2AE4012c2E053804));
    IConvexDeposit public convexDeposit = IConvexDeposit(0xF403C135812408BFbE8713b5A23a04b3D48AAE31);
    address public sms = address(0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7);
    address public ychad = address(0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52);
    address public devms = address(0x846e211e8ba920B353FB717631C015cf04061Cc9);
    address public treasury = address(0x93A62dA5a14C80f265DAbC077fCEE437B1a0Efde);
    address public keeper = address(0x736D7e3c5a6CB2CE3B764300140ABF476F6CFCCF);
    address public rewardsStrat = address(0xc491599b9A20c3A2F0A85697Ee6D9434EFa9f503);
    address public healthCheck = address(0xDDCea799fF1699e98EDF118e0629A974Df7DF012);
    address public tradeFactory = address(0xBf26Ff7C7367ee7075443c4F95dEeeE77432614d);

    address public stratImplementation;


    uint256 public keepCRV = 1000; // the percentage of CRV we re-lock for boost (in basis points).Default is 10%.
    uint256 public performanceFee = 1000;

    function initialise(address _stratImplementation) public{
        require(stratImplementation == address(0));
        stratImplementation = _stratImplementation;
    }

    // Set the amount of CRV to be locked in Yearn's veCRV voter from each harvest. 
    function setKeepCRV(uint256 _keepCRV) external {
        require(msg.sender == owner);
        require(_keepCRV <= 10_000);
        keepCRV = _keepCRV;
    }

    function setPerfFee(uint256 _perf) external {
        require(msg.sender == owner);
        require(_perf <= 10_000);
        performanceFee = _perf;
    }

    function setOwner(address newOwner) external{
        require(msg.sender == owner);
        owner = newOwner;
    }

    function createNewCurveVaultAndStrat(uint256 _pid) external returns (address vault, address strat){
            
        (address lptoken, , , , , ) = convexDeposit.poolInfo(_pid);

        vault = registry.newExperimentalVault(lptoken, address(this), devms, treasury, "", "");
        Vault(vault).setGovernance(sms);
        
        strat = StrategyConvexFactoryClonable(stratImplementation).cloneStrategyConvex(vault, sms, rewardsStrat, keeper,address(this), _pid, tradeFactory);

        StrategyConvexFactoryClonable(strat).setHealthCheck(healthCheck);

        Vault(vault).addStrategy(strat, 10_000, 0, type(uint256).max, performanceFee);
    }



    
}