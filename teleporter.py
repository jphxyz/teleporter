#!/usr/bin/env python

'''
    Copyright 2017 jphxyz

    This file is part of Teleporter.

    Teleporter is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Teleporter is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Teleporter.  If not, see <http://www.gnu.org/licenses/>.
'''

import json, os, sys, time
from decimal import ROUND_UP, ROUND_DOWN
from decimal import Decimal as Dec
from datetime import datetime
from Module import six
from Module.CryptopiaWrapper import CryptopiaWrapper
import Module.Markets as markets

class Logger(object):
    def __init__(self, logfilename='', logstamp=''):
        self.pipes = [sys.stdout]
        if logfilename != '':
            self.pipes.append(open(logfilename, 'a'))
            self.pipes[-1].write(logstamp)

    def write(self, message):
        for pipe in self.pipes:
            pipe.write(message)

    def flush(self):
        for pipe in self.pipes:
            pipe.flush()

def pause(pause_seconds):
    ERASE_LINE = '\x1b[2K'
    while pause_seconds > 0:
        m, s = divmod(pause_seconds, 60)
        h, m = divmod(m, 60)
        sys.stdout.write(ERASE_LINE)
        sys.stdout.write('\r  Sleeping %2d:%02d:%02d'%(h,m,s))
        sys.stdout.flush()
        time.sleep(1)
        pause_seconds -= 1
    sys.stdout.write(ERASE_LINE + '\r')
    sys.stdout.flush()

### read and validate config file
cfgloc = os.path.join(sys.path[0], 'config', 'teleporter.ini')
assert os.path.isfile(cfgloc), 'Configuration file not found.'

config = six.moves.configparser.ConfigParser()
config.read(cfgloc)
ConfDict        = config.__dict__['_sections']

DryRun          = (ConfDict['Main_Settings']['dry_run'].lower() in ('y', 'yes', '1', 'true'))
DonateFraction  = float(ConfDict['Main_Settings']['donate_percent'])/100.0
LogFile         = ConfDict['Main_Settings']['log_file']
BuyCoin         = ConfDict['Trade_Settings']['coin_to_buy']
SellFraction    = float(ConfDict['Trade_Settings']['sell_percent_of_available_balance'])/100.0
MaxTrades       = int(ConfDict['Trade_Settings']['max_trades'])
RateOvershoot   = float(ConfDict['Trade_Settings']['rate_overshoot'])/100.0
TradeTimeout    = float(ConfDict['Trade_Settings']['open_trade_timeout'])
VolumeThreshold = float(ConfDict['Trade_Settings']['volume_threshold'])
StopBalances    = {k.upper(): float(v) for k, v in six.iteritems(ConfDict['Keep_Balance']) if k not in ('symbol', '__name__')}
PublicKey       = ConfDict['Cryptopia']['public_key']
PrivateKey      = ConfDict['Cryptopia']['private_key']
AutoWithdraw      = (ConfDict['Withdraw']['auto_withdraw'].lower() in ('y', 'yes', '1', 'true'))
WithdrawCoin      = ConfDict['Withdraw']['withdraw_currency']
WithdrawAddress   = ConfDict['Withdraw']['withdraw_address']
WithdrawFraction  = float(ConfDict['Withdraw']['withdraw_percent'])/100.0
WithdrawThreshold = ConfDict['Withdraw']['withdraw_threshold']

# Check for CLI options (override config file options if so)
if '-n' in sys.argv or '--dry-run' in sys.argv:
    DryRun = True
if '-c' in sys.argv:
    BuyCoin = sys.argv[sys.argv.index('-c')+1]
if '--coin' in sys.argv:
    BuyCoin = sys.argv[sys.argv.index('--coin')+1]
if '-m' in sys.argv:
    MaxTrades = int(sys.argv[sys.argv.index('-m')+1])
if '--max-trades' in sys.argv:
    MaxTrades = int(sys.argv[sys.argv.index('--max-trades')+1])
if '-h' in sys.argv or '--help' in sys.argv:
    six.print_('Usage: teleporter [-h|--help] [-n|--dry-run] [-c|--coin <COIN>] [-m|--max-trades <MAX_TRADES>]')

api = CryptopiaWrapper(PublicKey, PrivateKey)

# Dramatic startup messages
zzz = 0.07
six.print_(' ---------------------------------------------------------------------------')
six.print_('')
sys.stdout.write('{:<28}'.format(''))
for letter in 'TELEPORTER':
    sys.stdout.write(' ' + letter)
    time.sleep(zzz)
    sys.stdout.flush()
six.print_('\n')
time.sleep(zzz)
if DryRun:
    six.print_('\033[93m'+'{:^76}\n'.format('!!! DRY RUN !!!')+'\033[0m')
    time.sleep(zzz)
six.print_('{:^76}'.format('Auto-sell program for Cryptopia'))
time.sleep(zzz)
six.print_('{:>76}'.format('by jphxyz'))
six.print_(' ---------------------------------------------------------------------------\n')
time.sleep(zzz)

# Initialize the logger
sys.stdout = Logger(LogFile, '\n'+'-'*10+'\n'+datetime.now().isoformat()+'\n\n')

# Get accout balances
six.print_('Fetching Account Balances...', end=' ', flush=True)
# Not documented, but querying GetBalance with no
# currency argument apparently returns all currencies.
balances = api.getBalance('')
six.print_('\033[92m'+'OK'+'\033[0m'+'\n')

# Sort out only the tradeable coins
istradeable = lambda bal: (bal['Status'] == 'OK') and (bal['Symbol'] != BuyCoin) and (bal['Available'] > 0)
available = {b['Symbol']:b['Available'] for b in balances if istradeable(b)}
initial_buycoin_balance = [bal['Available'] for bal in balances if bal['Symbol'] == BuyCoin][0]

# Print balances
rowfmt_s = '{:<10} {:>20} {:>20} {:>20}'
six.print_(rowfmt_s.format('Commodity', 'Balance', 'StopBalance', 'SellAmount'))
six.print_(rowfmt_s.format('-'*5, '-'*16, '-'*16, '-'*16))
six.print_('\033[1m' + rowfmt_s.format(BuyCoin, '%0.8f'%initial_buycoin_balance, '', '') + '\033[0m')
rowfmt_d = '{:<10} {:>20.8f} {:>20.8f} {:>20.8f}'
for sym, bal in six.iteritems(available):
    stopbal = StopBalances[sym] if sym in StopBalances else 0.0
    six.print_(rowfmt_d.format(sym, bal, stopbal, bal - stopbal))
six.print_('')

if len(available.keys()) == 0:
    six.print_('No coins to sell. Exiting.')
    sys.exit(0)

# Initialize Network object (Queries info on all coins, tradepairs, and markets)
six.print_('Initializing Market Network...', end=' ', flush=True)
net = markets.Network(api)
six.print_('\033[92m'+'OK'+'\033[0m'+'\n')

def getAvailable(coin):
    try:
        return api.getBalance(coin)[0]['Available']
    except AssertionError as e:
        pass

    return 0.0

def doTrade(pairId, trade_type, rate, amount, tocoin, amount_tocoin, timeout=TradeTimeout):
    if DryRun:
        time.sleep(1)
        return (True, {'OrderId': 0})
    else:
        initial_tocoin_bal = getAvailable(tocoin)
        result = api.submitTrade(pair.Id, trade_type, float(rate), float(trade_amount))

        time.sleep(2)

        final_tocoin_bal = getAvailable(tocoin)
        if final_tocoin_bal - initial_tocoin_bal < amount_tocoin:
            six.print_('\n    Waiting on open orders ...')
            pause(timeout)
            final_tocoin_bal = getAvailable(tocoin)
        if final_tocoin_bal - initial_tocoin_bal < amount_tocoin:
            return (False, result)
        else:
            return (True, result)

def precision(decimal, precision, rounding=None):
    if precision < 1:
        return Dec(int(decimal))

    return decimal.quantize(Dec('0.'+('0'*(precision-1))+'1'), rounding=rounding)

# TODO: Split most of the rest into a few smaller functions

total_converted = Dec(0)
to_trade = [(coin, value) for coin, value in six.iteritems(available)]
while len(to_trade) > 0:
    sellcoin, amt_to_sell = to_trade.pop()
    amt_to_sell *= SellFraction
    if sellcoin in StopBalances:
        amt_to_sell -= StopBalances[sellcoin]

    # Establish route
    final_value, route_info = net.getBestRoute(sellcoin, BuyCoin, amt_to_sell, MaxTrades, RateOvershoot, VolumeThreshold)

    if len(route_info) <= 1:
        # If no routes were found (happens when balances are
        # lower than minimum trades), then move on to next
        # tradeable coin.
        continue

    rtstring = ' -> '.join(['[%s]'%(coin) for coin, qty in route_info])
    six.print_('Established trade route: %s'%rtstring)

    # The following loop counts on knowing how much was aquired in the previous
    # trade (adjusted for fees and whatnot). On the first iteration it should be set
    # to the number of input coins to sell.
    value_of_previous_transaction = Dec(amt_to_sell)

    # Now execute trades
    route = [coin for coin, qty in route_info]
    failed_route = False
    for fromcoin, tocoin in zip(route[:-1], route[1:]):
        pair = net.getTradePair(fromcoin, tocoin)
        trade_symbol = pair.Symbol
        base_symbol   = pair.BaseSymbol
        assert (fromcoin in (trade_symbol, base_symbol)) \
                and (tocoin in (trade_symbol, base_symbol)), \
                'Wrong trade pair fetched.'

        if not DryRun:
            bal = api.getBalance(fromcoin)[0]
            assert bal['Available'] >= value_of_previous_transaction, \
                '  Unable to trade %g %s for %s.'%(value_of_previous_transaction, fromcoin, tocoin) \
                + '\n  Insufficient available funds.'

        # For reference, because I always get turned around here:
        #
        # Markets are labeled TradeSymbol/BaseSymbol (e.g. BTC/USDT)
        # If 'fromcoin' is TradeSymbol, then I want to place a sell order
        # to get the next currency in the route. (e.g. "Sell 1.5 BTC")
        #
        # The Amount field should always be specified in units of the
        # trade currency, not the base currency.
        # e.g. on market ETH/BTC I might "Buy 10 ETH" or "Sell 5 ETH"
        # The important part is that the trade amount is specified in ETH.
        #
        # The rate is in units of the BaseSymbol. That is, the number of
        # BaseSymbol's I can buy with one unit of TradeSymbol.
        # e.g If 1 LTC is worth 100 USDT, and I'm on market LTC/USDT, then
        # I can place an order like 'Sell 1 LTC at rate 100 (USDT/LTC)'.
        #
        # The BidPrice is the most competitive offer available to me
        # if I'm trying to sell TradeSymbols. The AskPrice is the reverse.
        # e.g. If I have 1 LTC, and I want to exchange it at market rate
        # on market LTC/USDT, then I should post a Sell order for amount
        # 1 at rate defined by market BidPrice.
        #
        # Conversely, if I have 450 USDT, and I'm on market LTC/USDT looking
        # to buy LTC at market rate, then I need to figure out how many
        # LTC I can get at the current AskPrice.
        # e.g. if AskPrice is 100 (USDT/LTC), then I can expect to get 4.5 LTC
        # (assuming volume is high enough, which might be a risky assumption).
        # Therefore I would place a Buy order for amount 4.5 at rate 100.
        #
        # To be more competitive in a Buy order, I would settle on a higher rate.
        # (more USDT per LTC in this case). Conversely, in a Sell order I
        # would need to settle on a lower rate (Accept fewer USDT for each of
        # my LTC in this case).
        #
        # Fees are weird. It appears that they do not need to be taken into account
        # for the trade amount on Sell orders, but they do on Buy orders. But in
        # both cases they are taken out of the trade. That means that Buy orders
        # must leave little bits of change in the source account.

        market = net.getMarket(pair.Id)

        amount_of_input_currency = value_of_previous_transaction
        amount_of_input_currency  = precision(amount_of_input_currency, 8, ROUND_DOWN)

        if fromcoin == trade_symbol:
            trade_type = 'Sell'
            rate = precision(Dec(market['BidPrice'] * (1.0 - RateOvershoot)), 8, ROUND_DOWN)
            assert rate > 0, 'Rate is below precision'
            trade_amount = amount_of_input_currency # Measured in the trade currency (this one)
            trade_amount = precision(trade_amount, 8, ROUND_DOWN)
            amount_of_output_currency = amount_of_input_currency * rate * (Dec(1) - Dec(pair.TradeFee)/Dec(100))
            amount_of_output_currency = precision(amount_of_output_currency, 8, ROUND_DOWN)
        else:
            trade_type = 'Buy'
            rate = precision(Dec(market['AskPrice'] * (1.0 + RateOvershoot)), 8, ROUND_UP)
            assert rate > 0, 'Rate is below precision'
            trade_amount = amount_of_input_currency/rate/(Dec(1) + Dec(pair.TradeFee)/Dec(100))
            trade_amount = precision(trade_amount, 8, ROUND_DOWN)
            # I think this is a bug in the API that forces us to leave little bits of change
            # in the source account on Buy orders.
            amount_of_output_currency = trade_amount * (Dec(1) - Dec(pair.TradeFee)/Dec(100))

        # Submit trade
        if DryRun:
            six.print_('\033[93m' + 'DRY RUN:' + '\033[0m', end='')
        six.print_('  Submitting %4s order: %g %4s -> %g %4s ...'%(trade_type, amount_of_input_currency, \
                fromcoin, amount_of_output_currency, tocoin), end='', flush=True)

        success, result = doTrade(pair.Id, trade_type, rate, trade_amount, tocoin, amount_of_output_currency)

        if success:
            six.print_('\033[92m'+'  OK'+'\033[0m')
        else:
            failed_trade = True
            six.print_('\033[91m'+'  Trade timed out.'+'\033[0m'+' Canceling and recomputing route.')
            orderId = result['OrderId']
            try:
                api.cancelTrade('All', orderId, '')
            except AssertionError as e:
                six.print_('  Cancel trade failed with error:', end=' ')
                six.print_(e)
            break

        value_of_previous_transaction = amount_of_output_currency

    if failed_route:

        six.print_('Fetching Account Balances...', end=' ', flush=True)
        balances = api.getBalance('')
        six.print_('\033[92m'+'OK'+'\033[0m'+'\n')

        available = {b['Symbol']:b['Available'] for b in api.getBalance('') if istradeable(b)}
        to_trade = [(coin, value) for coin, value in six.iteritems(available)]
        net.initialize()
        failed_route = False
    else:
        total_converted += value_of_previous_transaction

    six.print_('')

if total_converted == 0:
    six.print_('No routes found.')
    sys.exit(0)

if not DryRun:
    # Submit optional donation
    six.print_('Donating %g%% to developers.'%(DonateFraction*100))
    amtToDonate = float(total_converted) * DonateFraction
    if amtToDonate > 0:
        api.submitTransfer(BuyCoin, 'jphxyz', amtToDonate)
        six.print_(' Thank you!!')

    # Do auto-withdraw
    if AutoWithdraw:
        stopBal = StopBalances[WithdrawCoin] if WithdrawCoin in StopBalances else 0.0
        bal = api.getBalance(WithdrawCoin)[0]
        amtToWithdraw = bal['Available'] * WithdrawFraction - stopBal

        if bal['Available'] > WithdrawThreshold:
            six.print_('\nWithdrawing %g %s to %s'%(amtToWithdraw, WithdrawCoin, WithdrawAddress))
            api.submitWithdraw(WithdrawCoin, WithdrawAddress, amtToWithdraw)

