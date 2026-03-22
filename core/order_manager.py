# core/order_manager.py
"""Order manager for handling IB order operations"""
import logging
from typing import Dict, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from ibapi.contract import Contract
from ibapi.order import Order

logger = logging.getLogger(__name__)


class OrderManager(QObject):
    """Manages order submissions and bracket orders"""
    
    # Signals
    order_status_update = pyqtSignal(int, str, float, float, float, str)  # orderId, status, filled, remaining, avgFillPrice, permId
    order_error = pyqtSignal(str)  # error message
    
    def __init__(self, ib_app=None):
        super().__init__()
        self.ib_app = ib_app
        self.next_order_id = None
        self.active_orders = {}  # order_id -> order info
        
    def set_ib_app(self, ib_app):
        """Set the IB app instance"""
        self.ib_app = ib_app
        
    def set_next_order_id(self, order_id: int):
        """Set the next valid order ID from IB"""
        self.next_order_id = order_id
        logger.info(f"Next valid order ID: {order_id}")
        
    def get_next_order_id(self) -> int:
        """Get and increment the next order ID"""
        if self.next_order_id is None:
            logger.error("Next order ID not set")
            return None
            
        current_id = self.next_order_id
        self.next_order_id += 1
        return current_id
        
    def create_bracket_order(self, ticker: str, action: str, entry_price: float, 
                       stop_loss: float, take_profit: float, quantity: int,
                       entry_order_type: str = "LMT"):
        """Create and submit a bracket order with specified quantity and entry order type"""
        if not self.ib_app or not self.ib_app.isConnected():
            error_msg = "Cannot create order: Not connected to IB"
            logger.error(error_msg)
            self.order_error.emit(error_msg)
            return
            
        if self.next_order_id is None:
            error_msg = "Cannot create order: Order ID not initialized"
            logger.error(error_msg)
            self.order_error.emit(error_msg)
            return
            
        if quantity <= 0:
            error_msg = f"Invalid quantity: {quantity}"
            logger.error(error_msg)
            self.order_error.emit(error_msg)
            return
            
        try:
            # Create contract
            contract = self._create_stock_contract(ticker)
            
            # Get order IDs for bracket order
            parent_order_id = self.get_next_order_id()
            stop_order_id = self.get_next_order_id()
            profit_order_id = self.get_next_order_id()
            
            # Create parent order (entry) - can be LIMIT or STOP
            if entry_order_type == "STP":
                parent_order = self._create_stop_order(action, quantity, entry_price)
                order_type_text = "STOP"
            else:
                parent_order = self._create_limit_order(action, quantity, entry_price)
                order_type_text = "LIMIT"
                
            parent_order.orderId = parent_order_id
            parent_order.transmit = False  # Don't transmit until bracket is complete
            
            # Create stop loss order
            stop_action = "SELL" if action == "BUY" else "BUY"
            stop_order = self._create_stop_order(stop_action, quantity, stop_loss)
            stop_order.orderId = stop_order_id
            stop_order.parentId = parent_order_id
            stop_order.transmit = False
            
            # Create take profit order
            profit_order = self._create_limit_order(stop_action, quantity, take_profit)
            profit_order.orderId = profit_order_id
            profit_order.parentId = parent_order_id
            profit_order.transmit = True  # Transmit all orders now
            
            # Store order info
            self.active_orders[parent_order_id] = {
                'ticker': ticker,
                'action': action,
                'quantity': quantity,
                'entry': entry_price,
                'stop': stop_loss,
                'profit': take_profit,
                'type': 'bracket_parent',
                'entry_order_type': entry_order_type
            }
            self.active_orders[stop_order_id] = {
                'ticker': ticker,
                'type': 'bracket_stop',
                'parent': parent_order_id
            }
            self.active_orders[profit_order_id] = {
                'ticker': ticker,
                'type': 'bracket_profit',
                'parent': parent_order_id
            }
            
            # Submit orders
            logger.info(f"Submitting bracket order for {ticker}: {action} {quantity} @ {entry_price} ({order_type_text}), stop @ {stop_loss}, target @ {take_profit}")
            
            self.ib_app.placeOrder(parent_order_id, contract, parent_order)
            self.ib_app.placeOrder(stop_order_id, contract, stop_order)
            self.ib_app.placeOrder(profit_order_id, contract, profit_order)
            
            logger.info(f"Bracket order submitted with IDs: parent={parent_order_id} ({order_type_text}), stop={stop_order_id}, profit={profit_order_id}")
            
        except Exception as e:
            error_msg = f"Error creating bracket order: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.order_error.emit(error_msg)
            
    def _create_stock_contract(self, symbol: str) -> Contract:
        """Create a stock contract for the given symbol"""
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        return contract
        
    def _create_limit_order(self, action: str, quantity: int, limit_price: float) -> Order:
        """Create a limit order"""
        order = Order()
        order.action = action
        order.orderType = "LMT"
        order.totalQuantity = quantity
        order.lmtPrice = limit_price
        order.eTradeOnly = False
        order.firmQuoteOnly = False
        return order
        
    def _create_stop_order(self, action: str, quantity: int, stop_price: float) -> Order:
        """Create a stop order"""
        order = Order()
        order.action = action
        order.orderType = "STP"
        order.totalQuantity = quantity
        order.auxPrice = stop_price  # Stop price for stop orders
        order.eTradeOnly = False
        order.firmQuoteOnly = False
        return order
        
    def handle_order_status(self, order_id: int, status: str, filled: float, 
                          remaining: float, avg_fill_price: float, perm_id: int,
                          parent_id: int, last_fill_price: float, client_id: int,
                          why_held: str, mkt_cap_price: float):
        """Handle order status updates from IB"""
        if order_id in self.active_orders:
            order_info = self.active_orders[order_id]
            logger.info(f"Order {order_id} ({order_info['type']}): {status}, filled={filled}, remaining={remaining}")
            
            # Emit status update
            self.order_status_update.emit(order_id, status, filled, remaining, avg_fill_price, str(perm_id))
            
            # Clean up completed orders
            if status in ["Filled", "Cancelled", "ApiCancelled"]:
                logger.info(f"Order {order_id} completed with status: {status}")
                # Note: In a real application, you might want to keep order history
                
    def cancel_order(self, order_id: int):
        """Cancel an order"""
        if not self.ib_app or not self.ib_app.isConnected():
            logger.error("Cannot cancel order: Not connected to IB")
            return
            
        try:
            logger.info(f"Cancelling order {order_id}")
            self.ib_app.cancelOrder(order_id)
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            
    def get_active_orders(self) -> Dict:
        """Get all active orders"""
        return self.active_orders.copy()