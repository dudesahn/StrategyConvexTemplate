// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

import "@openzeppelin/contracts/math/SafeMath.sol";
import "@openzeppelin/contracts/utils/Address.sol";

interface IRocketPool {
    function getBalance() external view returns (uint256);

    function getMaximumDepositPoolSize() external view returns (uint256);

    function getAddress(bytes32 _key) external view returns (address);

    function getUint(bytes32 _key) external view returns (uint256);

    function getDepositEnabled() external view returns (bool);

    function getMinimumDeposit() external view returns (uint256);
}

contract RocketPoolHelper {
    using SafeMath for uint256;
    using Address for address;

    IRocketPool internal constant rocketStorage =
        IRocketPool(0x1d8f8f00cfa6758d7bE78336684788Fb0ee0Fa46);

    /// @notice
    /// Check if a user is able to transfer their rETH. Following deposit,
    /// rocketpool has an adjustable freeze period (in blocks). At deployment
    /// this is ~24 hours, but this will likely go down over time.
    ///
    /// @param _user The address of the user to check
    /// @return True if the user is free to move any rETH they have
    function isRethFree(address _user) public view returns (bool) {
        // Check which block the user's last deposit was
        bytes32 key = keccak256(abi.encodePacked("user.deposit.block", _user));
        uint256 lastDepositBlock = rocketStorage.getUint(key);
        if (lastDepositBlock > 0) {
            // Ensure enough blocks have passed
            uint256 depositDelay =
                rocketStorage.getUint(
                    keccak256(
                        abi.encodePacked(
                            keccak256("dao.protocol.setting.network"),
                            "network.reth.deposit.delay"
                        )
                    )
                );
            uint256 blocksPassed = block.number.sub(lastDepositBlock);
            return blocksPassed > depositDelay;
        } else {
            return true; // true if we haven't deposited
        }
    }

    /// @notice
    /// Check to see if the rETH deposit pool can accept a specified amount
    /// of ether based on deposits being enabled, minimum deposit size, and
    /// free space remaining in the deposit pool.
    ///
    /// @param _ethAmount The amount of ether to deposit
    /// @return True if we can deposit the input amount of ether
    function rEthCanAcceptDeposit(uint256 _ethAmount)
        public
        view
        returns (bool)
    {
        IRocketPool rocketDAOProtocolSettingsDeposit =
            IRocketPool(getRPLContract("rocketDAOProtocolSettingsDeposit"));

        // first check that deposits are enabled
        if (!rocketDAOProtocolSettingsDeposit.getDepositEnabled()) {
            return false;
        }

        // now check that we have enough free space for our deposit
        uint256 freeSpace = getPoolFreeSpace();

        return freeSpace > _ethAmount;
    }

    /// @notice The current minimum deposit size into the rETH deposit pool.
    function getMinimumDepositSize() public view returns (uint256) {
        // pull our contract address
        IRocketPool rocketDAOProtocolSettingsDeposit =
            IRocketPool(getRPLContract("rocketDAOProtocolSettingsDeposit"));

        return rocketDAOProtocolSettingsDeposit.getMinimumDeposit();
    }

    /// @notice The current free space in the rETH deposit pool.
    function getPoolFreeSpace() public view returns (uint256) {
        // pull our contract addresses
        IRocketPool rocketDAOProtocolSettingsDeposit =
            IRocketPool(getRPLContract("rocketDAOProtocolSettingsDeposit"));
        IRocketPool rocketDepositPool =
            IRocketPool(getRPLContract("rocketDepositPool"));

        // now check the difference between max and current size
        uint256 maxDeposit =
            rocketDAOProtocolSettingsDeposit.getMaximumDepositPoolSize().sub(
                rocketDepositPool.getBalance()
            );

        return maxDeposit;
    }

    /// @notice The current rETH pool deposit address.
    function getRocketDepositPoolAddress() public view returns (address) {
        return getRPLContract("rocketDepositPool");
    }

    /// @notice The current rETH pool deposit address.
    function getrocketDAOProtocolSettingsNetwork()
        public
        view
        returns (address)
    {
        return getRPLContract("rocketDAOProtocolSettingsNetwork");
    }

    function getRPLContract(string memory _contractName)
        public
        view
        returns (address)
    {
        return
            rocketStorage.getAddress(
                keccak256(abi.encodePacked("contract.address", _contractName))
            );
    }
}
