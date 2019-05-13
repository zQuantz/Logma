from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from threading import Thread
import queue

from zwrapper import zWrapper
from scanner_client import ScannerClient
from zmodel import Model

from zcontracts import forex_contract

import joblib

import time

##############################

ip_address = '127.0.0.1'
port = 4001
clientId = 0

##############################

class Scanner(ScannerClient, zWrapper):

	def __init__(self, ip_address, port, clientId):

		zWrapper.__init__(self)
		ScannerClient.__init__(self, self)

		self.connect(ip_address, port, clientId)

		thread = Thread(target = self.run)
		thread.start()

		self.init_errors()
		self.print_errors()

		self.bg_scheduler = BackgroundScheduler()
		self.model = Model('EURUSD', candle_size = 5, short_period = 20, long_period = 50, log_trim = 7)

	def on_period(self):
		
		dt = datetime.now() - timedelta(minutes=1)
		dt = dt.strftime('%Y%m%d  %H:%M:00')

		bar = None
		date = None

		while date != dt:
			try:
				bar = self.wrapper._updates_queue.get(timeout = 0.01)
				date = bar[0]
			except queue.Empty:
				break

		signal, features = self.model.is_trade(bar)
		
		print('\n%s' % datetime.now(), '\nSignal', signal, '\nFeatures', features)
		print(bar)

	def on_start(self, reqId):

		self.init_historical_queue()
		self.init_updates_queue()

		## Send the data to the model class
		self.model.data = self.init_historical_data(reqId)
		self.op_job = self.bg_scheduler.add_job(self.on_period, 'cron', minute='*')
		print(self.op_job)

		self.bg_scheduler.start()

	def on_close(self):

		self.disconnect()
		self.bg_scheduler.shutdown()

if __name__ == '__main__':

	scanner = Scanner(ip_address, port, clientId)