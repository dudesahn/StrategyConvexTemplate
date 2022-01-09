import brownie
from brownie import Contract
import time
import web3
from eth_abi import encode_single, encode_abi
from eth_abi.packed import encode_single_packed, encode_abi_packed
from brownie.convert import to_bytes
import eth_utils
import numpy as np


def test_yswap_basics():
    transaction = np.array([["uint8", "uint8"], [1, 2]])
    two = np.array([["uint8", "uint8"], [4, "3"]])
    conc = np.concatenate((transaction, two), axis=1)
    print(conc[1])
    # print(eth_utils.to_hex(transaction))
