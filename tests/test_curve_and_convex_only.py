import brownie
from brownie import Wei, accounts, Contract, config, ZERO_ADDRESS
import pytest
import math

# set our rewards to nothing, then turn them back on
def test_update_to_zero_then_back(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    keeper,
    rewards,
    chain,
    contract_name,
    voter,
    proxy,
    pid,
    amount,
    pool,
    strategy_name,
    gauge,
    has_rewards,
    convexToken,
    is_convex,
    rewards_token,
    sleep_time,
    vault_address,
    no_profit,
    is_slippery,
    rewards_template,
    sushi_router,
    rewards_amount,
    rewards_whale,
):
    # skip this test if we don't use rewards in this template
    if not rewards_template:
        return

    if is_convex:
        newStrategy = strategist.deploy(
            contract_name,
            vault,
            pid,
            pool,
            strategy_name,
        )
        print("\nConvex strategy")
    else:
        newStrategy = strategist.deploy(
            contract_name,
            vault,
            gauge,
            pool,
            strategy_name,
        )

    # revoke and send all funds back to vault
    startingDebtRatio = vault.strategies(strategy)["debtRatio"]
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})

    # attach our new strategy and approve it on the proxy
    vault.addStrategy(
        newStrategy, startingDebtRatio, 0, 2 ** 256 - 1, 1_000, {"from": gov}
    )

    # if a curve strat, whitelist on our strategy proxy
    if not is_convex:
        proxy.approveStrategy(strategy.gauge(), newStrategy, {"from": gov})

    if vault_address == ZERO_ADDRESS:
        assert vault.withdrawalQueue(1) == newStrategy
    else:
        assert vault.withdrawalQueue(2) == newStrategy

    assert vault.strategies(newStrategy)["debtRatio"] == startingDebtRatio
    assert vault.strategies(strategy)["debtRatio"] == 0

    # setup our rewards on our new stategy
    if is_convex:
        newStrategy.updateRewards(True, 0, {"from": gov})
    else:
        newStrategy.updateRewards(True, rewards_token, {"from": gov})

    ## deposit to the vault after approving; this is basically just our simple_harvest test
    before_pps = vault.pricePerShare()
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    # harvest, store asset amount
    chain.sleep(1)
    tx = newStrategy.harvest({"from": gov})
    chain.sleep(1)
    old_assets_dai = vault.totalAssets()
    assert old_assets_dai > 0
    assert token.balanceOf(newStrategy) == 0
    assert newStrategy.estimatedTotalAssets() > 0

    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest after a day, store new asset amount
    tx = newStrategy.harvest({"from": gov})
    rewards_on_profit = tx.events["Harvested"]["profit"]
    chain.sleep(1)
    new_assets_dai = vault.totalAssets()
    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets_dai >= old_assets_dai

    # Display estimated APR
    print(
        "\nEstimated APR (Rewards On): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * (86400 / sleep_time)))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # check what we have
    assert rewards_token.address == newStrategy.rewardsToken()
    assert newStrategy.hasRewards() == True
    assert rewards_token.allowance(newStrategy, sushi_router) > 0

    # turn off our rewards
    if is_convex:
        newStrategy.updateRewards(False, 0, {"from": gov})
    else:
        newStrategy.updateRewards(False, rewards_token, {"from": gov})

    assert newStrategy.rewardsToken() == ZERO_ADDRESS
    assert newStrategy.hasRewards() == False
    if (
        has_rewards
    ):  # if we have a separate reward token (not CVX) check that our allowance is zero
        assert rewards_token.allowance(newStrategy, sushi_router) == 0

    # track our new pps and assets
    new_pps = vault.pricePerShare()
    old_assets_dai = vault.totalAssets()

    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest with our new rewards token attached
    tx = newStrategy.harvest({"from": gov})
    rewards_off_profit = tx.events["Harvested"]["profit"]
    chain.sleep(1)
    chain.mine(1)
    new_assets_dai = vault.totalAssets()

    # Display estimated APR
    print(
        "\nEstimated APR (Rewards Off): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * (86400 / sleep_time)))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # add our rewards token, harvest to take the profit from it. this should be extra high yield from this harvest
    if is_convex:
        newStrategy.updateRewards(True, 0, {"from": gov})
    else:
        newStrategy.updateRewards(True, rewards_token, {"from": gov})

    # assert that we set things up correctly
    assert newStrategy.rewardsToken() == rewards_token
    assert newStrategy.hasRewards() == True
    assert rewards_token.allowance(newStrategy, sushi_router) > 0

    # track our new pps and assets
    new_pps = vault.pricePerShare()
    old_assets_dai = vault.totalAssets()

    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest with our new rewards token attached
    newStrategy.setDoHealthCheck(False, {"from": gov})
    tx = newStrategy.harvest({"from": gov})
    rewards_back_on_profit = tx.events["Harvested"]["profit"]

    # confirm that we are selling our rewards token
    assert newStrategy.rewardsToken() == rewards_token
    assert newStrategy.hasRewards() == True
    assert rewards_token.balanceOf(newStrategy) == 0
    new_assets_dai = vault.totalAssets()

    # Display estimated APR
    print(
        "\nEstimated APR (Rewards Back On, extra rewards tokens): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * (86400 / sleep_time)))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # compare all of our various profit values if we have active rewards
    if has_rewards:
        assert rewards_back_on_profit > rewards_on_profit
        assert rewards_on_profit > rewards_off_profit
        print("Rewards token is accumulating as expected\n")

    # sleep so we free locked profit
    chain.sleep(sleep_time)
    chain.mine(1)

    # withdraw and confirm what happened
    vault.withdraw({"from": whale})

    if no_profit and is_slippery:
        assert math.isclose(token.balanceOf(whale), startingWhale, abs_tol=10)
        assert vault.pricePerShare() >= before_pps
        assert vault.pricePerShare() >= new_pps
    else:
        assert token.balanceOf(whale) >= startingWhale
        assert vault.pricePerShare() > before_pps
        assert vault.pricePerShare() > new_pps


# test updating from on, then off, and still off
def test_update_from_zero_to_off(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    keeper,
    rewards,
    chain,
    contract_name,
    voter,
    proxy,
    pid,
    amount,
    pool,
    strategy_name,
    gauge,
    convexToken,
    has_rewards,
    is_convex,
    rewards_token,
    sleep_time,
    vault_address,
    no_profit,
    is_slippery,
    rewards_template,
    sushi_router,
):
    # skip this test if we don't use rewards in this template
    if not rewards_template:
        return

    if is_convex:
        newStrategy = strategist.deploy(
            contract_name,
            vault,
            pid,
            pool,
            strategy_name,
        )
        print("\nConvex strategy")
    else:
        newStrategy = strategist.deploy(
            contract_name,
            vault,
            gauge,
            pool,
            strategy_name,
        )

    # revoke and send all funds back to vault
    startingDebtRatio = vault.strategies(strategy)["debtRatio"]
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})

    # attach our new strategy and approve it on the proxy
    vault.addStrategy(
        newStrategy, startingDebtRatio, 0, 2 ** 256 - 1, 1_000, {"from": gov}
    )

    # if a curve strat, whitelist on our strategy proxy
    if not is_convex:
        proxy.approveStrategy(strategy.gauge(), newStrategy, {"from": gov})

    if vault_address == ZERO_ADDRESS:
        assert vault.withdrawalQueue(1) == newStrategy
    else:
        assert vault.withdrawalQueue(2) == newStrategy

    assert vault.strategies(newStrategy)["debtRatio"] == startingDebtRatio
    assert vault.strategies(strategy)["debtRatio"] == 0

    # setup our rewards on our new stategy
    if is_convex:
        newStrategy.updateRewards(True, 0, {"from": gov})
    else:
        newStrategy.updateRewards(True, rewards_token, {"from": gov})

    ## deposit to the vault after approving; this is basically just our simple_harvest test
    before_pps = vault.pricePerShare()
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    # harvest, store asset amount
    chain.sleep(1)
    newStrategy.harvest({"from": gov})
    chain.sleep(1)
    old_assets_dai = vault.totalAssets()
    assert old_assets_dai > 0
    assert token.balanceOf(newStrategy) == 0
    assert newStrategy.estimatedTotalAssets() > 0

    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest after a day, store new asset amount
    tx = newStrategy.harvest({"from": gov})
    rewards_on_profit = tx.events["Harvested"]["profit"]
    chain.sleep(1)
    chain.mine(1)
    new_assets_dai = vault.totalAssets()
    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets_dai >= old_assets_dai

    # Display estimated APR
    print(
        "\nEstimated APR (Rewards On): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * (86400 / sleep_time)))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # check what we have
    assert rewards_token.address == newStrategy.rewardsToken()
    assert newStrategy.hasRewards() == True
    assert rewards_token.allowance(newStrategy, sushi_router) > 0

    # turn off our rewards
    # setup our rewards on our new stategy
    if is_convex:
        newStrategy.updateRewards(False, 0, {"from": gov})
    else:
        newStrategy.updateRewards(False, rewards_token, {"from": gov})
    assert newStrategy.rewardsToken() == ZERO_ADDRESS
    assert newStrategy.hasRewards() == False
    if (
        has_rewards
    ):  # if we have a separate reward token (not CVX) check that our allowance is zero
        assert rewards_token.allowance(newStrategy, sushi_router) == 0

    # track our new pps and assets
    new_pps = vault.pricePerShare()
    old_assets_dai = vault.totalAssets()

    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest with our new rewards token attached
    tx = newStrategy.harvest({"from": gov})
    rewards_off_profit = tx.events["Harvested"]["profit"]
    chain.sleep(1)
    chain.mine(1)
    new_assets_dai = vault.totalAssets()

    # Display estimated APR
    print(
        "\nEstimated APR (Rewards Off): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * (86400 / sleep_time)))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # try turning off our rewards again
    if is_convex:
        newStrategy.updateRewards(False, 0, {"from": gov})
    else:
        newStrategy.updateRewards(False, rewards_token, {"from": gov})
    assert newStrategy.rewardsToken() == ZERO_ADDRESS
    assert newStrategy.hasRewards() == False
    if (
        has_rewards
    ):  # if we have a separate reward token (not CVX) check that our allowance is zero
        assert rewards_token.allowance(newStrategy, sushi_router) == 0

    # track our new pps and assets
    old_assets_dai = vault.totalAssets()

    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest with our new rewards token attached
    tx = newStrategy.harvest({"from": gov})
    rewards_still_off_profit = tx.events["Harvested"]["profit"]
    chain.sleep(1)
    chain.mine(1)
    new_assets_dai = vault.totalAssets()

    # Display estimated APR
    print(
        "\nEstimated APR (Rewards Off Still): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * (86400 / sleep_time)))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # compare all of our various profit values if we have active rewards
    if has_rewards:
        assert math.isclose(rewards_still_off_profit, rewards_off_profit, abs_tol=1e18)
        assert rewards_on_profit > rewards_off_profit
        print("Rewards token performing as expected\n")

    chain.sleep(sleep_time)
    chain.mine(1)

    # withdraw and confirm what happened
    vault.withdraw({"from": whale})

    if no_profit and is_slippery:
        assert math.isclose(token.balanceOf(whale), startingWhale, abs_tol=10)
        assert vault.pricePerShare() >= before_pps
        assert vault.pricePerShare() >= new_pps
    else:
        assert token.balanceOf(whale) >= startingWhale
        assert vault.pricePerShare() > before_pps
        assert vault.pricePerShare() > new_pps


# test changing our rewards to something else
def test_change_rewards(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    keeper,
    rewards,
    chain,
    contract_name,
    voter,
    proxy,
    pid,
    amount,
    pool,
    strategy_name,
    gauge,
    is_convex,
    rewards_token,
    sleep_time,
    rewards_template,
):
    # skip this test if we don't use rewards in this template
    if not rewards_template:
        return

    if is_convex:
        newStrategy = strategist.deploy(
            contract_name,
            vault,
            pid,
            pool,
            strategy_name,
        )
        print("\nConvex strategy")
    else:
        newStrategy = strategist.deploy(
            contract_name,
            vault,
            gauge,
            pool,
            strategy_name,
        )

    # revoke and send all funds back to vault
    startingDebtRatio = vault.strategies(strategy)["debtRatio"]
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})

    # attach our new strategy and approve it on the proxy
    vault.addStrategy(
        newStrategy, startingDebtRatio, 0, 2 ** 256 - 1, 1_000, {"from": gov}
    )

    # if a curve strat, whitelist on our strategy proxy
    if not is_convex:
        proxy.approveStrategy(strategy.gauge(), newStrategy, {"from": gov})

    # setup our rewards on our new stategy
    if is_convex:
        newStrategy.updateRewards(True, 0, {"from": gov})
    else:
        newStrategy.updateRewards(True, rewards_token, {"from": gov})

    ## deposit to the vault after approving; this is basically just our simple_harvest test
    before_pps = vault.pricePerShare()
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    # harvest, store asset amount
    chain.sleep(1)
    tx = newStrategy.harvest({"from": gov})
    chain.sleep(1)
    chain.mine(1)
    old_assets_dai = vault.totalAssets()

    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest after a day, store new asset amount
    newStrategy.harvest({"from": gov})
    new_assets_dai = vault.totalAssets()
    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets_dai >= old_assets_dai

    # Display estimated APR
    print(
        "\nEstimated APR (Rewards On): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * (86400 / sleep_time)))
            / (newStrategy.estimatedTotalAssets())
        ),
    )


# basic rewards check
def test_check_rewards(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    keeper,
    rewards,
    chain,
    contract_name,
    voter,
    proxy,
    pid,
    amount,
    pool,
    strategy_name,
    gauge,
    has_rewards,
    convexToken,
    is_convex,
    sleep_time,
    rewards_template,
    rewards_whale,
    rewards_amount,
    rewards_token,
    test_donation,
    try_blocks,
):
    # skip this test if we don't use rewards in this template
    if not rewards_template:
        return

    # if we're supposed to have a rewards token, make sure it's not CVX
    if has_rewards:
        assert rewards_token.address == strategy.rewardsToken()
        print("\nThis is our rewards token:", rewards_token.name())
        assert convexToken != rewards_token
    else:
        assert ZERO_ADDRESS == strategy.rewardsToken()

    if test_donation:
        ## deposit to the vault after approving
        token.approve(vault, 2 ** 256 - 1, {"from": whale})
        vault.deposit(amount, {"from": whale})
        strategy.harvest({"from": gov})

        # setup our rewards if we need to
        if not has_rewards:
            if is_convex:
                strategy.updateRewards(True, 0, {"from": gov})
            else:
                strategy.updateRewards(True, rewards_token, {"from": gov})

        if not is_convex and try_blocks:
            # test our proxy, some old gauges use blocks instead of seconds. make sure we're earning!
            chain.mine(240)
            assert gauge.balanceOf(voter) > 0
            balance_1 = gauge.claimable_reward(voter)
            print("Earned balance:", balance_1)
            chain.sleep(1)
            chain.mine(240)
            chain.sleep(1)
            balance_2 = gauge.claimable_reward(voter)
            print("Earned balance:", balance_2)
            assert balance_2 > balance_1
            tx = strategy.harvest({"from": gov})
            chain.mine(240)
            chain.sleep(1)
            balance_3 = gauge.claimable_reward(voter)
            print("Earned balance:", balance_3)
            assert balance_3 > balance_2
            proxy.claimRewards(gauge, rewards_token, {"from": strategy})
            assert rewards_token.balanceOf(strategy) > 0

        chain.sleep(sleep_time)
        chain.mine(1)
        tx = strategy.harvest({"from": gov})
        normal_profits = tx.events["Harvested"]["profit"]
        print("Normal Profit:", normal_profits / 1e18)

        # check after our whale donates
        rewards_token.transfer(strategy, rewards_amount, {"from": rewards_whale})
        chain.sleep(sleep_time)
        chain.mine(1)
        strategy.setDoHealthCheck(False, {"from": gov})
        tx = strategy.harvest({"from": gov})
        rewards_profits = tx.events["Harvested"]["profit"]
        print("Rewards Profit:", rewards_profits / 1e18)
        assert rewards_profits > normal_profits


# this one tests if we don't have any CRV to send to voter or any left over after sending
def test_weird_amounts(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    voter,
    amount,
    is_convex,
    sleep_time,
):

    ## deposit to the vault after approving
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    strategy.harvest({"from": gov})

    # set our optimal to DAI
    strategy.setOptimal(0, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)

    # take 100% of our CRV to the voter
    if is_convex:
        strategy.setKeep(10000, 0, gov, {"from": gov})
    else:
        strategy.setKeepCRV(10000, {"from": gov})
    chain.sleep(1)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)

    # switch to USDC, want to not have any profit tho
    strategy.setOptimal(1, {"from": gov})
    strategy.harvest({"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)

    # switch to USDT, want to not have any profit tho
    strategy.setOptimal(2, {"from": gov})
    strategy.harvest({"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)

    # take 0% of our CRV to the voter
    if is_convex:
        strategy.setKeep(0, 0, gov, {"from": gov})
    else:
        strategy.setKeepCRV(0, {"from": gov})
    chain.sleep(1)
    chain.mine(1)
    strategy.harvest({"from": gov})


# this one tests if we don't have any CRV to send to voter or any left over after sending
def test_more_rewards_stuff(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    voter,
    amount,
    rewards_token,
    rewards,
    keeper,
    pool,
    gauge,
    strategy_name,
    is_convex,
    sleep_time,
    rewards_template,
):
    # skip this test if we don't use rewards in this template
    if not rewards_template:
        return

    ## deposit to the vault after approving
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    strategy.harvest({"from": gov})

    # we do this twice to hit both branches of the if statement
    if is_convex:
        strategy.updateRewards(False, 0, {"from": gov})
        strategy.updateRewards(False, 0, {"from": gov})
    else:
        strategy.updateRewards(False, rewards_token, {"from": gov})
        strategy.updateRewards(False, rewards_token, {"from": gov})

    # set our optimal to DAI without rewards on
    strategy.setOptimal(0, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit DAI (rewards off):", tx.events["Harvested"]["profit"] / 1e18)

    # set our optimal to USDC without rewards on
    strategy.setOptimal(1, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit USDC (rewards off):", tx.events["Harvested"]["profit"] / 1e18)

    # set our optimal to USDT without rewards on
    strategy.setOptimal(2, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit USDT (rewards off):", tx.events["Harvested"]["profit"] / 1e18)

    # we do this twice to hit both branches of the if statement
    if is_convex:
        strategy.updateRewards(True, 0, {"from": gov})
        strategy.updateRewards(True, 0, {"from": gov})
    else:
        strategy.updateRewards(True, rewards_token, {"from": gov})
        strategy.updateRewards(True, rewards_token, {"from": gov})

    # set our optimal to DAI with rewards on
    strategy.setOptimal(0, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit DAI (rewards on):", tx.events["Harvested"]["profit"] / 1e18)

    # set our optimal to USDC with rewards on
    strategy.setOptimal(1, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit USDC (rewards on):", tx.events["Harvested"]["profit"] / 1e18)

    # set our optimal to USDT with rewards on
    strategy.setOptimal(2, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit USDT (rewards on):", tx.events["Harvested"]["profit"] / 1e18)

    # take 100% of our CRV to the voter
    if is_convex:
        strategy.setKeep(10000, 0, gov, {"from": gov})
    else:
        strategy.setKeepCRV(10000, {"from": gov})
    chain.sleep(1)
    chain.mine(1)
    tx = strategy.harvest(
        {"from": gov}
    )  # this one seems to randomly fail sometimes, adding sleep/mine before fixed it, likely because of updating the view variable?

    # we do this twice to hit both branches of the if statement
    if is_convex:
        strategy.updateRewards(False, 0, {"from": gov})
        strategy.updateRewards(False, 0, {"from": gov})
    else:
        strategy.updateRewards(False, rewards_token, {"from": gov})
        strategy.updateRewards(False, rewards_token, {"from": gov})

    # set our optimal to DAI without rewards on
    strategy.setOptimal(0, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit DAI (rewards off):", tx.events["Harvested"]["profit"] / 1e18)

    # set our optimal to USDC without rewards on
    strategy.setOptimal(1, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit USDC (rewards off):", tx.events["Harvested"]["profit"] / 1e18)

    # set our optimal to USDT without rewards on
    strategy.setOptimal(2, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit USDT (rewards off):", tx.events["Harvested"]["profit"] / 1e18)

    # we do this twice to hit both branches of the if statement
    if is_convex:
        strategy.updateRewards(True, 0, {"from": gov})
        strategy.updateRewards(True, 0, {"from": gov})
    else:
        strategy.updateRewards(True, rewards_token, {"from": gov})
        strategy.updateRewards(True, rewards_token, {"from": gov})

    # set our optimal to DAI with rewards on
    strategy.setOptimal(0, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # set our optimal to USDC with rewards on
    strategy.setOptimal(1, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit DAI (rewards on):", tx.events["Harvested"]["profit"] / 1e18)

    # set our optimal to USDT with rewards on
    strategy.setOptimal(2, {"from": gov})

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit USDC (rewards on):", tx.events["Harvested"]["profit"] / 1e18)

    # sleep to get some profit
    chain.sleep(sleep_time)
    chain.mine(1)

    # can't set to 4
    with brownie.reverts():
        strategy.setOptimal(4, {"from": gov})

    # take 0% of our CRV to the voter
    if is_convex:
        strategy.setKeep(0, 0, gov, {"from": gov})
    else:
        strategy.setKeepCRV(0, {"from": gov})
    chain.sleep(1)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print("Harvest Profit USDT (rewards on):", tx.events["Harvested"]["profit"] / 1e18)
