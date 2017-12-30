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
from Module import six
from Module.CryptopiaWrapper import CryptopiaWrapper
import Module.Markets as markets

def pause(pause_seconds):
    ERASE_LINE = '\x1b[2K'
    while pause_seconds > 0:
        m, s = divmod(pause_seconds, 60)
        h, m = divmod(m, 60)
        sys.stdout.write(ERASE_LINE)
        sys.stdout.write('\rSleeping %2d:%02d:%02d'%(h,m,s))
        sys.stdout.flush()
        time.sleep(1)
        pause_seconds -= 1
    six.print_('')

### read and validate config file
cfgloc = os.path.join(sys.path[0], 'config', 'teleporter.ini')
assert os.path.isfile(cfgloc), 'Configuration file not found.'

config = six.moves.configparser.ConfigParser()
config.read(cfgloc)
ConfDict        = config.__dict__['_sections']

DryRun        = (ConfDict['Main_Settings']['dry_run'].lower() in ('y', 'yes', '1', 'true'))
GaudyStartup    = (ConfDict['Main_Settings']['gaudy_startup_sequence'].lower() in ('y', 'yes', '1', 'true'))
DonatePercent   = float(ConfDict['Main_Settings']['donate_percent'])/100.0

BuyCoin         = ConfDict['Trade_Settings']['coin_to_buy']
SellFraction    = float(ConfDict['Trade_Settings']['sell_percent_of_available_balance'])/100.0
MaxTrades       = int(ConfDict['Trade_Settings']['max_trades'])
RateOvershoot   = float(ConfDict['Trade_Settings']['rate_overshoot'])/100.0

StopBalances    = {k.upper(): float(v) for k, v in six.iteritems(ConfDict['Keep_Balance']) if k not in ('symbol', '__name__')}

PublicKey       = ConfDict['Cryptopia']['public_key']
PrivateKey      = ConfDict['Cryptopia']['private_key']

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
zzz = 0.07 if GaudyStartup else 0.0
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

six.print_('Fetching Account Balances...', end=' ', flush=True)
# Not documented, but querying GetBalance with no
# currency argument apparently returns all currencies.
balances = api.getBalance('')
six.print_('OK.\n')

def istradeable(bal):
    result  = (bal['Status'] == 'OK')
    result &= (bal['Symbol'] != BuyCoin)
    result &= (bal['Available'] > 0)
    # TODO: Also check that there is a market on which the available quantity is above the 
    # minimum trade.
    #result &= (b['Available'] > net.getCurrency(bal['Symbol'])['MinBaseTrade'])
    return result

available = {b['Symbol']:b['Available'] for b in balances if istradeable(b)}

if len(available.keys()) == 0:
    six.print_('No coins to sell. Exiting.')
    sys.exit(0)

six.print_(' ---------------')
six.print_('   Buy : ', BuyCoin)
six.print_(' ---------------\n')
rowfmt_s = '{:<10} {:>20} {:>20} {:>20}'
six.print_(rowfmt_s.format('Commodity', 'Balance', 'StopBalance', 'SellAmount'))
six.print_(rowfmt_s.format('-'*5, '-'*16, '-'*16, '-'*16))
rowfmt_d = '{:<10} {:>20.8f} {:>20.8f} {:>20.8f}'
for sym, bal in six.iteritems(available):
    stopbal = StopBalances[sym] if sym in StopBalances else 0.0
    six.print_(rowfmt_d.format(sym, bal, stopbal, bal - stopbal))
six.print_('')

six.print_('Initializing Market Network...', end=' ', flush=True)
net = markets.Network(api)
six.print_('OK.\n')

totalconverted = 0.0

# TODO: Split most of the rest into a few smaller functions

completed_routes = 0

for sellcoin in available:
    if available[sellcoin] == 0:
        continue

    tosell = available[sellcoin] * SellFraction
    if sellcoin in StopBalances:
        tosell -= StopBalance[sellcoin]

    # Establish route
    expected_value, route = net.getBestRoute(sellcoin, BuyCoin, tosell, MaxTrades, RateOvershoot)
    if len(route) <= 1:
        continue
    else:
        completed_routes += 1

    rtstring = ' -> '.join(['[%s (%g)]'%(coin, qty) for coin, qty in route])
    six.print_('Established trade route: %s'%rtstring)

    # The following loop counts on knowing how much each trade got from the previous
    # trade (adjusted for fees and whatnot). On the first iteration it should be set
    # to the number of input coins to sell.
    resulting_value_of_previous_transaction = tosell

    # Now execute trades
    for i, coin in enumerate(route[:-1]):
        assert (coin != route[i+1]), 'Route is wonky. (%s)'(' -> '.join(route))
        fromcoin = coin[0]
        tocoin = route[i+1][0]
        pair = net.getTradePair(fromcoin, tocoin)
        # Markets are defined by Symbol/BaseSymbol pairs (e.g. ETH/BTC)
        # Transactions are placed in units of the BaseSymbol
        symbol = pair.Symbol
        base   = pair.BaseSymbol
        assert fromcoin in (symbol, base) and tocoin in (symbol, base), 'Wrong trade pair fetched.'

        while (not DryRun):
            bals = api.getBalance(fromcoin)[0]
            if bals['Available'] < resulting_value_of_previous_transaction-1e-8:
                if bals['HeldForTrades'] > 0:
                    six.print_(' Waiting on open orders ...')
                    pause(15)
                else:
                    six.print_(' Trade values changed. Reducting sell amount of %s to %g.'%(fromcoin, bals['Available']))
                    resulting_value_of_previous_transaction = bals['Available']
                    break
            else:
                break

        market = net.getMarket(pair.Id)

        # Echanges are labeled Symbol/BaseSymbol (e.g. BTC/USDT)
        # If 'fromcoin' is Symbol, then I want to place a sell order
        # to get the next currency in the route.
        # If 'fromcoin' is BaseSymbol, then I want to place a buy order.
        #
        # The Amount field should always be specified in units of the
        # trade symbol, not the base currency.
        input_val = resulting_value_of_previous_transaction
        if fromcoin == symbol:
            tradeType = 'Sell'
            rate = market['BidPrice'] * (1.0 - RateOvershoot)
            amount = input_val
            resulting_value_of_previous_transaction = amount*rate * (1.0 - pair.TradeFee/100.0)
        else:
            tradeType = 'Buy'
            rate = market['AskPrice'] * (1.0 + RateOvershoot)
            amount = input_val/rate
            resulting_value_of_previous_transaction = amount * (1.0 - pair.TradeFee/100.0)

        if DryRun:
            six.print_('\033[93m' + 'DRY RUN:' + '\033[0m', end='')

        six.print_('  Submitting %4s order: %g %s -> %g %s ...'%(tradeType, input_val, fromcoin, \
                resulting_value_of_previous_transaction, tocoin), end=' ', flush=True)

        if DryRun:
            time.sleep(1)
        else:
            api.submitTrade(pair.Id, tradeType, rate, amount)

        six.print_('OK.')

    totalconverted += resulting_value_of_previous_transaction
    six.print_('')

if completed_routes == 0:
    six.print_('No routes found.')
    sys.exit(0)

if not DryRun:
    six.print_('Donating %g%% to developers.'%(DonatePercent))
    amtToDonate = totalconverted * DonatePercent
    if amtToDonate > 0:
        api.submitTransfer(BuyCoin, 'jphxyz', amtToDonate)
        six.print_(' Thank you!!')
