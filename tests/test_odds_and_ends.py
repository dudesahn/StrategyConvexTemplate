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
    StrategyConvex3CrvRewardsClonable,
    cvxDeposit,
    rewardsContract,
    pid,
    crv,
    convexToken,
    amount,
    pool,
    strategy_name,
    rewards_token,
):

    ## deposit to the vault after approving. turn off health check before each harvest since we're doing weird shit
    strategy.setDoHealthCheck(False, {"from": gov})
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
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
    to_send = rewards_token.balanceOf(strategy)
    rewards_token.transfer(gov, to_send, {"from": strategy})
    assert strategy.estimatedTotalAssets() == 0

    # we want to check when we have a loss
    # comment this out since we no longer use harvestTrigger from baseStrategy
    # tx = strategy.harvestTrigger(0, {"from": gov})
    # print("\nShould we harvest? Should be true.", tx)
    # assert tx == True

    chain.sleep(86400)
    chain.mine(1)
    strategy.setDoHealthCheck(False, {"from": gov})
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # we can also withdraw from an empty vault as well
    vault.withdraw({"from": whale})

    # we can try to migrate too, lol
    # deploy our new strategy
    new_strategy = strategist.deploy(
        StrategyConvex3CrvRewardsClonable,
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
    assert new_strat_balance >= total_old

    startingVault = vault.totalAssets()
    print("\nVault starting assets with new strategy: ", startingVault)

    # simulate one day of earnings
    chain.sleep(86400)
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
    token.approve(vault, 2**256 - 1, {"from": whale})
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

    strategy.setEmergencyExit({"from": gov})

    chain.sleep(1)
    strategy.setDoHealthCheck(False, {"from": gov})
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # we can also withdraw from an empty vault as well
    vault.withdraw({"from": whale})


def test_odds_and_ends_migration(
    StrategyConvex3CrvRewardsClonable,
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
):

    ## deposit to the vault after approving
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # deploy our new strategy
    new_strategy = strategist.deploy(
        StrategyConvex3CrvRewardsClonable,
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

    # sleep for a dau
    chain.sleep(86400)

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

    # simulate one day of earnings
    chain.sleep(86400)
    chain.mine(1)

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
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
    token.approve(vault, 2**256 - 1, {"from": whale})
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
    token.approve(vault, 2**256 - 1, {"from": whale})
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
    token.approve(vault, 2**256 - 1, {"from": whale})
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
    vault.withdraw(10e18, whale, 10000, {"from": whale})


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


# this one makes sure our harvestTrigger doesn't trigger when we don't have assets, but will trigger if we have profit
def test_odds_and_ends_inactive_strat(
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
    ## deposit to the vault after approving
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    ## move our funds out of the strategy
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    # sleep for a day since univ3 is weird
    chain.sleep(86400)
    strategy.harvest({"from": gov})

    # we shouldn't harvest empty strategies
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False

    ## move our funds back into the strategy
    vault.updateStrategyDebtRatio(strategy, 10000, {"from": gov})
    chain.sleep(1)
    strategy.harvest({"from": gov})

    # sleep for five days to generate profit
    chain.sleep(86400 * 5)

    # send away all funds so we have profit but no assets
    strategy.withdrawToConvexDepositTokens({"from": gov})
    to_send = cvxDeposit.balanceOf(strategy)
    print("cvxToken Balance of Strategy", to_send)
    cvxDeposit.transfer(gov, to_send, {"from": strategy})
    assert strategy.estimatedTotalAssets() == 0

    # set debtRatio to zero so strategy will return inactive
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})

    # we should harvest empty strategies with profit to take, but our current profit is below our limit
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False

    # adjust our limit to 0, then check
    strategy.setHarvestProfitNeeded(0, 0, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True


# this one tests if we don't have any CRV to send to voter or any left over after sending
def test_odds_and_ends_weird_amounts(
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
):

    ## deposit to the vault after approving
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    strategy.harvest({"from": gov})

    # sleep for a week to get some profit
    chain.sleep(86400 * 7)
    chain.mine(1)

    # take 100% of our CRV to the voter
    strategy.setKeepCRV(10000, {"from": gov})
    chain.sleep(1)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # sleep for a week to get some profit
    chain.sleep(86400 * 7)
    chain.mine(1)

    # switch to USDC, want to not have any profit tho
    strategy.setOptimal(1, {"from": gov})
    strategy.harvest({"from": gov})

    # sleep for a week to get some profit
    chain.sleep(86400 * 7)
    chain.mine(1)

    # switch to USDT, want to not have any profit tho
    strategy.setOptimal(2, {"from": gov})
    strategy.harvest({"from": gov})

    # sleep for a week to get some profit
    chain.sleep(86400 * 7)
    chain.mine(1)

    # take 0% of our CRV to the voter
    strategy.setKeepCRV(0, {"from": gov})
    chain.sleep(1)
    chain.mine(1)
    strategy.harvest({"from": gov})


# this one tests if we don't have any CRV to send to voter or any left over after sending
def test_odds_and_ends_rewards_stuff(
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
):

    ## deposit to the vault after approving
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    strategy.harvest({"from": gov})

    # we do this twice to hit both branches of the if statement
    strategy.turnOffRewards({"from": gov})
    strategy.turnOffRewards({"from": gov})

    # set our optimal to DAI without rewards on
    strategy.setOptimal(0, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # set our optimal to USDC without rewards on
    strategy.setOptimal(1, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # set our optimal to USDT without rewards on
    strategy.setOptimal(2, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # we do this twice to hit both branches of the if statement
    strategy.updateRewards(rewards_token, {"from": gov})
    strategy.updateRewards(rewards_token, {"from": gov})

    # set our optimal to DAI with rewards on
    strategy.setOptimal(0, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # set our optimal to USDC with rewards on
    strategy.setOptimal(1, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # set our optimal to USDT with rewards on
    strategy.setOptimal(2, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # take 100% of our CRV to the voter
    strategy.setKeepCRV(10000, {"from": gov})
    chain.sleep(1)
    chain.mine(1)
    tx = strategy.harvest(
        {"from": gov}
    )  # this one seems to randomly fail sometimes, adding sleep/mine before fixed it, likely because of updating the view variable?

    # we do this twice to hit both branches of the if statement
    strategy.turnOffRewards({"from": gov})
    strategy.turnOffRewards({"from": gov})

    # set our optimal to DAI without rewards on
    strategy.setOptimal(0, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # set our optimal to USDC without rewards on
    strategy.setOptimal(1, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # set our optimal to USDT without rewards on
    strategy.setOptimal(2, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # we do this twice to hit both branches of the if statement
    strategy.updateRewards(rewards_token, {"from": gov})
    strategy.updateRewards(rewards_token, {"from": gov})

    # set our optimal to DAI with rewards on
    strategy.setOptimal(0, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # set our optimal to USDC with rewards on
    strategy.setOptimal(1, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # set our optimal to USDT with rewards on
    strategy.setOptimal(2, {"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)
    strategy.harvest({"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)

    # can't set to 4
    with brownie.reverts():
        strategy.setOptimal(4, {"from": gov})

    # take 0% of our CRV to the voter
    strategy.setKeepCRV(0, {"from": gov})
    chain.sleep(1)
    chain.mine(1)
    strategy.harvest({"from": gov})
