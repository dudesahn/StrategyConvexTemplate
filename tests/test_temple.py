import math
import brownie
from datetime import datetime, timezone
from brownie import Contract, chain, accounts
from brownie import config

def test_split(
    gov,
    token,
    vault,
    whale,
    strategy,
    chain,
    splitter,
    booster,
    rewardsContract,
    pid,
    crv,
    convexToken,
    crv_whale,
    pool
):

    assert False
    target_tvl_dominance = .95

    yearn_weights_to_test = [
        100, 1_000, 5_000
    ]

    convex_weights_to_test = [
        10, 100, 200
    ]

    ###########################################
    ###########################################
    ###########################################

    print_debug = False
    x = target_tvl_dominance + 0.05
    splitter.setStrategy(strategy, {'from':gov})
    amount_temple = token.balanceOf(whale) * x
    vault.deposit(amount_temple, {'from':whale})
    token.transfer(gov, token.balanceOf(whale),{'from':whale})
    token.approve(booster, 2**256-1,{'from':gov})
    # vault.deposit({'from':gov})
    amt = token.balanceOf(gov)
    if amt > 0:
        booster.deposit(pid,amt,True,{'from':gov})
    strategy.harvest({'from':gov})
    chain.snapshot()

    for w in yearn_weights_to_test:
        for c in convex_weights_to_test:
            print(f'--------------------------------------')
            print(f'𐄷 Pool Dominance: {"{:.2%}".format(strategy.estimatedTotalAssets()/pool.totalSupply())}')
            vote(w, c, vault, whale)
            # print(f'Stratgy Assets: {strategy.estimatedTotalAssets()/1e18}')
            vault.withdraw(1e18, {'from':whale})
            booster.earmarkRewards(pid,{'from':accounts[1]})
            rewardsContract.getReward(strategy, True,{'from':accounts[1]})
            crv.transfer(strategy, 10_000e18 - 10.035993473822e18, {'from': crv_whale})
            splitter.updatePeriod({'from':accounts[1]})
            # print(f'{strategy.estimatedTotalAssets()/1e18} {pool.totalSupply()/1e18}')
            print(f'🔎 READ-FUNCTIONS (ESTIMATES)')
            y, t = splitter.estimateSplitRatios()
            print(f'Split ratios: yearn: {"{:.2%}".format(y/10_000)} temple: {"{:.2%}".format(t/10_000)}')
            y, t = splitter.estimateSplit()
            # print(f'Splits: {y/1e18} temple: {t/1e18}')
            tx = strategy.harvest({'from':gov})
            # debug = tx.events["Debug"]
            # for i, d in enumerate(debug):
            #     if print_debug:
            #         print("DEBUG")
            #         print(d.values())
            transfers = tx.events['Transfer']
            for t in transfers:
                token = Contract(t.address)
                sender, receiver, value = t.values()
                if print_debug:
                    print(f'{token.symbol()} {value/10**token.decimals()}    {sender} --> {receiver}')
            split = tx.events["Split"]
            print('💰 SPLIT (ACTUALS)')
            print(f'Total CRV: {split["yearnAmount"]/1e18 + split["templeAmount"]/1e18}')
            print(f'Y: {split["yearnAmount"]/1e18}')
            # print(f'Keep Amount: {split["keep"]/1e18}')
            print(f'T: {split["templeAmount"]/1e18}')
            ts = split["period"]
            dt = datetime.utcfromtimestamp(ts).strftime("%m/%d/%Y, %H:%M:%S")
            # print(f'Period: {ts} --> {dt}')
            chain.revert()

def vote(weight, convex_weight, vault, whale):
    WEEK = 60 * 60 * 24 * 7
    DAY = 60 * 60 * 24
    chain.sleep(WEEK + (3*DAY))
    gauge_controller = Contract("0x2F50D538606Fa9EDD2B11E2446BEb18C9D5846bB")
    temple_gauge = '0x8f162742a7BCDb87EB52d83c687E43356055a68B'
    convex = accounts.at("0x989AEb4d175e16225E39E87d0D97A3360524AD80", force=True)
    yearn = accounts.at("0xF147b8125d2ef93FB6965Db97D6746952a133934", force=True)
    yearn_voted_gauges = [
        "0x05255C5BD33672b9FEA4129C13274D1E6193312d", # YFI/ETH
        "0xd8b712d29381748dB89c36BCa0138d7c75866ddF", # MIM
        "0x8Fa728F393588E8D8dD1ca397E9a710E53fA553a", # DOLA
        "0x95d16646311fDe101Eb9F897fE06AC881B7Db802", # STARGATE
    ]
    
    for g in yearn_voted_gauges:
        gauge_controller.vote_for_gauge_weights(g, 0,{'from': yearn})
    gauge_controller.vote_for_gauge_weights("0x8Fa728F393588E8D8dD1ca397E9a710E53fA553a", 0,{'from': convex})
    gauge_controller.vote_for_gauge_weights(temple_gauge, convex_weight,{'from': convex})
    gauge_controller.vote_for_gauge_weights(temple_gauge, weight,{'from': yearn})
    
    gauge_controller.checkpoint({'from': accounts[0]})
    gauge_controller.checkpoint_gauge(temple_gauge, {'from': accounts[0]})

    chain.sleep(WEEK)
    chain.mine()

    total_slope = gauge_controller.points_weight(temple_gauge, int(chain.time() / WEEK) * WEEK).dict()["slope"] / 1e18
    y_slope = gauge_controller.vote_user_slopes(yearn, temple_gauge).dict()["slope"] / 1e18
    c_slope = gauge_controller.vote_user_slopes(convex, temple_gauge).dict()["slope"] / 1e18

    print('🗳 VOTE DATA')
    print(f'Yearn vote weight: {weight} slope: {y_slope}')
    print(f'Convex vote weight: {convex_weight} slope: {c_slope}')
    # print(f'yearn slope: {y_slope}  convex slope: {c_slope}   total slope: {total_slope}')
    print(f'Percent of overall vote weight ... Yearn: {"{:.0%}".format(y_slope/total_slope)} Convex: {"{:.0%}".format(c_slope/total_slope)}')
