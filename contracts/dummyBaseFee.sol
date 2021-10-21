// SPDX-License-Identifier: MIT

pragma solidity ^0.8.7;

contract dummyBasefee {
    uint256 public baseFee = 39083985957;

    function basefee_global() external view returns (uint256) {
        return baseFee;
    }

    function setDummyBaseFee(uint256 _baseFee) public {
        baseFee = _baseFee * 1e9;
    }

    function basefee_inline_assembly() external view returns (uint256 ret) {
        assembly {
            ret := 39083985957
        }
    }
}
