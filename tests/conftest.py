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
@pytest.fixture(scope="session", autouse=use_tenderly)
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


@pytest.fixture(scope="session")
def tests_using_tenderly():
    yes_or_no = use_tenderly
    yield yes_or_no


# use this to set what chain we use. 1 for ETH, 250 for fantom
chain_used = 1

# put our pool's convex pid here
@pytest.fixture(scope="session")
def pid():
    pid = 22  # EURS 22, EURS-USDC 54, 3EUR 60. 3EUR and EURS are fucked on Curve, but work for Convex since we migrate
    yield pid


# this is the amount of funds we have our whale deposit. adjust this as needed based on their wallet balance
@pytest.fixture(scope="session")
def amount():
    amount = 330_000e18  # 165 for EURS-USDC, 330k for EURS, 472 for 3EUR
    yield amount


@pytest.fixture(scope="session")
def whale(accounts, amount, token):
    # Totally in it for the tech
    # Update this with a large holder of your want token (the largest EOA holder of LP)
    # EURS 0xC9f9f6cfD655417AcB8D1bB00Fe77aD9a6d9cA81, 660k
    # EURS-USDC 0xcF269308b782e9FF73634bA7DEd40A6C987831E9
    # 3EUR 0x9770E942e19aeB9FC935980cEB5eC81C10b1D030, 945
    whale = accounts.at("0xC9f9f6cfD655417AcB8D1bB00Fe77aD9a6d9cA81", force=True)
    if token.balanceOf(whale) < 2 * amount:
        raise ValueError(
            "Our whale needs more funds. Find another whale or reduce your amount variable."
        )
    yield whale


# set address if already deployed, use ZERO_ADDRESS if not
@pytest.fixture(scope="session")
def vault_address():
    vault_address = "0x25212Df29073FfFA7A67399AcEfC2dd75a831A1A"
    # EURS 0x25212Df29073FfFA7A67399AcEfC2dd75a831A1A
    # EURS-USDC 0x801Ab06154Bf539dea4385a39f5fa8534fB53073
    # 3EUR 0x5AB64C599FcC59f0f2726A300b03166A395578Da
    yield vault_address


# curve deposit pool for old pools, set to ZERO_ADDRESS otherwise
@pytest.fixture(scope="session")
def old_pool():
    old_pool = ZERO_ADDRESS
    # zero address for EURS and 3EUR
    # EURS-USDC 0x98a7F18d4E56Cfe84E3D081B40001B3d5bD3eB8B
    yield old_pool


# this is the name we want to give our strategy
@pytest.fixture(scope="session")
def strategy_name():
    strategy_name = "StrategyConvexEURS"
    yield strategy_name


# this is the name of our strategy in the .sol file
@pytest.fixture(scope="session")
def contract_name(StrategyConvexEURSClonable):
    contract_name = StrategyConvexEURSClonable
    yield contract_name


# this is the address of our rewards token
@pytest.fixture(scope="session")
def rewards_token():  # OGN 0x8207c1FfC5B6804F6024322CcF34F29c3541Ae26, SPELL 0x090185f2135308BaD17527004364eBcC2D37e5F6
    # SNX 0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F
    yield Contract("0x090185f2135308BaD17527004364eBcC2D37e5F6")


# sUSD gauge uses blocks instead of seconds to determine rewards, so this needs to be true for that to test if we're earning
@pytest.fixture(scope="session")
def try_blocks():
    try_blocks = False  # True for sUSD
    yield try_blocks


# whether or not we should try a test donation of our rewards token to make sure the strategy handles them correctly
# if you want to bother with whale and amount below, this needs to be true
@pytest.fixture(scope="session")
def test_donation():
    test_donation = False
    yield test_donation


@pytest.fixture(scope="session")
def rewards_whale(accounts):
    # SNX whale: 0x8D6F396D210d385033b348bCae9e4f9Ea4e045bD, >600k SNX
    # SPELL whale: 0x46f80018211D5cBBc988e853A8683501FCA4ee9b, >10b SPELL
    yield accounts.at("0x46f80018211D5cBBc988e853A8683501FCA4ee9b", force=True)


@pytest.fixture(scope="session")
def rewards_amount():
    rewards_amount = 1_000_000e18
    # SNX 50_000e18
    # SPELL 1_000_000e18
    yield rewards_amount


# whether or not a strategy is clonable. if true, don't forget to update what our cloning function is called in test_cloning.py
@pytest.fixture(scope="session")
def is_clonable():
    is_clonable = True
    yield is_clonable


# whether or not a strategy has ever had rewards, even if they are zero currently. essentially checking if the infra is there for rewards.
@pytest.fixture(scope="session")
def rewards_template():
    rewards_template = False
    yield rewards_template


# this is whether our pool currently has extra reward emissions (SNX, SPELL, etc)
@pytest.fixture(scope="session")
def has_rewards():
    has_rewards = False
    yield has_rewards


# this is whether our strategy is convex or not
@pytest.fixture(scope="session")
def is_convex():
    is_convex = True
    yield is_convex


# if our curve gauge deposits aren't tokenized (older pools), we can't as easily do some tests and we skip them
@pytest.fixture(scope="session")
def gauge_is_not_tokenized():
    gauge_is_not_tokenized = False
    yield gauge_is_not_tokenized


# use this to test our strategy in case there are no profits
@pytest.fixture(scope="session")
def no_profit():
    no_profit = False  # EURS sometimes has no profit, but try with False
    yield no_profit


# use this when we might lose a few wei on conversions between want and another deposit token
# generally this will always be true if no_profit is true, even for curve/convex since we can lose a wei converting
@pytest.fixture(scope="session")
def is_slippery(no_profit):
    is_slippery = False
    if no_profit:
        is_slippery = True
    yield is_slippery


# use this to set the standard amount of time we sleep between harvests.
# generally 1 day, but can be less if dealing with smaller windows (oracles) or longer if we need to trigger weekly earnings.
@pytest.fixture(scope="session")
def sleep_time():
    hour = 3600

    # change this one right here
    hours_to_sleep = 12

    sleep_time = hour * hours_to_sleep
    yield sleep_time


################################################ UPDATE THINGS ABOVE HERE ################################################

# Only worry about changing things above this line, unless you want to make changes to the vault or strategy.
# ----------------------------------------------------------------------- #

if chain_used == 1:  # mainnet

    @pytest.fixture(scope="session")
    def sushi_router():  # use this to check our allowances
        yield Contract("0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F")

    # all contracts below should be able to stay static based on the pid
    @pytest.fixture(scope="session")
    def booster():  # this is the deposit contract
        yield Contract("0xF403C135812408BFbE8713b5A23a04b3D48AAE31")

    @pytest.fixture(scope="session")
    def voter():
        yield Contract("0xF147b8125d2ef93FB6965Db97D6746952a133934")

    @pytest.fixture(scope="session")
    def convexToken():
        yield Contract("0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B")

    @pytest.fixture(scope="session")
    def crv():
        yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")

    @pytest.fixture(scope="session")
    def other_vault_strategy():
        yield Contract("0x8423590CD0343c4E18d35aA780DF50a5751bebae")

    @pytest.fixture(scope="session")
    def proxy():
        yield Contract("0xA420A63BbEFfbda3B147d0585F1852C358e2C152")

    @pytest.fixture(scope="session")
    def curve_registry():
        yield Contract("0x90E00ACe148ca3b23Ac1bC8C240C2a7Dd9c2d7f5")

    @pytest.fixture(scope="session")
    def curve_cryptoswap_registry():
        yield Contract("0x4AacF35761d06Aa7142B9326612A42A2b9170E33")

    @pytest.fixture(scope="session")
    def healthCheck():
        yield Contract("0xDDCea799fF1699e98EDF118e0629A974Df7DF012")

    @pytest.fixture(scope="session")
    def farmed():
        # this is the token that we are farming and selling for more of our want.
        yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")

    @pytest.fixture(scope="session")
    def token(pid, booster):
        # this should be the address of the ERC-20 used by the strategy/vault
        token_address = booster.poolInfo(pid)[0]
        yield Contract(token_address)

    @pytest.fixture(scope="session")
    def cvxDeposit(booster, pid):
        # this should be the address of the convex deposit token
        cvx_address = booster.poolInfo(pid)[1]
        yield Contract(cvx_address)

    @pytest.fixture(scope="session")
    def rewardsContract(pid, booster):
        rewardsContract = booster.poolInfo(pid)[3]
        yield Contract(rewardsContract)

    # gauge for the curve pool
    @pytest.fixture(scope="session")
    def gauge(pid, booster):
        gauge = booster.poolInfo(pid)[2]
        yield Contract(gauge)

    # curve deposit pool
    @pytest.fixture(scope="session")
    def pool(token, curve_registry, curve_cryptoswap_registry, old_pool):
        if old_pool == ZERO_ADDRESS:
            if curve_registry.get_pool_from_lp_token(token) == ZERO_ADDRESS:
                if (
                    curve_cryptoswap_registry.get_pool_from_lp_token(token)
                    == ZERO_ADDRESS
                ):
                    poolContract = token
                else:
                    poolAddress = curve_cryptoswap_registry.get_pool_from_lp_token(
                        token
                    )
                    poolContract = Contract(poolAddress)
            else:
                poolAddress = curve_registry.get_pool_from_lp_token(token)
                poolContract = Contract(poolAddress)
        else:
            poolContract = Contract(old_pool)
        yield poolContract

    @pytest.fixture(scope="session")
    def gasOracle():
        yield Contract("0xb5e1CAcB567d98faaDB60a1fD4820720141f064F")

    # Define any accounts in this section
    # for live testing, governance is the strategist MS; we will update this before we endorse
    # normal gov is ychad, 0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52
    @pytest.fixture(scope="session")
    def gov(accounts):
        yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)

    @pytest.fixture(scope="session")
    def strategist_ms(accounts):
        # like governance, but better
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    # set all of these accounts to SMS as well, just for testing
    @pytest.fixture(scope="session")
    def keeper(accounts):
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="session")
    def rewards(accounts):
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="session")
    def guardian(accounts):
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="session")
    def management(accounts):
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="session")
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
            chain.mine(1)
        else:
            vault = Contract(vault_address)
        yield vault

    # replace the first value with the name of your strategy
    @pytest.fixture(scope="module")
    def strategy(
        contract_name,
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
        is_convex,
        booster,
        gauge,
        rewards_token,
        has_rewards,
        vault_address,
        try_blocks,
    ):
        if is_convex:
            # make sure to include all constructor parameters needed here
            strategy = strategist.deploy(
                contract_name,
                vault,
                pid,
                pool,
                strategy_name,
            )
            print("\nConvex strategy")
        else:
            # make sure to include all constructor parameters needed here
            strategy = strategist.deploy(
                contract_name,
                vault,
                gauge,
                pool,
                strategy_name,
            )
            print("\nCurve strategy")

        strategy.setKeeper(keeper, {"from": gov})

        # set our management fee to zero so it doesn't mess with our profit checking
        vault.setManagementFee(0, {"from": gov})

        # start with other_strat as zero
        other_strat = ZERO_ADDRESS

        # we will be migrating on our live vault instead of adding it directly
        if is_convex:
            # earmark rewards if we are using a convex strategy
            booster.earmarkRewards(pid, {"from": gov})
            chain.sleep(1)
            chain.mine(1)

            # do slightly different if vault is existing or not
            if vault_address == ZERO_ADDRESS:
                vault.addStrategy(
                    strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov}
                )
                print("New Vault, Convex Strategy")
                chain.sleep(1)
                chain.mine(1)
            else:
                if vault.withdrawalQueue(1) == ZERO_ADDRESS:  # only has convex
                    old_strategy = Contract(vault.withdrawalQueue(0))
                    vault.migrateStrategy(old_strategy, strategy, {"from": gov})
                    vault.updateStrategyDebtRatio(strategy, 10000, {"from": gov})
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
        else:
            # do slightly different if vault is existing or not
            if vault_address == ZERO_ADDRESS:
                vault.addStrategy(
                    strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov}
                )
                print("New Vault, Curve Strategy")
                chain.sleep(1)
                chain.mine(1)
            else:
                if vault.withdrawalQueue(1) == ZERO_ADDRESS:  # only has convex
                    other_strat = Contract(vault.withdrawalQueue(0))
                    vault.updateStrategyDebtRatio(other_strat, 5000, {"from": gov})
                    vault.addStrategy(
                        strategy, 5000, 0, 2 ** 256 - 1, 1_000, {"from": gov}
                    )

                    # reorder so curve first, convex second
                    queue = [strategy.address, other_strat.address]
                    for x in range(18):
                        queue.append(ZERO_ADDRESS)
                    assert len(queue) == 20
                    vault.setWithdrawalQueue(queue, {"from": gov})

                    # turn off health check just in case it's a big harvest
                    other_strat.setDoHealthCheck(False, {"from": gov})
                    other_strat.harvest({"from": gov})
                    chain.sleep(1)
                    chain.mine(1)
                else:
                    other_strat = Contract(vault.withdrawalQueue(1))
                    # remove 50% of funds from our convex strategy
                    vault.updateStrategyDebtRatio(other_strat, 5000, {"from": gov})

                    # turn off health check just in case it's a big harvest
                    try:
                        other_strat.setDoHealthCheck(False, {"from": gov})
                    except:
                        print("This strategy doesn't have health check")
                    other_strat.harvest({"from": gov})
                    chain.sleep(1)
                    chain.mine(1)

                    # give our curve strategy 50% of our debt and migrate it
                    old_strategy = Contract(vault.withdrawalQueue(0))
                    vault.migrateStrategy(old_strategy, strategy, {"from": gov})
                    vault.updateStrategyDebtRatio(strategy, 5000, {"from": gov})

            # approve our new strategy on the proxy
            proxy.approveStrategy(strategy.gauge(), strategy, {"from": gov})

        # make all harvests permissive unless we change the value lower
        gasOracle.setMaxAcceptableBaseFee(2000 * 1e9, {"from": strategist_ms})
        strategy.setHealthCheck(healthCheck, {"from": gov})

        # add rewards token if needed. Double-check if we specify router here (sBTC new and old clonable only)
        if has_rewards:
            if is_convex:
                strategy.updateRewards(True, 0, {"from": gov})
            else:
                strategy.updateRewards(True, rewards_token, {"from": gov})

        # set up custom params and setters
        strategy.setMaxReportDelay(86400 * 21, {"from": gov})

        # harvest to send our funds into the strategy and fix any triggers already true
        if vault_address != ZERO_ADDRESS:
            tx = strategy.harvest({"from": gov})
            print(
                "Profits on first harvest (should only be on migrations):",
                tx.events["Harvested"]["profit"] / 1e18,
            )
        if try_blocks:
            chain.sleep(
                1
            )  # if we're close to Thursday midnight UTC, sleeping might kill our ability to earn from old gauges
        else:
            chain.sleep(10 * 3600)  # normalize share price
        chain.mine(1)

        # print assets in each strategy
        if vault_address != ZERO_ADDRESS and other_strat != ZERO_ADDRESS:
            print("Other strat assets:", other_strat.estimatedTotalAssets() / 1e18)
        print("Main strat assets:", strategy.estimatedTotalAssets() / 1e18)

        yield strategy


elif chain_used == 250:  # only fantom so far and convex doesn't exist there

    @pytest.fixture(scope="session")
    def voter():
        yield Contract("0xF147b8125d2ef93FB6965Db97D6746952a133934")

    @pytest.fixture(scope="session")
    def crv():
        yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")

    @pytest.fixture(scope="session")
    def other_vault_strategy():
        yield Contract("0x8423590CD0343c4E18d35aA780DF50a5751bebae")

    @pytest.fixture(scope="session")
    def curve_registry():
        yield Contract("0x90E00ACe148ca3b23Ac1bC8C240C2a7Dd9c2d7f5")

    @pytest.fixture(scope="session")
    def healthCheck():
        yield Contract("0xDDCea799fF1699e98EDF118e0629A974Df7DF012")

    @pytest.fixture(scope="session")
    def farmed():
        # this is the token that we are farming and selling for more of our want.
        yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")

    # curve deposit pool
    @pytest.fixture(scope="session")
    def pool(token, curve_registry):
        if curve_registry.get_pool_from_lp_token(token) == ZERO_ADDRESS:
            poolAddress = token
        else:
            _poolAddress = curve_registry.get_pool_from_lp_token(token)
            poolAddress = Contract(_poolAddress)
        yield poolAddress

    @pytest.fixture(scope="session")
    def gasOracle():
        yield Contract("0xb5e1CAcB567d98faaDB60a1fD4820720141f064F")

    # Define any accounts in this section
    # for live testing, governance is the strategist MS; we will update this before we endorse
    # normal gov is ychad, 0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52
    @pytest.fixture(scope="session")
    def gov(accounts):
        yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)

    @pytest.fixture(scope="session")
    def strategist_ms(accounts):
        # like governance, but better
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="session")
    def keeper(accounts):
        yield accounts.at("0xBedf3Cf16ba1FcE6c3B751903Cf77E51d51E05b8", force=True)

    @pytest.fixture(scope="session")
    def rewards(accounts):
        yield accounts.at("0x8Ef63b525fceF7f8662D98F77f5C9A86ae7dFE09", force=True)

    @pytest.fixture(scope="session")
    def guardian(accounts):
        yield accounts[2]

    @pytest.fixture(scope="session")
    def management(accounts):
        yield accounts[3]

    @pytest.fixture(scope="session")
    def strategist(accounts):
        yield accounts.at("0xBedf3Cf16ba1FcE6c3B751903Cf77E51d51E05b8", force=True)


# commented-out fixtures to be used with live testing

# # list any existing strategies here
# @pytest.fixture(scope="session")
# def LiveStrategy_1():
#     yield Contract("0xC1810aa7F733269C39D640f240555d0A4ebF4264")


# use this if your strategy is already deployed
# @pytest.fixture(scope="module")
# def strategy():
#     # parameters for this are: strategy, vault, max deposit, minTimePerInvest, slippage protection (10000 = 100% slippage allowed),
#     strategy = Contract("0xC1810aa7F733269C39D640f240555d0A4ebF4264")
#     yield strategy
