import brownie
from brownie import Contract
from brownie import config
import math


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
    accounts,
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

    # simulate 1 day of earnings
    chain.sleep(86400)
    chain.mine(1)

    # harvest, store new asset amount
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    new_assets = vault.totalAssets()
    # confirm we made money, or at least that we have about the same
    assert new_assets >= old_assets
    print("\nAssets after 1 day: ", new_assets / 1e18)

    # Display estimated APR
    print(
        "\nEstimated wstETH APR: ",
        "{:.2%}".format(
            ((new_assets - old_assets) * 365) / (strategy.estimatedTotalAssets())
        ),
    )

    # change our optimal deposit asset
    strategy.setMintReth(True, {"from": gov})

    # store asset amount
    before_usdc_assets = vault.totalAssets()
    assert token.balanceOf(strategy) == 0

    # try and include custom logic here to check that funds are in the staking contract (if needed)
    assert rewardsContract.balanceOf(strategy) > 0

    # simulate 7 days of earnings to clear the minimum deposit amount
    chain.sleep(86400 * 14)
    chain.mine(1)

    # tend, wait a day, store new asset amount
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.sleep(1)
    
    # check our rETH balance
    reth = Contract("0xae78736Cd615f374D3085123A210448E74Fc6393")
    print("rETH Strategy balance after tend:", reth.balanceOf(strategy)/1e18)
    
    # adjust our waiting period to 5 blocks so we aren't miserable in testing
    networkSettings = Contract("0xc1B6057e8232fB509Fc60F9e9297e11E59D4A189")
    daoSetter = accounts.at("0x42EC642eAa86091059569d8De8aeccf7F2F9B1a2", force=True)
    path = "network.reth.deposit.delay"
    networkSettings.setSettingUint(path, 5, {'from': daoSetter})
    assert networkSettings.getRethDepositDelay() == 5
    chain.mine(6)
    
    # harvest, store new asset amount
    chain.sleep(1)
    assert strategy.isRethFree()
    strategy.harvest({"from": gov})
    chain.sleep(1)
    
    print("rETH Strategy balance after harvest:", reth.balanceOf(strategy)/1e18)
    
    after_usdc_assets = vault.totalAssets()
    # confirm we made money, or at least that we have about the same
    assert after_usdc_assets >= before_usdc_assets
    
    print("Profit after 14 days:", (after_usdc_assets - before_usdc_assets) / 1e18)

    # Display estimated APR
    print(
        "\nEstimated rETH APR: ",
        "{:.2%}".format(
            ((after_usdc_assets - before_usdc_assets) * (365 / 14))
            / (strategy.estimatedTotalAssets())
        ),
    )

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and confirm we made money, or at least that we have about the same
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale
