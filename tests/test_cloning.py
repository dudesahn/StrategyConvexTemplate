import brownie
from brownie import Wei, accounts, Contract, config
import math

# test cloning our strategy, make sure the cloned strategy still works just fine by sending funds to it
def test_cloning(
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
    rewardsContract,
    pid,
    amount,
    pool,
    strategy_name,
    sleep_time,
    tests_using_tenderly,
    is_slippery,
    no_profit,
):
    # tenderly doesn't work for "with brownie.reverts"
    if tests_using_tenderly:
        ## clone our strategy
        tx = strategy.cloneConvex3CrvRewards(
            vault, strategist, rewards, keeper, pid, pool, strategy_name, {"from": gov}
        )
        newStrategy = StrategyConvex3CrvRewardsClonable.at(tx.return_value)
    else:
        # Shouldn't be able to call initialize again
        with brownie.reverts():
            strategy.initialize(
                vault,
                strategist,
                rewards,
                keeper,
                pid,
                pool,
                strategy_name,
                {"from": gov},
            )

        ## clone our strategy
        tx = strategy.cloneConvex3CrvRewards(
            vault, strategist, rewards, keeper, pid, pool, strategy_name, {"from": gov}
        )
        newStrategy = StrategyConvex3CrvRewardsClonable.at(tx.return_value)

        # Shouldn't be able to call initialize again
        with brownie.reverts():
            newStrategy.initialize(
                vault,
                strategist,
                rewards,
                keeper,
                pid,
                pool,
                strategy_name,
                {"from": gov},
            )

        ## shouldn't be able to clone a clone
        with brownie.reverts():
            newStrategy.cloneConvex3CrvRewards(
                vault,
                strategist,
                rewards,
                keeper,
                pid,
                pool,
                strategy_name,
                {"from": gov},
            )

    # revoke and get funds back into vault
    vault.revokeStrategy(strategy, {"from": gov})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # attach our new strategy
    vault.addStrategy(newStrategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    assert vault.withdrawalQueue(2) == newStrategy
    assert vault.strategies(newStrategy)[2] == 10_000
    assert vault.withdrawalQueue(1) == strategy
    assert vault.strategies(strategy)["debtRatio"] == 0

    ## deposit to the vault after approving; this is basically just our simple_harvest test
    before_pps = vault.pricePerShare()
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    # harvest, store asset amount
    newStrategy.harvest({"from": gov})
    chain.sleep(1)
    old_assets_dai = vault.totalAssets()
    assert old_assets_dai > 0
    assert token.balanceOf(newStrategy) == 0
    assert newStrategy.estimatedTotalAssets() > 0
    assert rewardsContract.balanceOf(newStrategy) > 0
    print("\nStarting Assets: ", old_assets_dai / 1e18)
    print("\nAssets Staked: ", rewardsContract.balanceOf(newStrategy) / 1e18)

    # simulate some earnings
    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest after a day, store new asset amount
    newStrategy.harvest({"from": gov})
    new_assets_dai = vault.totalAssets()
    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets_dai >= old_assets_dai
    print("\nAssets after 2 days: ", new_assets_dai / 1e18)

    # Display estimated APR based on the two days before the pay out
    print(
        "\nEstimated APR: ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * (86400 / sleep_time)))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and confirm we made money, or at least that we have about the same
    vault.withdraw({"from": whale})
    if is_slippery and no_profit:
        assert (
            math.isclose(token.balanceOf(whale), startingWhale, abs_tol=10)
            or token.balanceOf(whale) >= startingWhale
        )
    else:
        assert token.balanceOf(whale) >= startingWhale
    assert vault.pricePerShare() >= before_pps
