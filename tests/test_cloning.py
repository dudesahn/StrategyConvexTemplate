import brownie
from brownie import chain
import pytest
from utils import harvest_strategy

# make sure cloned strategy works just like normal
def test_cloning(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    rewards,
    keeper,
    amount,
    sleep_time,
    is_slippery,
    no_profit,
    contract_name,
    is_clonable,
    tests_using_tenderly,
    strategy_name,
    profit_whale,
    profit_amount,
    destination_strategy,
    use_yswaps,
    destination_vault,
):

    # skip this test if we don't clone
    if not is_clonable:
        return

    ## deposit to the vault after approving like normal
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
    before_pps = vault.pricePerShare()

    # clone our strategy
    tx = strategy.cloneRouterStrategy(
        vault,
        strategist,
        rewards,
        keeper,
        destination_vault,
        strategy_name,
    )
    new_strategy = contract_name.at(tx.return_value)

    # tenderly doesn't work for "with brownie.reverts"
    if tests_using_tenderly == False:
        # Shouldn't be able to call initialize again
        with brownie.reverts():
            strategy.initialize(
                vault,
                strategist,
                rewards,
                keeper,
                destination_vault,
                strategy_name,
                {"from": gov},
            )

        # Shouldn't be able to call initialize again
        with brownie.reverts():
            new_strategy.initialize(
                vault,
                strategist,
                rewards,
                keeper,
                destination_vault,
                strategy_name,
                {"from": gov},
            )

            ## shouldn't be able to clone a clone
        with brownie.reverts():
            new_strategy.cloneRouterStrategy(
                vault,
                strategist,
                rewards,
                keeper,
                destination_vault,
                strategy_name,
                {"from": gov},
            )

    # revoke, get funds back into vault, remove old strat from queue
    vault.revokeStrategy(strategy, {"from": gov})
    (profit, loss) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )
    vault.removeStrategyFromQueue(strategy.address, {"from": gov})

    # attach our new strategy, ensure it's the only one
    vault.addStrategy(
        new_strategy.address, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov}
    )
    assert vault.withdrawalQueue(0) == new_strategy.address
    assert vault.strategies(new_strategy)["debtRatio"] == 10_000
    assert vault.strategies(strategy)["debtRatio"] == 0

    # harvest, store asset amount
    (profit, loss) = harvest_strategy(
        use_yswaps,
        new_strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )
    old_assets = vault.totalAssets()
    assert old_assets > 0
    assert token.balanceOf(new_strategy) == 0
    assert new_strategy.estimatedTotalAssets() > 0

    # simulate some earnings
    chain.sleep(sleep_time)

    # harvest after a day, store new asset amount
    (profit, loss) = harvest_strategy(
        use_yswaps,
        new_strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )
    new_assets = vault.totalAssets()

    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets >= old_assets

    # Display estimated APR based on the two days before the pay out
    print(
        "\nEstimated APR: ",
        "{:.2%}".format(
            ((new_assets - old_assets) * (365 * (86400 / sleep_time)))
            / (new_strategy.estimatedTotalAssets())
        ),
    )

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

    # make sure our PPS went us as well
    assert vault.pricePerShare() >= before_pps
