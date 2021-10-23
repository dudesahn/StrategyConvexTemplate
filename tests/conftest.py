import pytest
from brownie import config, Wei, Contract
from eth_abi import encode_single

# Snapshots the chain before each test and reverts after test completion.
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


# put our pool's convex pid here; this is the only thing that should need to change up here **************
@pytest.fixture(scope="module")
def pid():
    pid = 45
    yield pid


@pytest.fixture(scope="module")
def whale(accounts):
    # Totally in it for the tech
    # Update this with a large holder of your want token (attenboro.eth, holding some ibEUR LPs)
    whale = accounts.at("0x3Ee505bA316879d246a8fD2b3d7eE63b51B44FAB", force=True)
    yield whale


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance. Make sure to do no more than half of their balance.
@pytest.fixture(scope="module")
def amount():
    amount = 5_000e18
    yield amount


# this is the name we want to give our strategy
@pytest.fixture(scope="module")
def strategy_name():
    strategy_name = "StrategyConvexibEUR"
    yield strategy_name


@pytest.fixture(scope="module")
def sToken():  # this is the token we swap CRV for and then deposit to our LP
    yield Contract("0xD71eCFF9342A5Ced620049e616c5035F1dB98620")


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


# # list any existing strategies here
# @pytest.fixture(scope="module")
# def LiveStrategy_1():
#     yield Contract("0xC1810aa7F733269C39D640f240555d0A4ebF4264")


# use this if you need to deploy the vault
@pytest.fixture(scope="function")
def vault(pm, gov, rewards, guardian, management, token, chain):
    Vault = pm(config["dependencies"][0]).Vault
    vault = guardian.deploy(Vault)
    vault.initialize(token, gov, rewards, "", "", guardian)
    vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
    vault.setManagement(management, {"from": gov})
    chain.sleep(1)
    yield vault


# use this if your vault is already deployed
# @pytest.fixture(scope="function")
# def vault(pm, gov, rewards, guardian, management, token, chain):
#     vault = Contract("0x497590d2d57f05cf8B42A36062fA53eBAe283498")
#     yield vault


# replace the first value with the name of your strategy
@pytest.fixture(scope="function")
def strategy(
    StrategyConvexFixedForexClonable,
    strategist,
    keeper,
    vault,
    gov,
    guardian,
    token,
    healthCheck,
    chain,
    proxy,
    pool,
    strategy_name,
    sToken,
    gauge,
    accounts,
    pid,
):
    # harvest our live curve vault/strat and remove its funds from voter/gauges
    live_strat = Contract("0xB431A88a6cFFfa66dBCf96Ebc89aE72Ff7Fcc34f")
    live_vault = Contract(live_strat.vault())
    live_vault.updateStrategyDebtRatio(live_strat, 0, {"from": gov})
    live_strat.harvest({"from": gov})

    # force open the markets if they're closed
    _target = sToken.target()
    target = Contract(_target)
    currencyKey = [target.currencyKey()]
    systemStatus = Contract("0x1c86B3CDF2a60Ae3a574f7f71d44E2C50BDdB87E")
    synthGod = accounts.at("0xc105ea57eb434fbe44690d7dec2702e4a2fbfcf7", force=True)
    systemStatus.resumeSynthsExchange(currencyKey, {"from": synthGod})

    # parameters for this are: strategy, vault, max deposit, minTimePerInvest, slippage protection (10000 = 100% slippage allowed),
    strategy = strategist.deploy(
        StrategyConvexFixedForexClonable, vault, pid, pool, sToken, strategy_name
    )
    strategy.setKeeper(keeper, {"from": gov})
    # set our management fee to zero so it doesn't mess with our profit checking
    vault.setManagementFee(0, {"from": gov})
    # add our new strategy
    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    strategy.setHealthCheck(healthCheck, {"from": gov})
    strategy.setDoHealthCheck(True, {"from": gov})
    strategy.tend({"from": gov})
    chain.mine(1)
    chain.sleep(361)
    strategy.harvest({"from": gov})
    chain.sleep(1)
    yield strategy


@pytest.fixture(scope="module")
def dummy_gas_oracle(strategist, dummyBasefee):
    dummy_gas_oracle = strategist.deploy(dummyBasefee)
    yield dummy_gas_oracle


# use this if your strategy is already deployed
# @pytest.fixture(scope="function")
# def strategy():
#     # parameters for this are: strategy, vault, max deposit, minTimePerInvest, slippage protection (10000 = 100% slippage allowed),
#     strategy = Contract("0xC1810aa7F733269C39D640f240555d0A4ebF4264")
#     yield strategy
