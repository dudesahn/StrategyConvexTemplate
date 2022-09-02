import pytest
from brownie import config, Wei, Contract, chain, accounts, StrategyConvexCrvCvxPairsClonable, Splitter, web3
import requests

def main():
    strategist = accounts.load('wavey')
    vault = Contract('0xe92AE2cF5b373c1713eB5855D4D3aF81D8a8aCAE')

    pid = 62
    pool = '0xAA5A67c256e27A5d80712c51971408db3370927D'
    strategy_name = 'StrategyConvexDOLA-U'
    s = Contract('')
    s
    # splitter = strategist.deploy(
    #     Splitter,
    #     publish_source=True
    # )
    
    # strategy = strategist.deploy(
    #     StrategyConvexCrvCvxPairsClonable,
    #     vault,
    #     # strategist,
    #     # '0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52',
    #     # '0x736D7e3c5a6CB2CE3B764300140ABF476F6CFCCF',
    #     '0x34a045499247B983d16a49A1b72D5b3b2e76e526', # SPLIT
    #     publish_source=True
    # )

    assert False

    StrategyConvex3CrvRewardsClonable.get_verification_info()
    source = StrategyConvex3CrvRewardsClonable._flattener.flattened_source
    print(source)
    f = open("/Users/wavey/Desktop/dolau.sol", 'w')
    f.write(source)
    # gov = accounts.at(web3.ens.resolve('ychad.eth'), force=True)
    # vault = Contract(strategy.vault(), owner=gov)
    # old = vault.withdrawalQueue(0)
    # vault.migrateStrategy(old, strategy)