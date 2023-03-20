from brownie import chain, ZERO_ADDRESS
import pytest
from utils import harvest_strategy

# these tests all assess whether a strategy will hit accounting errors following donations to the strategy.
# lower debtRatio to 50%, donate, withdraw less than the donation, then harvest
def test_withdraw_after_donation_1(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    amount,
    sleep_time,
    is_slippery,
    no_profit,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    RELATIVE_APPROX,
    vault_address,
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
    prev_params = vault.strategies(strategy)

    # reduce our debtRatio to 50%
    currentDebt = prev_params["debtRatio"]
    vault.updateStrategyDebtRatio(strategy, currentDebt / 2, {"from": gov})
    assert vault.strategies(strategy)["debtRatio"] == currentDebt / 2

    # our profit whale donates to the vault, what a nice person! 🐳
    donation = amount / 2
    token.transfer(strategy, donation, {"from": profit_whale})

    # have our whale withdraw half of the donation, this ensures that we test withdrawing without pulling from the staked balance
    to_withdraw = donation / 2
    if vault_address == ZERO_ADDRESS:
        vault.withdraw(to_withdraw, {"from": whale})
    else:
        # convert since our PPS isn't 1 (live vault!)
        withdrawal_in_shares = to_withdraw * 1e18 / vault.pricePerShare()
        vault.withdraw(withdrawal_in_shares, {"from": whale})

    # simulate some earnings
    chain.sleep(sleep_time)

    # after our donation, best to use health check in case our donation profit is too big
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

    # harvest again so the strategy reports the profit
    if use_yswaps:
        print("Using ySwaps for harvests")
        (profit, loss) = harvest_strategy(
            use_yswaps,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            destination_strategy,
        )

    # record our new strategy params
    new_params = vault.strategies(strategy)

    # sleep 5 days to allow share price to normalize
    chain.sleep(86400 * 5)
    chain.mine(1)

    # specifically check that our profit is greater than our donation or at least close if we get slippage on deposit/withdrawal and have no profit
    profit = new_params["totalGain"] - prev_params["totalGain"]
    if is_slippery and no_profit:
        assert pytest.approx(profit, rel=RELATIVE_APPROX) == donation
    else:
        assert profit > donation

    # check that we didn't add any more loss, or close if we get slippage on deposit/withdrawal
    if is_slippery:
        assert (
            pytest.approx(new_params["totalLoss"], rel=RELATIVE_APPROX)
            == prev_params["totalLoss"]
        )
    else:
        assert new_params["totalLoss"] == prev_params["totalLoss"]

    # assert that our vault total assets, multiplied by our debtRatio, is about equal to our estimated total assets plus credit available
    # we multiply this by the debtRatio of our strategy out of 10_000 total
    # a vault only knows it has assets if the strategy has reported, and yswaps adds extra unrealized profit to the strategy since debtRatio > 0
    if use_yswaps:
        assert (
            pytest.approx(
                strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
                rel=RELATIVE_APPROX,
            )
            == int(
                vault.totalAssets() * new_params["debtRatio"] / 10_000 + profit_amount
            )
        )
    else:
        assert (
            pytest.approx(
                strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
                rel=RELATIVE_APPROX,
            )
            == int(vault.totalAssets() * new_params["debtRatio"] / 10_000)
        )


# lower debtRatio to 0, donate, withdraw less than the donation, then harvest
def test_withdraw_after_donation_2(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    amount,
    sleep_time,
    is_slippery,
    no_profit,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    RELATIVE_APPROX,
    vault_address,
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
    prev_params = vault.strategies(strategy)

    # reduce our debtRatio to 0%
    currentDebt = prev_params["debtRatio"]
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    assert vault.strategies(strategy)["debtRatio"] == 0

    # our profit whale donates to the vault, what a nice person! 🐳
    donation = amount / 2
    token.transfer(strategy, donation, {"from": profit_whale})

    # have our whale withdraw half of the donation, this ensures that we test withdrawing without pulling from the staked balance
    to_withdraw = donation / 2
    if vault_address == ZERO_ADDRESS:
        vault.withdraw(to_withdraw, {"from": whale})
    else:
        # convert since our PPS isn't 1 (live vault!)
        withdrawal_in_shares = to_withdraw * 1e18 / vault.pricePerShare()
        vault.withdraw(withdrawal_in_shares, {"from": whale})

    # simulate some earnings
    chain.sleep(sleep_time)

    # after our donation, best to use health check in case our donation profit is too big
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

    # harvest again so the strategy reports the profit
    if use_yswaps:
        print("Using ySwaps for harvests")
        (profit, loss) = harvest_strategy(
            use_yswaps,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            destination_strategy,
        )
    new_params = vault.strategies(strategy)

    # sleep 5 days to allow share price to normalize
    chain.sleep(86400 * 5)
    chain.mine(1)

    # specifically check that our profit is greater than our donation or at least close if we get slippage on deposit/withdrawal and have no profit
    profit = new_params["totalGain"] - prev_params["totalGain"]
    if is_slippery and no_profit:
        assert pytest.approx(profit, rel=RELATIVE_APPROX) == donation
    else:
        assert profit > donation

    # check that we didn't add any more loss, or close if we get slippage on deposit/withdrawal
    if is_slippery:
        assert (
            pytest.approx(new_params["totalLoss"], rel=RELATIVE_APPROX)
            == prev_params["totalLoss"]
        )
    else:
        assert new_params["totalLoss"] == prev_params["totalLoss"]

    # assert that our vault total assets, multiplied by our debtRatio, is about equal to our estimated total assets plus credit available
    # we multiply this by the debtRatio of our strategy out of 10_000 total
    # a vault only knows it has assets if the strategy has reported. also, if strategy assets are zero, we don't get additional yswaps profit.
    # so in this case, no difference expected between yswaps and non-yswaps strategies.
    assert (
        pytest.approx(
            strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
            rel=RELATIVE_APPROX,
        )
        == int(vault.totalAssets() * new_params["debtRatio"] / 10_000)
    )


# lower debtRatio to 0, donate, withdraw more than the donation, then harvest
def test_withdraw_after_donation_3(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    amount,
    sleep_time,
    is_slippery,
    no_profit,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    RELATIVE_APPROX,
    vault_address,
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
    prev_params = vault.strategies(strategy)

    # reduce our debtRatio to 0%
    currentDebt = prev_params["debtRatio"]
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    assert vault.strategies(strategy)["debtRatio"] == 0

    # our profit whale donates to the vault, what a nice person! 🐳
    donation = amount / 2
    token.transfer(strategy, donation, {"from": profit_whale})

    # have our whale withdraw more than the donation, ensuring we pull from strategy
    to_withdraw = donation * 1.05
    if vault_address == ZERO_ADDRESS:
        vault.withdraw(to_withdraw, {"from": whale})
    else:
        # convert since our PPS isn't 1 (live vault!)
        withdrawal_in_shares = to_withdraw * 1e18 / vault.pricePerShare()
        vault.withdraw(withdrawal_in_shares, {"from": whale})

    # simulate some earnings
    chain.sleep(sleep_time)

    # after our donation, best to use health check in case we have a big profit
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

    # harvest again so the strategy reports the profit
    if use_yswaps:
        print("Using ySwaps for harvests")
        (profit, loss) = harvest_strategy(
            use_yswaps,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            destination_strategy,
        )
    new_params = vault.strategies(strategy)

    # sleep 5 days to allow share price to normalize
    chain.sleep(86400 * 5)
    chain.mine(1)

    # specifically check that our profit is greater than our donation or at least close if we get slippage on deposit/withdrawal and have no profit
    profit = new_params["totalGain"] - prev_params["totalGain"]
    if is_slippery and no_profit:
        assert pytest.approx(profit, rel=RELATIVE_APPROX) == donation
    else:
        assert profit > donation

    # check that we didn't add any more loss, or close if we get slippage on deposit/withdrawal
    if is_slippery:
        assert (
            pytest.approx(new_params["totalLoss"], rel=RELATIVE_APPROX)
            == prev_params["totalLoss"]
        )
    else:
        assert new_params["totalLoss"] == prev_params["totalLoss"]

    # assert that our vault total assets, multiplied by our debtRatio, is about equal to our estimated total assets plus credit available
    # we multiply this by the debtRatio of our strategy out of 10_000 total
    # a vault only knows it has assets if the strategy has reported. also, if strategy assets are zero, we don't get additional yswaps profit.
    # so in this case, no difference expected between yswaps and non-yswaps strategies.
    assert (
        pytest.approx(
            strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
            rel=RELATIVE_APPROX,
        )
        == int(vault.totalAssets() * new_params["debtRatio"] / 10_000)
    )


# lower debtRatio to 50%, donate, withdraw more than the donation, then harvest
def test_withdraw_after_donation_4(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    amount,
    sleep_time,
    is_slippery,
    no_profit,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    RELATIVE_APPROX,
    vault_address,
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
    prev_params = vault.strategies(strategy)

    # reduce our debtRatio to 50%
    currentDebt = prev_params["debtRatio"]
    vault.updateStrategyDebtRatio(strategy, currentDebt / 2, {"from": gov})
    assert vault.strategies(strategy)["debtRatio"] == currentDebt / 2

    # our profit whale donates to the vault, what a nice person! 🐳
    donation = amount / 2
    token.transfer(strategy, donation, {"from": profit_whale})

    # have our whale withdraw more than the donation, ensuring we pull from strategy
    to_withdraw = donation * 1.05
    if vault_address == ZERO_ADDRESS:
        vault.withdraw(to_withdraw, {"from": whale})
    else:
        # convert since our PPS isn't 1 (live vault!)
        withdrawal_in_shares = to_withdraw * 1e18 / vault.pricePerShare()
        vault.withdraw(withdrawal_in_shares, {"from": whale})

    # simulate some earnings
    chain.sleep(sleep_time)

    # after our donation, best to use health check in case we have a big profit
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

    # harvest again so the strategy reports the profit
    if use_yswaps:
        print("Using ySwaps for harvests")
        (profit, loss) = harvest_strategy(
            use_yswaps,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            destination_strategy,
        )
    new_params = vault.strategies(strategy)

    # sleep 5 days to allow share price to normalize
    chain.sleep(86400 * 5)
    chain.mine(1)

    # specifically check that our profit is greater than our donation or at least close if we get slippage on deposit/withdrawal and have no profit
    profit = new_params["totalGain"] - prev_params["totalGain"]
    if is_slippery and no_profit:
        assert pytest.approx(profit, rel=RELATIVE_APPROX) == donation
    else:
        assert profit > donation

    # check that we didn't add any more loss, or close if we get slippage on deposit/withdrawal
    if is_slippery:
        assert (
            pytest.approx(new_params["totalLoss"], rel=RELATIVE_APPROX)
            == prev_params["totalLoss"]
        )
    else:
        assert new_params["totalLoss"] == prev_params["totalLoss"]

    # assert that our vault total assets, multiplied by our debtRatio, is about equal to our estimated total assets plus credit available
    # we multiply this by the debtRatio of our strategy out of 10_000 total
    # a vault only knows it has assets if the strategy has reported, and yswaps adds extra unrealized profit to the strategy since debtRatio > 0
    if use_yswaps:
        assert (
            pytest.approx(
                strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
                rel=RELATIVE_APPROX,
            )
            == int(
                vault.totalAssets() * new_params["debtRatio"] / 10_000 + profit_amount
            )
        )
    else:
        assert (
            pytest.approx(
                strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
                rel=RELATIVE_APPROX,
            )
            == int(vault.totalAssets() * new_params["debtRatio"] / 10_000)
        )


# donate, withdraw more than the donation, then harvest
def test_withdraw_after_donation_5(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    amount,
    sleep_time,
    is_slippery,
    no_profit,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    RELATIVE_APPROX,
    vault_address,
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
    prev_params = vault.strategies(strategy)

    # our profit whale donates to the vault, what a nice person! 🐳
    donation = amount / 2
    token.transfer(strategy, donation, {"from": profit_whale})

    # have our whale withdraw more than the donation, ensuring we pull from strategy
    to_withdraw = donation * 1.05
    if vault_address == ZERO_ADDRESS:
        vault.withdraw(to_withdraw, {"from": whale})
    else:
        # convert since our PPS isn't 1 (live vault!)
        withdrawal_in_shares = to_withdraw * 1e18 / vault.pricePerShare()
        vault.withdraw(withdrawal_in_shares, {"from": whale})

    # simulate some earnings
    chain.sleep(sleep_time)

    # after our donation, best to use health check in case we have a big profit
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

    # harvest again so the strategy reports the profit
    if use_yswaps:
        print("Using ySwaps for harvests")
        (profit, loss) = harvest_strategy(
            use_yswaps,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            destination_strategy,
        )
    new_params = vault.strategies(strategy)

    # sleep 5 days to allow share price to normalize
    chain.sleep(86400 * 5)
    chain.mine(1)

    # specifically check that our profit is greater than our donation or at least close if we get slippage on deposit/withdrawal and have no profit
    profit = new_params["totalGain"] - prev_params["totalGain"]
    if is_slippery and no_profit:
        assert pytest.approx(profit, rel=RELATIVE_APPROX) == donation
    else:
        assert profit > donation

    # check that we didn't add any more loss, or close if we get slippage on deposit/withdrawal
    if is_slippery:
        assert (
            pytest.approx(new_params["totalLoss"], rel=RELATIVE_APPROX)
            == prev_params["totalLoss"]
        )
    else:
        assert new_params["totalLoss"] == prev_params["totalLoss"]

    # assert that our vault total assets, multiplied by our debtRatio, is about equal to our estimated total assets plus credit available
    # we multiply this by the debtRatio of our strategy out of 10_000 total
    # a vault only knows it has assets if the strategy has reported, and yswaps adds extra unrealized profit to the strategy since debtRatio > 0
    if use_yswaps:
        assert (
            pytest.approx(
                strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
                rel=RELATIVE_APPROX,
            )
            == int(
                vault.totalAssets() * new_params["debtRatio"] / 10_000 + profit_amount
            )
        )
    else:
        assert (
            pytest.approx(
                strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
                rel=RELATIVE_APPROX,
            )
            == int(vault.totalAssets() * new_params["debtRatio"] / 10_000)
        )


# donate, withdraw less than the donation, then harvest
def test_withdraw_after_donation_6(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    amount,
    sleep_time,
    is_slippery,
    no_profit,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    RELATIVE_APPROX,
    vault_address,
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

    prev_params = vault.strategies(strategy)

    # our profit whale donates to the vault, what a nice person! 🐳
    donation = amount / 2
    token.transfer(strategy, donation, {"from": profit_whale})

    # have our whale withdraw half of the donation, this ensures that we test withdrawing without pulling from the staked balance
    to_withdraw = donation / 2
    if vault_address == ZERO_ADDRESS:
        vault.withdraw(to_withdraw, {"from": whale})
    else:
        # convert since our PPS isn't 1 (live vault!)
        withdrawal_in_shares = to_withdraw * 1e18 / vault.pricePerShare()
        vault.withdraw(withdrawal_in_shares, {"from": whale})

    # simulate some earnings
    chain.sleep(sleep_time)

    # after our donation, best to use health check in case our donation profit is too big
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

    # harvest again so the strategy reports the profit
    if use_yswaps:
        print("Using ySwaps for harvests")
        (profit, loss) = harvest_strategy(
            use_yswaps,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            destination_strategy,
        )
    new_params = vault.strategies(strategy)

    # sleep 5 days to allow share price to normalize
    chain.sleep(86400 * 5)
    chain.mine(1)

    # specifically check that our profit is greater than our donation or at least close if we get slippage on deposit/withdrawal and have no profit
    profit = new_params["totalGain"] - prev_params["totalGain"]
    if is_slippery and no_profit:
        assert pytest.approx(profit, rel=RELATIVE_APPROX) == donation
    else:
        assert profit > donation

    # check that we didn't add any more loss, or close if we get slippage on deposit/withdrawal
    if is_slippery:
        assert (
            pytest.approx(new_params["totalLoss"], rel=RELATIVE_APPROX)
            == prev_params["totalLoss"]
        )
    else:
        assert new_params["totalLoss"] == prev_params["totalLoss"]

    # assert that our vault total assets, multiplied by our debtRatio, is about equal to our estimated total assets plus credit available
    # we multiply this by the debtRatio of our strategy out of 10_000 total
    # a vault only knows it has assets if the strategy has reported, and yswaps adds extra unrealized profit to the strategy since debtRatio > 0
    if use_yswaps:
        assert (
            pytest.approx(
                strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
                rel=RELATIVE_APPROX,
            )
            == int(
                vault.totalAssets() * new_params["debtRatio"] / 10_000 + profit_amount
            )
        )
    else:
        assert (
            pytest.approx(
                strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
                rel=RELATIVE_APPROX,
            )
            == int(vault.totalAssets() * new_params["debtRatio"] / 10_000)
        )


# lower debtRatio to 0, donate, withdraw more than the donation, then harvest
# this is the same as test 3 but with some extra checks that the strategy is empty
def test_withdraw_after_donation_7(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    amount,
    sleep_time,
    is_slippery,
    no_profit,
    profit_whale,
    profit_amount,
    destination_strategy,
    vault_address,
    use_yswaps,
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
    prev_params = vault.strategies(strategy)
    prev_assets = vault.totalAssets()

    # reduce our debtRatio to 0%
    currentDebt = prev_params["debtRatio"]
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    assert vault.strategies(strategy)["debtRatio"] == 0

    # our profit whale donates to the vault, what a nice person! 🐳
    donation = amount / 2
    token.transfer(strategy, donation, {"from": profit_whale})

    # have our whale withdraw more than the donation, ensuring we pull from strategy
    to_withdraw = donation * 1.05
    if vault_address == ZERO_ADDRESS:
        vault.withdraw(to_withdraw, {"from": whale})
    else:
        # convert since our PPS isn't 1 (live vault!)
        withdrawal_in_shares = to_withdraw * 1e18 / vault.pricePerShare()
        vault.withdraw(withdrawal_in_shares, {"from": whale})

    # simulate some earnings
    chain.sleep(sleep_time)

    # after our donation, best to use health check in case we have a big profit
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

    # harvest again so the strategy reports the profit
    if use_yswaps:
        print("Using ySwaps for harvests")
        (profit, loss) = harvest_strategy(
            use_yswaps,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            destination_strategy,
        )
    new_params = vault.strategies(strategy)

    # sleep 5 days to allow share price to normalize
    chain.sleep(86400 * 5)
    chain.mine(1)

    # specifically check that our profit is greater than our donation or at least close if we get slippage on deposit/withdrawal and have no profit
    profit = new_params["totalGain"] - prev_params["totalGain"]
    if is_slippery and no_profit:
        assert pytest.approx(profit, rel=RELATIVE_APPROX) == donation
    else:
        assert profit > donation

    # check that we didn't add any more loss, or close if we get slippage on deposit/withdrawal
    if is_slippery:
        assert (
            pytest.approx(new_params["totalLoss"], rel=RELATIVE_APPROX)
            == prev_params["totalLoss"]
        )
    else:
        assert new_params["totalLoss"] == prev_params["totalLoss"]

    # assert that our vault total assets, multiplied by our debtRatio, is about equal to our estimated total assets plus credit available
    # we multiply this by the debtRatio of our strategy out of 10_000 total
    # a vault only knows it has assets if the strategy has reported. also, if strategy assets are zero, we don't get additional yswaps profit.
    # so in this case, no difference expected between yswaps and non-yswaps strategies.
    assert (
        pytest.approx(
            strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
            rel=RELATIVE_APPROX,
        )
        == int(vault.totalAssets() * new_params["debtRatio"] / 10_000)
    )

    # check everywhere to make sure we emptied out the strategy
    if is_slippery:
        assert strategy.estimatedTotalAssets() <= 10
    else:
        assert strategy.estimatedTotalAssets() == 0
    assert token.balanceOf(strategy) == 0
    current_assets = vault.totalAssets()

    # assert that our total assets have gone up or stayed the same when accounting for the donation and withdrawal, or that we're close at least
    if is_slippery and no_profit:
        assert (
            pytest.approx(donation - to_withdraw + prev_assets, rel=RELATIVE_APPROX)
            == current_assets
        )
    else:
        assert current_assets >= donation - to_withdraw + prev_assets

    new_params = vault.strategies(strategy)

    # assert that our strategy has no debt
    assert new_params["totalDebt"] == 0
    assert vault.totalDebt() == 0


# lower debtRatio to 0, donate, withdraw less than the donation, then harvest
# this is the same as test 2 but with some extra checks that the strategy is empty
def test_withdraw_after_donation_8(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    amount,
    sleep_time,
    is_slippery,
    no_profit,
    profit_whale,
    profit_amount,
    destination_strategy,
    vault_address,
    use_yswaps,
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
    prev_params = vault.strategies(strategy)
    prev_assets = vault.totalAssets()
    print("Prev assets:", prev_assets / 1e18)

    # reduce our debtRatio to 0%
    currentDebt = prev_params["debtRatio"]
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    assert vault.strategies(strategy)["debtRatio"] == 0

    # our profit whale donates to the vault, what a nice person! 🐳
    donation = amount / 2
    token.transfer(strategy, donation, {"from": profit_whale})

    # have our whale withdraw half of the donation, this ensures that we test withdrawing without pulling from the staked balance
    to_withdraw = donation / 2
    if vault_address == ZERO_ADDRESS:
        vault.withdraw(to_withdraw, {"from": whale})
    else:
        # convert since our PPS isn't 1 (live vault!)
        withdrawal_in_shares = to_withdraw * 1e18 / vault.pricePerShare()
        vault.withdraw(withdrawal_in_shares, {"from": whale})

    # simulate some earnings
    chain.sleep(sleep_time)

    # after our donation, best to use health check in case our donation profit is too big
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
    print("Harvest Profit:", profit)

    # harvest again so the strategy reports the profit
    if use_yswaps:
        print("Using ySwaps for harvests")
        (profit, loss) = harvest_strategy(
            use_yswaps,
            strategy,
            token,
            gov,
            profit_whale,
            profit_amount,
            destination_strategy,
        )
    new_params = vault.strategies(strategy)
    current_assets = vault.totalAssets()
    print("New assets:", current_assets / 1e18)

    # sleep 5 days to allow share price to normalize
    chain.sleep(86400 * 5)
    chain.mine(1)

    # specifically check that our profit is greater than our donation or at least close if we get slippage on deposit/withdrawal and have no profit
    profit = new_params["totalGain"] - prev_params["totalGain"]
    if is_slippery and no_profit:
        assert pytest.approx(profit, rel=RELATIVE_APPROX) == donation
    else:
        assert profit > donation

    # check that we didn't add any more loss, or close if we get slippage on deposit/withdrawal
    if is_slippery:
        assert (
            pytest.approx(new_params["totalLoss"], rel=RELATIVE_APPROX)
            == prev_params["totalLoss"]
        )
    else:
        assert new_params["totalLoss"] == prev_params["totalLoss"]

    # assert that our vault total assets, multiplied by our debtRatio, is about equal to our estimated total assets plus credit available
    # we multiply this by the debtRatio of our strategy out of 10_000 total
    # a vault only knows it has assets if the strategy has reported. also, if strategy assets are zero, we don't get additional yswaps profit.
    # so in this case, no difference expected between yswaps and non-yswaps strategies.
    assert (
        pytest.approx(
            strategy.estimatedTotalAssets() + vault.creditAvailable(strategy),
            rel=RELATIVE_APPROX,
        )
        == int(vault.totalAssets() * new_params["debtRatio"] / 10_000)
    )

    # check everywhere to make sure we emptied out the strategy
    if is_slippery:
        assert strategy.estimatedTotalAssets() <= 10
    else:
        assert strategy.estimatedTotalAssets() == 0
    assert token.balanceOf(strategy) == 0

    # assert that our total assets have gone up or stayed the same when accounting for the donation and withdrawal, or that we're close at least
    if is_slippery and no_profit:
        assert (
            pytest.approx(donation - to_withdraw + prev_assets, rel=RELATIVE_APPROX)
            == current_assets
        )
    else:
        assert current_assets >= donation - to_withdraw + prev_assets

    new_params = vault.strategies(strategy)

    # assert that our strategy has no debt
    assert new_params["totalDebt"] == 0
    assert vault.totalDebt() == 0
