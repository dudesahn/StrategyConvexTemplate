import brownie
from brownie import Contract
from brownie import config
import math


def test_harvest_triggers_reth(
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
    accounts,
):

    # change our optimal deposit asset
    strategy.setMintReth(True, {"from": gov})

    # inactive strategy (0 DR and 0 assets) shouldn't be touched by keepers
    gasOracle.setMaxAcceptableBaseFee(10000 * 1e9, {"from": strategist_ms})
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False
    vault.updateStrategyDebtRatio(strategy, 10000, {"from": gov})

    # adjust our waiting period to 1 block so we aren't miserable in testing
    networkSettings = Contract("0xc1B6057e8232fB509Fc60F9e9297e11E59D4A189")
    daoSetter = accounts.at("0x42EC642eAa86091059569d8De8aeccf7F2F9B1a2", force=True)
    path = "network.reth.deposit.delay"
    networkSettings.setSettingUint(path, 1, {"from": daoSetter})
    assert networkSettings.getRethDepositDelay() == 1
    chain.mine(1)

    # set our minimum deposit to 1 wei
    depositSettings = Contract("0x781693a15E1fA7c743A299f4F0242cdF5489A0D9")
    path = "deposit.minimum"
    depositSettings.setSettingUint(path, 1, {"from": daoSetter})

    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)
    starting_assets = vault.totalAssets()

    # should be true, we have credit
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # harvest our credit
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # simulate an hour of earnings
    chain.sleep(3600)
    chain.mine(1)

    # harvest should trigger false; hasn't been long enough since our tend for rETH to be movable
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.sleep(1)
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    # harvest should trigger true, we've waited long enough since our tend for our rETH to free up
    chain.mine(2)
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # harvest to reset our trigger
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # test our manual harvest trigger
    strategy.setForceTriggerOnce(False, True, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # manual harvest shouldn't trigger if manual tend is also triggered
    strategy.setForceTriggerOnce(True, True, {"from": gov})
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


def test_harvest_triggers_wsteth(
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
    accounts,
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
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)
    starting_assets = vault.totalAssets()

    # harvest should trigger true, we have a credit
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be True.", tx)
    assert tx == True

    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # harvest should trigger false; hasn't been long enough
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    # simulate an hour of earnings
    chain.sleep(3600)
    chain.mine(1)

    # turn on our check for earmark. Shouldn't block anything. Turn off earmark check after.
    strategy.setHarvestTriggerParams(1000000e6, 1000000e6, 1e30, True, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    assert strategy.needsEarmarkReward() == False
    if strategy.needsEarmarkReward():
        print("\nShould we harvest? Should be no since we need to earmark.", tx)
        assert tx == False
    else:
        print("\nShould we harvest? Should be false since it was already false.", tx)
        assert tx == False
    strategy.setHarvestTriggerParams(1000000e6, 1000000e6, 1e30, False, {"from": gov})

    # simulate one hour of earnings
    chain.sleep(3600)
    chain.mine(1)

    # harvest should trigger false
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False

    # test our manual harvest trigger
    strategy.setForceTriggerOnce(False, True, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # manual harvest shouldn't trigger if manual tend is also triggered
    strategy.setForceTriggerOnce(True, True, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False
    strategy.setForceTriggerOnce(False, False, {"from": gov})

    # simulate 1 hour of earnings and update our maxDelay to be 1 hour. don't want our oracle to get stale!
    chain.sleep(3600)
    chain.mine(1)
    strategy.setMaxReportDelay(3600)

    # harvest should trigger true since enough time has elapsed
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # update our minProfit so our harvest triggers true
    strategy.setHarvestTriggerParams(1e6, 1000000e6, 1e30, False, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # update our maxProfit so harvest triggers true
    strategy.setHarvestTriggerParams(1000000e6, 1e6, 1e30, False, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # increase this so it doesn't trigger stuff below
    strategy.setHarvestTriggerParams(1000000e6, 1000000e6, 1e30, False, {"from": gov})

    # earmark should be false now (it's been too long), turn it off after
    chain.sleep(86400 * 15)
    strategy.setHarvestTriggerParams(90000e6, 150000e6, 1e24, True, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    assert strategy.needsEarmarkReward() == True
    if strategy.needsEarmarkReward():
        print("\nShould we harvest? Should be no since we need to earmark.", tx)
        assert tx == False
    else:
        print("\nShould we harvest? Should be false since it was already false.", tx)
        assert tx == False
    strategy.setHarvestTriggerParams(90000e6, 150000e6, 1e24, False, {"from": gov})

    # harvest should trigger false due to high gas price
    gasOracle.setMaxAcceptableBaseFee(1 * 1e9, {"from": strategist_ms})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False


# this tests all of the various branches for our tend trigger function
def test_tend_triggers(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    amount,
    accounts,
    strategist_ms,
    gasOracle,
):

    # only tend if we're minting rETH
    strategy.setMintReth(True, {"from": gov})

    # inactive strategy (0 DR and 0 assets) shouldn't be touched by keepers
    gasOracle.setMaxAcceptableBaseFee(10000 * 1e9, {"from": strategist_ms})
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be false.", tx)
    assert tx == False
    vault.updateStrategyDebtRatio(strategy, 10000, {"from": gov})

    # adjust our waiting period to 1 block so we aren't miserable in testing
    networkSettings = Contract("0xc1B6057e8232fB509Fc60F9e9297e11E59D4A189")
    daoSetter = accounts.at("0x42EC642eAa86091059569d8De8aeccf7F2F9B1a2", force=True)
    path = "network.reth.deposit.delay"
    networkSettings.setSettingUint(path, 1, {"from": daoSetter})
    assert networkSettings.getRethDepositDelay() == 1
    chain.mine(1)

    # set our minimum deposit to 1 wei, again so we aren't miserable in testing
    depositSettings = Contract("0x781693a15E1fA7c743A299f4F0242cdF5489A0D9")
    path = "deposit.minimum"
    depositSettings.setSettingUint(path, 1, {"from": daoSetter})

    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)
    starting_assets = vault.totalAssets()

    # harvest
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # simulate an hour of earnings
    chain.sleep(3600)
    chain.mine(1)

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

    # test our manual trigger
    strategy.setForceTriggerOnce(True, True, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be True.", tx)
    assert tx == True

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

    # update our minProfit so our tend triggers true
    strategy.setHarvestTriggerParams(1e6, 1000000e6, 1e30, False, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be true.", tx)
    assert tx == True

    # update our maxProfit so tend triggers true
    strategy.setHarvestTriggerParams(1000000e6, 1e6, 1e30, False, {"from": gov})
    tx = strategy.tendTrigger(0, {"from": gov})
    print("\nShould we tend? Should be true.", tx)
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
