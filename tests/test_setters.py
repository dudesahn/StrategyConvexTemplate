import brownie
from brownie import Contract
from brownie import config

# test the setters on our strategy
def test_setters(
    gov,
    strategy,
    strategist,
    chain,
    whale,
    token,
    vault,
    amount,
    gasOracle,
    strategist_ms,
    is_convex,
):

    # test our manual harvest trigger
    strategy.setForceHarvestTriggerOnce(True, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True

    # shouldn't manually harvest when gas is high
    gasOracle.setManualBaseFeeBool(False, {"from": strategist_ms})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False
    gasOracle.setManualBaseFeeBool(True, {"from": strategist_ms})

    strategy.setForceHarvestTriggerOnce(False, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False

    # test our manual harvest trigger, and that a harvest turns it off
    strategy.setForceHarvestTriggerOnce(True, {"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be true.", tx)
    assert tx == True
    strategy.harvest({"from": gov})
    tx = strategy.harvestTrigger(0, {"from": gov})
    print("\nShould we harvest? Should be false.", tx)
    assert tx == False

    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})

    # test our setters in baseStrategy and our main strategy
    strategy.setMaxReportDelay(0, {"from": gov})
    strategy.setMaxReportDelay(1e18, {"from": gov})
    strategy.setMetadataURI(0, {"from": gov})
    strategy.setMinReportDelay(100, {"from": gov})
    strategy.setRewards(gov, {"from": strategist})
    strategy.setClaimRewards(True, {"from": gov})
    strategy.setHarvestTriggerParams(90000e6, 150000e6, {"from": gov})

    strategy.setStrategist(strategist, {"from": gov})
    name = strategy.name()
    print("Strategy Name:", name)

    # health check stuff
    chain.sleep(86400)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    strategy.setDoHealthCheck(False, {"from": gov})
    chain.sleep(86400)
    strategy.harvest({"from": gov})
    chain.sleep(86400)

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

    # try a health check with zero address as health check
    strategy.setHealthCheck(zero, {"from": gov})
    strategy.setDoHealthCheck(True, {"from": gov})
    strategy.harvest({"from": gov})
    chain.sleep(86400)

    # do this last so it doesn't mess with our harvests
    strategy.setUniFees(0, {"from": gov})
