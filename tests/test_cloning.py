import brownie
from brownie import Wei, accounts, Contract, config

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
    StrategyConvexOldPoolsClonable,
    rewardsContract,
    pid,
    amount,
    pool,
    strategy_name,
):
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
    newStrategy = StrategyConvexOldPoolsClonable.at(tx.return_value)

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
            vault, strategist, rewards, keeper, pid, pool, strategy_name, {"from": gov}
        )
        
    # revoke and send all funds back to vault
    vault.revokeStrategy(strategy, {"from": gov})
    
    # attach our new strategy
    vault.addStrategy(newStrategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    assert vault.withdrawalQueue(1) == newStrategy
    assert vault.strategies(newStrategy)["debtRatio"] == 10_000
    assert vault.withdrawalQueue(0) == strategy
    assert vault.strategies(strategy)["debtRatio"] == 0

    ## deposit to the vault after approving; this is basically just our simple_harvest test
    before_pps = vault.pricePerShare()
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    # this is part of our check into the staking contract balance
    stakingBeforeHarvest = rewardsContract.balanceOf(newStrategy)

    # harvest, store asset amount
    tx = newStrategy.harvest({"from": gov})
    old_assets = vault.totalAssets()
    assert old_assets > 0
    assert token.balanceOf(newStrategy) == 0
    assert strategy.estimatedTotalAssets() == 0
    assert newStrategy.estimatedTotalAssets() > 0
    assert rewardsContract.balanceOf(newStrategy) > 0
    print("\nStarting Assets: ", old_assets / 1e18)
    print("\nAssets Staked: ", rewardsContract.balanceOf(newStrategy) / 1e18)

    # try and include custom logic here to check that funds are in the staking contract (if needed)
    assert rewardsContract.balanceOf(newStrategy) > stakingBeforeHarvest

    # simulate 1 day of earnings
    chain.sleep(86400)
    chain.mine(1)

    # harvest after a day, store new asset amount
    newStrategy.harvest({"from": gov})
    new_assets_dai = vault.totalAssets()
    
    # confirm we made money, or at least that we have about the same
    assert new_assets >= old_assets
    print("\nAssets after 1 hour: ", new_assets / 1e18)

    # Display estimated APR based on the two days before the pay out
    print(
        "\nEstimated APR: ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale
    assert vault.pricePerShare() > before_pps
