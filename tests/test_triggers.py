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
    gasOracle,
    strategist_ms,
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
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
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    # turn on our check for earmark. Shouldn't block anything. Turn off earmark check after.
    strategy.setCheckEarmark(True, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    if strategy.needsEarmarkReward():
        print("\nShould we harvest? Should be no since we need to earmark.", tx)
        assert tx == False
    else:
        print("\nShould we harvest? Should be false since it was already false.", tx)
        assert tx == False
    strategy.setCheckEarmark(False, {"from": gov})

    # update our minProfit so our harvest triggers true
    strategy.setHarvestProfitNeeded(1e6, 1000000e6, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # update our maxProfit so harvest triggers true
    strategy.setHarvestProfitNeeded(1000000e6, 1e6, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # earmark should be false now (it's been too long), turn it off after
    chain.sleep(86400 * 21)
    strategy.setCheckEarmark(True, {"from": gov})
    assert strategy.needsEarmarkReward() == True
    tx = strategy.harvestTrigger(0, {"from": gov})
    print(
        "\nShould we harvest? Should be false, even though it was true before because of earmark.",
        tx,
    )
    assert tx == False
    strategy.setCheckEarmark(False, {"from": gov})

    # harvest, wait
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale

    # harvest should trigger false due to high gas price
    gasOracle.setMaxAcceptableBaseFee(1 * 1e9, {"from": strategist_ms})
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
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)
    starting_assets = vault.totalAssets()
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    strategy.setMinReportDelay(100, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    chain.sleep(200)
