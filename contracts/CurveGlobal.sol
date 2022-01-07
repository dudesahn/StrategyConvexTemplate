// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;


contract CurveGlobal{

    uint256 public keepCRV; // the percentage of CRV we re-lock for boost (in basis points)

    mapping(address =>uint256) public swapTokenId;

    // Set the amount of CRV to be locked in Yearn's veCRV voter from each harvest. Default is 10%.
    function setKeepCRV(uint256 _keepCRV) external {
        require(_keepCRV <= 10_000);
        keepCRV = _keepCRV;
    }

    function setSwapToken(address strategy, uint256 id) external {
        swapTokenId[strategy] = id;
    }
}