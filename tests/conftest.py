import pytest
from brownie import config, Contract, ZERO_ADDRESS, chain, interface, accounts
from eth_abi import encode_single
import requests


@pytest.fixture(scope="function", autouse=True)
def isolate(fn_isolation):
    pass


# set this for if we want to use tenderly or not; mostly helpful because with brownie.reverts fails in tenderly forks.
use_tenderly = False

# use this to set what chain we use. 1 for ETH, 250 for fantom, 10 optimism, 42161 arbitrum
chain_used = 42161


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

#################### FIXTURES BELOW NEED TO BE ADJUSTED FOR THIS REPO ####################


@pytest.fixture(scope="session")
def token():
    token_address = "0x8e0B8c8BB9db49a46697F3a5Bb8A308e744821D2"  # this should be the address of the ERC-20 used by the strategy/vault (curve 3Crypto)
    yield interface.IERC20(token_address)


@pytest.fixture(scope="session")
def whale(amount, token):
    # Totally in it for the tech
    # Update this with a large holder of your want token (the largest EOA holder of LP)
    whale = accounts.at(
        "0x97E2768e8E73511cA874545DC5Ff8067eB19B787", force=True
    )  # 0x97E2768e8E73511cA874545DC5Ff8067eB19B787, 3Crypto 330 tokens
    if token.balanceOf(whale) < 2 * amount:
        raise ValueError(
            "Our whale needs more funds. Find another whale or reduce your amount variable."
        )
    yield whale


@pytest.fixture(scope="session")
def amount(token):
    amount = 100 * 10 ** token.decimals()
    yield amount


@pytest.fixture(scope="session")
def profit_whale(profit_amount, token):
    # ideally not the same whale as the main whale, or else they will lose money
    profit_whale = accounts.at(
        "0xF403C135812408BFbE8713b5A23a04b3D48AAE31", force=True
    )  # 0xF403C135812408BFbE8713b5A23a04b3D48AAE31, 3Crypto 139 tokens
    if token.balanceOf(profit_whale) < 5 * profit_amount:
        raise ValueError(
            "Our profit whale needs more funds. Find another whale or reduce your profit_amount variable."
        )
    yield profit_whale


@pytest.fixture(scope="session")
def profit_amount(token):
    profit_amount = 3 * 10 ** token.decimals()
    yield profit_amount


# set address if already deployed, use ZERO_ADDRESS if not
@pytest.fixture(scope="session")
def vault_address():
    vault_address = ZERO_ADDRESS
    yield vault_address


# if our vault is pre-0.4.3, this will affect a few things
@pytest.fixture(scope="session")
def old_vault():
    old_vault = False
    yield old_vault


# this is the name we want to give our strategy
@pytest.fixture(scope="session")
def strategy_name():
    strategy_name = "StrategyConvex3CryptoArbitrum"
    yield strategy_name


# this is the name of our strategy in the .sol file
@pytest.fixture(scope="session")
def contract_name(StrategyConvex3CryptoArbitrum):
    contract_name = StrategyConvex3CryptoArbitrum
    yield contract_name


# if our strategy is using ySwaps, then we need to donate profit to it from our profit whale
@pytest.fixture(scope="session")
def use_yswaps():
    use_yswaps = False
    yield use_yswaps


# whether or not a strategy is clonable. if true, don't forget to update what our cloning function is called in test_cloning.py
@pytest.fixture(scope="session")
def is_clonable():
    is_clonable = False
    yield is_clonable


# use this to test our strategy in case there are no profits
@pytest.fixture(scope="session")
def no_profit():
    no_profit = False
    yield no_profit


# use this when we might lose a few wei on conversions between want and another deposit token (like router strategies)
# generally this will always be true if no_profit is true, even for curve/convex since we can lose a wei converting
@pytest.fixture(scope="session")
def is_slippery(no_profit):
    is_slippery = False  # set this to true or false as needed
    if no_profit:
        is_slippery = True
    yield is_slippery


# use this to set the standard amount of time we sleep between harvests.
# generally 1 day, but can be less if dealing with smaller windows (oracles) or longer if we need to trigger weekly earnings.
@pytest.fixture(scope="session")
def sleep_time():
    hour = 3600

    # change this one right here
    hours_to_sleep = 24

    sleep_time = hour * hours_to_sleep
    yield sleep_time


#################### FIXTURES ABOVE NEED TO BE ADJUSTED FOR THIS REPO ####################

#################### FIXTURES BELOW SHOULDN'T NEED TO BE ADJUSTED FOR THIS REPO ####################


@pytest.fixture(scope="session")
def tests_using_tenderly():
    yes_or_no = use_tenderly
    yield yes_or_no


# by default, pytest uses decimals, but in solidity we use uints, so 10 actually equals 10 wei (1e-17 for most assets, or 1e-6 for USDC/USDT)
@pytest.fixture(scope="session")
def RELATIVE_APPROX(token):
    approx = 10
    print("Approx:", approx, "wei")
    yield approx


# use this to set various fixtures that differ by chain
if chain_used == 1:  # mainnet

    @pytest.fixture(scope="session")
    def gov():
        yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)

    @pytest.fixture(scope="session")
    def health_check():
        yield interface.IHealthCheck("0xddcea799ff1699e98edf118e0629a974df7df012")

    @pytest.fixture(scope="session")
    def base_fee_oracle():
        yield interface.IBaseFeeOracle("0xfeCA6895DcF50d6350ad0b5A8232CF657C316dA7")

    # set all of the following to SMS, just simpler
    @pytest.fixture(scope="session")
    def management():
        yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)

    @pytest.fixture(scope="session")
    def rewards(management):
        yield management

    @pytest.fixture(scope="session")
    def guardian(management):
        yield management

    @pytest.fixture(scope="session")
    def strategist(management):
        yield management

    @pytest.fixture(scope="session")
    def keeper(management):
        yield management

    # token we can sweep out of strategy (use CRV)
    @pytest.fixture(scope="session")
    def to_sweep():
        yield interface.IERC20("0xD533a949740bb3306d119CC777fa900bA034cd52")

    @pytest.fixture(scope="session")
    def trade_factory():
        yield Contract("0xcADBA199F3AC26F67f660C89d43eB1820b7f7a3b")

    @pytest.fixture(scope="session")
    def keeper_wrapper():
        yield Contract("0x0D26E894C2371AB6D20d99A65E991775e3b5CAd7")


# use this to set various fixtures that differ by chain
if chain_used == 42161:  # arbitrum

    @pytest.fixture(scope="session")
    def gov():
        yield accounts.at("0xb6bc033D34733329971B938fEf32faD7e98E56aD", force=True)

    @pytest.fixture(scope="session")
    def health_check():
        yield interface.IHealthCheck("0x32059ccE723b4DD15dD5cb2a5187f814e6c470bC")

    @pytest.fixture(scope="session")
    def base_fee_oracle():
        yield interface.IBaseFeeOracle("0x8273217252254Ad7353f227aaEcd2b1C4A326Fa2")

    # set all of the following to SMS, just simpler
    @pytest.fixture(scope="session")
    def management():
        yield accounts.at("0xC6387E937Bcef8De3334f80EDC623275d42457ff", force=True)

    @pytest.fixture(scope="session")
    def rewards(management):
        yield management

    @pytest.fixture(scope="session")
    def guardian(management):
        yield management

    @pytest.fixture(scope="session")
    def strategist(management):
        yield management

    @pytest.fixture(scope="session")
    def keeper(management):
        yield management

    # token we can sweep out of strategy (use CRV)
    @pytest.fixture(scope="session")
    def to_sweep():
        yield interface.IERC20("0x11cDb42B0EB46D95f990BeDD4695A6e3fA034978")

    # not actually arbitrum, just left as placeholderr
    @pytest.fixture(scope="session")
    def trade_factory():
        yield "0xcADBA199F3AC26F67f660C89d43eB1820b7f7a3b"

    # not actually arbitrum, just left as placeholderr
    @pytest.fixture(scope="session")
    def keeper_wrapper():
        yield "0x0D26E894C2371AB6D20d99A65E991775e3b5CAd7"


@pytest.fixture(scope="module")
def vault(pm, gov, rewards, guardian, management, token, vault_address):
    if vault_address == ZERO_ADDRESS:
        Vault = pm(config["dependencies"][0]).Vault
        vault = guardian.deploy(Vault)
        vault.initialize(token, gov, rewards, "", "", guardian)
        vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
        vault.setManagement(management, {"from": gov})
    else:
        vault = interface.IVaultFactory045(vault_address)
    yield vault


#################### FIXTURES ABOVE SHOULDN'T NEED TO BE ADJUSTED FOR THIS REPO ####################

#################### FIXTURES BELOW LIKELY NEED TO BE ADJUSTED FOR THIS REPO ####################


@pytest.fixture
def strategy(
    strategist,
    keeper,
    vault,
    gov,
    management,
    health_check,
    contract_name,
    strategy_name,
    base_fee_oracle,
    vault_address,
    pid,
    pool,
):
    # will need to update this based on the strategy's constructor ******
    strategy = gov.deploy(
        contract_name,
        vault,
        pid,
        pool,
        strategy_name,
    )

    strategy.setKeeper(keeper, {"from": gov})
    strategy.setHealthCheck(health_check, {"from": gov})
    strategy.setDoHealthCheck(True, {"from": gov})
    vault.setPerformanceFee(0, {"from": gov})
    vault.setManagementFee(0, {"from": gov})

    # if we have other strategies, set them to zero DR and remove them from the queue
    if vault_address != ZERO_ADDRESS:
        for i in range(0, 20):
            strat_address = vault.withdrawalQueue(i)
            if ZERO_ADDRESS == strat_address:
                break

            if vault.strategies(strat_address)["debtRatio"] > 0:
                vault.updateStrategyDebtRatio(strat_address, 0, {"from": gov})
                interface.ICurveStrategy045(strat_address).harvest({"from": gov})
                vault.removeStrategyFromQueue(strat_address, {"from": gov})

    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})

    # turn our oracle into testing mode by setting the provider to 0x00, then forcing true
    strategy.setBaseFeeOracle(base_fee_oracle, {"from": gov})
    base_fee_oracle.setBaseFeeProvider(ZERO_ADDRESS, {"from": management})
    base_fee_oracle.setManualBaseFeeBool(True, {"from": management})
    assert strategy.isBaseFeeAcceptable() == True

    # this is the same for new or existing vaults
    strategy.setHarvestTriggerParams(90000e6, 150000e6, {"from": gov})

    yield strategy


#################### FIXTURES ABOVE LIKELY NEED TO BE ADJUSTED FOR THIS REPO ####################

####################   PUT UNIQUE FIXTURES FOR THIS REPO BELOW         ####################

# put our pool's convex pid here
@pytest.fixture(scope="session")
def pid():
    pid = 8  # 8 = new 3crypto
    yield pid


@pytest.fixture(scope="session")
def destination_strategy():
    # destination strategy of the route
    yield "0x83D0458e627cFD7C6d0da12a1223bd168e1c8B64"
    # yield interface.ICurveStrategy045("0x83D0458e627cFD7C6d0da12a1223bd168e1c8B64")


# curve deposit pool for old pools, set to ZERO_ADDRESS otherwise
@pytest.fixture(scope="session")
def pool():
    pool = "0x960ea3e3C7FB317332d990873d354E18d7645590"
    yield pool
