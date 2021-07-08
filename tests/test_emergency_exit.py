import brownie
from brownie import Contract
from brownie import config

# test passes as of 21-05-20
def test_emergency_exit(
    gov,
    token,
    vault,
    dudesahn,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    strategyProxy,
    gaugeIB,
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(100000e18, {"from": whale})
    strategy.harvest({"from": dudesahn})

    # simulate a day of earnings
    chain.sleep(86400)
    chain.mine(1)

    # confirm that we will set emergency and exit, then confirm that the strategy has no funds
    strategy.setEmergencyExit({"from": gov})
    strategy.harvest({"from": dudesahn})
    assert strategy.estimatedTotalAssets() == 0
    assert strategyProxy.balanceOf(gaugeIB) == 0

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) > startingWhale


def test_emergency_shutdown_from_vault(
    gov, token, vault, whale, strategy, chain, dudesahn, strategyProxy, gaugeIB
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(100000e18, {"from": whale})
    strategy.harvest({"from": dudesahn})

    # simulate a day of earnings
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": dudesahn})

    # simulate a day of earnings
    chain.sleep(86400)
    chain.mine(1)

    # set emergency and exit, then confirm that the strategy has no funds
    vault.setEmergencyShutdown(True, {"from": gov})
    strategy.harvest({"from": gov})
    assert strategy.estimatedTotalAssets() == 0

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale
