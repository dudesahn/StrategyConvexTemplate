import brownie
from brownie import Contract
from brownie import config
import math

# test the our strategy's ability to deposit, harvest, and withdraw, with different optimal deposit tokens if we have them
def test_simple_harvest(
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
    sleep_time,
    is_slippery,
    no_profit,
    is_convex,
    crv,
    accounts,
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)
    chain.sleep(1)
    chain.mine(1)

    # this is part of our check into the staking contract balance
    if is_convex:
        stakingBeforeHarvest = rewardsContract.balanceOf(strategy)
    else:
        stakingBeforeHarvest = strategy.stakedBalance()

    # change our optimal deposit asset
    strategy.setOptimal(0, {"from": gov})

    # harvest, store asset amount
    tx = strategy.harvest({"from": gov})
    print("Harvest info:", tx.events["Harvested"])
    chain.sleep(1)
    chain.mine(1)
    old_assets = vault.totalAssets()
    assert old_assets > 0
    assert token.balanceOf(strategy) == 0
    assert strategy.estimatedTotalAssets() > 0
    print("Starting Assets: ", old_assets / 1e18)

    # try and include custom logic here to check that funds are in the staking contract (if needed)
    if is_convex:
        stakingBeforeHarvest < rewardsContract.balanceOf(strategy)
    else:
        stakingBeforeHarvest < strategy.stakedBalance()

    # simulate profits
    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest, store new asset amount
    chain.sleep(1)
    tx = strategy.harvest({"from": gov})
    chain.sleep(1)
    new_assets = vault.totalAssets()
    # confirm we made money, or at least that we have about the same
    assert new_assets >= old_assets
    print("\nAssets after 1 day: ", new_assets / 1e18)

    # Display estimated APR
    print(
        "\nEstimated DAI APR: ",
        "{:.2%}".format(
            ((new_assets - old_assets) * (365 * 86400 / sleep_time))
            / (strategy.estimatedTotalAssets())
        ),
    )
    print("Harvest info:", tx.events["Harvested"])
    if not no_profit:
        assert tx.events["Harvested"]["profit"] > 0

    # simulate some profits if we don't have any to make sure everything else works
    if no_profit:
        crv_whale = accounts.at(
            "0x32D03DB62e464c9168e41028FFa6E9a05D8C6451", force=True
        )
        crv.transfer(strategy, 10_000e18, {"from": crv_whale})

        # harvest, store new asset amount, turn off health check since we're donating a lot
        old_assets = vault.totalAssets()
        chain.sleep(1)
        chain.mine(1)
        strategy.setDoHealthCheck(False, {"from": gov})
        tx = strategy.harvest({"from": gov})
        chain.sleep(1)
        chain.mine(1)
        new_assets = vault.totalAssets()
        # confirm we made money, or at least that we have about the same
        assert new_assets >= old_assets
        print("\nAssets after 1 day: ", new_assets / 1e18)

        # Display estimated APR
        print(
            "\nEstimated Simulated CRV APR: ",
            "{:.2%}".format(
                ((new_assets - old_assets) * (365 * 86400 / sleep_time))
                / (strategy.estimatedTotalAssets())
            ),
        )
        print("CRV harvest info:", tx.events["Harvested"])
        assert tx.events["Harvested"]["profit"] > 0

        if is_convex:
            cvx = Contract("0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B")
            cvx_whale = accounts.at(
                "0x28C6c06298d514Db089934071355E5743bf21d60", force=True
            )
            cvx.transfer(strategy, 1000e18, {"from": cvx_whale})

            # harvest, store new asset amount, turn off health check since we're donating a lot
            old_assets = vault.totalAssets()
            chain.sleep(1)
            chain.mine(1)
            strategy.setDoHealthCheck(False, {"from": gov})
            tx = strategy.harvest({"from": gov})
            chain.sleep(1)
            chain.mine(1)
            new_assets = vault.totalAssets()
            # confirm we made money, or at least that we have about the same
            assert new_assets >= old_assets
            print("\nAssets after 1 day: ", new_assets / 1e18)

            # Display estimated APR
            print(
                "\nEstimated Simulated CVX APR: ",
                "{:.2%}".format(
                    ((new_assets - old_assets) * (365 * 86400 / sleep_time))
                    / (strategy.estimatedTotalAssets())
                ),
            )
            print("CVX harvest info:", tx.events["Harvested"])
            assert tx.events["Harvested"]["profit"] > 0

        # end here if no profit, no reason to test USDC and USDT
        return

    # change our optimal deposit asset
    strategy.setOptimal(1, {"from": gov})

    # store asset amount
    before_usdc_assets = vault.totalAssets()
    assert token.balanceOf(strategy) == 0

    # try and include custom logic here to check that funds are in the staking contract (if needed)
    if is_convex:
        stakingBeforeHarvest < rewardsContract.balanceOf(strategy)
    else:
        stakingBeforeHarvest < strategy.stakedBalance()

    # simulate profits
    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest, store new asset amount
    chain.sleep(1)
    tx = strategy.harvest({"from": gov})
    chain.sleep(1)
    after_usdc_assets = vault.totalAssets()
    # confirm we made money, or at least that we have about the same
    assert after_usdc_assets >= before_usdc_assets

    # Display estimated APR
    print(
        "\nEstimated USDC APR: ",
        "{:.2%}".format(
            ((after_usdc_assets - before_usdc_assets) * (365 * 86400 / sleep_time))
            / (strategy.estimatedTotalAssets())
        ),
    )
    print("Harvest info:", tx.events["Harvested"])
    if not no_profit:
        assert tx.events["Harvested"]["profit"] > 0

    # change our optimal deposit asset
    strategy.setOptimal(2, {"from": gov})

    # store asset amount
    before_usdt_assets = vault.totalAssets()
    assert token.balanceOf(strategy) == 0
    assert strategy.estimatedTotalAssets() > 0

    # try and include custom logic here to check that funds are in the staking contract (if needed)
    if is_convex:
        stakingBeforeHarvest < rewardsContract.balanceOf(strategy)
    else:
        stakingBeforeHarvest < strategy.stakedBalance()

    # simulate profits
    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest, store new asset amount
    chain.sleep(1)
    tx = strategy.harvest({"from": gov})
    chain.sleep(1)
    after_usdt_assets = vault.totalAssets()
    # confirm we made money, or at least that we have about the same
    assert after_usdt_assets >= before_usdt_assets

    # Display estimated APR
    print(
        "\nEstimated USDT APR: ",
        "{:.2%}".format(
            ((after_usdt_assets - before_usdt_assets) * (365 * 86400 / sleep_time))
            / (strategy.estimatedTotalAssets())
        ),
    )
    print("Harvest info:", tx.events["Harvested"])
    if not no_profit:
        assert tx.events["Harvested"]["profit"] > 0

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
