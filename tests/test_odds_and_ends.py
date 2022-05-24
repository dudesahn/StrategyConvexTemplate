import brownie
from brownie import Contract
from brownie import config
import math


def test_odds_and_ends(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    voter,
    gauge,
    StrategyConvexUnderlying3Clonable,
    cvxDeposit,
    rewardsContract,
    pid,
    crv,
    convexToken,
    amount,
    pool,
    strategy_name,
    sleep_time,
):

    ## deposit to the vault after approving. turn off health check before each harvest since we're doing weird shit
    strategy.setDoHealthCheck(False, {"from": gov})
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # send away all funds, will need to alter this based on strategy
    # set claim rewards to true and send away CRV and CVX so we don't have dust leftover, this is a problem with uni v3
    strategy.setClaimRewards(True, {"from": gov})
    strategy.withdrawToConvexDepositTokens({"from": gov})
    to_send = cvxDeposit.balanceOf(strategy)
    print("cvxToken Balance of Strategy", to_send)
    cvxDeposit.transfer(gov, to_send, {"from": strategy})
    to_send = crv.balanceOf(strategy)
    crv.transfer(gov, to_send, {"from": strategy})
    to_send = convexToken.balanceOf(strategy)
    convexToken.transfer(gov, to_send, {"from": strategy})
    assert strategy.estimatedTotalAssets() == 0

    # our whale donates 1 wei to the vault so we don't divide by zero (0.3.2 vault, errors in vault._reportLoss)
    token.transfer(strategy, 1, {"from": whale})

    # sleep to collect earnings
    chain.sleep(sleep_time)
    chain.mine(1)

    strategy.setDoHealthCheck(False, {"from": gov})
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # we can also withdraw from an empty vault as well
    vault.withdraw({"from": whale})

    # we can try to migrate too, lol
    # deploy our new strategy
    new_strategy = strategist.deploy(
        StrategyConvexUnderlying3Clonable,
        vault,
        pid,
        pool,
        strategy_name,
    )
    total_old = strategy.estimatedTotalAssets()

    # migrate our old strategy
    vault.migrateStrategy(strategy, new_strategy, {"from": gov})

    # assert that our old strategy is empty
    updated_total_old = strategy.estimatedTotalAssets()
    assert updated_total_old == 0

    # harvest to get funds back in strategy
    new_strategy.harvest({"from": gov})
    new_strat_balance = new_strategy.estimatedTotalAssets()
    assert new_strat_balance >= updated_total_old

    startingVault = vault.totalAssets()
    print("\nVault starting assets with new strategy: ", startingVault)

    # sleep to collect earnings
    chain.sleep(sleep_time)
    chain.mine(1)

    # Test out our migrated strategy, confirm we're making a profit
    new_strategy.harvest({"from": gov})
    vaultAssets_2 = vault.totalAssets()
    assert vaultAssets_2 >= startingVault
    print("\nAssets after 1 day harvest: ", vaultAssets_2)

    # check our oracle
    one_eth_in_want = strategy.ethToWant(1000000000000000000)
    print("This is how much want one ETH buys:", one_eth_in_want)
    zero_eth_in_want = strategy.ethToWant(0)

    # check our views
    strategy.apiVersion()
    strategy.isActive()

    # tend stuff
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.sleep(1)
    strategy.tendTrigger(0, {"from": gov})


def test_odds_and_ends_2(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    voter,
    gauge,
    cvxDeposit,
    amount,
):

    ## deposit to the vault after approving. turn off health check since we're doing weird shit
    strategy.setDoHealthCheck(False, {"from": gov})
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # send away all funds, will need to alter this based on strategy
    strategy.withdrawToConvexDepositTokens({"from": gov})
    to_send = cvxDeposit.balanceOf(strategy)
    print("cvxToken Balance of Strategy", to_send)
    cvxDeposit.transfer(gov, to_send, {"from": strategy})
    assert strategy.estimatedTotalAssets() == 0

    # our whale donates 1 gwei to the vault so we don't divide by zero (0.3.2 vault, errors in vault._reportLoss)
    token.transfer(strategy, 1, {"from": whale})

    strategy.setEmergencyExit({"from": gov})

    chain.sleep(1)
    strategy.setDoHealthCheck(False, {"from": gov})
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # we can also withdraw from an empty vault as well
    vault.withdraw({"from": whale})


def test_odds_and_ends_migration(
    StrategyConvexUnderlying3Clonable,
    gov,
    token,
    vault,
    guardian,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    proxy,
    pid,
    amount,
    pool,
    strategy_name,
    sleep_time,
):

    ## deposit to the vault after approving
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # deploy our new strategy
    new_strategy = strategist.deploy(
        StrategyConvexUnderlying3Clonable,
        vault,
        pid,
        pool,
        strategy_name,
    )
    total_old = strategy.estimatedTotalAssets()

    # can we harvest an unactivated strategy? should be no
    tx = new_strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be False.", tx)
    assert tx == False

    # sleep to collect earnings
    chain.sleep(sleep_time)
    chain.mine(1)

    # migrate our old strategy
    vault.migrateStrategy(strategy, new_strategy, {"from": gov})

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

    # sleep to collect earnings
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


def test_odds_and_ends_liquidatePosition(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    gauge,
    voter,
    rewardsContract,
    amount,
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)

    # this is part of our check into the staking contract balance
    stakingBeforeHarvest = rewardsContract.balanceOf(strategy)

    # harvest, store asset amount
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    old_assets = vault.totalAssets()
    assert old_assets > 0
    assert token.balanceOf(strategy) == 0
    assert strategy.estimatedTotalAssets() > 0
    print("\nStarting Assets: ", old_assets / 1e18)

    # try and include custom logic here to check that funds are in the staking contract (if needed)
    assert rewardsContract.balanceOf(strategy) > stakingBeforeHarvest

    # simulate one day of earnings
    chain.sleep(86400)
    chain.mine(1)

    # harvest, store new asset amount
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    new_assets = vault.totalAssets()
    # confirm we made money, or at least that we have about the same
    assert new_assets >= old_assets or math.isclose(new_assets, old_assets, abs_tol=5)
    print("\nAssets after 7 days: ", new_assets / 1e18)

    # Display estimated APR
    print(
        "\nEstimated APR: ",
        "{:.2%}".format(
            ((new_assets - old_assets) * (365)) / (strategy.estimatedTotalAssets())
        ),
    )

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # transfer funds to our strategy so we have enough for our withdrawal
    token.transfer(strategy, amount, {"from": whale})

    # withdraw and confirm we made money, or at least that we have about the same
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) + amount >= startingWhale or math.isclose(
        token.balanceOf(whale), startingWhale, abs_tol=5
    )


def test_odds_and_ends_rekt(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    voter,
    cvxDeposit,
    rewardsContract,
    crv,
    convexToken,
    amount,
):
    ## deposit to the vault after approving. turn off health check since we're doing weird shit
    strategy.setDoHealthCheck(False, {"from": gov})
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # send away all funds, will need to alter this based on strategy
    # set claim rewards to true and send away CRV and CVX so we don't have dust leftover
    strategy.setClaimRewards(True, {"from": gov})
    strategy.withdrawToConvexDepositTokens({"from": gov})
    to_send = cvxDeposit.balanceOf(strategy)
    print("cvxToken Balance of Strategy", to_send)
    cvxDeposit.transfer(gov, to_send, {"from": strategy})
    to_send = crv.balanceOf(strategy)
    crv.transfer(gov, to_send, {"from": strategy})
    to_send = convexToken.balanceOf(strategy)
    convexToken.transfer(gov, to_send, {"from": strategy})
    assert strategy.estimatedTotalAssets() == 0

    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})

    # our whale donates 1 wei to the vault so we don't divide by zero (0.3.2 vault, errors in vault._reportLoss)
    token.transfer(strategy, 1, {"from": whale})

    strategy.setDoHealthCheck(False, {"from": gov})
    chain.sleep(1)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    chain.sleep(1)

    # we can also withdraw from an empty vault as well
    vault.withdraw({"from": whale})


# goal of this one is to hit a withdraw when we don't have any staked assets
def test_odds_and_ends_liquidate_rekt(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    voter,
    cvxDeposit,
    amount,
):
    ## deposit to the vault after approving. turn off health check since we're doing weird shit
    strategy.setDoHealthCheck(False, {"from": gov})
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # send away all funds, will need to alter this based on strategy
    strategy.withdrawToConvexDepositTokens({"from": gov})
    to_send = cvxDeposit.balanceOf(strategy)
    print("cvxToken Balance of Strategy", to_send)
    cvxDeposit.transfer(gov, to_send, {"from": strategy})
    assert strategy.estimatedTotalAssets() == 0
    strategy.withdrawToConvexDepositTokens({"from": gov})

    # we can also withdraw from an empty vault as well, but make sure we're okay with losing 100%
    to_withdraw = 2 ** 256 - 1  # withdraw our full amount
    vault.withdraw(to_withdraw, whale, 10000, {"from": whale})


def test_weird_reverts(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    other_vault_strategy,
    amount,
):

    # only vault can call this
    with brownie.reverts():
        strategy.migrate(strategist_ms, {"from": gov})

    # can't migrate to a different vault
    with brownie.reverts():
        vault.migrateStrategy(strategy, other_vault_strategy, {"from": gov})

    # can't withdraw from a non-vault address
    with brownie.reverts():
        strategy.withdraw(1e18, {"from": gov})

    # can't do health check with a non-health check contract
    with brownie.reverts():
        strategy.withdraw(1e18, {"from": gov})


# this test makes sure we can still harvest without any assets but with a profit
def test_odds_and_ends_empty_strat(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    voter,
    cvxDeposit,
    amount,
    sleep_time,
):
    ## deposit to the vault after approving
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    ## move our funds out of the strategy
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    chain.sleep(sleep_time)
    strategy.harvest({"from": gov})

    ## move our funds back into the strategy
    vault.updateStrategyDebtRatio(strategy, 10000, {"from": gov})
    chain.sleep(1)
    strategy.harvest({"from": gov})

    # sleep to generate some profit
    chain.sleep(sleep_time)

    # send away all funds so we have profit but no assets. make sure to turn off claimRewards first
    strategy.setClaimRewards(False, {"from": gov})
    strategy.withdrawToConvexDepositTokens({"from": gov})
    to_send = cvxDeposit.balanceOf(strategy)
    print("cvxToken Balance of Strategy", to_send)
    cvxDeposit.transfer(gov, to_send, {"from": strategy})
    assert strategy.estimatedTotalAssets() == 0
    assert strategy.claimableBalance() > 0

    # harvest to check that it works okay, turn off health check since we'll have profit without assets lol
    chain.sleep(1)
    strategy.setDoHealthCheck(False, {"from": gov})
    strategy.harvest({"from": gov})


# this test makes sure we can still harvest without any profit and not revert
def test_odds_and_ends_no_profit(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    voter,
    cvxDeposit,
    amount,
    sleep_time,
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # sleep two weeks into the future so we need to earmark, harvest to clear our profit
    strategy.setDoHealthCheck(False, {"from": gov})
    chain.sleep(86400 * 14)
    tx = strategy.harvest({"from": gov})
    profit = tx.events["Harvested"]["profit"]
    print("Harvest profit:", profit)
    assert profit > 0
    chain.mine(1)
    chain.sleep(1)
    assert strategy.needsEarmarkReward()

    # sleep to try and generate profit, but it shouldn't. we should still be able to harvest though.
    chain.sleep(1)
    assert strategy.claimableBalance() == 0
    tx = strategy.harvest({"from": gov})
    profit = tx.events["Harvested"]["profit"]
    assert profit == 0

    # withdraw and confirm we made money, or at least that we have about the same
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale
