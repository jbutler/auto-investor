#!/usr/bin/env python3

import datetime
import json
import requests
import logging
import time

# investor imports
from investor import LoanFilter
from investor import Loan


class Investor:
	'A simple class to interact with your LendingClub account'

	def __init__(self, iid, authKey, investAmt=25, productionMode=False):
		self.iid = iid
		self.headers = { 'Authorization' : authKey, 'Accept' : 'application/json', 'Content-type' : 'application/json' }
		self.endpoint = 'https://api.lendingclub.com/api/investor/v1/'
		self.investAmt = investAmt
		self.productionMode = productionMode
		self.logger = logging.getLogger(__name__)
		self.time_delay = datetime.timedelta(seconds=1) # We must wait one second between requests
		self.last_request_ts = datetime.datetime.min # No requests have been made yet
		self.filters = []
		self.my_note_ids = [ x['loanId'] for x in self.get_notes_owned() ]

	def __set_ts(self):
		self.last_request_ts = datetime.datetime.now()
		return

	def __get_ts(self):
		return self.last_request_ts

	def __execute_delay(self):
		cur_time = datetime.datetime.now()
		delta = cur_time - self.__get_ts()
		if delta < self.time_delay:
			# Round up sleep time to the nearest second
			sleep_time = (delta + datetime.timedelta(milliseconds=999)).seconds
			time.sleep(sleep_time)
		return

	def __execute_get(self, url):
		self.__execute_delay()
		response = requests.get(self.endpoint + url, headers=self.headers)
		self.__set_ts()
		if not response:
			self.logger.error('Error occurred during GET: %s\n  HTTP response: %s' % (url, response.status_code))
		return response.text

	def __execute_post(self, url, payload=None):
		self.__execute_delay()
		response = requests.post(self.endpoint + url, data=payload, headers=self.headers)
		self.__set_ts()
		if not response:
			self.logger.error('Error occurred during POST: %s\n  HTTP response: %s' % (url, response.status_code))
		return response.text

	def __apply_filters(self, loans):
		# First, filter out loans we already own
		num_loans = len(loans)
		loans = [ loan for loan in loans if loan['id'] not in self.my_note_ids ]
		if num_loans != len(loans):
			self.logger.info('Filtering out loan(s) already invested in')

		# Second, apply user defined filters
		for f in self.filters:
			loans = [ loan for loan in loans if f.apply(loan) ]
		return loans

	def __get_loans(self, showAll=False):
		loans = []
		listings_json = self.__execute_get('loans/listing?showAll=%s' % (showAll))
		try:
			raw_loans = json.loads(listings_json)['loans']
			loans = [ Loan.Loan(raw_loan) for raw_loan in raw_loans ]
		except:
			# Key error, most likely
			self.logger.warning('Loan retrieval failed. Response text:\n  -- %s' % (listings_json))
		return loans

	def add_filters(self, filters):
		self.filters.extend(filters)

	def test_filters(self):
		loans = self.__get_loans(showAll=True)
		for f in self.filters:
			self.logger.info('Testing filter: %s' % (f))
			for l in loans:
				f.apply(l)

	def get_cash(self):
		cash = self.__execute_get('accounts/%s/availablecash' % (self.iid))
		if not cash:
			return 0
		return json.loads(cash)['availableCash']

	def get_new_loans(self, showAll=False):
		for _ in range(1,140):
			loans = self.__get_loans(showAll)
			loans = self.__apply_filters(loans)
			if len(loans):
				self.logger.info('%d loan(s) pass filters' % len(loans))
				return loans

		self.logger.info('No loans pass filters.')
		return []

	def get_notes_owned(self):
		mynotes_json = self.__execute_get('accounts/%s/notes' % (self.iid))
		return [ Loan.Loan(raw_loan) for raw_loan in json.loads(mynotes_json)['myNotes'] ]

	def submit_order(self, loans, portfolioId=None):
		if self.productionMode:
			loan_dict = [ { 'loanId' : loan['id'], 'requestedAmount' : self.investAmt, 'portfolioId' : portfolioId } for loan in loans ]
			order = json.dumps({ "aid" : self.iid, "orders" : loan_dict })
			return self.__execute_post('accounts/%s/orders' % (self.iid), payload=order)
		else:
			self.logger.info('Running in test mode. Skipping loan order')
			return None

	def add_funds(self, amount):
		if self.productionMode:
			payload = json.dumps({ 'amount' : amount, 'transferFrequency' : 'LOAD_NOW' })
			return self.__execute_post('accounts/%s/funds/add' % (self.iid), payload=payload)
		else:
			self.logger.info('Running in test mode. Skipping money transfer.')
			return None

	def get_pending_transfers(self):
		xfers = json.loads(self.__execute_get('accounts/%s/funds/pending' % (self.iid)))
		if 'transfers' in xfers:
			return xfers['transfers']
		else:
			return []

	def get_portfolios(self):
		portfolios = json.loads(self.__execute_get('accounts/%s/portfolios' % (self.iid)))
		try:
			return portfolios['myPortfolios']
		except KeyError:
			return []

	def create_portfolio(self, portfolioName, portfolioDescription=None):
		if self.productionMode:
			payload = json.dumps({ 'aid' : self.iid, 'portfolioName' : portfolioName, 'portfolioDescription' : portfolioDescription })
			return self.__execute_post('accounts/%d/portfolios' % (self.iid), payload=payload)
		else:
			self.logger.info('Running in test mode. Skipping portfolio creation.')
			return None

