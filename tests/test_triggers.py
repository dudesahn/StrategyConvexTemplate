import brownie
from brownie import Contract
from brownie import config
import math

# test our harvest triggers
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
    is_slippery,
    no_profit,
    is_convex,
    sleep_time,
    rewardsContract,
):

    # convex inactive strategy (0 DR and 0 assets) shouldn't be touched by keepers
    gasOracle.setMaxAcceptableBaseFee(10000 * 1e9, {"from": strategist_ms})
    currentDebtRatio = vault.strategies(strategy)["debtRatio"]
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    if is_convex:
        strategy.harvest({"from": gov})
        tx = strategy.harvestTrigger(0, {"from": gov})
        print("\nShould we harvest? Should be false.", tx)
        assert tx == False
    vault.updateStrategyDebtRatio(strategy, currentDebtRatio, {"from": gov})

    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)
    starting_assets = vault.totalAssets()

    if is_convex:
        # update our min credit so harvest triggers true
        strategy.setCreditThreshold(1, {"from": gov})
        tx = strategy.harvestTrigger(0, {"from": gov})
        print("\nShould we harvest? Should be true.", tx)
        assert tx == True
        strategy.setCreditThreshold(1e24, {"from": gov})

        # harvest the credit
        chain.sleep(1)
        strategy.harvest({"from": gov})
        chain.sleep(1)
        chain.mine(1)

        # should trigger false, nothing is ready yet
        tx = strategy.harvestTrigger(0, {"from": gov})
        print("\nShould we harvest? Should be false.", tx)
        assert tx == False
    else:
        # harvest the credit
        chain.sleep(1)
        strategy.harvest({"from": gov})
        chain.sleep(1)
        chain.mine(1)

    # simulate earnings
    chain.sleep(sleep_time)
    chain.mine(1)

    # set our max delay to 1 day so we trigger true, then set it back to 21 days
    strategy.setMaxReportDelay(sleep_time - 1)
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be True.", tx)
    assert tx == True
    strategy.setMaxReportDelay(86400 * 21)

    # only convex has claimable profit readouts
    if is_convex:
        strategy.setHarvestTriggerParams(90000e6, 150000e6, {"from": gov})
        tx = strategy.harvestTrigger(0, {"from": gov})
        assert tx == False

        if not (is_slippery and no_profit):
            # update our minProfit so our harvest triggers true, also need to checkpoint
            rewardsContract.user_checkpoint(strategy.address, {"from": gov})
            strategy.setHarvestTriggerParams(1, 1000000e6, {"from": gov})
            tx = strategy.harvestTrigger(0, {"from": gov})
            print("\nShould we harvest? Should be true.", tx)
            assert tx == True

            # update our maxProfit so harvest triggers true
            strategy.setHarvestTriggerParams(1000000e6, 1, {"from": gov})
            tx = strategy.harvestTrigger(0, {"from": gov})
            print("\nShould we harvest? Should be true.", tx)
            assert tx == True

        # return back to normal
        strategy.setHarvestTriggerParams(90000e6, 150000e6, {"from": gov})

    else:  # curve uses minDelay as well
        strategy.setMinReportDelay(sleep_time - 1)
        tx = strategy.harvestTrigger(0, {"from": gov})
        print("\nShould we harvest? Should be True.", tx)
        assert tx == True

    # harvest, wait
    chain.sleep(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest info:", tx.events["Harvested"])
    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest should trigger false due to high gas price
    gasOracle.setMaxAcceptableBaseFee(1 * 1e9, {"from": strategist_ms})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False

    # withdraw and confirm we made money, or at least that we have about the same
    vault.withdraw({"from": whale})
    if is_slippery and no_profit:
        assert (
            math.isclose(token.balanceOf(whale), startingWhale, abs_tol=10)
            or token.balanceOf(whale) >= startingWhale
        )
    else:
        assert token.balanceOf(whale) >= startingWhale
