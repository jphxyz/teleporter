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

from . import six

class TradePair:
    def __init__(self, api_entry):
        self.BaseCurrency = api_entry['BaseCurrency']
        self.BaseSymbol = api_entry['BaseSymbol']
        self.Currency = api_entry['Currency']
        self.Id = api_entry['Id']
        self.Label = api_entry['Label']
        self.MaximumBaseTrade = api_entry['MaximumBaseTrade']
        self.MaximumPrice = api_entry['MaximumPrice']
        self.MaximumTrade = api_entry['MaximumTrade']
        self.MinimumBaseTrade = api_entry['MinimumBaseTrade']
        self.MinimumPrice = api_entry['MinimumPrice']
        self.MinimumTrade = api_entry['MinimumTrade']
        self.Status = api_entry['Status']
        self.StatusMessage = api_entry['StatusMessage']
        self.Symbol = api_entry['Symbol']
        self.TradeFee = api_entry['TradeFee']

class Commodity:
    def __init__(self, apidata):
        self.Id = apidata['Id']
        self.Name = apidata['Name']
        self.Symbol = apidata['Symbol']
        self.MinBaseTrade = apidata['MinBaseTrade']
        self.IsTipEnabled = apidata['IsTipEnabled']
        self.MinTip = apidata['MinTip']
        self.Status = apidata['Status']
        self.neighbors = []

    def addneighbor(self, neighbor, rate, fee, mintrade, volume):
        # rate = 1 of me can buy n of neighbor
        # volume = N of me have been traded for this neighbor in the past 24 hours
        self.neighbors.append((neighbor, rate, fee, mintrade, volume))

    def getNeighbor(self, symbol):
        for n in self.neighbors:
            if n[0].Symbol == symbol:
                return n
        return None

    def clearneighbors(self):
        self.neighbors = []

    def getRoute(self, quantity, goal, route=[], maxdepth=3, overshoot=0.0):
        ''' Recursively query neighbors until 'goal' coin is reached. '''
        route = route + [(self.Symbol, quantity)]
        if self.Symbol == goal: return (quantity, route)
        if len(route) > maxdepth: return (0.0, [])
        max_val = 0.0
        best_route = []
        for neighbor, rate, fee, mintrade, volume in self.neighbors:
            beenthere = False
            for sym, qty in route:
                if neighbor.Symbol == sym:
                    beenthere = True
                    break
            if beenthere: continue
            if quantity * (1.0 - fee/100.0) < mintrade: continue
            if quantity > volume/20.0: continue
            Q = quantity * rate * (1.0-overshoot) * (1.0-fee/100.0)
            val, rt = neighbor.getRoute(Q, goal, route, maxdepth, overshoot)
            if val > max_val:
                max_val = val
                best_route = rt
        return (max_val, best_route)
            

class Network:
    def __init__(self, api):
        self.api = api
        self.currencies = None
        self.markets = None
        self.pairs = None
        self.initialize()

    def initialize(self):
        self.initcurrencies()
        self.initpairs()
        self.initmarkets()

    def initcurrencies(self):
        if self.currencies is None:
            self.currencies = {q['Symbol']:Commodity(q) for q in self.api.query('GetCurrencies')}
        else:
            for sym in self.currencies:
                self.currencies[sym].clearneighbors()

    def initpairs(self):
        self.pairs = {}
        apipairs = {q['Id']:q for q in self.api.query('GetTradePairs')}
        for p in apipairs:
            PAIR = TradePair(apipairs[p])
            self.pairs[apipairs[p]['Id']] = PAIR

    def initmarkets(self):
        self.initcurrencies()
        self.markets = {q['TradePairId']:q for q in self.api.query('GetMarkets')}

        for m in self.markets:
            MKT = self.markets[m]
            pair = self.pairs[MKT['TradePairId']]
            if pair.Status == 'OK':
                sym = self.currencies[pair.Symbol]
                base = self.currencies[pair.BaseSymbol]
                bid = MKT['BidPrice']
                ask = MKT['AskPrice']
                vol = MKT['Volume']
                basevol = MKT['BaseVolume']
                if ask > 0 and bid > 0:
                    sym.addneighbor(base, bid, pair.TradeFee, pair.MinimumBaseTrade/bid, vol)
                    base.addneighbor(sym, 1.0/ask, pair.TradeFee, pair.MinimumBaseTrade, basevol)

    def getCurrency(self, symbol):
        return self.currencies[symbol]

    def getTradePair(self, coin1, coin2):
        pair = [pair for pair in six.itervalues(self.pairs) \
                if pair.Label == '%s/%s'%(coin1, coin2) or pair.Label == '%s/%s'%(coin2, coin1)]
        assert len(pair) == 1, 'Multiple markets found for trade pair %s / %s'%(coin1, coin2)
        return pair[0]

    def getMarket(self, Id):
        return self.markets[Id]

    def getBestRoute(self, from_currency, to_currency, amount, maxTx, overshoot):
        ''' Trades 'amount' of 'from_currency' for 'to_currency' with
            no more than 'maxTx' transactions. '''
        start = self.currencies[from_currency]
        value, route = start.getRoute(amount, to_currency, maxdepth=maxTx, overshoot=overshoot)
        # route is a list of (CURRENCY, QUANTITY) pairs
        return (value, route)

