import pytest
from brownie import config, Wei, Contract, Splitter
import requests

# Snapshots the chain before each test and reverts after test completion.
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


################################################## TENDERLY DEBUGGING ##################################################

# change autouse to True if we want to use this fork to help debug tests
@pytest.fixture(scope="module", autouse=False)
def tenderly_fork(web3, chain):
    fork_base_url = "https://simulate.yearn.network/fork"
    payload = {"network_id": str(chain.id)}
    resp = requests.post(fork_base_url, headers={}, json=payload)
    fork_id = resp.json()["simulation_fork"]["id"]
    fork_rpc_url = f"https://rpc.tenderly.co/fork/{fork_id}"
    print(fork_rpc_url)
    tenderly_provider = web3.HTTPProvider(fork_rpc_url, {"timeout": 600})
    web3.provider = tenderly_provider
    print(f"https://dashboard.tenderly.co/yearn/yearn-web/fork/{fork_id}")


################################################ UPDATE THINGS BELOW HERE ################################################

@pytest.fixture(scope="function")
def splitter(strategist):
    splitter = strategist.deploy(Splitter)
    yield splitter

# for this strategy, set this if we want to test CVX or CRV-ETH LPs. shouldn't need to touch anything else
@pytest.fixture(scope="module")
def use_crv():
    use_crv = True
    yield use_crv


# for these LPs, we only use this to generate the correct want token. 61 CRV-ETH, 64 CVX-ETH
@pytest.fixture(scope="module")
def pid(use_crv):
    # if use_crv:
    #     pid = 61
    # else:
    #     pid = 64
    yield 109


@pytest.fixture(scope="module")
def whale(accounts, use_crv, rewardsContract, vault, token):
    # Totally in it for the tech
    # Update this with a large holder of your want token (the largest EOA holder of LP)
    temple_ms = accounts.at('0x5C8898f8E0F9468D4A677887bC03EE2659321012', force=True)
    b = token.balanceOf(temple_ms)
    amt = rewardsContract.balanceOf(temple_ms)
    rewardsContract.withdrawAndUnwrap(amt, True, {'from': temple_ms})
    assert token.balanceOf(temple_ms) > b
    token.approve(vault, 2**256-1, {'from': temple_ms})
    yield temple_ms


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance
@pytest.fixture(scope="module")
def amount(use_crv):
    if use_crv:
        amount = 175e18
    else:
        amount = 300e18
    yield amount


# this is the name we want to give our strategy
@pytest.fixture(scope="module")
def strategy_name():
    strategy_name = "StrategyConvexCrvCvxPairsClonable"
    yield strategy_name


# use this to set the standard amount of time we sleep between harvests.
# generally 1 day, but can be less if dealing with smaller windows (oracles) or longer if we need to trigger weekly earnings.
@pytest.fixture(scope="module")
def sleep_time():
    hour = 3600

    # change this one right here
    hours_to_sleep = 2

    sleep_time = hour * hours_to_sleep
    yield sleep_time


# curve deposit pool, we don't actually need it but set it anyway
@pytest.fixture(scope="module")
def pool(use_crv):
    if use_crv:
        poolAddress = Contract("0x8301AE4fc9c624d1D396cbDAa1ed877821D7C511")
    else:
        poolAddress = Contract("0xB576491F1E6e5E62f1d8F26062Ee822B40B0E0d4")
    yield poolAddress


# use this when we might lose a few wei on conversions between want and another deposit token
@pytest.fixture(scope="module")
def is_slippery():
    is_slippery = False
    yield is_slippery


# use this to test our strategy in case there are no profits
@pytest.fixture(scope="module")
def no_profit():
    no_profit = False
    yield no_profit


# Only worry about changing things above this line, unless you want to make changes to the vault or strategy.
# ----------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def gasOracle():
    yield Contract("0xb5e1CAcB567d98faaDB60a1fD4820720141f064F")


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


@pytest.fixture(scope="module")
def yregistry():
    # this is yearn's registry, we use it to get our most recent vault for a token
    yield Contract("0x50c1a2eA0a861A967D9d0FFE2AE4012c2E053804")


# Define relevant tokens and contracts in this section
@pytest.fixture(scope="module")
def token(booster, pid):
    # this should be the address of the ERC-20 used by the strategy/vault
    token_address = booster.poolInfo(pid)[0]
    yield Contract(token_address)


# gauge for the curve pool
@pytest.fixture(scope="module")
def gauge(booster, pid):
    # this should be the address of the convex deposit token
    gauge = booster.poolInfo(pid)[2]
    yield Contract(gauge)


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
@pytest.fixture(scope="module")
def vault(pm, gov, rewards, guardian, management, token, chain):
    Vault = pm(config["dependencies"][0]).Vault
    vault = guardian.deploy(Vault)
    vault.initialize(token, gov, rewards, "", "", guardian)
    vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
    vault.setManagement(management, {"from": gov})
    chain.sleep(1)
    yield vault


# # use this if your vault is already deployed
# @pytest.fixture(scope="function")
# def vault(pm, gov, rewards, guardian, management, token, chain, use_crv):
#     if use_crv:
#         vault = Contract("0x6A5468752f8DB94134B6508dAbAC54D3b45efCE6")
#     else:
#         vault = Contract("0x1635b506a88fBF428465Ad65d00e8d6B6E5846C3")
#     yield vault

# replace the first value with the name of your strategy
@pytest.fixture(scope="function")
def strategy(
    StrategyConvexCrvCvxPairsClonable,
    strategist,
    keeper,
    vault,
    gov,
    guardian,
    token,
    healthCheck,
    chain,
    proxy,
    pid,
    pool,
    strategy_name,
    gasOracle,
    strategist_ms,
    booster,
    use_crv,
    splitter
):
    # make sure to include all constructor parameters needed here
    strategy = strategist.deploy(
        StrategyConvexCrvCvxPairsClonable,
        vault,
        splitter,
    )
    strategy.setKeeper(keeper, {"from": gov})

    # set our management fee to zero so it doesn't mess with our profit checking
    vault.setManagementFee(0, {"from": gov})

    # we will be migrating on our live vault instead of adding it directly
    # old_strategy = Contract(vault.withdrawalQueue(0))
    # vault.migrateStrategy(old_strategy, strategy, {"from": gov})
    vault.addStrategy(strategy, 10_000, 0, 2**256-1, 0, {"from": gov})
    strategy.setHealthCheck(healthCheck, {"from": gov})
    strategy.setDoHealthCheck(True, {"from": gov})
    # vault.updateStrategyDebtRatio(strategy, 10000, {"from": gov})

    # earmark rewards if we are using a convex strategy
    booster.earmarkRewards(pid, {"from": gov})
    chain.sleep(1)
    chain.mine(1)

    # make all harvests permissive unless we change the value lower
    gasOracle.setMaxAcceptableBaseFee(2000 * 1e9, {"from": strategist_ms})

    # set up custom params and setters
    strategy.setHarvestTriggerParams(90000e6, 150000e6, 1e24, False, {"from": gov})
    strategy.setMaxReportDelay(86400 * 21)

    # harvest to send our funds into the strategy and fix any triggers already true
    strategy.harvest({"from": gov})
    chain.sleep(1)
    chain.mine(1)

    yield strategy


# use this if your strategy is already deployed
# @pytest.fixture(scope="function")
# def strategy():
#     # parameters for this are: strategy, vault, max deposit, minTimePerInvest, slippage protection (10000 = 100% slippage allowed),
#     strategy = Contract("0xC1810aa7F733269C39D640f240555d0A4ebF4264")
#     yield strategy
