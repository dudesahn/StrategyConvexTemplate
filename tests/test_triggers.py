import brownie
from brownie import Contract
from brownie import config
import math
import pytest


@pytest.mark.no_call_coverage
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
    # inactive strategy (0 DR and 0 assets) shouldn't be touched by keepers
    gasOracle.setMaxAcceptableBaseFee(10000 * 1e9, {"from": strategist_ms})
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False
    vault.updateStrategyDebtRatio(strategy, 10000, {"from": gov})

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

    # harvest should trigger false; hasn't been long enough since tend
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.sleep(1)
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    # harvest should trigger true, we've waited since our tend and we have tended since our last harvest
    chain.sleep(361)
    chain.mine(1)
    print("Tend timestamp:", strategy.lastTendTime())
    print("Last report:", vault.strategies(strategy)["lastReport"])
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # harvest should trigger false, we harvested more recently than tended
    strategy.harvest({"from": gov})
    chain.sleep(1)
    chain.mine(1)
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False

    # test our manual harvest trigger
    strategy.setForceTriggerOnce(False, True, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # manual harvest shouldn't trigger if manual tend is also triggered
    strategy.setForceTriggerOnce(True, False, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False
    strategy.setForceTriggerOnce(False, False, {"from": gov})

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale

    # harvest should trigger false due to high gas price
    gasOracle.setMaxAcceptableBaseFee(1 * 1e9, {"from": strategist_ms})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False


@pytest.mark.no_call_coverage
def test_tend_triggers(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    amount,
    sToken,
    accounts,
    strategist_ms,
    gasOracle,
):
    # inactive strategy (0 DR and 0 assets) shouldn't be touched by keepers
    gasOracle.setMaxAcceptableBaseFee(10000 * 1e9, {"from": strategist_ms})
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be false.", tx)
    assert tx == False
    vault.updateStrategyDebtRatio(strategy, 10000, {"from": gov})

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

    # turn off and then back on our markets
    _target = sToken.target()
    target = Contract(_target)
    currencyKey = [target.currencyKey()]
    systemStatus = Contract("0x1c86B3CDF2a60Ae3a574f7f71d44E2C50BDdB87E")
    synthGod = accounts.at("0xC105Ea57Eb434Fbe44690d7Dec2702e4a2FBFCf7", force=True)
    systemStatus.suspendSynthsExchange(currencyKey, 2, {"from": synthGod})
    chain.sleep(1)
    chain.mine(1)
    assert strategy.isMarketClosed() == True

    # tend should be false if markets are off
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be False.", tx)
    assert tx == False
    systemStatus.resumeSynthsExchange(currencyKey, {"from": synthGod})

    # simulate an hour of earnings
    chain.sleep(3600)
    chain.mine(1)
    assert strategy.isMarketClosed() == False
    assert strategy.claimableProfitInUsdt() < strategy.harvestProfitMin()

    # tend should trigger false; hasn't been long enough
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be False.", tx)
    assert tx == False

    # turn on our check for earmark. Shouldn't block anything. Turn off earmark check after.
    strategy.setHarvestTriggerParams(1000000e6, 1000000e6, 1e30, True, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    assert strategy.needsEarmarkReward() == False
    if strategy.needsEarmarkReward():
        print("\nShould we tend? Should be no since we need to earmark.", tx)
        assert tx == False
    else:
        print("\nShould we tend? Should be false since it was already false.", tx)
        assert tx == False
    strategy.setHarvestTriggerParams(1000000e6, 1000000e6, 1e30, False, {"from": gov})

    # simulate one hour of earnings
    chain.sleep(3600)
    chain.mine(1)

    # tend should trigger false
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be false.", tx)
    assert tx == False

    # simulate 1 hour of earnings and update our maxDelay to be 1 hour. don't want our oracle to get stale!
    chain.sleep(3600)
    chain.mine(1)
    strategy.setMaxReportDelay(3600)

    # tend should trigger true since enough time has elapsed
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be true.", tx)
    assert tx == True

    # tend should still trigger true, even after a harvest
    strategy.harvest({"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be true.", tx)
    assert tx == True

    # update our minProfit so our harvest triggers true
    strategy.setHarvestTriggerParams(1e6, 1000000e6, 1e30, False, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # update our maxProfit so harvest triggers true
    strategy.setHarvestTriggerParams(1000000e6, 1e6, 1e30, False, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True
    # increase this so it doesn't trigger stuff below
    strategy.setHarvestTriggerParams(1000000e6, 1000000e6, 1e30, False, {"from": gov})

    # earmark should be false now (it's been too long), turn it off after
    chain.sleep(86400 * 15)
    strategy.setHarvestTriggerParams(90000e6, 150000e6, 1e24, True, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    assert strategy.needsEarmarkReward() == True
    if strategy.needsEarmarkReward():
        print("\nShould we tend? Should be no since we need to earmark.", tx)
        assert tx == False
    else:
        print("\nShould we tend? Should be false since it was already false.", tx)
        assert tx == False
    strategy.setHarvestTriggerParams(90000e6, 150000e6, 1e24, False, {"from": gov})

    # tend should trigger false due to high gas price
    gasOracle.setMaxAcceptableBaseFee(1, {"from": strategist_ms})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be false.", tx)
    assert tx == False
