import brownie
from brownie import Contract
from brownie import config
import math


def test_triggers(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    amount,
    dummy_gas_oracle,
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)
    starting_assets = vault.totalAssets()
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.sleep(361)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # simulate an hour of earnings
    chain.sleep(3600)
    chain.mine(1)

    # harvest should trigger false; hasn't been long enough
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    # update our maxDelay to be 1 hour. don't want our oracle to get stale!
    strategy.setMaxReportDelay(3600)

    # harvest should trigger false; hasn't been long enough since tend
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.sleep(1)
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    # harvest should trigger true, we've waited since our tend and it's been past our maxDelay
    chain.sleep(361)
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale

    # harvest should trigger false due to high gas price
    dummy_gas_oracle.setDummyBaseFee(400)
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False


def test_less_useful_triggers(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    amount,
    dummy_gas_oracle,
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)
    starting_assets = vault.totalAssets()
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    strategy.setMinReportDelay(100, {"from": gov})
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    chain.sleep(200)


def test_tend_triggers(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    amount,
    dummy_gas_oracle,
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)
    starting_assets = vault.totalAssets()
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # simulate an hour of earnings
    chain.sleep(3600)
    chain.mine(1)

    # tend should trigger false
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be false.", tx)
    assert tx == False

    # simulate one hour of earnings
    chain.sleep(3600)
    chain.mine(1)

    # tend should trigger false
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be false.", tx)
    assert tx == False

    # simulate 1 hour of earnings and update our maxDelay to be 1 hour. don't want our oracle to get stale!
    chain.sleep(3600)
    chain.mine(1)
    strategy.setMaxReportDelay(3600)

    # tend should trigger true since enough time has elapsed
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be true.", tx)
    assert tx == True

    # tend should still trigger true, even after a harvest
    strategy.harvest({"from": gov})
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be true.", tx)
    assert tx == True

    # tend should trigger false due to high gas price
    dummy_gas_oracle.setDummyBaseFee(400)
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be false.", tx)
    assert tx == False

    # claim our earnings
    chain.sleep(1)
    chain.sleep(361)
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale

    # harvest should trigger false due to high gas price
    dummy_gas_oracle.setDummyBaseFee(400)
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False
