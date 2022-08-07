import math
import brownie
from brownie import Contract
from brownie import config

# test that emergency exit works properly
def test_split(
    gov,
    token,
    vault,
    whale,
    strategy,
    chain,
    splitter,
    booster,
    rewardsContract,
    pid,
    crv,
    convexToken,
):
    splitter.setStrategy(strategy, {'from':gov})
    vault.deposit({'from':whale})
    strategy.harvest({'from':gov})
    chain.sleep(24*60*60*10)
    tx = strategy.harvest({'from':gov})
    print(f'Stats: {tx.events["Stats"]}')
    print(f'Split: {tx.events["Split"]}')
    assert convexToken.balanceOf(strategy) == 0
    chain.sleep(60*60)
    chain.mine()
    tx = splitter.claimAndSplit({'from':gov})
    assert False