import brownie
from brownie import Contract, Wei
from brownie import config
import math

# test zapping in and out with weth, dai, usdc, usdt, wbtc, and eth
def test_zap_weth(
    weth,
    zapTarget,
    whale,
    amount,
    zap,
    vaultTarget,
    synth,
    chain,
):
    ## deposit to the vault after approving
    startingWhale = weth.balanceOf(whale)

    # adjust our amount for decimals
    amount = amount * 10 ** weth.decimals() * 13.99

    # approve and zap in our asset
    weth.approve(zap, 2 ** 256 - 1, {"from": whale})
    tx = zap.zapIn(weth, amount, vaultTarget, {"from": whale})

    newWhale = weth.balanceOf(whale)
    print("Balance of zap", weth.balanceOf(zap))
    assert startingWhale > newWhale
    print("Token used", startingWhale - newWhale)
    print("zap synth balance", synth.balanceOf(zap))

    sETH = Contract("0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb")
    print("sETH Balance", sETH.balanceOf(whale) / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    # finish our zap
    synth.approve(zap, 2 ** 256 - 1, {"from": whale})
    synth_balance = synth.balanceOf(whale)
    assert synth_balance > 0
    print("synth balance", synth.balanceOf(whale) / 1e18)
    tx = zap.synthToVault(synth, synth_balance, {"from": whale})

    # check that we have vault tokens
    assert vaultTarget.balanceOf(whale) > 0
    print("Whale vault token balance:", vaultTarget.balanceOf(whale) / 1e18)

    # test our zap out, approve it to spend our tokens
    vault_balance = vaultTarget.balanceOf(whale)
    vaultTarget.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.zapOut(vaultTarget, vault_balance, {"from": whale})
    seth_balance = sETH.balanceOf(whale)
    assert seth_balance > 0
    print("sETH Balance", seth_balance / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    token_balance = weth.balanceOf(whale)
    seth_balance = sETH.balanceOf(whale)
    sETH.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.sETHToWant(weth, seth_balance, {"from": whale})
    new_token_balance = weth.balanceOf(whale)
    assert new_token_balance > token_balance


def test_zap_wbtc(
    wbtc,
    zapTarget,
    whale,
    amount,
    zap,
    vaultTarget,
    synth,
    chain,
):
    ## deposit to the vault after approving
    startingWhale = wbtc.balanceOf(whale)

    # adjust our amount for decimals
    amount = amount * 10 ** wbtc.decimals()

    # approve and zap in our asset
    wbtc.approve(zap, 2 ** 256 - 1, {"from": whale})
    tx = zap.zapIn(wbtc, amount, vaultTarget, {"from": whale})

    newWhale = wbtc.balanceOf(whale)
    print("Balance of zap", wbtc.balanceOf(zap))
    assert startingWhale > newWhale
    print("Token used", startingWhale - newWhale)
    print("zap synth balance", synth.balanceOf(zap))

    sETH = Contract("0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb")
    print("sETH Balance", sETH.balanceOf(whale) / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    # finish our zap
    synth.approve(zap, 2 ** 256 - 1, {"from": whale})
    synth_balance = synth.balanceOf(whale)
    assert synth_balance > 0
    print("synth balance", synth.balanceOf(whale) / 1e18)
    tx = zap.synthToVault(synth, synth_balance, {"from": whale})

    # check that we have vault tokens
    assert vaultTarget.balanceOf(whale) > 0
    print("Whale vault token balance:", vaultTarget.balanceOf(whale) / 1e18)

    # test our zap out, approve it to spend our tokens
    vault_balance = vaultTarget.balanceOf(whale)
    vaultTarget.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.zapOut(vaultTarget, vault_balance, {"from": whale})
    seth_balance = sETH.balanceOf(whale)
    assert seth_balance > 0
    print("sETH Balance", seth_balance / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    token_balance = wbtc.balanceOf(whale)
    seth_balance = sETH.balanceOf(whale)
    sETH.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.sETHToWant(wbtc, seth_balance, {"from": whale})
    new_token_balance = wbtc.balanceOf(whale)
    assert new_token_balance > token_balance


def test_zap_usdc(
    usdc,
    zapTarget,
    whale,
    amount,
    zap,
    vaultTarget,
    synth,
    chain,
):
    ## deposit to the vault after approving
    startingWhale = usdc.balanceOf(whale)

    # adjust our amount for decimals
    amount = amount * 10 ** usdc.decimals() * 48194.21

    # approve and zap in our asset
    usdc.approve(zap, 2 ** 256 - 1, {"from": whale})
    tx = zap.zapIn(usdc, amount, vaultTarget, {"from": whale})

    newWhale = usdc.balanceOf(whale)
    print("Balance of zap", usdc.balanceOf(zap))
    assert startingWhale > newWhale
    print("Token used", startingWhale - newWhale)
    print("zap synth balance", synth.balanceOf(zap))

    sETH = Contract("0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb")
    print("sETH Balance", sETH.balanceOf(whale) / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    # finish our zap
    synth.approve(zap, 2 ** 256 - 1, {"from": whale})
    synth_balance = synth.balanceOf(whale)
    assert synth_balance > 0
    print("synth balance", synth.balanceOf(whale) / 1e18)
    tx = zap.synthToVault(synth, synth_balance, {"from": whale})

    # check that we have vault tokens
    assert vaultTarget.balanceOf(whale) > 0
    print("Whale vault token balance:", vaultTarget.balanceOf(whale) / 1e18)

    # test our zap out, approve it to spend our tokens
    vault_balance = vaultTarget.balanceOf(whale)
    vaultTarget.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.zapOut(vaultTarget, vault_balance, {"from": whale})
    seth_balance = sETH.balanceOf(whale)
    assert seth_balance > 0
    print("sETH Balance", seth_balance / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    token_balance = usdc.balanceOf(whale)
    seth_balance = sETH.balanceOf(whale)
    sETH.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.sETHToWant(usdc, seth_balance, {"from": whale})
    new_token_balance = usdc.balanceOf(whale)
    assert new_token_balance > token_balance


def test_zap_dai(
    dai,
    zapTarget,
    whale,
    amount,
    zap,
    vaultTarget,
    synth,
    chain,
    accounts,
):
    # need to use a different whale for DAI, avax bridge
    whale = accounts.at("0xE78388b4CE79068e89Bf8aA7f218eF6b9AB0e9d0", force=True)

    ## deposit to the vault after approving
    startingWhale = dai.balanceOf(whale)

    # adjust our amount for decimals
    amount = amount * 10 ** dai.decimals() * 48194.21

    # approve and zap in our asset
    dai.approve(zap, 2 ** 256 - 1, {"from": whale})
    tx = zap.zapIn(dai, amount, vaultTarget, {"from": whale})

    newWhale = dai.balanceOf(whale)
    print("Balance of zap", dai.balanceOf(zap))
    assert startingWhale > newWhale
    print("Token used", startingWhale - newWhale)
    print("zap synth balance", synth.balanceOf(zap))

    sETH = Contract("0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb")
    print("sETH Balance", sETH.balanceOf(whale) / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    # finish our zap
    synth.approve(zap, 2 ** 256 - 1, {"from": whale})
    synth_balance = synth.balanceOf(whale)
    assert synth_balance > 0
    print("synth balance", synth.balanceOf(whale) / 1e18)
    tx = zap.synthToVault(synth, synth_balance, {"from": whale})

    # check that we have vault tokens
    assert vaultTarget.balanceOf(whale) > 0
    print("Whale vault token balance:", vaultTarget.balanceOf(whale) / 1e18)

    # test our zap out, approve it to spend our tokens
    vault_balance = vaultTarget.balanceOf(whale)
    vaultTarget.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.zapOut(vaultTarget, vault_balance, {"from": whale})
    seth_balance = sETH.balanceOf(whale)
    assert seth_balance > 0
    print("sETH Balance", seth_balance / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    token_balance = dai.balanceOf(whale)
    seth_balance = sETH.balanceOf(whale)
    sETH.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.sETHToWant(dai, seth_balance, {"from": whale})
    new_token_balance = dai.balanceOf(whale)
    assert new_token_balance > token_balance


def test_zap_usdt(
    usdt,
    zapTarget,
    whale,
    amount,
    zap,
    vaultTarget,
    synth,
    chain,
):
    ## deposit to the vault after approving
    startingWhale = usdt.balanceOf(whale)

    # adjust our amount for decimals
    amount = amount * 10 ** usdt.decimals() * 48194.21

    # approve and zap in our asset
    usdt.approve(zap, 2 ** 256 - 1, {"from": whale})
    tx = zap.zapIn(usdt, amount, vaultTarget, {"from": whale})

    newWhale = usdt.balanceOf(whale)
    print("Balance of zap", usdt.balanceOf(zap))
    assert startingWhale > newWhale
    print("Token used", startingWhale - newWhale)
    print("zap synth balance", synth.balanceOf(zap))

    sETH = Contract("0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb")
    print("sETH Balance", sETH.balanceOf(whale) / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    # finish our zap
    synth.approve(zap, 2 ** 256 - 1, {"from": whale})
    synth_balance = synth.balanceOf(whale)
    assert synth_balance > 0
    print("synth balance", synth.balanceOf(whale) / 1e18)
    tx = zap.synthToVault(synth, synth_balance, {"from": whale})

    # check that we have vault tokens
    assert vaultTarget.balanceOf(whale) > 0
    print("Whale vault token balance:", vaultTarget.balanceOf(whale) / 1e18)

    # test our zap out, approve it to spend our tokens
    vault_balance = vaultTarget.balanceOf(whale)
    vaultTarget.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.zapOut(vaultTarget, vault_balance, {"from": whale})
    seth_balance = sETH.balanceOf(whale)
    assert seth_balance > 0
    print("sETH Balance", seth_balance / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    token_balance = usdt.balanceOf(whale)
    seth_balance = sETH.balanceOf(whale)
    sETH.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.sETHToWant(usdt, seth_balance, {"from": whale})
    new_token_balance = usdt.balanceOf(whale)
    assert new_token_balance > token_balance


def test_zap_eth(
    eth,
    weth,
    zapTarget,
    whale,
    amount,
    zap,
    vaultTarget,
    synth,
    chain,
):
    ## deposit to the vault after approving
    startingWhale = whale.balance()

    # adjust our amount for decimals
    amount = amount * 10 ** weth.decimals() * 13.99

    # approve and zap in our asset (don't need to approve for ETH)
    zap.zapIn(eth, amount, vaultTarget, {"value": Wei("13.99 ether"), "from": whale})

    newWhale = whale.balance()
    print("Balance of zap", zap.balance())
    assert startingWhale > newWhale
    print("Token used", startingWhale - newWhale)
    print("zap synth balance", synth.balanceOf(zap))

    sETH = Contract("0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb")
    print("sETH Balance", sETH.balanceOf(whale) / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    # finish our zap
    synth.approve(zap, 2 ** 256 - 1, {"from": whale})
    synth_balance = synth.balanceOf(whale)
    assert synth_balance > 0
    print("synth balance", synth.balanceOf(whale) / 1e18)
    tx = zap.synthToVault(synth, synth_balance, {"from": whale})

    # check that we have vault tokens
    assert vaultTarget.balanceOf(whale) > 0
    print("Whale vault token balance:", vaultTarget.balanceOf(whale) / 1e18)

    # test our zap out, approve it to spend our tokens
    vault_balance = vaultTarget.balanceOf(whale)
    vaultTarget.approve(zap, 2 ** 256 - 1, {"from": whale})
    zap.zapOut(vaultTarget, vault_balance, {"from": whale})
    seth_balance = sETH.balanceOf(whale)
    assert seth_balance > 0
    print("sETH Balance", seth_balance / 1e18)

    # sleep for 6 mins
    chain.mine(1)
    chain.sleep(361)

    eth_balance = whale.balance()
    seth_balance = sETH.balanceOf(whale)
    sETH.approve(zap, 2 ** 256 - 1, {"from": whale})
    tx = zap.sETHToWant(eth, seth_balance, {"from": whale})
    new_eth_balance = whale.balance()
    assert new_eth_balance > eth_balance
