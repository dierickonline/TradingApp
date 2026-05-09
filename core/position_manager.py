# core/position_manager.py
"""Position manager for handling IB position tracking and P&L calculations"""
import logging
from typing import Dict, Optional, Set
from PyQt6.QtCore import QObject, pyqtSignal
from ibapi.contract import Contract
from ibapi.order import Order

logger = logging.getLogger(__name__)


class Position:
    """Represents a trading position"""
    def __init__(self, contract, quantity: float, avg_cost: float):
        self.contract = contract
        self.symbol = contract.symbol
        self.quantity = quantity
        self.avg_cost = avg_cost
        self.current_price = 0.0
        self.realized_pnl = 0.0
        # Track orders associated with this position
        self.parent_order_ids = set()  # Parent orders for this position
        self.child_order_ids = set()   # Stop loss and take profit orders
        
    @property
    def market_value(self) -> float:
        """Current market value of the position"""
        return self.quantity * self.current_price
        
    @property
    def unrealized_pnl(self) -> float:
        """Unrealized P&L"""
        if self.current_price == 0:
            return 0.0
        return (self.current_price - self.avg_cost) * self.quantity
        
    @property
    def total_pnl(self) -> float:
        """Total P&L (realized + unrealized)"""
        return self.realized_pnl + self.unrealized_pnl
        
    def update_price(self, price: float):
        """Update current market price"""
        self.current_price = price


class PositionManager(QObject):
    """Manages positions and P&L calculations"""
    
    # Signals
    position_update = pyqtSignal(str, object)  # symbol, position object
    position_removed = pyqtSignal(str)  # symbol
    all_positions_updated = pyqtSignal()  # when position update cycle completes
    close_position_error = pyqtSignal(str)  # error message
    cancel_orders = pyqtSignal(list)  # list of order IDs to cancel
    
    def __init__(self, ib_app=None):
        super().__init__()
        self.ib_app = ib_app
        self.positions = {}  # symbol -> Position object
        self.next_order_id = None
        self.pending_updates = set()  # Track symbols expecting price updates
        
        # Track used order IDs to prevent reuse
        self.used_order_ids = set()
        self.filled_order_ids = set()  # Track filled orders specifically
        
        # Track open orders
        self.open_orders = {}  # order_id -> order info
        self.symbol_to_orders = {}  # symbol -> set of order IDs
        
    def set_ib_app(self, ib_app):
        """Set the IB app instance"""
        self.ib_app = ib_app
        
    def set_next_order_id(self, order_id: int):
        """Update the next order ID"""
        # Always jump ahead significantly to avoid conflicts with recent orders
        if self.next_order_id is None:
            self.next_order_id = order_id + 100  # Start 100 IDs ahead
        else:
            # If IB suggests a lower ID than we're using, keep our higher one
            self.next_order_id = max(self.next_order_id, order_id + 100)
            
        logger.info(f"Position Manager: Next order ID set to {self.next_order_id}")
        
    def request_positions(self):
        """Request current positions from IB"""
        if not self.ib_app or not self.ib_app.isConnected():
            logger.error("Cannot request positions: Not connected to IB")
            return
            
        logger.info("Requesting positions from IB")
        self.ib_app.reqPositions()
        
        # Also request open orders to track stop loss and take profit orders
        self.request_open_orders()
        
    def handle_position(self, account: str, contract: Contract, position: float, avg_cost: float):
        """Handle position update from IB"""
        try:
            symbol = contract.symbol
            
            if position == 0:
                # Position closed
                if symbol in self.positions:
                    # Cancel any remaining orders for this position
                    self._cancel_position_orders(symbol)
                    del self.positions[symbol]
                    # Use QTimer to defer the signal emission
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self.position_removed.emit(symbol))
                return
        except Exception as e:
            logger.error(f"Error in handle_position: {e}", exc_info=True)
            return
            
        # Create or update position
        if symbol not in self.positions:
            self.positions[symbol] = Position(contract, position, avg_cost)
            logger.info(f"New position: {symbol} qty={position} avg_cost={avg_cost}")
        else:
            # Update existing position
            pos = self.positions[symbol]
            pos.quantity = position
            pos.avg_cost = avg_cost
            logger.info(f"Updated position: {symbol} qty={position} avg_cost={avg_cost}")
            
        # Track that we need a price update for this symbol
        self.pending_updates.add(symbol)
        
        # Emit update
        self.position_update.emit(symbol, self.positions[symbol])
        
    def handle_position_end(self):
        """Called when all positions have been received"""
        logger.info("Position update complete")
        
        # Remove positions that weren't in the update (closed positions)
        current_symbols = set(self.pending_updates)
        symbols_to_remove = [sym for sym in self.positions.keys() if sym not in current_symbols]
        
        for symbol in symbols_to_remove:
            self._cancel_position_orders(symbol)
            del self.positions[symbol]
            self.position_removed.emit(symbol)
            
        self.pending_updates.clear()
        
        # Emit the signal to update position subscriptions
        self.all_positions_updated.emit()
        
        # Cancel position updates
        if self.ib_app and self.ib_app.isConnected():
            self.ib_app.cancelPositions()
            
    def update_market_price(self, symbol: str, price: float):
        """Update market price for a position"""
        if symbol in self.positions:
            self.positions[symbol].update_price(price)
            self.position_update.emit(symbol, self.positions[symbol])
            
    def handle_commission_report(self, commission_report):
        """Handle commission report from IB - NO LONGER USED"""
        # Commission tracking has been removed from position management
        # Commissions are now only tracked in the execution logbook
        logger.debug(f"Commission report received but not processed in position manager")
        
    def handle_execution_details(self, reqId: int, contract: Contract, execution):
        """Handle execution details - simplified without commission tracking"""
        try:
            symbol = contract.symbol
            logger.info(f"Execution for {symbol}: {execution.shares} @ {execution.price}")
            
        except Exception as e:
            logger.error(f"Error handling execution details: {e}")
            
    def handle_open_order(self, order_id: int, contract: Contract, order: Order, order_state):
        """Track open orders for positions"""
        try:
            symbol = contract.symbol
            
            # Store order info
            self.open_orders[order_id] = {
                'symbol': symbol,
                'contract': contract,
                'order': order,
                'state': order_state,
                'parent_id': order.parentId
            }
            
            # Track by symbol
            if symbol not in self.symbol_to_orders:
                self.symbol_to_orders[symbol] = set()
            self.symbol_to_orders[symbol].add(order_id)
            
            # Associate orders with positions
            if symbol in self.positions:
                if order.parentId > 0:
                    # This is a child order
                    self.positions[symbol].child_order_ids.add(order_id)
                    # Find parent and add to its position
                    parent_info = self.open_orders.get(order.parentId)
                    if parent_info and parent_info['symbol'] == symbol:
                        self.positions[symbol].parent_order_ids.add(order.parentId)
                else:
                    # This might be a parent order
                    self.positions[symbol].parent_order_ids.add(order_id)
                    
        except Exception as e:
            logger.error(f"Error handling open order: {e}")
            
    def _cancel_position_orders(self, symbol: str):
        """Cancel all orders associated with a position"""
        if symbol not in self.symbol_to_orders:
            return
            
        order_ids_to_cancel = list(self.symbol_to_orders[symbol])
        
        if order_ids_to_cancel:
            logger.info(f"Cancelling {len(order_ids_to_cancel)} orders for {symbol}: {order_ids_to_cancel}")
            
            for order_id in order_ids_to_cancel:
                try:
                    if self.ib_app and self.ib_app.isConnected():
                        self.ib_app.cancelOrder(order_id)
                        logger.info(f"Cancelled order {order_id}")
                except Exception as e:
                    logger.error(f"Error cancelling order {order_id}: {e}")
                    
        # Clean up tracking
        del self.symbol_to_orders[symbol]
        for order_id in order_ids_to_cancel:
            if order_id in self.open_orders:
                del self.open_orders[order_id]
            
    def close_position(self, symbol: str, percentage: float = 100.0):
        """Close a position by percentage (50 or 100)"""
        try:
            if not self.ib_app or not self.ib_app.isConnected():
                self.close_position_error.emit("Not connected to IB")
                return
                
            if symbol not in self.positions:
                self.close_position_error.emit(f"No position found for {symbol}")
                return
                
            if self.next_order_id is None:
                self.close_position_error.emit("Order ID not initialized")
                return
                
            position = self.positions[symbol]
            
            # Get the actual position quantity from IB's perspective
            actual_position_qty = position.quantity
            
            # Calculate quantity to close
            quantity_to_close = int(abs(actual_position_qty) * (percentage / 100.0))
            if quantity_to_close == 0:
                self.close_position_error.emit("Position too small to close partially")
                return
                
            # For closing positions:
            # - If LONG (positive qty): SELL to close
            # - If SHORT (negative qty): BUY to close (cover)
            if actual_position_qty > 0:
                # Long position - sell to close
                action = "SELL"
                # Make sure we don't sell more than we own
                quantity_to_close = min(quantity_to_close, int(actual_position_qty))
            else:
                # Short position - buy to close (cover)
                action = "BUY"
                # For short positions, quantity is negative, so abs() it
                quantity_to_close = min(quantity_to_close, int(abs(actual_position_qty)))
                
            logger.info(f"Position details: {actual_position_qty} shares")
            logger.info(f"Closing {percentage}% = {quantity_to_close} shares with {action} order")
            
            # If closing 100%, cancel all related orders first
            if percentage == 100.0:
                self._cancel_position_orders(symbol)
            
            # Create a fresh contract to ensure all fields are properly set.
            # primaryExchange is copied from the position's IB-supplied
            # contract — delayed-data accounts otherwise get an "ambiguous
            # contract" rejection on SMART-only stock orders.
            contract = Contract()
            contract.symbol = position.contract.symbol
            contract.secType = "STK"
            contract.exchange = "SMART"
            contract.primaryExchange = getattr(position.contract, 'primaryExchange', '') or ''
            contract.currency = "USD"
            
            # Create market order with proper settings for closing positions
            order = Order()
            order.action = action
            order.orderType = "MKT"
            order.eTradeOnly = False
            order.firmQuoteOnly = False
            order.totalQuantity = quantity_to_close
            order.tif = "DAY"
            
            # CRITICAL FOR CLOSING POSITIONS ON NON-SHORTABLE STOCKS:
            if action == "SELL" and actual_position_qty > 0:
                # This is closing a long position
                # Tell IB explicitly that we're not short selling
                order.shortSaleSlot = 0  # 0 = Not a short sale
                order.designatedLocation = ""  # Empty for non-short sales
                
            # These help ensure proper position closing
            order.transmit = True
            order.clearingIntent = "IB"  # Let IB handle clearing
            order.orderRef = f"ClosePos_{symbol}_{percentage}%"  # Reference for tracking
            
            # Get a fresh order ID and ensure it's unique
            order_id = self.get_next_valid_order_id()

            # Log detailed order info for debugging
            logger.info(f"Closing {percentage}% of {symbol} position:")
            logger.info(f"  Order ID: {order_id}")
            logger.info(f"  Action: {action}")
            logger.info(f"  Quantity: {quantity_to_close}")
            logger.info(f"  Order Ref: {order.orderRef}")
            logger.info(f"  Contract: {contract.symbol} {contract.secType} {contract.exchange} {contract.currency}")
            
            # Submit order
            self.ib_app.placeOrder(order_id, contract, order)
            
            # Don't remove the position here - wait for IB to confirm
            logger.info(f"Close order submitted for {symbol} with order ID {order_id}")
            
        except Exception as e:
            error_msg = f"Error closing position: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.close_position_error.emit(error_msg)
            
    def get_total_pnl(self) -> float:
        """Get total P&L across all positions"""
        return sum(pos.total_pnl for pos in self.positions.values())
        
    def get_positions_list(self) -> list:
        """Get list of all positions"""
        return list(self.positions.values())
        
    def get_next_valid_order_id(self) -> int:
        """Get a guaranteed unique order ID"""
        if self.next_order_id is None:
            raise ValueError("Order ID not initialized - not connected to IB")
            
        # Start with current next_order_id
        order_id = self.next_order_id
        
        # Skip any previously used IDs
        while order_id in self.used_order_ids:
            order_id += 1
            logger.debug(f"Skipping used order ID {order_id}")
            
        # Update next_order_id to be well ahead of this one
        self.next_order_id = order_id + 10  # Jump ahead by 10 to avoid conflicts
        
        # Track this ID as used
        self.used_order_ids.add(order_id)
        
        # Keep only recent used IDs to prevent memory growth
        if len(self.used_order_ids) > 1000:
            # Keep only the 500 most recent IDs
            sorted_ids = sorted(self.used_order_ids)
            self.used_order_ids = set(sorted_ids[-500:])
            
        logger.info(f"Generated new order ID: {order_id}, next will be >= {self.next_order_id}")
        return order_id
        
    def validate_position_before_close(self, symbol: str) -> tuple:
        """Validate position data before attempting to close
        Returns: (is_valid, error_message)
        """
        if symbol not in self.positions:
            return False, f"No position found for {symbol}"
            
        position = self.positions[symbol]
        
        if position.quantity == 0:
            return False, "Position quantity is zero"
            
        # Log current position state
        logger.info(f"Validating position for {symbol}:")
        logger.info(f"  Quantity: {position.quantity}")
        logger.info(f"  Average cost: ${position.avg_cost:.2f}")
        logger.info(f"  Current price: ${position.current_price:.2f}")
        logger.info(f"  Contract type: {position.contract.secType}")
        
        return True, ""
        
    def request_open_orders(self):
        """Request all open orders from IB"""
        if not self.ib_app or not self.ib_app.isConnected():
            return
            
        try:
            logger.info("Requesting open orders")
            self.ib_app.reqAllOpenOrders()
        except Exception as e:
            logger.error(f"Error requesting open orders: {e}")
            
    def handle_order_status(self, order_id: int, status: str, filled: float, 
                          remaining: float, avg_fill_price: float, perm_id: int,
                          parent_id: int, last_fill_price: float, client_id: int,
                          why_held: str, mkt_cap_price: float):
        """Track order status to prevent reusing filled order IDs and clean up completed orders"""
        if status in ["Filled", "Cancelled", "ApiCancelled"]:
            self.filled_order_ids.add(order_id)
            self.used_order_ids.add(order_id)
            logger.info(f"Order {order_id} marked as {status}")
            
            # Remove from open orders tracking
            if order_id in self.open_orders:
                order_info = self.open_orders[order_id]
                symbol = order_info['symbol']
                
                # Remove from symbol tracking
                if symbol in self.symbol_to_orders:
                    self.symbol_to_orders[symbol].discard(order_id)
                    if not self.symbol_to_orders[symbol]:
                        del self.symbol_to_orders[symbol]
                        
                # Remove from position tracking
                if symbol in self.positions:
                    self.positions[symbol].parent_order_ids.discard(order_id)
                    self.positions[symbol].child_order_ids.discard(order_id)
                    
                del self.open_orders[order_id]
            
    def reset_order_ids(self):
        """Reset order ID tracking - use with caution"""
        logger.warning("Resetting order ID tracking")
        self.used_order_ids.clear()
        self.filled_order_ids.clear()
        if self.next_order_id:
            # Jump significantly ahead to avoid any conflicts
            self.next_order_id += 1000
            logger.info(f"Order IDs reset, next ID will be {self.next_order_id}")
            
    def debug_order_ids(self):
        """Debug method to check order ID status"""
        logger.info("=== Order ID Debug Info ===")
        logger.info(f"Next order ID: {self.next_order_id}")
        logger.info(f"Used order IDs count: {len(self.used_order_ids)}")
        logger.info(f"Filled order IDs count: {len(self.filled_order_ids)}")
        logger.info(f"Open orders count: {len(self.open_orders)}")
        if self.used_order_ids:
            recent_ids = sorted(self.used_order_ids)[-10:]
            logger.info(f"Recent used IDs: {recent_ids}")
        if self.symbol_to_orders:
            for symbol, order_ids in self.symbol_to_orders.items():
                logger.info(f"Orders for {symbol}: {order_ids}")