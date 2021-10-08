import brownie
from brownie import Contract
from brownie import config


def test_setters(
    gov,
    strategy,
    strategist,
    chain,
    whale,
    token,
    vault,
    proxy,
    amount,
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})

    # test our setters in baseStrategy and our main strategy
    strategy.setDebtThreshold(1, {"from": gov})
    strategy.setMaxReportDelay(0, {"from": gov})
    strategy.setMaxReportDelay(1e18, {"from": gov})
    strategy.setMetadataURI(0, {"from": gov})
    strategy.setMinReportDelay(100, {"from": gov})
    strategy.setProfitFactor(1000, {"from": gov})
    strategy.setRewards(gov, {"from": strategist})
    strategy.setKeepCRV(10, {"from": gov})
    strategy.setClaimRewards(True, {"from": gov})
    strategy.setHarvestProfitNeeded(1e18, {"from": gov})
    strategy.setGasPrice(100, {"from": gov})
    strategy.setUniCrvFee(3000, {"from": gov})

    strategy.setStrategist(strategist, {"from": gov})
    name = strategy.name()
    print("Strategy Name:", name)

    # health check stuff
    chain.sleep(3600)
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    strategy.setDoHealthCheck(False, {"from": gov})
    chain.sleep(3600)
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})
    chain.sleep(3600)

    zero = "0x0000000000000000000000000000000000000000"

    with brownie.reverts():
        strategy.setKeeper(zero, {"from": gov})
    with brownie.reverts():
        strategy.setRewards(zero, {"from": strategist})
    with brownie.reverts():
        strategy.setStrategist(zero, {"from": gov})
    with brownie.reverts():
        strategy.setDoHealthCheck(False, {"from": whale})
    with brownie.reverts():
        strategy.setEmergencyExit({"from": whale})
    with brownie.reverts():
        strategy.setMaxReportDelay(1000, {"from": whale})
    with brownie.reverts():
        strategy.setRewards(strategist, {"from": whale})
    with brownie.reverts():
        strategy.setKeepCRV(10_001, {"from": gov})

    # try a health check with zero address as health check
    strategy.setHealthCheck(zero, {"from": gov})
    strategy.setDoHealthCheck(True, {"from": gov})
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})
    chain.sleep(3600)

    # try a health check with random contract as health check
    strategy.setHealthCheck(gov, {"from": gov})
    strategy.setDoHealthCheck(True, {"from": gov})
    with brownie.reverts():
        strategy.harvest({"from": gov})

    # set emergency exit last
    strategy.setEmergencyExit({"from": gov})
    with brownie.reverts():
        strategy.setEmergencyExit({"from": gov})


def test_sell_on_uni(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    chain,
    strategist_ms,
    amount,
    crv,
    sToken,
):
    strategy.setSellOnSushi(False, {"from": gov})
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)

    # harvest, store asset amount
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    old_assets = vault.totalAssets()
    assert old_assets > 0
    assert token.balanceOf(strategy) == 0
    assert strategy.estimatedTotalAssets() > 0
    print("\nStarting Assets: ", old_assets / 1e18)


    # simulate 1 hour of earnings (so chainlink oracles don't go stale, normally would do 1 day)
    chain.sleep(3600)
    chain.mine(1)

    # harvest, store new asset amount
    chain.sleep(1)
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    new_assets = vault.totalAssets()
    # confirm we made money, or at least that we have about the same
    assert new_assets >= old_assets or math.isclose(new_assets, old_assets, abs_tol=5)
    print("\nAssets after 1 day: ", new_assets / 1e18)

    # Display estimated APR
    print(
        "\nEstimated ibEUR APR: ",
        "{:.2%}".format(
            ((new_assets - old_assets) * (365 * 24)) / (strategy.estimatedTotalAssets())
        ),
    )

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and confirm we made money, or at least that we have about the same
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale or math.isclose(
        token.balanceOf(whale), startingWhale, abs_tol=5
    )
