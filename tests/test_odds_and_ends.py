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
    StrategyConvexRocketpool,
    cvxDeposit,
    rewardsContract,
    pid,
    crv,
    convexToken,
    amount,
    pool,
    strategy_name,
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
    assert strategy.estimatedTotalAssets() == 0

    chain.sleep(86400 * 2)
    chain.mine(1)
    strategy.setDoHealthCheck(False, {"from": gov})
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # we can also withdraw from an empty vault as well
    vault.withdraw({"from": whale})

    # we can try to migrate too, lol
    # deploy our new strategy
    new_strategy = strategist.deploy(
        StrategyConvexRocketpool,
        vault,
        pid,
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
    StrategyConvexRocketpool,
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
        StrategyConvexRocketpool,
        vault,
        pid,
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
    accounts,
):

    ## deposit to the vault after approving
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    strategy.harvest({"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)

    # take 100% of our CRV to the voter
    strategy.setKeepCRV(10000, {"from": gov})
    strategy.harvest({"from": gov})

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)

    # take 0% of our CRV to the voter
    strategy.setKeepCRV(0, {"from": gov})
    strategy.harvest({"from": gov})

    # change our optimal deposit asset
    strategy.setMintReth(True, {"from": gov})

    # store asset amount
    before_usdc_assets = vault.totalAssets()
    assert token.balanceOf(strategy) == 0

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)

    # adjust our waiting period to 1 block so we aren't miserable in testing
    networkSettings = Contract("0xc1B6057e8232fB509Fc60F9e9297e11E59D4A189")
    daoSetter = accounts.at("0x42EC642eAa86091059569d8De8aeccf7F2F9B1a2", force=True)
    path = "network.reth.deposit.delay"
    networkSettings.setSettingUint(path, 1, {"from": daoSetter})
    assert networkSettings.getRethDepositDelay() == 1
    chain.mine(1)

    # set our minimum deposit to 1 wei
    depositSettings = Contract("0x781693a15E1fA7c743A299f4F0242cdF5489A0D9")
    path = "deposit.minimum"
    depositSettings.setSettingUint(path, 1, {"from": daoSetter})

    # read the maximum pool size and add 100 ETH to it
    new_size = depositSettings.getMaximumDepositPoolSize() + 100e18
    path = "deposit.pool.maximum"
    depositSettings.setSettingUint(path, new_size, {"from": daoSetter})

    # tend, wait a day, store new asset amount
    chain.sleep(1)
    strategy.setKeepCRV(10000, {"from": gov})
    strategy.tend({"from": gov})
    chain.sleep(1)
    chain.mine(2)

    # harvest, store new asset amount
    chain.sleep(1)
    assert strategy.isRethFree()
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # sleep for a day to get some profit
    chain.sleep(86400)
    chain.mine(1)

    strategy.setKeepCRV(0, {"from": gov})
    strategy.tend({"from": gov})
    chain.sleep(1)
    chain.mine(2)

    # harvest, store new asset amount
    chain.sleep(1)
    assert strategy.isRethFree()
    strategy.harvest({"from": gov})
    chain.sleep(1)
