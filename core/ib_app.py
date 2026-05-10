# core/ib_app.py
import logging
import threading
from typing import Optional
from PyQt6.QtCore import pyqtSignal, QObject
from ibapi.client import EClient
from ibapi.wrapper import EWrapper

from config import APP_CONFIG

logger = logging.getLogger(__name__)

# Human-readable labels for marketDataType values returned by IB
MARKET_DATA_TYPE_LABELS = {
    1: "Live",
    2: "Frozen",
    3: "Delayed",
    4: "Delayed-Frozen",
}

# Request-ID categories. Used by the central allocator on IBApp so the error
# router can dispatch IB error callbacks back to the right manager without
# relying on hardcoded numeric ranges.
REQ_CATEGORY_MARKET = "market"
REQ_CATEGORY_HISTORICAL = "historical"
REQ_CATEGORY_EXECUTION = "execution"
REQ_CATEGORY_CONTRACT = "contract"

# Allocator starts above the small reserved window we use for special
# single-shot requests (currently reqAccountSummary uses reqId=1).
_REQ_ID_START = 1000


class IBSignals(QObject):
    """Custom signals for thread-safe GUI updates"""
    connection_status = pyqtSignal(bool)
    account_value = pyqtSignal(str, str, str, str)
    error_message = pyqtSignal(int, int, str)
    tick_price = pyqtSignal(int, int, float, object)  # reqId, tickType, price, attrib
    tick_size = pyqtSignal(int, int, int)  # reqId, tickType, size
    historical_data = pyqtSignal(int, object)  # reqId, bar
    historical_data_end = pyqtSignal(int, str, str)  # reqId, start, end
    historical_data_update = pyqtSignal(int, object)  # reqId, bar (live updates)
    next_valid_id = pyqtSignal(int)  # orderId
    order_status = pyqtSignal(int, str, float, float, float, int, int, float, int, str, float)  # full order status
    position = pyqtSignal(str, object, float, float)  # account, contract, position, avgCost
    position_end = pyqtSignal()
    commission_report = pyqtSignal(object)  # commissionReport
    execution_details = pyqtSignal(int, object, object)  # reqId, contract, execution
    execution_details_end = pyqtSignal(int)  # reqId
    open_order = pyqtSignal(int, object, object, object)  # orderId, contract, order, orderState
    contract_details = pyqtSignal(int, object)  # reqId, contractDetails
    contract_details_end = pyqtSignal(int)  # reqId


class IBApp(EWrapper, EClient):
    """
    Interactive Brokers API application that handles connection and data retrieval.
    Inherits from both EWrapper (handles incoming messages) and EClient (sends requests).
    """
    
    def __init__(self, signals):
        EClient.__init__(self, self)
        self.signals = signals
        self.account_values = {}
        # Set before connect() so connectAck can apply it. Defaults to delayed
        # so anyone running without a live data subscription still gets quotes.
        self.market_data_type = APP_CONFIG.default_market_data_type
        # Centralized request-ID registry. Managers call allocate_request_id()
        # to get an ID + category tag; the error router uses request_category()
        # to dispatch to the right manager.
        self._req_id_lock = threading.Lock()
        self._next_req_id = _REQ_ID_START
        self._req_categories: dict[int, str] = {}
        logger.info("IBApp initialized")

    def allocate_request_id(self, category: str) -> int:
        """Allocate a fresh request ID and tag it with a category.

        Thread-safe; the IB run loop is on its own thread but allocation
        currently happens from the GUI thread. The lock is defensive.
        """
        with self._req_id_lock:
            req_id = self._next_req_id
            self._next_req_id += 1
            self._req_categories[req_id] = category
        return req_id

    def release_request_id(self, req_id: int) -> None:
        """Drop a request from the category map once its lifecycle is done."""
        with self._req_id_lock:
            self._req_categories.pop(req_id, None)

    def request_category(self, req_id: int) -> Optional[str]:
        """Return the category a request was allocated under, or None if unknown."""
        with self._req_id_lock:
            return self._req_categories.get(req_id)
        
    def error(self, reqId, errorCode, errorString):
        """Handle errors from IB"""
        # 2104/2106/2158: market data farm OK messages
        # 2174/2176: timezone & fractional-share warnings
        # 10089/10090/10091: "subscription required" notices that IB sends
        #   alongside the auto-fallback to delayed data. Noisy but harmless
        #   when the user has explicitly chosen the Delayed feed.
        # 10167/10168: confirmation that IB is serving delayed data instead of
        #   live (expected when the user picks Delayed, or when Live was
        #   requested without a subscription and IB silently falls back).
        # 300: "Can't find EId with tickerId" — fired when cancelMktData
        #   targets a subscription IB never registered (e.g. one IB rejected
        #   on creation). Benign by the time it arrives; local state has
        #   already been cleaned up.
        if errorCode in [2104, 2106, 2158, 2174, 2176, 10089, 10090, 10091, 10167, 10168, 300]:
            logger.info(f"IB Info {errorCode}: {errorString}")
        else:
            logger.error(f"IB Error {errorCode}: {errorString} (reqId: {reqId})")
        self.signals.error_message.emit(reqId, errorCode, errorString)
        
    def accountSummary(self, reqId, account, tag, value, currency):
        """Receive account summary data"""
        logger.debug(f"Account summary - {account}: {tag}={value} {currency}")
        if tag == "AvailableFunds":
            logger.info(f"Available funds update: {value} {currency} for account {account}")
            self.signals.account_value.emit(account, tag, value, currency)
            
    def accountSummaryEnd(self, reqId):
        """Called when account summary data is complete"""
        pass
    
    def connectAck(self):
        """Called when connection is acknowledged"""
        logger.info("Connection to IB established successfully")
        self.signals.connection_status.emit(True)

    def marketDataType(self, reqId, marketDataType):
        """IB confirms the active market data type for a request."""
        label = MARKET_DATA_TYPE_LABELS.get(marketDataType, str(marketDataType))
        logger.info(f"IB confirmed market data type {marketDataType} ({label}) for reqId {reqId}")

    def connectionClosed(self):
        """Called when connection is closed"""
        logger.info("Connection to IB closed")
        self.signals.connection_status.emit(False)
        
    def tickPrice(self, reqId, tickType, price, attrib):
        """Handle tick price updates"""
        self.signals.tick_price.emit(reqId, tickType, price, attrib)
        
    def tickSize(self, reqId, tickType, size):
        """Handle tick size updates"""
        self.signals.tick_size.emit(reqId, tickType, size)
        
    def contractDetails(self, reqId, contractDetails):
        """Receive resolved contract details (one row per matching listing)."""
        self.signals.contract_details.emit(reqId, contractDetails)

    def contractDetailsEnd(self, reqId):
        """End-of-data marker for a contractDetails request."""
        self.signals.contract_details_end.emit(reqId)

    def historicalData(self, reqId, bar):
        """Handle historical data bar"""
        self.signals.historical_data.emit(reqId, bar)
        
    def historicalDataEnd(self, reqId, start, end):
        """Handle end of historical data"""
        self.signals.historical_data_end.emit(reqId, start, end)

    def historicalDataUpdate(self, reqId, bar):
        """Handle live bar updates (only fires when keepUpToDate=True)."""
        self.signals.historical_data_update.emit(reqId, bar)
        
    def nextValidId(self, orderId):
        """Called when connection is established with next valid order ID.

        This is the canonical 'session fully ready' signal from IB — the
        message-pump thread is running and the server has assigned us an
        order ID. It's the right place to apply session-level settings
        like the market data type.
        """
        logger.info(f"Next valid order ID: {orderId}")
        self.signals.next_valid_id.emit(orderId)
        try:
            label = MARKET_DATA_TYPE_LABELS.get(self.market_data_type, str(self.market_data_type))
            logger.info(f"Requesting market data type {self.market_data_type} ({label})")
            self.reqMarketDataType(self.market_data_type)
        except Exception as e:
            logger.error(f"Failed to set market data type {self.market_data_type}: {e}")
        
    def position(self, account, contract, position, avgCost):
        """Handle position updates"""
        self.signals.position.emit(account, contract, position, avgCost)
        
    def positionEnd(self):
        """Called when all positions have been received"""
        self.signals.position_end.emit()
        
    def commissionReport(self, commissionReport):
        """Handle commission reports"""
        logger.info(f"Commission report received: {commissionReport.commission}")
        self.signals.commission_report.emit(commissionReport)
        
    def execDetails(self, reqId, contract, execution):
        """Handle execution details"""
        logger.info(f"Execution details: {contract.symbol} - {execution.shares} @ {execution.price}")
        self.signals.execution_details.emit(reqId, contract, execution)
        
    def execDetailsEnd(self, reqId):
        """Called when all execution details have been received"""
        logger.info(f"Execution details complete for request {reqId}")
        self.signals.execution_details_end.emit(reqId)
        
    def openOrder(self, orderId, contract, order, orderState):
        """Handle open order"""
        logger.info(f"Open order: {orderId} - {contract.symbol} {order.action} {order.totalQuantity} (parentId: {order.parentId})")
        self.signals.open_order.emit(orderId, contract, order, orderState)
        
    def openOrderEnd(self):
        """Called when all open orders have been received"""
        logger.info("Open orders update complete")
        
    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId,
                   parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        """Handle order status updates"""
        logger.info(f"Order status: {orderId} - {status} (filled: {filled}, remaining: {remaining})")
        self.signals.order_status.emit(orderId, status, filled, remaining, avgFillPrice,
                                     permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)