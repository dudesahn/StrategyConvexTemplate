import pytest
from brownie import config, Wei, Contract
from eth_abi import encode_single

# Snapshots the chain before each test and reverts after test completion.
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


# put our pool's convex pid here; this is the only thing that should need to change up here **************
@pytest.fixture(scope="module")
def pid(zapTarget):
    if zapTarget == 0:  # sAUD
        pid = 44
    elif zapTarget == 1:  # sCHF
        pid = 46
    elif zapTarget == 2:  # sEUR
        pid = 45
    elif zapTarget == 3:  # sGBP
        pid = 43
    elif zapTarget == 4:  # sJPY
        pid = 42
    else:  # sKRW
        pid = 47
    yield pid


@pytest.fixture(scope="module")
def whale(accounts):
    # Totally in it for the tech
    # Update this with a large holder of your want token (BINANCE 8)
    whale = accounts.at("0xf977814e90da44bfa03b6295a0616a897441acec", force=True)
    yield whale


@pytest.fixture(scope="module")
def weth():  # this is the token we zap in
    yield Contract("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")


@pytest.fixture(scope="module")
def wbtc():  # this is the token we zap in
    yield Contract("0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599")


@pytest.fixture(scope="module")
def usdc():  # this is the token we zap in
    yield Contract("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")


@pytest.fixture(scope="module")
def dai():  # this is the token we zap in
    yield Contract("0x6B175474E89094C44Da98b954EedeAC495271d0F")


@pytest.fixture(scope="module")
def weth():  # this is the token we zap in
    yield Contract("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")


@pytest.fixture(scope="module")
def usdt():  # this is the token we zap in
    yield Contract("0xdAC17F958D2ee523a2206206994597C13D831ec7")


@pytest.fixture(scope="module")
def eth():  # this is the token we zap in
    eth = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
    yield eth


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance. Make sure to do no more than half of their balance.
@pytest.fixture(scope="module")
def amount():
    amount = 1
    yield amount


# this is the name we want to give our strategy
@pytest.fixture(scope="module")
def strategy_name():
    strategy_name = "StrategyConvexibEUR"
    yield strategy_name


@pytest.fixture(scope="module")
def synth(zapTarget):  # this is our target synth
    if zapTarget == 0:  # sAUD
        synth = Contract("0xF48e200EAF9906362BB1442fca31e0835773b8B4")
    elif zapTarget == 1:  # sCHF
        synth = Contract("0x0F83287FF768D1c1e17a42F44d644D7F22e8ee1d")
    elif zapTarget == 2:  # sEUR
        synth = Contract("0xD71eCFF9342A5Ced620049e616c5035F1dB98620")
    elif zapTarget == 3:  # sGBP
        synth = Contract("0x97fe22E7341a0Cd8Db6F6C021A24Dc8f4DAD855F")
    elif zapTarget == 4:  # sJPY
        synth = Contract("0xF6b1C627e95BFc3c1b4c9B825a032Ff0fBf3e07d")
    else:  # sKRW
        synth = Contract("0x269895a3dF4D73b077Fc823dD6dA1B95f72Aaf9B")
    yield synth


@pytest.fixture(scope="module")
def zapTarget():  # this is the synth we want to target.
    fiat = 2
    yield fiat


@pytest.fixture(scope="module")
def vaultTarget(zapTarget):  # this is the vault we want to target
    if zapTarget == 0:  # sAUD
        vault = Contract("0x1B905331F7DE2748F4D6A0678E1521E20347643F")
    elif zapTarget == 1:  # sCHF
        vault = Contract("0x490BD0886F221A5F79713D3E84404355A9293C50")
    elif zapTarget == 2:  # sEUR
        vault = Contract("0x67E019BFBD5A67207755D04467D6A70C0B75BF60")
    elif zapTarget == 3:  # sGBP
        vault = Contract("0x595A68A8C9D5C230001848B69B1947EE2A607164")
    elif zapTarget == 4:  # sJPY
        vault = Contract("0x59518884EEBFB03E90A18ADBAAAB770D4666471E")
    else:  # sKRW
        vault = Contract("0x528D50DC9A333F01544177A924893FA1F5B9F748")
    yield vault


# Only worry about changing things above this line, unless you want to make changes to the vault or strategy.
# ----------------------------------------------------------------------- #

# all contracts below should be able to stay static based on the pid
@pytest.fixture(scope="module")
def booster():  # this is the deposit contract
    yield Contract("0xF403C135812408BFbE8713b5A23a04b3D48AAE31")


@pytest.fixture(scope="function")
def voter():
    yield Contract("0xF147b8125d2ef93FB6965Db97D6746952a133934")


@pytest.fixture(scope="function")
def convexToken():
    yield Contract("0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B")


@pytest.fixture(scope="function")
def crv():
    yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")


@pytest.fixture(scope="module")
def other_vault_strategy():
    yield Contract("0x8423590CD0343c4E18d35aA780DF50a5751bebae")


@pytest.fixture(scope="function")
def proxy():
    yield Contract("0xA420A63BbEFfbda3B147d0585F1852C358e2C152")


@pytest.fixture(scope="module")
def curve_registry():
    yield Contract("0x90E00ACe148ca3b23Ac1bC8C240C2a7Dd9c2d7f5")


@pytest.fixture(scope="module")
def healthCheck():
    yield Contract("0xDDCea799fF1699e98EDF118e0629A974Df7DF012")


@pytest.fixture(scope="module")
def farmed():
    # this is the token that we are farming and selling for more of our want.
    yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")


# Define relevant tokens and contracts in this section
@pytest.fixture(scope="module")
def token():
    # this should be the address of the ERC-20 used by the strategy/vault
    token_address = "0x19b080FE1ffA0553469D20Ca36219F17Fcf03859"
    yield Contract(token_address)


# gauge for the curve pool
@pytest.fixture(scope="module")
def gauge():
    # this should be the address of the convex deposit token
    gauge = "0x99fb76F75501039089AAC8f20f487bf84E51d76F"
    yield Contract(gauge)


# curve deposit pool
@pytest.fixture(scope="module")
def pool(token, curve_registry):
    zero_address = "0x0000000000000000000000000000000000000000"
    if curve_registry.get_pool_from_lp_token(token) == zero_address:
        poolAddress = token
    else:
        _poolAddress = curve_registry.get_pool_from_lp_token(token)
        poolAddress = Contract(_poolAddress)
    yield poolAddress


@pytest.fixture(scope="module")
def cvxDeposit(booster, pid):
    # this should be the address of the convex deposit token
    cvx_address = booster.poolInfo(pid)[1]
    yield Contract(cvx_address)


@pytest.fixture(scope="module")
def rewardsContract(pid, booster):
    rewardsContract = booster.poolInfo(pid)[3]
    yield Contract(rewardsContract)


# Define any accounts in this section
# for live testing, governance is the strategist MS; we will update this before we endorse
# normal gov is ychad, 0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52
@pytest.fixture(scope="module")
def gov(accounts):
    yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)


@pytest.fixture(scope="module")
def strategist_ms(accounts):
    # like governance, but better
    yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)


@pytest.fixture(scope="module")
def keeper(accounts):
    yield accounts.at("0xBedf3Cf16ba1FcE6c3B751903Cf77E51d51E05b8", force=True)


@pytest.fixture(scope="module")
def rewards(accounts):
    yield accounts.at("0x8Ef63b525fceF7f8662D98F77f5C9A86ae7dFE09", force=True)


@pytest.fixture(scope="module")
def guardian(accounts):
    yield accounts[2]


@pytest.fixture(scope="module")
def management(accounts):
    yield accounts[3]


@pytest.fixture(scope="module")
def strategist(accounts):
    yield accounts.at("0xBedf3Cf16ba1FcE6c3B751903Cf77E51d51E05b8", force=True)


# replace the first value with the name of your strategy
@pytest.fixture(scope="function")
def zap(
    FixedForexZap,
    strategist,
    token,
    chain,
    synth,
    accounts,
):
    # force open the markets if they're closed
    _target = synth.target()
    target = Contract(_target)
    currencyKey = [target.currencyKey()]
    systemStatus = Contract("0x1c86B3CDF2a60Ae3a574f7f71d44E2C50BDdB87E")
    synthGod = accounts.at("0xc105ea57eb434fbe44690d7dec2702e4a2fbfcf7", force=True)
    systemStatus.resumeSynthsExchange(currencyKey, {"from": synthGod})

    # deploy our zap
    zap = strategist.deploy(FixedForexZap)
    yield zap
