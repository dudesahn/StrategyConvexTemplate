import brownie
from brownie import Contract
from brownie import config
import math

# test migrating a strategy
def test_migration(
    contract_name,
    gov,
    token,
    vault,
    guardian,
    strategist,
    whale,
    strategy,
    chain,
    proxy,
    strategist_ms,
    healthCheck,
    pid,
    amount,
    pool,
    strategy_name,
    sleep_time,
    is_convex,
    gauge,
):

    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    if is_convex:
        # make sure to include all constructor parameters needed here
        new_strategy = strategist.deploy(
            contract_name,
            vault,
            pid,
            pool,
            strategy_name,
        )

        # can we harvest an unactivated strategy? should be no
        tx = new_strategy.harvestTrigger(0, {"from": gov})
        print("\nShould we harvest? Should be False.", tx)
        assert tx == False
    else:
        # make sure to include all constructor parameters needed here
        new_strategy = strategist.deploy(
            contract_name,
            vault,
            gauge,
            pool,
            strategy_name,
        )
        # harvestTrigger check for isActive() doesn't work if we have multiple curve strategies for the same LP

    total_old = strategy.estimatedTotalAssets()

    # sleep to collect earnings
    chain.sleep(sleep_time)

    # migrate our old strategy
    vault.migrateStrategy(strategy, new_strategy, {"from": gov})
    new_strategy.setHealthCheck(healthCheck, {"from": gov})
    new_strategy.setDoHealthCheck(True, {"from": gov})

    # if a curve strat, whitelist on our strategy proxy
    if not is_convex:
        proxy.approveStrategy(strategy.gauge(), new_strategy, {"from": gov})

    # assert that our old strategy is empty
    updated_total_old = strategy.estimatedTotalAssets()
    assert updated_total_old == 0

    # harvest to get funds back in strategy
    chain.sleep(1)
    new_strategy.harvest({"from": gov})
    new_strat_balance = new_strategy.estimatedTotalAssets()

    # confirm we made money, or at least that we have about the same
    assert new_strat_balance >= total_old or math.isclose(
        new_strat_balance, total_old, abs_tol=5
    )

    startingVault = vault.totalAssets()
    print("\nVault starting assets with new strategy: ", startingVault)

    # simulate earnings
    chain.sleep(sleep_time)
    chain.mine(1)

    # Test out our migrated strategy, confirm we're making a profit
    new_strategy.harvest({"from": gov})
    vaultAssets_2 = vault.totalAssets()
    # confirm we made money, or at least that we have about the same
    assert vaultAssets_2 >= startingVault or math.isclose(
        vaultAssets_2, startingVault, abs_tol=5
    )
    print("\nAssets after 1 day harvest: ", vaultAssets_2)
