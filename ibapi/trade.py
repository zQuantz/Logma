from datetime import datetime
from zorders import limit_order, limit_if_touched
from utils import adjust_price

from collections import namedtuple

TradeOrders = namedtuple('TradeOrders', ['init_order', 'init_oid', 'profit_order', 'profit_oid', 'loss_order', 'loss_oid'])

class Trade(object):

	def __init__(self, manager, symbol, action, initial_order, details):

		## Start Time
		self.init_time = datetime.now()

		## Book keeping
		self.symbol = symbol
		self.contract = manager.contracts[symbol]
		self.action = action
		self.direction = manager.action_directions[action]
		self.closing_action = manager.closing_actions[action]

		## Manager stuff
		self.manager = manager
		self.tick_incr = manager.tick_increments[self.symbol]

		## Closing instructions
		self.details = details

		## Trade status
		self.status = 'PENDING'

		## Initial order
		self.init_quantity = initial_order.totalQuantity

		## Place initial order
		self.setup(initial_order)

		## Switches
		self.soft_stop_switch = True
		self.take_profit_switch = True
		self.hard_stop_switch = True

		## Placeholders
		self.num_filled = 0
		self.num_filled_on_close = 0

		## Period details
		self.time_period = 1
		self.maturity = 1

	def setup(self):

		## Initial order
		init_oid = self.manager.order_id
		init_order = limit_order(action = action, quantity = quantity, 
								 price = self.details['entry_price'], purpose = 'initiate')
		self.manager.placeOrder(init_oid, self.contract, init_order)

		## Take profit order
		self.manager.order_id_offset += 1
		profit_oid = init_oid + 1
		profit_order = limit_order(action = self.closing_action, quantity = self.init_quantity,
								   price = self.details['take_profit'], purpose = 'close')

		## Stop loss order
		self.manager.order_id_offset += 1
		loss_oid = profit_oid + 1
		loss_order = limit_order(action = self.closing_action, quantity = self.init_quantity,
								   price = self.details['hard_stop'], purpose = 'close')

		## Orders object for modifications
		self.orders = TradeOrders(init_order = init_order, init_oid = init_oid, 
								  profit_order = profit_order, profit_oid = profit_oid,
								  loss_order = loss_order, loss_oid = loss_oid)
		
		## Book keeping
		for order, oid in zip([init_order, profit_order, loss_order], [init_oid, profit_oid, loss_oid]):
			self.manager.orders[oid] = order
			self.manager.order2trade[oid] = self

		## Get next ID
		self.manager.reqIds(-1)

	def on_fill(self):

		## Set trade status
		self.status = 'ACTIVE'
		self.execution_time = datetime.now()

		## Send closing orders
		self.manager.placeOrder(self.orders.profit_oid, self.contract, self.orders.profit_order)

	def on_close(self):

		## Clean up maps
		for i in range(1, len(self.orders), 2):
			oid = self.orders[i]
			del self.manager.order2trade[oid]
			del self.manager.orders[oid]
			self.manager.cancelOrder(oid)

		# Remove trade from list
		del self.manager.trades[self.symbol]

		## Cancel market data
		self.manager.cancelMktData(self.manager.ticker_ids[self.symbol])

	def update_and_send(self, adjusted_price):
		
		self.orders.loss_order.lmtPrice = adjusted_price
		self.orders.loss_order.totalQuantity -= self.num_filled_on_close
		self.manager.placeOrder(self.orders.loss_oid, self.contract, self.orders.loss_order)	

	def on_update(self, price):

		self.last_update = price

		if self.status == 'ACTIVE':

			if self.is_hard_stop() and self.hard_stop_switch:

				print('HARD STOP')

				adjust_price = adjust_price(self.last_update, self.tick_incr, self.direction, margin = 1)
				if self.orders.loss_order.lmtPrice != adjusted_price:
					self.update_and_send(adjusted_price)

			elif self.is_soft_stop() and self.soft_stop_switch: 

				print('SOFT STOP')

				adjusted_price = adjust_price(self.last_update, self.tick_incr, self.direction, margin = 1)
				if self.orders.loss_order.lmtPrice != adjusted_price:
					self.update_and_send(adjusted_price)

			elif self.is_matured():

				print('MATURITY')

				factor = 1 if self.is_in_profit() else -1
				self.closing_details['hard_stop'] = adjust_price(self.last_update, self.tick_incr, factor * self.direction, margin = 1)
				self.soft_stop_switch = False

		elif self.status == 'PENDING':
			
			if self.is_no_fill():

				print('NO FILL')

				self.on_close()

		elif self.status == 'CLOSING':
			pass

	## Action logic
	def is_in_profit(self):

		target = self.init_order.lmtPrice
		return self.direction * (self.last_update - target) >= 0

	def is_take_profit(self):
		
		target = self.closing_details['take_profit']
		return self.direction * (self.last_update - target) > 0

	def is_hard_stop(self):

		target = self.closing_details['hard_stop']
		return self.direction * (target - self.last_update) > 0

	def is_soft_stop(self):

		dt = datetime.now()
		target = self.closing_details['soft_stop']
		return dt.minute % 1 == 0 and dt.second == 0 and self.direction * (target - self.last_update) > 0

	def is_matured(self):

		dt = datetime.now()
		delta = dt - self.init_time
		return delta.seconds >= self.time_period * self.maturity * 60

	def is_no_fill(self):

		dt = datetime.now()
		delta = dt - self.init_time
		return self.num_filled == 0 and delta.seconds >= self.time_period * 60
