# core/ib_app.py
import logging
from PyQt6.QtCore import pyqtSignal, QObject
from ibapi.client import EClient
from ibapi.wrapper import EWrapper

logger = logging.getLogger(__name__)


class IBSignals(QObject):
    """Custom signals for thread-safe GUI updates"""
    connection_status = pyqtSignal(bool)
    account_value = pyqtSignal(str, str, str, str)
    error_message = pyqtSignal(int, int, str)
    tick_price = pyqtSignal(int, int, float, object)  # reqId, tickType, price, attrib
    tick_size = pyqtSignal(int, int, int)  # reqId, tickType, size
    historical_data = pyqtSignal(int, object)  # reqId, bar
    historical_data_end = pyqtSignal(int, str, str)  # reqId, start, end
    next_valid_id = pyqtSignal(int)  # orderId
    order_status = pyqtSignal(int, str, float, float, float, int, int, float, int, str, float)  # full order status
    position = pyqtSignal(str, object, float, float)  # account, contract, position, avgCost
    position_end = pyqtSignal()
    commission_report = pyqtSignal(object)  # commissionReport
    execution_details = pyqtSignal(int, object, object)  # reqId, contract, execution
    execution_details_end = pyqtSignal(int)  # reqId
    open_order = pyqtSignal(int, object, object, object)  # orderId, contract, order, orderState


class IBApp(EWrapper, EClient):
    """
    Interactive Brokers API application that handles connection and data retrieval.
    Inherits from both EWrapper (handles incoming messages) and EClient (sends requests).
    """
    
    def __init__(self, signals):
        EClient.__init__(self, self)
        self.signals = signals
        self.account_values = {}
        logger.info("IBApp initialized")
        
    def error(self, reqId, errorCode, errorString):
        """Handle errors from IB"""
        if errorCode in [2104, 2106, 2158, 2174, 2176]:  # Information messages and warnings
            logger.debug(f"IB Info {errorCode}: {errorString}")
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
        
    def historicalData(self, reqId, bar):
        """Handle historical data bar"""
        self.signals.historical_data.emit(reqId, bar)
        
    def historicalDataEnd(self, reqId, start, end):
        """Handle end of historical data"""
        self.signals.historical_data_end.emit(reqId, start, end)
        
    def nextValidId(self, orderId):
        """Called when connection is established with next valid order ID"""
        logger.info(f"Next valid order ID: {orderId}")
        self.signals.next_valid_id.emit(orderId)
        
    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId,
                   parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        """Handle order status updates"""
        self.signals.order_status.emit(orderId, status, filled, remaining, avgFillPrice,
                                     permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)
                                     
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