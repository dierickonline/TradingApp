# core/market_data_manager.py
"""Market data manager for handling IB market data subscriptions"""
import logging
from typing import Dict, Optional, Set
from PyQt6.QtCore import QObject, pyqtSignal
from ibapi.contract import Contract
from ibapi.ticktype import TickTypeEnum

logger = logging.getLogger(__name__)


class MarketDataManager(QObject):
    """Manages market data subscriptions and updates"""
    
    # Signals
    market_data_update = pyqtSignal(str, float, float, float, int)  # ticker, bid, ask, last, volume
    subscription_error = pyqtSignal(str, str)  # ticker, error message
    
    def __init__(self, ib_app=None):
        super().__init__()
        self.ib_app = ib_app
        self.active_subscriptions = {}  # ticker -> req_id mapping
        self.market_data = {}  # req_id -> market data dict
        self.next_req_id = 1000  # Start with a high number to avoid conflicts
        
        # Track position subscriptions separately
        self.position_subscriptions = {}  # ticker -> req_id for positions
        self.trader_subscription = None  # Current trader widget subscription
        
    def set_ib_app(self, ib_app):
        """Set the IB app instance"""
        self.ib_app = ib_app
        
    def subscribe_market_data(self, ticker: str, is_position: bool = False):
        """Subscribe to market data for a ticker
        
        Args:
            ticker: The ticker symbol
            is_position: True if this is for position tracking (won't be unsubscribed on ticker change)
        """
        if not self.ib_app or not self.ib_app.isConnected():
            logger.error("Cannot subscribe: Not connected to IB")
            self.subscription_error.emit(ticker, "Not connected to IB")
            return
            
        # Check if already subscribed
        if ticker in self.active_subscriptions:
            logger.info(f"Already subscribed to {ticker}")
            return
            
        try:
            # Create contract
            contract = self._create_stock_contract(ticker)
            
            # Get next request ID
            req_id = self.next_req_id
            self.next_req_id += 1
            
            # Store subscription info
            self.active_subscriptions[ticker] = req_id
            self.market_data[req_id] = {
                'ticker': ticker,
                'bid': None,
                'ask': None,
                'last': None,
                'volume': None,
                'is_position': is_position
            }
            
            # Track position subscriptions separately
            if is_position:
                self.position_subscriptions[ticker] = req_id
            else:
                # Unsubscribe from previous trader subscription if exists
                if self.trader_subscription and self.trader_subscription != ticker:
                    self.unsubscribe_trader_data()
                self.trader_subscription = ticker
            
            # Request market data
            logger.info(f"Requesting market data for {ticker} with req_id {req_id} (position={is_position})")
            self.ib_app.reqMktData(
                req_id,
                contract,
                "",  # Generic tick list
                False,  # Snapshot
                False,  # Regulatory snapshot
                []  # Tag value list
            )
            
        except Exception as e:
            logger.error(f"Error subscribing to {ticker}: {e}")
            self.subscription_error.emit(ticker, str(e))
            # Clean up on error
            if ticker in self.active_subscriptions:
                del self.active_subscriptions[ticker]
            if req_id in self.market_data:
                del self.market_data[req_id]
                
    def unsubscribe_market_data(self, ticker: str):
        """Unsubscribe from market data for a ticker (only if not a position subscription)"""
        if ticker not in self.active_subscriptions:
            logger.warning(f"Not subscribed to {ticker}")
            return
            
        req_id = self.active_subscriptions[ticker]
        
        # Don't unsubscribe position data when changing tickers
        if ticker in self.position_subscriptions:
            logger.info(f"Keeping position subscription for {ticker}")
            return
            
        self._unsubscribe_ticker(ticker)
            
    def unsubscribe_trader_data(self):
        """Unsubscribe only the trader widget's current ticker"""
        if self.trader_subscription and self.trader_subscription in self.active_subscriptions:
            # Only unsubscribe if it's not also a position subscription
            if self.trader_subscription not in self.position_subscriptions:
                self._unsubscribe_ticker(self.trader_subscription)
            self.trader_subscription = None
            
    def unsubscribe_position_data(self, ticker: str):
        """Explicitly unsubscribe position data"""
        if ticker in self.position_subscriptions:
            del self.position_subscriptions[ticker]
            # Only unsubscribe if it's not the current trader ticker
            if ticker != self.trader_subscription:
                self._unsubscribe_ticker(ticker)
                
    def _unsubscribe_ticker(self, ticker: str):
        """Internal method to actually unsubscribe from a ticker"""
        if ticker not in self.active_subscriptions:
            return
            
        req_id = self.active_subscriptions[ticker]
        
        try:
            if self.ib_app and self.ib_app.isConnected():
                logger.info(f"Canceling market data for {ticker} with req_id {req_id}")
                self.ib_app.cancelMktData(req_id)
                
            # Clean up
            del self.active_subscriptions[ticker]
            if req_id in self.market_data:
                del self.market_data[req_id]
                
        except Exception as e:
            logger.error(f"Error unsubscribing from {ticker}: {e}")
            
    def handle_tick_price(self, req_id: int, tick_type: int, price: float, attrib):
        """Handle tick price updates from IB"""
        if req_id not in self.market_data:
            return
            
        data = self.market_data[req_id]
        ticker = data['ticker']
        
        # Update price based on tick type
        if tick_type == TickTypeEnum.BID:
            data['bid'] = price
            logger.debug(f"{ticker} Bid: {price}")
        elif tick_type == TickTypeEnum.ASK:
            data['ask'] = price
            logger.debug(f"{ticker} Ask: {price}")
        elif tick_type == TickTypeEnum.LAST:
            data['last'] = price
            logger.debug(f"{ticker} Last: {price}")
            
        # Emit update if we have both bid and ask
        if data['bid'] is not None and data['ask'] is not None:
            self.market_data_update.emit(
                ticker,
                data['bid'],
                data['ask'],
                data['last'] or 0,
                data['volume'] or 0
            )
            
    def handle_tick_size(self, req_id: int, tick_type: int, size: int):
        """Handle tick size updates from IB"""
        if req_id not in self.market_data:
            return
            
        data = self.market_data[req_id]
        
        # Update size based on tick type
        if tick_type == TickTypeEnum.VOLUME:
            data['volume'] = size
            logger.debug(f"{data['ticker']} Volume: {size}")
            
    def handle_error(self, req_id: int, error_code: int, error_string: str):
        """Handle errors from IB"""
        if req_id in self.market_data:
            ticker = self.market_data[req_id]['ticker']
            logger.error(f"Market data error for {ticker}: {error_code} - {error_string}")
            self.subscription_error.emit(ticker, error_string)
            
    def clear_all_subscriptions(self):
        """Clear all active subscriptions"""
        for ticker in list(self.active_subscriptions.keys()):
            self._unsubscribe_ticker(ticker)
        self.position_subscriptions.clear()
        self.trader_subscription = None
            
    def _create_stock_contract(self, symbol: str) -> Contract:
        """Create a stock contract for the given symbol"""
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        return contract
        
    def get_active_tickers(self) -> list:
        """Get list of actively subscribed tickers"""
        return list(self.active_subscriptions.keys())
        
    def is_subscribed(self, ticker: str) -> bool:
        """Check if subscribed to a ticker"""
        return ticker in self.active_subscriptions
        
    def get_position_subscriptions(self) -> Set[str]:
        """Get set of position subscriptions"""
        return set(self.position_subscriptions.keys())
        
    def refresh_position_subscriptions(self, position_tickers: Set[str]):
        """Refresh position subscriptions - subscribe to new, unsubscribe from old"""
        current_position_subs = self.get_position_subscriptions()
        
        # Subscribe to new positions
        for ticker in position_tickers - current_position_subs:
            logger.info(f"Adding position subscription for {ticker}")
            self.subscribe_market_data(ticker, is_position=True)
            
        # Unsubscribe from closed positions
        for ticker in current_position_subs - position_tickers:
            logger.info(f"Removing position subscription for {ticker}")
            self.unsubscribe_position_data(ticker)