import brownie
from brownie import Contract
import time
import web3
from eth_abi import encode_single, encode_abi
from brownie.convert import to_bytes
from eth_abi.packed import encode_abi_packed
import eth_utils


def test_yswap(
    gov,
    vault,
    strategy,
    strategist,
    token,
    dai,
    weth,
    amount,
    Contract,
    curve_zapper,
    chain,
    interface,
    uniswap_router,
    sushiswap_router,
    whale,
    ymechs_safe,
    trade_factory,
    crv,
    convexToken,
    multicall_swapper,
):
    vault_before = token.balanceOf(vault)
    strat_before = token.balanceOf(strategy)
    ## deposit to the vault after approving
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    vault_after = token.balanceOf(vault)

    strategy.harvest({"from": strategist})

    chain.sleep(60 * 60 * 6)
    chain.mine(10)
    strategy.harvest({"from": strategist})

    token_out = interface.ERC20(vault.token())

    ins = [crv, convexToken]

    if strategy.hasRewards():
        ins.append(interface.ERC20(strategy.rewardsToken()))

    print(f"Executing trades...")
    for id in ins:

        print(id.address)
        receiver = strategy.address
        token_in = id

        amount_in = id.balanceOf(strategy)
        print(
            f"Executing trade {id}, tokenIn: {token_in} -> tokenOut {token_out} amount {amount_in}"
        )

        if amount_in == 0:
            continue

        asyncTradeExecutionDetails = [strategy, token_in, token_out, amount_in, 1]

        # always start with optimisations. 5 is CallOnlyNoValue
        optimsations = [["uint8"], [5]]
        a = optimsations[0]
        b = optimsations[1]

        calldata = token_in.approve.encode_input(sushiswap_router, amount_in)
        t = createTx(token_in, calldata)
        a = a + t[0]
        b = b + t[1]

        path = [token_in.address, weth, dai]
        calldata = sushiswap_router.swapExactTokensForTokens.encode_input(
            amount_in, 0, path, multicall_swapper, 2**256 - 1
        )
        t = createTx(sushiswap_router, calldata)
        a = a + t[0]
        b = b + t[1]

        expectedOut = sushiswap_router.getAmountsOut(amount_in, path)[2]
        calldata = dai.approve.encode_input(curve_zapper, expectedOut)
        t = createTx(dai, calldata)
        a = a + t[0]
        b = b + t[1]

        calldata = curve_zapper.add_liquidity.encode_input(
            token_out, [0, expectedOut, 0, 0], 0
        )
        t = createTx(curve_zapper, calldata)
        a = a + t[0]
        b = b + t[1]

        expectedOut = (
            curve_zapper.calc_token_amount(token_out, [0, expectedOut, 0, 0], True)
            * 0.98
        )  # less because it doesnt take into account fees
        calldata = token_out.transfer.encode_input(receiver, expectedOut)
        t = createTx(token_out, calldata)
        a = a + t[0]
        b = b + t[1]

        transaction = encode_abi_packed(a, b)

        # min out must be at least 1 to ensure that the tx works correctly
        # trade_factory.execute["uint256, address, uint, bytes"](
        #    multicall_swapper.address, 1, transaction, {"from": ymechs_safe}
        # )
        trade_factory.execute["tuple,address,bytes"](
            asyncTradeExecutionDetails,
            multicall_swapper.address,
            transaction,
            {"from": ymechs_safe},
        )
        print(token_out.balanceOf(strategy))
    tx = strategy.harvest({"from": strategist})
    print(tx.events)
    assert tx.events["Harvested"]["profit"] > 0

    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    strategy.harvest({"from": strategist})
    assert token.balanceOf(vault) > amount
    assert strategy.estimatedTotalAssets() == 0


def createTx(to, data):
    inBytes = eth_utils.to_bytes(hexstr=data)
    return [["address", "uint256", "bytes"], [to.address, len(inBytes), inBytes]]
