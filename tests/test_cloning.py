import brownie
from brownie import Wei, accounts, Contract, config, ZERO_ADDRESS
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
    contract_name,
    rewardsContract,
    pid,
    amount,
    pool,
    gauge,
    strategy_name,
    sleep_time,
    tests_using_tenderly,
    is_slippery,
    no_profit,
    is_convex,
    vault_address,
    has_rewards,
    rewards_token,
    is_clonable,
    proxy,
):

    # skip this test if we don't clone
    if not is_clonable:
        return

    # tenderly doesn't work for "with brownie.reverts"
    if tests_using_tenderly:
        if is_convex:
            ## clone our strategy
            tx = strategy.cloneCurve3CrvRewards(
                vault,
                strategist,
                rewards,
                keeper,
                pid,
                pool,
                strategy_name,
                {"from": gov},
            )
            newStrategy = contract_name.at(tx.return_value)
        else:
            ## clone our strategy
            tx = strategy.cloneCurve3CrvRewards(
                vault,
                strategist,
                rewards,
                keeper,
                gauge,
                pool,
                strategy_name,
                {"from": gov},
            )
            newStrategy = contract_name.at(tx.return_value)
    else:
        if is_convex:
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
            tx = strategy.cloneCurve3CrvRewards(
                vault,
                strategist,
                rewards,
                keeper,
                pid,
                pool,
                strategy_name,
                {"from": gov},
            )
            newStrategy = contract_name.at(tx.return_value)

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
                newStrategy.cloneCurve3CrvRewards(
                    vault,
                    strategist,
                    rewards,
                    keeper,
                    pid,
                    pool,
                    strategy_name,
                    {"from": gov},
                )

        else:
            # Shouldn't be able to call initialize again
            with brownie.reverts():
                strategy.initialize(
                    vault,
                    strategist,
                    rewards,
                    keeper,
                    gauge,
                    pool,
                    strategy_name,
                    {"from": gov},
                )

            ## clone our strategy
            tx = strategy.cloneCurve3CrvRewards(
                vault,
                strategist,
                rewards,
                keeper,
                gauge,
                pool,
                strategy_name,
                {"from": gov},
            )
            newStrategy = contract_name.at(tx.return_value)

            # Shouldn't be able to call initialize again
            with brownie.reverts():
                newStrategy.initialize(
                    vault,
                    strategist,
                    rewards,
                    keeper,
                    gauge,
                    pool,
                    strategy_name,
                    {"from": gov},
                )

            ## shouldn't be able to clone a clone
            with brownie.reverts():
                newStrategy.cloneCurve3CrvRewards(
                    vault,
                    strategist,
                    rewards,
                    keeper,
                    gauge,
                    pool,
                    strategy_name,
                    {"from": gov},
                )

    # revoke and get funds back into vault
    currentDebt = vault.strategies(strategy)["debtRatio"]
    vault.revokeStrategy(strategy, {"from": gov})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # attach our new strategy
    vault.addStrategy(newStrategy, currentDebt, 0, 2 ** 256 - 1, 1_000, {"from": gov})

    if vault_address == ZERO_ADDRESS:
        assert vault.withdrawalQueue(1) == newStrategy
    else:
        if (
            vault.withdrawalQueue(2) == ZERO_ADDRESS
        ):  # only has convex, since we just added our clone to position index 1
            assert vault.withdrawalQueue(1) == newStrategy
        else:
            assert vault.withdrawalQueue(2) == newStrategy
    assert vault.strategies(newStrategy)["debtRatio"] == currentDebt
    assert vault.strategies(strategy)["debtRatio"] == 0

    # add rewards token if needed
    if has_rewards:
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
    if not is_convex:  # make sure to update our proxy if a curve strategy
        proxy.approveStrategy(strategy.gauge(), newStrategy, {"from": gov})
    newStrategy.harvest({"from": gov})
    chain.sleep(1)
    old_assets = vault.totalAssets()
    assert old_assets > 0
    assert token.balanceOf(newStrategy) == 0
    assert newStrategy.estimatedTotalAssets() > 0
    print("\nStarting Assets: ", old_assets / 1e18)

    # try and include custom logic here to check that funds are in the staking contract (if needed)
    if is_convex:
        assert rewardsContract.balanceOf(newStrategy) > 0
        print("\nAssets Staked: ", rewardsContract.balanceOf(newStrategy) / 1e18)
    else:
        assert newStrategy.stakedBalance() > 0
        print("\nAssets Staked: ", newStrategy.stakedBalance() / 1e18)

    # simulate some earnings
    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest after a day, store new asset amount
    newStrategy.harvest({"from": gov})
    new_assets = vault.totalAssets()

    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets >= old_assets
    print("\nAssets after 2 days: ", new_assets / 1e18)

    # Display estimated APR based on the two days before the pay out
    print(
        "\nEstimated APR: ",
        "{:.2%}".format(
            ((new_assets - old_assets) * (365 * (86400 / sleep_time)))
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
