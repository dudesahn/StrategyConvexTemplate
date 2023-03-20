import brownie
from brownie import Contract, chain, ZERO_ADDRESS
import pytest
from utils import harvest_strategy, check_status

# this module includes other tests we may need to generate, for instance to get best possible coverage on prepareReturn or liquidatePosition
# do any extra testing here to hit all parts of liquidatePosition
# generally this involves sending away all assets and then withdrawing before another harvest
def test_liquidatePosition(
    gov,
    token,
    vault,
    whale,
    strategy,
    amount,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    destination_vault,
    is_slippery,
    RELATIVE_APPROX,
    vault_address,
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

    # check our current status
    print("\nAfter first harvest")
    strategy_params = check_status(strategy, vault)

    # evaluate our current total assets
    old_assets = vault.totalAssets()
    initial_debt = strategy_params["totalDebt"]
    starting_share_price = vault.pricePerShare()
    initial_strategy_assets = strategy.estimatedTotalAssets()

    ################# SEND ALL FUNDS AWAY. ADJUST AS NEEDED PER STRATEGY. #################
    to_send = destination_vault.balanceOf(strategy)
    destination_vault.transfer(gov, to_send, {"from": strategy})

    # check our current status
    print("\nAfter fund transfer, before withdrawal")
    strategy_params = check_status(strategy, vault)

    # we shouldn't have taken any actual losses yet, and debt/DR/share price should all still be the same
    assert strategy_params["debtRatio"] == 10_000
    assert strategy_params["totalLoss"] == 0
    assert strategy_params["totalDebt"] == initial_debt == old_assets
    assert vault.pricePerShare() == starting_share_price

    # if slippery, then assets may differ slightly from debt
    if is_slippery:
        assert (
            pytest.approx(initial_debt, rel=RELATIVE_APPROX) == initial_strategy_assets
        )
    else:
        assert initial_debt == initial_strategy_assets

    # confirm we emptied the strategy
    assert strategy.estimatedTotalAssets() == 0

    # calculate how much of our vault tokens our whale holds
    whale_holdings = vault.balanceOf(whale) / vault.totalSupply() * 10_000
    print("Whale Holdings:", whale_holdings)

    # withdraw and see how down bad we are, confirm we can withdraw from an empty vault
    # it's important to do this before harvesting, also allow max loss
    vault.withdraw(vault.balanceOf(whale), whale, 10_000, {"from": whale})

    # check our current status
    print("\nAfter withdrawal")
    strategy_params = check_status(strategy, vault)

    # this is where we branch. if we have an existing vault we assume there are other holders. if not, we assumed 100% loss on withdrawal.
    if vault_address == ZERO_ADDRESS:
        # because we only withdrew, and didn't harvest, only the withdrawn portion of assets will be known as a loss
        # however, if we own all of the vault, this is a moot point
        assert strategy_params["totalGain"] == 0

        # if we burn all vault shares, then price per share is 1.0
        assert vault.pricePerShare() == 10 ** token.decimals()

        # everything is gone, except for our debtOutstanding 😅
        assert strategy_params["debtRatio"] == 0
        assert strategy_params["totalLoss"] == initial_debt == old_assets
        assert strategy_params["totalDebt"] == 0

        # if total debt is equal to zero, then debt outsanding is also zero
        assert vault.debtOutstanding(strategy) == 0

        if is_slippery:
            # remaining debt, plus whale's deposits, should be approximately our old assets
            assert (
                pytest.approx(
                    strategy_params["totalDebt"] + amount, rel=RELATIVE_APPROX
                )
                == old_assets
            )
            # DR scales proportionally with the holdings of our whale (ie, x% of vault that was lost)
            assert (
                pytest.approx(strategy_params["debtRatio"], rel=RELATIVE_APPROX)
                == whale_holdings
            )
            # vault assets will still be the same minus the "withdrawn" assets
            assert (
                pytest.approx(vault.totalAssets() + amount, rel=RELATIVE_APPROX)
                == old_assets
            )
            # debt outstanding is the portion of debt that needs to be paid back (DR is still greater than zero)
            assert (
                pytest.approx(
                    vault.totalAssets()
                    * (10_000 - strategy_params["debtRatio"])
                    / 10_000,
                    rel=RELATIVE_APPROX,
                )
                == vault.debtOutstanding(strategy)
            )
        else:
            assert strategy_params["totalDebt"] + amount == old_assets
            assert strategy_params["debtRatio"] == whale_holdings
            assert vault.totalAssets() + amount == old_assets
            assert vault.totalAssets() * (
                10_000 - strategy_params["debtRatio"]
            ) / 10_000 == vault.debtOutstanding(strategy)

    else:
        # because we only withdrew, and didn't harvest, only the withdrawn portion of assets will be known as a loss
        # this means total loss isn't all of our debt, and share price won't be zero yet
        assert strategy_params["totalLoss"] > 0
        assert strategy_params["totalGain"] == 0

        # share price isn't affected since shares are burned proportionally with losses
        assert vault.pricePerShare() == starting_share_price

        if is_slippery:
            # remaining debt, plus whale's deposits, should be approximately our old assets
            assert (
                pytest.approx(
                    strategy_params["totalDebt"] + amount, rel=RELATIVE_APPROX
                )
                == old_assets
            )
            # DR scales proportionally with the holdings of our whale (ie, x% of vault that was lost)
            assert (
                pytest.approx(strategy_params["debtRatio"], rel=RELATIVE_APPROX)
                == whale_holdings
            )
            # vault assets will still be the same minus the "withdrawn" assets
            assert (
                pytest.approx(vault.totalAssets() + amount, rel=RELATIVE_APPROX)
                == old_assets
            )
            # debt outstanding is the portion of debt that needs to be paid back (DR is still greater than zero)
            assert (
                pytest.approx(
                    vault.totalAssets()
                    * (10_000 - strategy_params["debtRatio"])
                    / 10_000,
                    rel=RELATIVE_APPROX,
                )
                == vault.debtOutstanding(strategy)
            )
        else:
            assert strategy_params["totalDebt"] + amount == old_assets
            assert strategy_params["debtRatio"] == whale_holdings
            assert vault.totalAssets() + amount == old_assets
            assert vault.totalAssets() * (
                10_000 - strategy_params["debtRatio"]
            ) / 10_000 == vault.debtOutstanding(strategy)

    # confirm that the strategy has no funds
    assert strategy.estimatedTotalAssets() == 0


# there also may be situations where the destination protocol is exploited or funds are locked but you still hold the same number of wrapper tokens
# though liquity doesn't have this as an option, it's important to test if it is to make sure debt is maintained properly in the case future assets free up
def test_locked_funds(
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
    old_vault,
    destination_vault,
):
    # should update this one for Router
    print("No way to test this for current strategy")


# here we take a loss intentionally without entering emergencyExit
def test_rekt(
    gov,
    token,
    vault,
    whale,
    strategy,
    amount,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    old_vault,
    destination_vault,
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

    # check our current status
    print("\nAfter first harvest")
    strategy_params = check_status(strategy, vault)

    # evaluate our current total assets
    old_assets = vault.totalAssets()
    initial_strategy_assets = strategy.estimatedTotalAssets()
    initial_debt = strategy_params["totalDebt"]
    starting_share_price = vault.pricePerShare()

    ################# SEND ALL FUNDS AWAY. ADJUST AS NEEDED PER STRATEGY. #################
    to_send = destination_vault.balanceOf(strategy)
    destination_vault.transfer(gov, to_send, {"from": strategy})

    # confirm we emptied the strategy
    assert strategy.estimatedTotalAssets() == 0

    # our whale donates 5 wei to the vault so we don't divide by zero (needed for older vaults)
    if old_vault:
        token.transfer(strategy, 5, {"from": whale})

    # set debtRatio to zero so we try and pull everything that we can out. turn off health check because of massive losses
    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
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
    # assert strategy.estimatedTotalAssets() == 0

    if old_vault:
        assert vault.totalAssets() == 5
    else:
        assert vault.totalAssets() == 0

    # simulate 5 days of waiting for share price to bump back up
    chain.sleep(86400 * 5)
    chain.mine(1)

    # withdraw and see how down bad we are, confirm we can withdraw from an empty vault
    vault.withdraw({"from": whale})

    print(
        "Raw loss:",
        (starting_whale - token.balanceOf(whale)) / 1e18,
        "Percentage:",
        (starting_whale - token.balanceOf(whale)) / starting_whale,
    )
    print("Share price:", vault.pricePerShare() / 1e18)


def test_weird_reverts(
    gov,
    token,
    vault,
    whale,
    strategy,
    destination_strategy,
):

    # only vault can call this
    with brownie.reverts():
        strategy.migrate(whale, {"from": gov})

    # can't migrate to a different vault
    with brownie.reverts():
        vault.migrateStrategy(strategy, destination_strategy, {"from": gov})

    # can't withdraw from a non-vault address
    with brownie.reverts():
        strategy.withdraw(1e18, {"from": gov})


# this test makes sure we can still harvest without any assets but still get our profits
# can also test here whether we claim rewards from an empty strategy, some protocols will revert
def test_empty_strat(
    gov,
    token,
    vault,
    whale,
    strategy,
    amount,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    destination_vault,
    old_vault,
    is_slippery,
    RELATIVE_APPROX,
    vault_address,
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

    # check our current status
    print("\nAfter first harvest")
    strategy_params = check_status(strategy, vault)

    # evaluate our current total assets
    old_assets = vault.totalAssets()
    initial_strategy_assets = strategy.estimatedTotalAssets()
    initial_debt = strategy_params["totalDebt"]
    starting_share_price = vault.pricePerShare()

    ################# SEND ALL FUNDS AWAY. ADJUST AS NEEDED PER STRATEGY. #################
    to_send = destination_vault.balanceOf(strategy)
    destination_vault.transfer(gov, to_send, {"from": strategy})

    # confirm we emptied the strategy
    assert strategy.estimatedTotalAssets() == 0

    # check that our losses are approximately the whole strategy
    print("\nBefore dust transfer, after main fund transfer")
    strategy_params = check_status(strategy, vault)

    # we shouldn't have taken any actual losses yet, and debt/DR/share price should all still be the same
    assert strategy_params["debtRatio"] == 10_000
    assert strategy_params["totalLoss"] == 0
    assert strategy_params["totalDebt"] == initial_debt == old_assets
    assert vault.pricePerShare() == starting_share_price

    # if slippery, then assets may differ slightly from debt
    if is_slippery:
        assert (
            pytest.approx(initial_debt, rel=RELATIVE_APPROX) == initial_strategy_assets
        )
    else:
        assert initial_debt == initial_strategy_assets

    # confirm we emptied the strategy
    assert strategy.estimatedTotalAssets() == 0

    # our whale donates 5 wei to the vault so we don't divide by zero (needed for older vaults)
    # old vaults also don't have the totalIdle var
    if old_vault:
        dust_donation = 5
        token.transfer(strategy, dust_donation, {"from": whale})
        assert strategy.estimatedTotalAssets() == dust_donation
    else:
        total_idle = vault.totalIdle()
        assert total_idle == 0

    # check our current status
    print("\nBefore harvest, after funds transfer out + dust transfer in")
    strategy_params = check_status(strategy, vault)

    # we shouldn't have taken any actual losses yet, and debt/DR/share price should all still be the same
    assert strategy_params["debtRatio"] == 10_000
    assert strategy_params["totalLoss"] == 0
    assert strategy_params["totalDebt"] == initial_debt == old_assets
    assert vault.pricePerShare() == starting_share_price
    assert vault.debtOutstanding(strategy) == 0

    # accept our losses, sad day 🥲
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
    assert loss > 0

    # check our status
    print("\nAfter our big time loss")
    strategy_params = check_status(strategy, vault)

    # DR goes to zero, loss is > 0, gain and debt should be near zero (zero for new vaults), share price also nearr zero (bye-bye assets 💀)
    assert strategy_params["debtRatio"] == 0
    assert strategy_params["totalLoss"] > 0
    assert strategy_params["totalGain"] == 0
    assert vault.pricePerShare() == 0

    # vault should also have no assets, except old ones will have 5 wei
    if old_vault:
        assert strategy_params["totalDebt"] == dust_donation == vault.totalAssets()
        assert strategy.estimatedTotalAssets() <= dust_donation
    else:
        assert strategy_params["totalDebt"] == 0 == vault.totalAssets()
        total_idle = vault.totalIdle()
        assert total_idle == 0
        assert strategy.estimatedTotalAssets() == 0

    # some profits fall from the heavens
    # this should be used to pay down debt vs taking profits
    token.transfer(strategy, profit_amount, {"from": profit_whale})
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
    assert profit > 0
    share_price = vault.pricePerShare()
    assert share_price > 0
    print("Share price:", share_price)


# this test makes sure we can still harvest without any profit and not revert
# for some strategies it may be impossible to harvest without generating profit, especially if not using yswaps
def test_no_profit(
    gov,
    token,
    vault,
    whale,
    strategy,
    amount,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    sleep_time,
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

    # check our current status
    print("\nAfter first harvest")
    strategy_params = check_status(strategy, vault)

    # evaluate our current total assets
    old_assets = vault.totalAssets()
    initial_strategy_assets = strategy.estimatedTotalAssets()
    initial_debt = strategy_params["totalDebt"]
    starting_share_price = vault.pricePerShare()

    # sleep
    chain.sleep(sleep_time)

    # if are using yswaps and we don't want profit, don't use yswaps (False for first argument).
    # Or just don't harvest our destination strategy, can pass 0 for profit_amount and use if statement in utils
    (profit, loss) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        0,
        destination_strategy,
    )

    # check our current status
    print("\nAfter harvest")
    strategy_params = check_status(strategy, vault)

    assert profit == 0
    assert vault.pricePerShare() == starting_share_price
