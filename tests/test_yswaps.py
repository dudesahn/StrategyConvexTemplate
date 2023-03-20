import brownie
from brownie import ZERO_ADDRESS, interface, chain
from utils import harvest_strategy

# test our permissionless swaps and our trade handler functions as intended
def test_keepers_and_trade_handler(
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
    keeper_wrapper,
    trade_factory,
):
    # no testing needed if we're not using yswaps
    if not use_yswaps:
        return

    ## deposit to the vault after approving
    starting_whale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    newWhale = token.balanceOf(whale)

    # harvest, store asset amount
    (profit, loss) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )

    # simulate profits
    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest, store new asset amount
    (profit, loss) = harvest_strategy(
        use_yswaps,
        strategy,
        token,
        gov,
        profit_whale,
        profit_amount,
        destination_strategy,
    )

    # set our keeper up
    strategy.setKeeper(keeper_wrapper, {"from": gov})

    # here we make sure we can harvest through our keeper wrapper
    keeper_wrapper.harvest(strategy, {"from": profit_whale})

    ####### ADD LOGIC AS NEEDED FOR SENDING REWARDS TO STRATEGY #######
    # send our strategy some LUSD. normally it would be sitting waiting for trade handler but we automatically process it
    lusd = interface.IERC20(strategy.lusd())
    lusd.transfer(strategy, 100e18, {"from": lusd_whale})

    # whale can't sweep, but trade handler can
    with brownie.reverts():
        lusd.transferFrom(
            strategy, whale, lusd.balanceOf(strategy) / 2, {"from": whale}
        )

    lusd.transferFrom(
        strategy, whale, lusd.balanceOf(strategy) / 2, {"from": trade_factory}
    )

    # remove our trade handler
    strategy.removeTradeFactoryPermissions(True, {"from": gov})
    assert strategy.tradeFactory() == ZERO_ADDRESS
    assert lusd.balanceOf(strategy) > 0

    # trade factory now cant sweep
    with brownie.reverts():
        lusd.transferFrom(
            strategy, whale, lusd.balanceOf(strategy) / 2, {"from": trade_factory}
        )

    # give back those permissions, now trade factory can sweep
    strategy.updateTradeFactory(trade_factory, {"from": gov})
    lusd.transferFrom(
        strategy, whale, lusd.balanceOf(strategy) / 2, {"from": trade_factory}
    )

    # remove again!
    strategy.removeTradeFactoryPermissions(False, {"from": gov})

    # update again
    strategy.updateTradeFactory(trade_factory, {"from": gov})

    # simulate profits
    chain.sleep(sleep_time)
    chain.mine(1)

    # can't set trade factory to zero
    with brownie.reverts():
        strategy.updateTradeFactory(ZERO_ADDRESS, {"from": gov})

    # update our rewards to just LUSD
    strategy.updateRewards([strategy.lusd()], {"from": gov})
    assert strategy.rewardsTokens(0) == strategy.lusd()

    # don't have another token here anymore
    with brownie.reverts():
        assert strategy.rewardsTokens(1) == ZERO_ADDRESS

    # only gov can update rewards
    with brownie.reverts():
        strategy.updateRewards([strategy.lusd()], {"from": whale})
