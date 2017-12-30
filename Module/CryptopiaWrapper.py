#!/usr/bin/python

import base64, hashlib, hmac, json, time
from . import six

public_set = set([ "GetCurrencies", "GetTradePairs", "GetMarkets", "GetMarket", "GetMarketHistory", "GetMarketOrders" ])
private_set = set([ "GetBalance", "GetDepositAddress", "GetOpenOrders", "GetTradeHistory", "GetTransactions", "SubmitTrade", "CancelTrade", "SubmitTip", "SubmitWithdraw"])
NonceTimeFactor = 3

def NonceValue(NonceTimeFactor):
    Nonce = str( int( time.time() * NonceTimeFactor - 4361732500 ) )
    return Nonce

class CryptopiaWrapper:

    def __init__(self, PublicKey, PrivateKey, retries=3):
        self._PublicKey = PublicKey
        self._PrivateKey = PrivateKey
        self.http_retries = retries

    def query(self, method, req = {}):
        time.sleep(1.0 / float(NonceTimeFactor) + 0.01)
        if method in public_set:
            url = '/'.join(['https://www.cryptopia.co.nz/api', method] + list(req.keys()))
            r = six.moves.urllib.request.urlopen(url).read()

        elif method in private_set:
            repeat = self.http_retries
            while repeat > 0:
                r = None
                url = 'https://www.cryptopia.co.nz/api/' + method
                nonce = NonceValue(NonceTimeFactor)
                post_data = six.b(json.dumps(req))
                m = hashlib.md5()
                m.update(post_data)
                requestContentBase64String = base64.b64encode(m.digest())
                signature = six.b(self._PublicKey + "POST" + six.moves.urllib.parse.quote_plus( url ).lower() + nonce) + requestContentBase64String
                hmacsignature = base64.b64encode(hmac.new(base64.b64decode(self._PrivateKey), signature, hashlib.sha256).digest())
                header_value = "amx " + self._PublicKey + ":" + hmacsignature.decode('utf-8') +  ":" + nonce
                handler = six.moves.urllib.request.HTTPHandler()
                opener  = six.moves.urllib.request.build_opener(handler)
                request = six.moves.urllib.request.Request(url, data=post_data)
                request.add_header('Authorization', header_value)
                request.add_header("Content-Type",'application/json; charset=utf-8')
                request.get_method = lambda: 'POST'
                try:
                    connection = opener.open(request)
                except six.moves.urllib.error.HTTPError as e:
                    connection = e

                # check. Substitute with appropriate HTTP code.
                if connection.code == 200:
                    r = connection.read()
                    break
                elif connection.code == 503:
                    six.print_(r, "The server is currently unavailable. Retrying %d more times."%repeat)
                    repeat -= 1
                    time.sleep( 5 )
                elif connection.code == 429:
                    six.print_(r, "Too many requests in a given amount of time.")
                    break
                else:
                    repeat -= 1
                    six.print_('Connection error. Retrying %d more times.'%repeat)
                    time.sleep( 5 )
        else:
            assert False, 'API Method <%s> not defined'%method

        result = json.loads(r)
        assert result['Success'], result['Error']
        return result['Data']

    ##### Public:
    def getCurrencies(self):
        return self.query("GetCurrencies")

    def getMarkets(self):
        return self.query("GetMarkets")

    def getMarket(self, Id):
        return self.query("GetMarket", [ Id ] )

    def getTradePairs(self):
        return self.query("GetTradePairs")

    def getMarketOrders(self, Id, depth):
        return self.query("GetMarketOrders", [ Id, depth ] )

    ##### Private:
    def submitTrade(self, Id, Type, Rate, Amount):
        # Amount is in units of top currency (e.g. if I'm placing a 'buy' order on
        # XVG/BTC at rate 0.00001119, for amount = 10.0, I'm saying I want to buy
        # 10.0 XVG using BTC at exchange rate 0.00002 BTC/XVG. That will cost me
        # 0.0002 BTC. I believe the 0.2% fee comes out of that.
        return self.query("SubmitTrade", {'TradePairId':Id, 'Type':Type, 'Rate':Rate, 'Amount':Amount})

    def getBalance(self, Id):
        return self.query("GetBalance", {'Currency':Id})

    def tip(self, Coin, User, Sum):
        return self.query("SubmitTip", {'Currency':Coin, 'ActiveUsers':User, 'Amount':Sum})

    def getOpenOrders(self, Id):
        return self.query("GetOpenOrders", {'TradePairId': Id})

    def submitTransfer(self, currency, user, amount):
        return self.query("SubmitTransfer", {'Currency':currency, 'Username':user, 'Amount':amount})

    def submitWithdraw(self, currency, address, amount, paymentId=None):
        args = {'Currency': currency, 'Address': address, 'PaymentId': paymentId, 'Amount': amount}
        if paymentId:
            args['PaymentId'] = paymentId
        return self.query('SubmitWithdraw', args)
