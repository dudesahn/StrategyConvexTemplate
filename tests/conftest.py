import pytest
from brownie import config, Wei, Contract, chain, ZERO_ADDRESS
import requests

# Snapshots the chain before each test and reverts after test completion.
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


# set this for if we want to use tenderly or not; mostly helpful because with brownie.reverts fails in tenderly forks.
use_tenderly = False

################################################## TENDERLY DEBUGGING ##################################################

# change autouse to True if we want to use this fork to help debug tests
@pytest.fixture(scope="module", autouse=use_tenderly)
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


@pytest.fixture(scope="module")
def tests_using_tenderly():
    yes_or_no = use_tenderly
    yield yes_or_no


# use this to set what chain we use. 1 for ETH, 250 for fantom
chain_used = 1


# If testing a Convex strategy, set this equal to your PID
@pytest.fixture(scope="module")
def pid():
    pid = 77  # new pBTC 77
    yield pid


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance
@pytest.fixture(scope="module")
def amount():
    amount = 0.1e18  # new pBTC only has 0.236160916790470771
    yield amount


@pytest.fixture(scope="module")
def whale(accounts, amount, token):
    # Totally in it for the tech
    # Update this with a large holder of your want token (the largest EOA holder of LP)
    # new pBTC 0xf324Dca1Dc621FCF118690a9c6baE40fbD8f09b7,
    whale = accounts.at("0xf324Dca1Dc621FCF118690a9c6baE40fbD8f09b7", force=True)
    if token.balanceOf(whale) < 2 * amount:
        raise ValueError(
            "Our whale needs more funds. Find another whale or reduce your amount variable."
        )
    yield whale


# set address if already deployed, use ZERO_ADDRESS if not
@pytest.fixture(scope="module")
def vault_address():
    vault_address = ZERO_ADDRESS
    # MIM 0x2DfB14E32e2F8156ec15a2c21c3A6c053af52Be8
    # FRAX 0xB4AdA607B9d6b2c9Ee07A275e9616B84AC560139
    yield vault_address


# this is the name we want to give our strategy
@pytest.fixture(scope="module")
def strategy_name():
    strategy_name = "StrategyConvexpBTC"
    yield strategy_name


# we need these next two fixtures for deploying our curve strategy, but not for convex. for convex we can pull them programmatically.
# this is the address of our rewards token, in this case it's a dummy (ALCX) that our whale happens to hold just used to test stuff
@pytest.fixture(scope="module")
def rewards_token():  # PNT (pBTC) 0x89Ab32156e46F46D02ade3FEcbe5Fc4243B9AAeD
    yield Contract("0x89Ab32156e46F46D02ade3FEcbe5Fc4243B9AAeD")


# this is whether our pool has extra rewards tokens or not, use this to confirm that our strategy set everything up correctly.
@pytest.fixture(scope="module")
def has_rewards():
    has_rewards = True  # new pBTC true, all else false
    yield has_rewards


# this is whether our strategy is convex or not
@pytest.fixture(scope="module")
def is_convex():
    is_convex = True
    yield is_convex


# this is whether our strategy is curve or not
@pytest.fixture(scope="module")
def is_curve():
    is_curve = False
    yield is_curve


# use this when we might lose a few wei on conversions between want and another deposit token
@pytest.fixture(scope="module")
def is_slippery():
    is_slippery = False
    yield is_slippery


# use this to test our strategy in case there are no profits
@pytest.fixture(scope="module")
def no_profit():
    no_profit = True  # pBTC has no CRV/CVX yield
    yield no_profit


# use this to set the standard amount of time we sleep between harvests.
# generally 1 day, but can be less if dealing with smaller windows (oracles) or longer if we need to trigger weekly earnings.
@pytest.fixture(scope="module")
def sleep_time():
    hour = 3600

    # change this one right here
    hours_to_sleep = 96

    sleep_time = hour * hours_to_sleep
    yield sleep_time


################################################ UPDATE THINGS ABOVE HERE ################################################

# Only worry about changing things above this line, unless you want to make changes to the vault or strategy.
# ----------------------------------------------------------------------- #

if chain_used == 1:  # mainnet
    # all contracts below should be able to stay static based on the pid
    @pytest.fixture(scope="module")
    def booster():  # this is the deposit contract
        yield Contract("0xF403C135812408BFbE8713b5A23a04b3D48AAE31")

    @pytest.fixture(scope="module")
    def voter():
        yield Contract("0xF147b8125d2ef93FB6965Db97D6746952a133934")

    @pytest.fixture(scope="module")
    def convexToken():
        yield Contract("0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B")

    @pytest.fixture(scope="module")
    def crv():
        yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")

    @pytest.fixture(scope="module")
    def other_vault_strategy():
        yield Contract("0x8423590CD0343c4E18d35aA780DF50a5751bebae")

    @pytest.fixture(scope="module")
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
    def token(pid, booster):
        # this should be the address of the ERC-20 used by the strategy/vault
        token_address = booster.poolInfo(pid)[0]
        yield Contract(token_address)

    @pytest.fixture(scope="module")
    def cvxDeposit(booster, pid):
        # this should be the address of the convex deposit token
        cvx_address = booster.poolInfo(pid)[1]
        yield Contract(cvx_address)

    @pytest.fixture(scope="module")
    def rewardsContract(pid, booster):
        rewardsContract = booster.poolInfo(pid)[3]
        yield Contract(rewardsContract)

    # gauge for the curve pool
    @pytest.fixture(scope="module")
    def gauge(pid, booster):
        # this should be the address of the convex deposit token
        gauge = booster.poolInfo(pid)[2]
        yield Contract(gauge)

    # curve deposit pool
    @pytest.fixture(scope="module")
    def pool(token, curve_registry):
        if curve_registry.get_pool_from_lp_token(token) == ZERO_ADDRESS:
            poolAddress = token
        else:
            _poolAddress = curve_registry.get_pool_from_lp_token(token)
            poolAddress = Contract(_poolAddress)
        yield poolAddress

    @pytest.fixture(scope="module")
    def gasOracle():
        yield Contract("0xb5e1CAcB567d98faaDB60a1fD4820720141f064F")

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

    # set all of these accounts to SMS as well, just for testing
    @pytest.fixture(scope="module")
    def keeper(accounts):
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="module")
    def rewards(accounts):
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="module")
    def guardian(accounts):
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="module")
    def management(accounts):
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="module")
    def strategist(accounts):
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="module")
    def vault(pm, gov, rewards, guardian, management, token, chain, vault_address):
        if vault_address == ZERO_ADDRESS:
            Vault = pm(config["dependencies"][0]).Vault
            vault = guardian.deploy(Vault)
            vault.initialize(token, gov, rewards, "", "", guardian)
            vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
            vault.setManagement(management, {"from": gov})
            chain.sleep(1)
        else:
            vault = Contract(vault_address)
        yield vault

    # replace the first value with the name of your strategy
    @pytest.fixture(scope="module")
    def strategy(
        StrategyConvexsBTCFactoryClonable,
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
        crv,
        voter,
        strategy_name,
        gasOracle,
        strategist_ms,
        is_convex,
        booster,
        gauge,
        rewards_token,
        has_rewards,
        vault_address,
    ):
        if is_convex:
            # make sure to include all constructor parameters needed here
            strategy = strategist.deploy(
                StrategyConvexsBTCFactoryClonable,
                vault,
                pid,
                pool,
                strategy_name,
            )
            print("\nConvex strategy")
        else:
            # make sure to include all constructor parameters needed here
            strategy = strategist.deploy(
                StrategyConvexsBTCFactoryClonable,
                vault,
                gauge,
                pool,
                strategy_name,
            )
            print("\nCurve strategy")

        strategy.setKeeper(keeper, {"from": gov})
        # set our management fee to zero so it doesn't mess with our profit checking
        vault.setManagementFee(0, {"from": gov})

        # we will be migrating on our live vault instead of adding it directly
        if is_convex:
            # do slightly different if vault is existing or not
            if vault_address == ZERO_ADDRESS:
                vault.addStrategy(
                    strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov}
                )
            else:
                old_strategy = Contract(vault.withdrawalQueue(1))
                other_strat = Contract(vault.withdrawalQueue(0))
                vault.migrateStrategy(old_strategy, strategy, {"from": gov})
                vault.updateStrategyDebtRatio(other_strat, 0, {"from": gov})
                vault.updateStrategyDebtRatio(strategy, 10000, {"from": gov})

            # this is the same for new or existing vaults
            strategy.setHarvestTriggerParams(
                90000e6, 150000e6, 1e24, False, {"from": gov}
            )
            # earmark rewards if we are using a convex strategy
            booster.earmarkRewards(pid, {"from": gov})
            chain.sleep(1)
            chain.mine(1)
        else:
            proxy.approveStrategy(strategy.gauge(), strategy, {"from": gov})

            # do slightly different if vault is existing or not
            if vault_address == ZERO_ADDRESS:
                vault.addStrategy(
                    strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov}
                )
            else:
                # remove 50% of funds from our convex strategy
                other_strat = Contract(vault.withdrawalQueue(1))
                vault.updateStrategyDebtRatio(other_strat, 5000, {"from": gov})

                # turn off health check just in case it's a big harvest
                other_strat.setDoHealthCheck(False, {"from": gov})
                other_strat.harvest({"from": gov})
                chain.sleep(1)
                chain.mine(1)

                # give our curve strategy 50% of our debt and migrate it
                old_strategy = Contract(vault.withdrawalQueue(0))
                vault.migrateStrategy(old_strategy, strategy, {"from": gov})
                vault.updateStrategyDebtRatio(strategy, 5000, {"from": gov})

        # make all harvests permissive unless we change the value lower, turn on health check
        gasOracle.setMaxAcceptableBaseFee(2000 * 1e9, {"from": strategist_ms})
        strategy.setHealthCheck(healthCheck, {"from": gov})
        strategy.setDoHealthCheck(True, {"from": gov})

        # set up custom params and setters
        strategy.setMaxReportDelay(86400 * 21, {"from": gov})

        # harvest to send our funds into the strategy and fix any triggers already true
        assert strategy.estimatedTotalAssets() == 0
        strategy.harvest({"from": gov})
        chain.sleep(1)
        chain.mine(1)

        # print assets in each strategy
        if vault_address != ZERO_ADDRESS:
            print("Other strat assets:", other_strat.estimatedTotalAssets() / 1e18)
        print("Main strat assets:", strategy.estimatedTotalAssets() / 1e18)

        # add rewards token if needed
        if has_rewards:
            if (
                is_convex
            ):  # pBTC is the only BTC factory token with rewards, and it needs UniV2
                strategy.updateRewards(True, 0, False, {"from": gov})
            else:
                strategy.updateRewards(True, rewards_token, False, {"from": gov})

        yield strategy


elif chain_used == 250:  # only fantom so far and convex doesn't exist there

    @pytest.fixture(scope="function")
    def voter():
        yield Contract("0xF147b8125d2ef93FB6965Db97D6746952a133934")

    @pytest.fixture(scope="function")
    def crv():
        yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")

    @pytest.fixture(scope="module")
    def other_vault_strategy():
        yield Contract("0x8423590CD0343c4E18d35aA780DF50a5751bebae")

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

    # curve deposit pool
    @pytest.fixture(scope="module")
    def pool(token, curve_registry):
        if curve_registry.get_pool_from_lp_token(token) == ZERO_ADDRESS:
            poolAddress = token
        else:
            _poolAddress = curve_registry.get_pool_from_lp_token(token)
            poolAddress = Contract(_poolAddress)
        yield poolAddress

    @pytest.fixture(scope="module")
    def gasOracle():
        yield Contract("0xb5e1CAcB567d98faaDB60a1fD4820720141f064F")

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


# commented-out fixtures to be used with live testing

# # list any existing strategies here
# @pytest.fixture(scope="module")
# def LiveStrategy_1():
#     yield Contract("0xC1810aa7F733269C39D640f240555d0A4ebF4264")


# use this if your strategy is already deployed
# @pytest.fixture(scope="function")
# def strategy():
#     # parameters for this are: strategy, vault, max deposit, minTimePerInvest, slippage protection (10000 = 100% slippage allowed),
#     strategy = Contract("0xC1810aa7F733269C39D640f240555d0A4ebF4264")
#     yield strategy
