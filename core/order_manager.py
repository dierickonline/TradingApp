# core/order_manager.py
"""Order manager for handling IB order operations"""
import logging
import math
from PyQt6.QtCore import QObject, pyqtSignal
from ibapi.order import Order

logger = logging.getLogger(__name__)


def _round_to_tick(price: float, min_tick: float) -> float:
    """Snap ``price`` to the nearest multiple of ``min_tick``.

    IB rejects orders whose prices aren't on the contract's tick grid
    (error 110). FP imprecision after the divide can leave a residual
    fractional part, so we re-round to a sensible decimal precision
    derived from the tick (e.g. minTick=0.0001 → 4 decimals).
    """
    if min_tick is None or min_tick <= 0 or price <= 0:
        return price
    steps = round(price / min_tick)
    snapped = steps * min_tick
    decimals = max(0, -int(math.floor(math.log10(min_tick))))
    return round(snapped, decimals + 2)


class OrderManager(QObject):
    """Manages order submissions and bracket orders"""
    
    # Signals
    order_status_update = pyqtSignal(int, str, float, float, float, str)  # orderId, status, filled, remaining, avgFillPrice, permId
    order_error = pyqtSignal(str)  # error message
    
    def __init__(self, ib_app=None, contract_resolver=None):
        super().__init__()
        self.ib_app = ib_app
        self.contract_resolver = contract_resolver
        self.next_order_id = None
        self.active_orders = {}  # order_id -> order info

    def set_ib_app(self, ib_app):
        """Set the IB app instance"""
        self.ib_app = ib_app

    def set_contract_resolver(self, resolver):
        """Set the contract resolver used to qualify SMART contracts."""
        self.contract_resolver = resolver
        
    def set_next_order_id(self, order_id: int):
        """Set the next valid order ID from IB"""
        self.next_order_id = order_id
        logger.info(f"Next valid order ID: {order_id}")
        
    def get_next_order_id(self) -> int:
        """Get and increment the next order ID.

        Raises ``ConnectionError`` if IB has not yet provided a starting ID
        (i.e. ``nextValidId`` hasn't fired). Callers should guard against
        the not-connected case before invoking; this raise is a hard fence
        for accidental use.
        """
        if self.next_order_id is None:
            raise ConnectionError("Order ID not initialized — not connected to IB")

        current_id = self.next_order_id
        self.next_order_id += 1
        return current_id
        
    def create_bracket_order(self, ticker: str, action: str, entry_price: float,
                       stop_loss: float, take_profit: float, quantity: int,
                       entry_order_type: str = "LMT", trailing_percent: float = 0.0):
        """Create and submit a bracket order with specified quantity and entry order type.

        Contract resolution is async (so delayed-data subscriptions get a
        primaryExchange) — synchronous validation runs first, then the
        actual order placement happens in the resolve callback.

        ``trailing_percent`` > 0 swaps the protective stop leg for a TRAIL
        order; ``stop_loss`` becomes the initial trigger (``trailStopPrice``).
        """
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

        if not self.contract_resolver:
            error_msg = "Cannot create order: contract resolver not configured"
            logger.error(error_msg)
            self.order_error.emit(error_msg)
            return

        self.contract_resolver.resolve(
            ticker,
            lambda c, e, t=ticker, a=action, ep=entry_price, sl=stop_loss,
                   tp=take_profit, q=quantity, ot=entry_order_type, tr=trailing_percent:
                self._on_contract_resolved_bracket(t, a, ep, sl, tp, q, ot, tr, c, e),
        )

    def _on_contract_resolved_bracket(self, ticker, action, entry_price,
                                       stop_loss, take_profit, quantity,
                                       entry_order_type, trailing_percent,
                                       contract, error):
        if not contract:
            error_msg = f"Contract resolution failed for {ticker}: {error}"
            logger.error(error_msg)
            self.order_error.emit(error_msg)
            return
        if not self.ib_app or not self.ib_app.isConnected():
            self.order_error.emit("Not connected to IB")
            return

        try:
            min_tick = None
            if self.contract_resolver is not None:
                getter = getattr(self.contract_resolver, 'get_min_tick', None)
                if callable(getter):
                    min_tick = getter(ticker)
            if min_tick:
                snapped_entry = _round_to_tick(entry_price, min_tick)
                snapped_stop = _round_to_tick(stop_loss, min_tick)
                snapped_target = _round_to_tick(take_profit, min_tick)
                if (snapped_entry, snapped_stop, snapped_target) != (entry_price, stop_loss, take_profit):
                    logger.info(
                        f"Snapping {ticker} prices to minTick={min_tick}: "
                        f"entry {entry_price}->{snapped_entry}, "
                        f"stop {stop_loss}->{snapped_stop}, "
                        f"target {take_profit}->{snapped_target}"
                    )
                entry_price = snapped_entry
                stop_loss = snapped_stop
                take_profit = snapped_target

            parent_order_id = self.get_next_order_id()
            stop_order_id = self.get_next_order_id()
            profit_order_id = self.get_next_order_id()

            if entry_order_type == "STP":
                parent_order = self._create_stop_order(action, quantity, entry_price)
                order_type_text = "STOP"
            else:
                parent_order = self._create_limit_order(action, quantity, entry_price)
                order_type_text = "LIMIT"

            parent_order.orderId = parent_order_id
            parent_order.transmit = False

            stop_action = "SELL" if action == "BUY" else "BUY"
            if trailing_percent > 0:
                stop_order = self._create_trailing_stop_order(
                    stop_action, quantity, trailing_percent, stop_loss
                )
                stop_desc = f"trailing {trailing_percent}% (initial trigger {stop_loss})"
            else:
                stop_order = self._create_stop_order(stop_action, quantity, stop_loss)
                stop_desc = f"stop @ {stop_loss}"
            stop_order.orderId = stop_order_id
            stop_order.parentId = parent_order_id
            stop_order.tif = "GTC"  # Survive across sessions for swing trades.
            stop_order.transmit = False

            profit_order = self._create_limit_order(stop_action, quantity, take_profit)
            profit_order.orderId = profit_order_id
            profit_order.parentId = parent_order_id
            profit_order.tif = "GTC"
            profit_order.transmit = True

            self.active_orders[parent_order_id] = {
                'ticker': ticker, 'action': action, 'quantity': quantity,
                'entry': entry_price, 'stop': stop_loss, 'profit': take_profit,
                'type': 'bracket_parent', 'entry_order_type': entry_order_type,
                'trailing_percent': trailing_percent,
            }
            self.active_orders[stop_order_id] = {
                'ticker': ticker, 'type': 'bracket_stop', 'parent': parent_order_id,
                'trailing_percent': trailing_percent,
            }
            self.active_orders[profit_order_id] = {
                'ticker': ticker, 'type': 'bracket_profit', 'parent': parent_order_id,
            }

            logger.info(f"Submitting bracket order for {ticker}: {action} {quantity} @ {entry_price} ({order_type_text}), {stop_desc}, target @ {take_profit}")

            self.ib_app.placeOrder(parent_order_id, contract, parent_order)
            self.ib_app.placeOrder(stop_order_id, contract, stop_order)
            self.ib_app.placeOrder(profit_order_id, contract, profit_order)

            logger.info(f"Bracket order submitted with IDs: parent={parent_order_id} ({order_type_text}), stop={stop_order_id}, profit={profit_order_id}")

        except Exception as e:
            error_msg = f"Error creating bracket order: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.order_error.emit(error_msg)


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

    def _create_trailing_stop_order(self, action: str, quantity: int,
                                     trailing_percent: float, stop_price: float) -> Order:
        """Create a percentage trailing stop order.

        ``trailing_percent`` is the % distance the stop trails the high water
        mark (e.g. 2.0 = 2%). ``stop_price`` becomes ``trailStopPrice`` — the
        initial trigger that protects until the trail has a favorable move
        to track from.
        """
        order = Order()
        order.action = action
        order.orderType = "TRAIL"
        order.totalQuantity = quantity
        order.trailingPercent = trailing_percent
        order.trailStopPrice = stop_price
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
            
    def get_active_orders(self) -> dict:
        """Get all active orders"""
        return self.active_orders.copy()