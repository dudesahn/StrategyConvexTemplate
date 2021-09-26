import brownie
from brownie import Wei, accounts, Contract, config

# test passes as of 21-06-26
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
    StrategyConvexFixedForexClonable,
    rewardsContract,
    pid,
    amount,
    pool,
    sToken,
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
            sToken,
            strategy_name,
            {"from": gov},
        )

    ## clone our strategy
    tx = strategy.cloneConvexibFF(
        vault,
        strategist,
        rewards,
        keeper,
        pid,
        pool,
        sToken,
        strategy_name,
        {"from": gov},
    )
    newStrategy = StrategyConvexFixedForexClonable.at(tx.return_value)

    # Shouldn't be able to call initialize again
    with brownie.reverts():
        newStrategy.initialize(
            vault,
            strategist,
            rewards,
            keeper,
            pid,
            pool,
            sToken,
            strategy_name,
            {"from": gov},
        )

    # revoke and send all funds back to vault
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})
    
    # attach our new strategy
    vault.addStrategy(newStrategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    
    assert vault.withdrawalQueue(1) == newStrategy
    assert vault.strategies(newStrategy)[2] == 10_000
    assert vault.withdrawalQueue(0) == strategy
    assert vault.strategies(strategy)[2] == 0

    ## deposit to the vault after approving; this is basically just our simple_harvest test
    before_pps = vault.pricePerShare()
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(20000e18, {"from": whale})
    
    # harvest, store asset amount
    newStrategy.tend({"from": gov})
    chain.sleep(361)
    tx = newStrategy.harvest({"from": gov})
    old_assets_dai = vault.totalAssets()
    assert old_assets_dai > 0
    assert token.balanceOf(newStrategy) == 0
    assert newStrategy.estimatedTotalAssets() > 0
    assert rewardsContract.balanceOf(newStrategy) > 0
    print("\nStarting Assets: ", old_assets_dai / 1e18)
    print("\nAssets Staked: ", rewardsContract.balanceOf(newStrategy) / 1e18)

    # simulate one hour of earnings
    chain.sleep(3600)
    chain.mine(1)

    # harvest after a day, store new asset amount
    chain.sleep(361)
    newStrategy.harvest({"from": gov})
    new_assets_dai = vault.totalAssets()
    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets_dai >= old_assets_dai
    print("\nAssets after 2 days: ", new_assets_dai / 1e18)

    # Display estimated APR based on the two days before the pay out
    print(
        "\nEstimated ibEUR APR: ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * 24))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)
    
    tx = newStrategy.tend({"from": gov})

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale
    assert vault.pricePerShare() >= before_pps
