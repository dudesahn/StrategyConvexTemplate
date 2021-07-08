import brownie
from brownie import Contract
from brownie import config

# test passes as of 21-05-20
def test_setters(gov, token, vault, new_address, chain, strategy, strategist, dudesahn):

    strategy.setKeepCRV(2000, {"from": strategist})
    assert strategy.keepCRV() > 1000

    strategy.setOptimal(2, {"from": dudesahn})
    assert strategy.optimal() == 2
