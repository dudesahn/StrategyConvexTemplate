import brownie
from brownie import Contract
import time

def test_yswap(
    gov,
    vault,
    strategy,
    strategist,
    token,
    weth,
    amount,
    chain,
    uniswap_router,
    whale,
    ymechs_safe,
    trade_factory,
    multicall_swapper
):
    vault_before = token.balanceOf(vault)
    strat_before = token.balanceOf(strategy)
    ## deposit to the vault after approving
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})
    vault_after = token.balanceOf(vault)

    strategy.harvest({"from": strategist})

    chain.sleep(60*60*6) 
    chain.mine(10)
    strategy.harvest({"from": strategist})
    

    print(f"Executing trades...")
    for id in trade_factory.pendingTradesIds(strategy):
        trade = trade_factory.pendingTradesById(id).dict()
        print(trade)
        token_in = trade["_tokenIn"]
        token_out = trade["_tokenOut"]
        print(f"Executing trade {id}, tokenIn: {token_in} -> tokenOut {token_out}")

        #path = [toke_token.address, token.address]
        #trade_data = encode_abi(["address[]"], [path])

        path = [token_in, weth]
        calldata = uniswap_router.swapExactTokensForTokens.encode_input(amount, 0, path, trade_factory, 2**256-1)
        
        trade_factory.execute["uint256, address, uint, bytes"](id, multicall_swapper.address, 0, calldata, {"from": ymechs_safe})

        #path = [toke_token.address, token.address]
        #trade_data = encode_abi(["address[]"], [path])
        #trade_factory.execute["uint256, address, uint, bytes"](id, sushi_swapper.address, Wei("0.1 ether"), trade_data, {"from": ymechs_safe})