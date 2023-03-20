import pytest
from utils import harvest_strategy
import brownie
from brownie import ZERO_ADDRESS, chain, interface

# test removing a strategy from the withdrawal queue
def test_remove_from_withdrawal_queue(
    gov,
    token,
    vault,
    whale,
    strategy,
    amount,
    sleep_time,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
):
    ## deposit to the vault after approving
    starting_whale = token.balanceOf(whale)
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

    # simulate earnings, harvest
    chain.sleep(sleep_time)
    (profit, loss) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )

    # removing a strategy from the queue shouldn't change its assets
    before = strategy.estimatedTotalAssets()
    vault.removeStrategyFromQueue(strategy, {"from": gov})
    after = strategy.estimatedTotalAssets()
    assert before == after

    # check that our strategy is no longer in the withdrawal queue's 20 addresses
    addresses = []
    for x in range(19):
        address = vault.withdrawalQueue(x)
        addresses.append(address)
    print(
        "Strategy Address: ",
        strategy.address,
        "\nWithdrawal Queue Addresses: ",
        addresses,
    )
    assert not strategy.address in addresses


# test revoking a strategy from the vault
def test_revoke_strategy_from_vault(
    gov,
    token,
    vault,
    whale,
    strategy,
    amount,
    is_slippery,
    no_profit,
    sleep_time,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    RELATIVE_APPROX,
):

    ## deposit to the vault after approving
    starting_whale = token.balanceOf(whale)
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

    # sleep to earn some yield
    chain.sleep(sleep_time)

    # record our assets everywhere
    vault_assets_starting = vault.totalAssets()
    vault_holdings_starting = token.balanceOf(vault)
    strategy_starting = strategy.estimatedTotalAssets()

    # revoke and harvest
    vault.revokeStrategy(strategy.address, {"from": gov})
    (profit, loss) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )

    # confirm we made money, or at least that we have about the same
    vault_assets_after_revoke = vault.totalAssets()
    strategy_assets_after_revoke = strategy.estimatedTotalAssets()

    if is_slippery and no_profit:
        assert (
            pytest.approx(vault_assets_after_revoke, rel=RELATIVE_APPROX)
            == vault_assets_starting
        )
        assert (
            pytest.approx(token.balanceOf(vault), rel=RELATIVE_APPROX)
            == vault_holdings_starting + strategy_starting
        )
    else:
        assert vault_assets_after_revoke >= vault_assets_starting
        assert token.balanceOf(vault) >= vault_holdings_starting + strategy_starting

    # should be zero in our strategy unless we use yswaps, then some profit will still be sitting there
    if use_yswaps:
        assert (
            pytest.approx(strategy_assets_after_revoke, rel=RELATIVE_APPROX)
            == profit_amount
        )
    else:
        assert pytest.approx(strategy_assets_after_revoke, rel=RELATIVE_APPROX) == 0

    # simulate five days of waiting for share price to bump back up
    chain.sleep(86400 * 5)
    chain.mine(1)

    # withdraw and confirm we made money, or at least that we have about the same (profit whale has to be different from normal whale)
    vault.withdraw({"from": whale})
    if is_slippery and no_profit:
        assert (
            pytest.approx(token.balanceOf(whale), rel=RELATIVE_APPROX) == starting_whale
        )
    else:
        assert token.balanceOf(whale) >= starting_whale


# test the setters on our strategy
def test_setters(
    gov,
    token,
    vault,
    whale,
    strategy,
    amount,
):
    # deposit to the vault after approving
    starting_whale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    name = strategy.name()

    # test our setters in baseStrategy
    strategy.setMaxReportDelay(1e18, {"from": gov})
    strategy.setMinReportDelay(100, {"from": gov})
    strategy.setRewards(gov, {"from": gov})
    strategy.setStrategist(gov, {"from": gov})

    ######### BELOW WILL NEED TO BE UPDATED BASED SETTERS OUR STRATEGY HAS #########
    strategy.setMaxLoss(1, {"from": gov})

    with brownie.reverts():
        strategy.setMaxLoss(7, {"from": whale})


# test sweeping out tokens
def test_sweep(
    gov,
    token,
    vault,
    whale,
    strategy,
    to_sweep,
    amount,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
):
    # deposit to the vault after approving
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

    # we can sweep out non-want tokens
    strategy.sweep(to_sweep, {"from": gov})

    # Strategy want token doesn't work
    token.transfer(strategy.address, amount, {"from": whale})
    assert token.address == strategy.want()
    assert token.balanceOf(strategy) > 0
    with brownie.reverts("!want"):
        strategy.sweep(token, {"from": gov})
    with brownie.reverts():
        strategy.sweep(to_sweep, {"from": whale})

    # Vault share token doesn't work
    with brownie.reverts("!shares"):
        strategy.sweep(vault.address, {"from": gov})
