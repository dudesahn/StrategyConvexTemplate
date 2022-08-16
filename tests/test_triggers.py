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
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)
    starting_assets = vault.totalAssets()

    if is_convex:
        # update our min credit so harvest triggers true
        strategy.setHarvestTriggerParams(1000000e6, 1000000e6, 1, False, {"from": gov})
        tx = strategy.harvestTrigger(0, {"from": gov})
        print("\nShould we harvest? Should be true.", tx)
        assert tx == True
        strategy.setHarvestTriggerParams(90000e6, 150000e6, 1e24, False, {"from": gov})

        # harvest the credit
        chain.sleep(1)
        strategy.harvest({"from": gov})
        chain.sleep(1)

        # should trigger false, nothing is ready yet
        tx = strategy.harvestTrigger(0, {"from": gov})
        print("\nShould we harvest? Should be false.", tx)
        assert tx == False

    # simulate earnings
    chain.sleep(sleep_time)
    chain.mine(1)

    # set our max delay to 1 day so we trigger true, then set it back to 21 days
    strategy.setMaxReportDelay(sleep_time - 1)
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be True.", tx)
    assert tx == True
    strategy.setMaxReportDelay(86400 * 21)

    # only convex does this mess with earmarking
    if is_convex:
        # turn on our check for earmark. Shouldn't block anything. Turn off earmark check after.
        strategy.setHarvestTriggerParams(90000e6, 150000e6, 1e24, True, {"from": gov})
        tx = strategy.harvestTrigger(0, {"from": gov})
        if strategy.needsEarmarkReward():
            print("\nShould we harvest? Should be no since we need to earmark.", tx)
            assert tx == False
        else:
            print(
                "\nShould we harvest? Should be false since it was already false and we don't need to earmark.",
                tx,
            )
            assert tx == False
        strategy.setHarvestTriggerParams(90000e6, 150000e6, 1e24, False, {"from": gov})

        if not (is_slippery and no_profit):
            # update our minProfit so our harvest triggers true
            strategy.setHarvestTriggerParams(1e6, 1000000e6, 1e24, False, {"from": gov})
            tx = strategy.harvestTrigger(0, {"from": gov})
            print("\nShould we harvest? Should be true.", tx)
            assert tx == True

            # update our maxProfit so harvest triggers true
            strategy.setHarvestTriggerParams(1000000e6, 1e6, 1e24, False, {"from": gov})
            tx = strategy.harvestTrigger(0, {"from": gov})
            print("\nShould we harvest? Should be true.", tx)
            assert tx == True

        # earmark should be false now (it's been too long), turn it off after
        chain.sleep(86400 * 21)
        strategy.setHarvestTriggerParams(90000e6, 150000e6, 1e24, True, {"from": gov})
        assert strategy.needsEarmarkReward() == True
        tx = strategy.harvestTrigger(0, {"from": gov})
        print(
            "\nShould we harvest? Should be false, even though it was true before because of earmark.",
            tx,
        )
        assert tx == False
        strategy.setHarvestTriggerParams(90000e6, 150000e6, 1e24, False, {"from": gov})
    else:  # curve uses minDelay as well
        strategy.setMinReportDelay(sleep_time - 1)
        tx = strategy.harvestTrigger(0, {"from": gov})
        print("\nShould we harvest? Should be True.", tx)
        assert tx == True

    # harvest, wait
    chain.sleep(1)
    strategy.harvest({"from": gov})
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
