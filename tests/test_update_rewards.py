import brownie
from brownie import Wei, accounts, Contract, config


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
    StrategyConvex3CrvRewardsClonable,
    voter,
    proxy,
    pid,
    amount,
    pool,
    strategy_name,
    gauge,
    zero_address,
    has_rewards,
    convexToken,
):
    ## clone our strategy, set our rewards to none
    tx = strategy.cloneConvex3CrvRewards(
        vault,
        strategist,
        rewards,
        keeper,
        pid,
        pool,
        strategy_name,
        {"from": gov},
    )
    newStrategy = StrategyConvex3CrvRewardsClonable.at(tx.return_value)

    # revoke and send all funds back to vault
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})

    # attach our new strategy and approve it on the proxy
    vault.addStrategy(newStrategy, 10_000, 0, 2**256 - 1, 1_000, {"from": gov})

    assert vault.withdrawalQueue(1) == newStrategy
    assert vault.strategies(newStrategy)[2] == 10_000
    assert vault.withdrawalQueue(0) == strategy
    assert vault.strategies(strategy)[2] == 0

    ## deposit to the vault after approving; this is basically just our simple_harvest test
    before_pps = vault.pricePerShare()
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    # harvest, store asset amount
    chain.sleep(1)
    tx = newStrategy.harvest({"from": gov})
    chain.sleep(1)
    old_assets_dai = vault.totalAssets()
    assert old_assets_dai > 0
    assert token.balanceOf(newStrategy) == 0
    assert newStrategy.estimatedTotalAssets() > 0

    # simulate 6 hours of earnings so we don't outrun our convex earmark
    chain.sleep(21600)
    chain.mine(1)

    # harvest after a day, store new asset amount
    newStrategy.harvest({"from": gov})
    chain.sleep(1)
    new_assets_dai = vault.totalAssets()
    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets_dai >= old_assets_dai

    # Display estimated APR
    print(
        "\nEstimated DAI APR (Rewards On): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * 4))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # check what we have
    _rewards_token = newStrategy.rewardsToken()
    rewards_token = Contract(_rewards_token)
    assert newStrategy.hasRewards() == True
    assert (
        rewards_token.allowance(
            newStrategy, "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
        )
        > 0
    )

    # turn off our rewards
    newStrategy.turnOffRewards({"from": gov})
    assert newStrategy.rewardsToken() == zero_address
    assert newStrategy.hasRewards() == False
    if (
        has_rewards
    ):  # if we have a separate reward token (not CVX) check that our allowance is zero
        assert (
            rewards_token.allowance(
                newStrategy, "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
            )
            == 0
        )

    # track our new pps and assets
    new_pps = vault.pricePerShare()
    old_assets_dai = vault.totalAssets()

    # simulate 6 hours of earnings so we don't outrun our convex earmark
    chain.sleep(21600)
    chain.mine(1)

    # harvest with our new rewards token attached
    newStrategy.harvest({"from": gov})
    chain.sleep(1)
    chain.mine(1)
    new_assets_dai = vault.totalAssets()

    # Display estimated APR
    print(
        "\nEstimated DAI APR (Rewards Off): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * 4))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # add our rewards token, harvest to take the profit from it. this should be extra high yield from this harvest
    newStrategy.updateRewards(_rewards_token, {"from": gov})

    # assert that we set things up correctly
    assert newStrategy.rewardsToken() == _rewards_token
    assert newStrategy.hasRewards() == True
    assert (
        rewards_token.allowance(
            newStrategy, "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
        )
        > 0
    )

    # track our new pps and assets
    new_pps = vault.pricePerShare()
    old_assets_dai = vault.totalAssets()

    # simulate 6 hours of earnings so we don't outrun our convex earmark
    chain.sleep(21600)
    chain.mine(1)

    # harvest with our new rewards token attached
    newStrategy.harvest({"from": gov})

    # confirm that we are selling our rewards token
    assert newStrategy.rewardsToken() == rewards_token
    assert newStrategy.hasRewards() == True
    assert rewards_token.balanceOf(newStrategy) == 0
    new_assets_dai = vault.totalAssets()

    # Display estimated APR
    print(
        "\nEstimated DAI APR (Rewards Back On, 6 hours of rewards tokens): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * 4))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # simulate 6 hours of earnings so we don't outrun our convex earmark
    chain.sleep(21600)
    chain.mine(1)

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale
    assert vault.pricePerShare() > before_pps
    assert vault.pricePerShare() > new_pps


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
    StrategyConvex3CrvRewardsClonable,
    voter,
    proxy,
    pid,
    amount,
    pool,
    strategy_name,
    gauge,
    zero_address,
    convexToken,
    has_rewards,
):
    ## clone our strategy, set our rewards to none
    tx = strategy.cloneConvex3CrvRewards(
        vault,
        strategist,
        rewards,
        keeper,
        pid,
        pool,
        strategy_name,
        {"from": gov},
    )
    newStrategy = StrategyConvex3CrvRewardsClonable.at(tx.return_value)

    # revoke and send all funds back to vault
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})

    # attach our new strategy and approve it on the proxy
    vault.addStrategy(newStrategy, 10_000, 0, 2**256 - 1, 1_000, {"from": gov})

    assert vault.withdrawalQueue(1) == newStrategy
    assert vault.strategies(newStrategy)[2] == 10_000
    assert vault.withdrawalQueue(0) == strategy
    assert vault.strategies(strategy)[2] == 0

    ## deposit to the vault after approving; this is basically just our simple_harvest test
    before_pps = vault.pricePerShare()
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    # harvest, store asset amount
    chain.sleep(1)
    tx = newStrategy.harvest({"from": gov})
    chain.sleep(1)
    old_assets_dai = vault.totalAssets()
    assert old_assets_dai > 0
    assert token.balanceOf(newStrategy) == 0
    assert newStrategy.estimatedTotalAssets() > 0

    # simulate 6 hours of earnings so we don't outrun our convex earmark
    chain.sleep(21600)
    chain.mine(1)

    # harvest after a day, store new asset amount
    newStrategy.harvest({"from": gov})
    chain.sleep(1)
    chain.mine(1)
    new_assets_dai = vault.totalAssets()
    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets_dai >= old_assets_dai

    # Display estimated APR
    print(
        "\nEstimated DAI APR (Rewards On): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * 4))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # check what we have
    _rewards_token = newStrategy.rewardsToken()
    rewards_token = Contract(_rewards_token)
    assert newStrategy.hasRewards() == True
    assert (
        rewards_token.allowance(
            newStrategy, "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
        )
        > 0
    )

    # turn off our rewards
    newStrategy.turnOffRewards({"from": gov})
    assert newStrategy.rewardsToken() == zero_address
    assert newStrategy.hasRewards() == False
    if (
        has_rewards
    ):  # if we have a separate reward token (not CVX) check that our allowance is zero
        assert (
            rewards_token.allowance(
                newStrategy, "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
            )
            == 0
        )

    # track our new pps and assets
    new_pps = vault.pricePerShare()
    old_assets_dai = vault.totalAssets()

    # simulate 6 hours of earnings so we don't outrun our convex earmark
    chain.sleep(21600)
    chain.mine(1)

    # harvest with our new rewards token attached
    newStrategy.harvest({"from": gov})
    chain.sleep(1)
    chain.mine(1)
    new_assets_dai = vault.totalAssets()

    # Display estimated APR
    print(
        "\nEstimated DAI APR (Rewards Off): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * 4))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # try turning off our rewards again
    newStrategy.turnOffRewards({"from": gov})
    assert newStrategy.rewardsToken() == zero_address
    assert newStrategy.hasRewards() == False
    if (
        has_rewards
    ):  # if we have a separate reward token (not CVX) check that our allowance is zero
        assert (
            rewards_token.allowance(
                newStrategy, "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
            )
            == 0
        )

    # track our new pps and assets
    old_assets_dai = vault.totalAssets()

    # simulate 6 hours of earnings so we don't outrun our convex earmark
    chain.sleep(21600)
    chain.mine(1)

    # harvest with our new rewards token attached
    newStrategy.harvest({"from": gov})
    chain.sleep(1)
    chain.mine(1)
    new_assets_dai = vault.totalAssets()

    # Display estimated APR
    print(
        "\nEstimated DAI APR (Rewards Off Still): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * 4))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # simulate 6 hours of earnings so we don't outrun our convex earmark
    chain.sleep(21600)
    chain.mine(1)

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale
    assert vault.pricePerShare() > before_pps


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
    StrategyConvex3CrvRewardsClonable,
    voter,
    proxy,
    pid,
    amount,
    pool,
    strategy_name,
    gauge,
    zero_address,
):
    ## clone our strategy, set our rewards to none
    tx = strategy.cloneConvex3CrvRewards(
        vault,
        strategist,
        rewards,
        keeper,
        pid,
        pool,
        strategy_name,
        {"from": gov},
    )
    newStrategy = StrategyConvex3CrvRewardsClonable.at(tx.return_value)

    # revoke and send all funds back to vault
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})

    # attach our new strategy and approve it on the proxy
    vault.addStrategy(newStrategy, 10_000, 0, 2**256 - 1, 1_000, {"from": gov})

    ## deposit to the vault after approving; this is basically just our simple_harvest test
    before_pps = vault.pricePerShare()
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    # harvest, store asset amount
    chain.sleep(1)
    tx = newStrategy.harvest({"from": gov})
    chain.sleep(1)
    chain.mine(1)
    old_assets_dai = vault.totalAssets()

    # simulate 6 hours of earnings so we don't outrun our convex earmark
    chain.sleep(21600)
    chain.mine(1)

    # harvest after a day, store new asset amount
    newStrategy.harvest({"from": gov})
    new_assets_dai = vault.totalAssets()
    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets_dai >= old_assets_dai

    # Display estimated APR
    print(
        "\nEstimated DAI APR (Rewards On): ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * 4))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # pretend that we're getting our underlying token as a reward, assert that the approvals worked on sushi router
    _rewards_token = newStrategy.rewardsToken()
    rewards_token = Contract(_rewards_token)
    newStrategy.updateRewards(_rewards_token, {"from": gov})
    assert (
        rewards_token.allowance(
            newStrategy, "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
        )
        > 0
    )
    assert newStrategy.rewardsToken() == rewards_token
    assert newStrategy.hasRewards() == True


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
    StrategyConvex3CrvRewardsClonable,
    voter,
    proxy,
    pid,
    amount,
    pool,
    strategy_name,
    gauge,
    zero_address,
    has_rewards,
    convexToken,
):
    # check if our strategy has extra rewards
    rewards_token = Contract(strategy.rewardsToken())
    print("\nThis is our rewards token:", rewards_token.name())

    # if we're supposed to have a rewards token, make sure it's not CVX
    if has_rewards:
        assert convexToken != rewards_token
    else:
        assert zero_address == rewards_token
