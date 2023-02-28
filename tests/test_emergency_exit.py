import math
import brownie
from brownie import Contract
from brownie import config

# test that emergency exit works properly
def test_emergency_exit(
    gov,
    token,
    vault,
    whale,
    strategy,
    chain,
    amount,
    is_slippery,
    no_profit,
    sleep_time,
):
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # simulate earnings
    chain.sleep(sleep_time)
    chain.mine(1)
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # set emergency and exit, then confirm that the strategy has no funds
    strategy.setEmergencyExit({"from": gov})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    assert strategy.estimatedTotalAssets() == 0

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


# test emergency exit, but with a donation (profit)
def test_emergency_exit_with_profit(
    gov,
    token,
    vault,
    whale,
    strategy,
    chain,
    amount,
    is_slippery,
    no_profit,
    sleep_time,
):
    ## deposit to the vault after approving. turn off health check since we're doing weird shit
    strategy.setDoHealthCheck(False, {"from": gov})
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # simulate earnings
    chain.sleep(sleep_time)
    chain.mine(1)
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    # set emergency and exit, then confirm that the strategy has no funds
    donation = amount / 2
    token.transfer(strategy, donation, {"from": whale})
    strategy.setDoHealthCheck(False, {"from": gov})
    strategy.setEmergencyExit({"from": gov})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    assert strategy.estimatedTotalAssets() == 0

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and confirm we made money, or at least that we have about the same
    vault.withdraw({"from": whale})
    if is_slippery and no_profit:
        assert (
            math.isclose(token.balanceOf(whale) + donation, startingWhale, abs_tol=10)
            or token.balanceOf(whale) + donation >= startingWhale
        )
    else:
        assert token.balanceOf(whale) + donation >= startingWhale


# test emergency exit, but after somehow losing all of our assets
def test_emergency_exit_with_loss(
    gov,
    token,
    vault,
    whale,
    strategy,
    chain,
    gauge,
    amount,
    is_slippery,
    no_profit,
    booster,
    pid,
    is_convex,
    gauge_is_not_tokenized,
    rewardsContract,
):
    ## deposit to the vault after approving. turn off health check since we're doing weird shit
    strategy.setDoHealthCheck(False, {"from": gov})
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    if is_convex:
        # send away all funds, will need to alter this based on strategy
        rewardsContract.withdrawAll(False, {"from": strategy})
        to_send = token.balanceOf(strategy)
        token.transfer(gov, to_send, {"from": strategy})
        assert strategy.estimatedTotalAssets() == 0
    else:
        if gauge_is_not_tokenized:
            return
        # send all funds out of the gauge
        to_send = gauge.balanceOf(voter)
        print("Gauge Balance of Vault", to_send)
        gauge.transfer(gov, to_send, {"from": voter})
        assert strategy.estimatedTotalAssets() == 0

    # our whale donates 1 wei to the vault so we don't divide by zero (0.3.2 vault, errors in vault._reportLoss)
    token.transfer(strategy, 1, {"from": whale})

    # set emergency and exit, then confirm that the strategy has no funds
    strategy.setEmergencyExit({"from": gov})
    strategy.setDoHealthCheck(False, {"from": gov})
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    assert strategy.estimatedTotalAssets() == 0

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and see how down bad we are
    vault.withdraw({"from": whale})
    print(
        "Raw loss:",
        (startingWhale - token.balanceOf(whale)) / 1e18,
        "Percentage:",
        (startingWhale - token.balanceOf(whale)) / startingWhale,
    )
    print("Share price:", vault.pricePerShare() / 1e18)


# test emergency exit, after somehow losing all of our assets but miraculously getting them recovered
def test_emergency_exit_with_no_loss(
    gov,
    token,
    vault,
    whale,
    strategy,
    chain,
    gauge,
    amount,
    is_slippery,
    no_profit,
    booster,
    pid,
    is_convex,
    gauge_is_not_tokenized,
    rewardsContract,
):
    ## deposit to the vault after approving. turn off health check since we're doing weird shit
    strategy.setDoHealthCheck(False, {"from": gov})
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    depositSharePrice = vault.pricePerShare()
    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(1)

    if is_convex:
        # send away all funds, will need to alter this based on strategy
        rewardsContract.withdrawAll(False, {"from": strategy})
        to_send = token.balanceOf(strategy)
        token.transfer(gov, to_send, {"from": strategy})
        assert strategy.estimatedTotalAssets() == 0

        # gov unwraps and sends it back, glad someone was watching!
        token.transfer(strategy, to_send, {"from": gov})
        assert strategy.estimatedTotalAssets() > 0
    else:
        if gauge_is_not_tokenized:
            return
        # send all funds out of the gauge
        to_send = gauge.balanceOf(voter)
        print("Gauge Balance of Vault", to_send / 1e18)
        gauge.transfer(gov, to_send, {"from": voter})
        assert strategy.estimatedTotalAssets() == 0

        # gov unwraps and sends it back, glad someone was watching!
        gauge.withdraw(to_send, {"from": gov})
        token.transfer(strategy, to_send, {"from": gov})
        assert strategy.estimatedTotalAssets() > 0

    # set emergency and exit, then confirm that the strategy has no funds
    strategy.setEmergencyExit({"from": gov})
    strategy.setDoHealthCheck(False, {"from": gov})
    chain.sleep(1)
    tx = strategy.harvest({"from": gov})
    assert tx.events["Harvested"]["loss"] == 0
    chain.sleep(1)
    assert strategy.estimatedTotalAssets() == 0

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and confirm we have about the same when including convex profit
    whale_profit = (
        (vault.pricePerShare() - depositSharePrice) * vault.balanceOf(whale) / 1e18
    )
    print("Whale profit from other strat PPS increase:", whale_profit / 1e18)
    vault.withdraw({"from": whale})
    profit = token.balanceOf(whale) - startingWhale
    if no_profit and is_slippery:
        assert math.isclose(
            whale_profit, token.balanceOf(whale) - startingWhale, abs_tol=10
        )
    else:
        assert profit > -5  # allow for some slippage here
    print("Whale profit, should be low:", profit / 1e18)
