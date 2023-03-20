import pytest
from utils import harvest_strategy
from brownie import accounts, interface, chain

# test migrating a strategy
def test_migration(
    gov,
    token,
    vault,
    whale,
    strategy,
    amount,
    sleep_time,
    contract_name,
    profit_whale,
    profit_amount,
    destination_strategy,
    trade_factory,
    use_yswaps,
    is_slippery,
    no_profit,
    destination_vault,
    strategy_name,
):

    ## deposit to the vault after approving
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    (profit, loss) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )

    # record our current strategy's assets
    total_old = strategy.estimatedTotalAssets()

    # sleep to collect earnings
    chain.sleep(sleep_time)

    ######### THIS WILL NEED TO BE UPDATED BASED ON STRATEGY CONSTRUCTOR #########
    new_strategy = gov.deploy(contract_name, vault, destination_vault, strategy_name)

    # can we harvest an unactivated strategy? should be no
    tx = new_strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    ######### ADD LOGIC TO TEST CLAIMING OF ASSETS FOR TRANSFER TO NEW STRATEGY AS NEEDED #########
    # none needed for router strategy since we just hold the vault token

    # migrate our old strategy
    vault.migrateStrategy(strategy, new_strategy, {"from": gov})

    ####### ADD LOGIC TO MAKE SURE ASSET TRANSFER WENT AS EXPECTED #######
    assert destination_vault.balanceOf(strategy) == 0
    assert destination_vault.balanceOf(new_strategy) > 0

    # assert that our old strategy is empty
    updated_total_old = strategy.estimatedTotalAssets()
    assert updated_total_old == 0

    # harvest to get funds back in new strategy
    (profit, loss) = harvest_strategy(
        use_yswaps,
        new_strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )
    new_strat_balance = new_strategy.estimatedTotalAssets()

    # confirm that we have the same amount of assets in our new strategy as old
    if no_profit and is_slippery:
        assert pytest.approx(new_strat_balance, rel=RELATIVE_APPROX) == total_old
    else:
        assert new_strat_balance >= total_old

    # record our new assets
    vault_new_assets = vault.totalAssets()

    # simulate earnings
    chain.sleep(sleep_time)
    chain.mine(1)

    # Test out our migrated strategy, confirm we're making a profit
    (profit, loss) = harvest_strategy(
        True,
        new_strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )

    vault_newer_assets = vault.totalAssets()
    # confirm we made money, or at least that we have about the same
    if is_slippery and no_profit:
        assert (
            pytest.approx(vault_newer_assets, rel=RELATIVE_APPROX) == vault_new_assets
        )
    else:
        assert vault_newer_assets >= vault_new_assets


# make sure we can still migrate when we don't have funds
def test_empty_migration(
    gov,
    token,
    vault,
    whale,
    strategy,
    amount,
    sleep_time,
    contract_name,
    profit_whale,
    profit_amount,
    destination_strategy,
    trade_factory,
    use_yswaps,
    destination_vault,
    strategy_name,
    is_slippery,
    RELATIVE_APPROX,
):

    ## deposit to the vault after approving
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    (profit, loss) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )

    # record our current strategy's assets
    total_old = strategy.estimatedTotalAssets()

    # sleep to collect earnings
    chain.sleep(sleep_time)

    ######### THIS WILL NEED TO BE UPDATED BASED ON STRATEGY CONSTRUCTOR #########
    new_strategy = gov.deploy(contract_name, vault, destination_vault, strategy_name)

    # set our debtRatio to zero so our harvest sends all funds back to vault
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    (profit, loss) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )

    # yswaps needs another harvest to get the final bit of profit to the vault
    if use_yswaps:
        (profit, loss) = harvest_strategy(
            use_yswaps,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            destination_strategy,
        )

    # shouldn't have any assets, unless we have slippage, then this might leave dust
    # for complete emptying in this situtation, use emergencyExit
    if is_slippery:
        assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == 0
        strategy.setEmergencyExit({"from": gov})

        # turn off health check since taking profit on no debt
        strategy.setDoHealthCheck(False, {"from": gov})
        (profit, loss) = harvest_strategy(
            use_yswaps,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            destination_strategy,
        )

    assert strategy.estimatedTotalAssets() == 0

    # make sure we transferred strat params over
    total_debt = vault.strategies(strategy)["totalDebt"]
    debt_ratio = vault.strategies(strategy)["debtRatio"]

    # migrate our old strategy
    vault.migrateStrategy(strategy, new_strategy, {"from": gov})

    # new strategy should also be empty
    assert new_strategy.estimatedTotalAssets() == 0

    # make sure we took our gains and losses with us
    assert total_debt == vault.strategies(new_strategy)["totalDebt"]
    assert debt_ratio == vault.strategies(new_strategy)["debtRatio"] == 0
