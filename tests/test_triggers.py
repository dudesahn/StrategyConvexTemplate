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
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # simulate a day of earnings
    chain.sleep(86400)
    chain.mine(1)

    # harvest should trigger false
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    # simulate eight days of earnings to get beyond our min Delay, turn off health check since it will be a big harvest
    strategy.setDoHealthCheck(False, {"from": gov})
    chain.sleep(86400 * 8)
    chain.mine(1)

    # harvest should trigger true
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    assert tx == True

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400 * 9)
    chain.mine(1)
    strategy.setMaxReportDelay(1e18, {"from": gov})
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale

    # harvest should trigger false due to high gas price
    dummy_gas_oracle.setDummyBaseFee(400)
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
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
    strategy.harvest({"from": gov})
    chain.sleep(1)

    strategy.setMinReportDelay(100, {"from": gov})
    strategy.setGasOracle(dummy_gas_oracle, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    chain.sleep(200)
