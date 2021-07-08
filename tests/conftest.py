import pytest
from brownie import config, Wei, Contract

# Snapshots the chain before each test and reverts after test completion.
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


# Define relevant tokens and contracts in this section


@pytest.fixture(scope="module")
def token():
    # this should be the address of the ERC-20 used by the strategy/vault. In this case, Curve's Iron Bank Pool token
    token_address = "0x5282a4eF67D9C33135340fB3289cc1711c13638C"
    yield Contract(token_address)


@pytest.fixture(scope="module")
def crv():
    yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")


@pytest.fixture(scope="module")
def dai():
    yield Contract("0x6B175474E89094C44Da98b954EedeAC495271d0F")


@pytest.fixture(scope="module")
def strategyProxy():
    # This is Yearn's StrategyProxy contract, overlord of the Curve world
    yield Contract("0xA420A63BbEFfbda3B147d0585F1852C358e2C152")


@pytest.fixture(scope="module")
def voter():
    # this is yearn's veCRV voter, where all gauge tokens are held (for v2 curve gauges that are tokenized)
    yield Contract("0xF147b8125d2ef93FB6965Db97D6746952a133934")


@pytest.fixture(scope="module")
def gaugeIB():
    # this is the gauge contract for the Iron Bank Curve Pool, in Curve v2 these are tokenized.
    yield Contract("0xF5194c3325202F456c95c1Cf0cA36f8475C1949F")


# Define any accounts in this section
@pytest.fixture(scope="module")
def gov(accounts):
    # yearn multis... I mean YFI governance. I swear!
    yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)


@pytest.fixture(scope="module")
def dudesahn(accounts):
    yield accounts.at("0xBedf3Cf16ba1FcE6c3B751903Cf77E51d51E05b8", force=True)


@pytest.fixture(scope="module")
def strategist_ms(accounts):
    # like governance, but better
    yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)


@pytest.fixture(scope="module")
def new_address(accounts):
    # new account for voter and proxy tests
    yield accounts.at("0xb5DC07e23308ec663E743B1196F5a5569E4E0555", force=True)


@pytest.fixture(scope="module")
def keeper(accounts):
    yield accounts[0]


@pytest.fixture(scope="module")
def rewards(accounts):
    yield accounts[1]


@pytest.fixture(scope="module")
def guardian(accounts):
    yield accounts[2]


@pytest.fixture(scope="module")
def management(accounts):
    yield accounts[3]


@pytest.fixture(scope="module")
def strategist(accounts):
    yield accounts.at("0xBedf3Cf16ba1FcE6c3B751903Cf77E51d51E05b8", force=True)


@pytest.fixture(scope="module")
def strategist_ms(accounts):
    # like governance, but better
    yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)


@pytest.fixture(scope="module")
def whale(accounts):
    # Totally in it for the tech
    whale = accounts.at("0x9817569Dc3015C84846159dAbcb80425186f506f", force=True)
    yield whale


@pytest.fixture(scope="function")
def vault(pm):
    Vault = pm(config["dependencies"][0]).Vault
    vault = Vault.at("0x27b7b1ad7288079A66d12350c828D3C00A6F07d7")
    yield vault


@pytest.fixture(scope="function")
def strategy(
    strategist, keeper, vault, gov, StrategyCurveIBVoterProxy, guardian, strategyProxy
):
    # parameters for this are: strategy, vault, max deposit, minTimePerInvest, slippage protection (10000 = 100% slippage allowed),
    strategy = strategist.deploy(StrategyCurveIBVoterProxy, vault)
    strategy.setKeeper(keeper, {"from": gov})
    strategyProxy.approveStrategy(strategy.gauge(), strategy, {"from": gov})
    vault.setManagementFee(0, {"from": gov})
    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 1000, {"from": gov})
    strategy.setStrategist(strategist, {"from": gov})
    # we harvest to deploy all funds to this strategy
    strategy.harvest({"from": gov})
    yield strategy
