import brownie
from brownie import Contract
import time
import web3
from eth_abi import encode_single, encode_abi
from brownie.convert import to_bytes
from eth_abi.packed import encode_abi_packed
import eth_utils


def test_spell_yswap(
    gov,
    live_spell_strat,
    dai,
    weth,
    amount,
    Contract,
    curve_zapper,
    chain,
    accounts,
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
    strategy = live_spell_strat
    vault = Contract(strategy.vault())
    token = Contract(vault.token())
    print(token)
    curve_zapper = Contract(token.minter())
    whale = accounts.at(
        "0xF9A2Fa22CB7Df26E3a10622C696f37fC345c6239", force=True
    )  # prob needs changing a lot
    strategist = accounts.at(strategy.strategist(), force=True)
    amount = 1_000 * 1e18
    gov = accounts.at(vault.governance(), force=True)

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

    token_out = token

    ins = [crv, convexToken]

    if strategy.hasRewards():
        ins.append(interface.ERC20(strategy.rewardsToken()))
        print(strategy.rewardsToken())

    print(f"Executing trades...")
    for id in ins:

        print(id.address)
        receiver = strategy.address
        token_in = id

        amount_in = id.balanceOf(strategy)
        print(
            f"Executing trade {id}, tokenIn: {token_in} -> tokenOut {token_out} amount {amount_in}"
        )

        asyncTradeExecutionDetails = [strategy, token_in, token_out, amount_in, 1]

        # always start with optimisations. 5 is CallOnlyNoValue
        optimsations = [["uint8"], [5]]
        a = optimsations[0]
        b = optimsations[1]

        calldata = token_in.approve.encode_input(sushiswap_router, amount_in)
        t = createTx(token_in, calldata)
        a = a + t[0]
        b = b + t[1]

        path = [token_in.address, weth]
        calldata = sushiswap_router.swapExactTokensForTokens.encode_input(
            amount_in, 0, path, multicall_swapper, 2**256 - 1
        )
        t = createTx(sushiswap_router, calldata)
        a = a + t[0]
        b = b + t[1]

        expectedOut = sushiswap_router.getAmountsOut(amount_in, path)[1]
        calldata = weth.approve.encode_input(curve_zapper, expectedOut)
        t = createTx(weth, calldata)
        a = a + t[0]
        b = b + t[1]

        calldata = curve_zapper.add_liquidity.encode_input([expectedOut, 0], 0, False)
        t = createTx(curve_zapper, calldata)
        a = a + t[0]
        b = b + t[1]

        expectedOut = (
            curve_zapper.calc_token_amount([expectedOut, 0]) * 0.98
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
    print(tx.events["Harvested"])
    assert tx.events["Harvested"]["profit"] > 0

    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    strategy.harvest({"from": strategist})
    print(token.balanceOf(vault) / 1e18)
    print(strategy.estimatedTotalAssets() / 1e18)
    assert token.balanceOf(vault) > amount
    assert strategy.estimatedTotalAssets() == 0


def createTx(to, data):
    inBytes = eth_utils.to_bytes(hexstr=data)
    return [["address", "uint256", "bytes"], [to.address, len(inBytes), inBytes]]
