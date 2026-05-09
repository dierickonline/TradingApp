# core/historical_data_manager.py
"""Historical data manager for fetching historical bars and calculating technical indicators"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal
import pandas as pd

from core.ib_app import REQ_CATEGORY_HISTORICAL

logger = logging.getLogger(__name__)


class HistoricalDataManager(QObject):
    """Manages historical data requests and technical indicator calculations"""

    # Signals
    atr_calculated = pyqtSignal(str, float, int)  # ticker, atr_value, period
    historical_data_error = pyqtSignal(str, str)  # ticker, error message
    historical_data_received = pyqtSignal(str, object)  # ticker, dataframe

    def __init__(self, ib_app=None, contract_resolver=None):
        super().__init__()
        self.ib_app = ib_app
        self.contract_resolver = contract_resolver
        self.active_requests = {}  # req_id -> (ticker, request_type)
        self.historical_data = {}  # req_id -> list of bars

    def set_ib_app(self, ib_app):
        """Set the IB app instance"""
        self.ib_app = ib_app

    def set_contract_resolver(self, resolver):
        """Set the contract resolver used to qualify SMART contracts."""
        self.contract_resolver = resolver

    def request_atr(self, ticker: str, period: int = 14, timeframe: str = "1 day"):
        """Request historical data to calculate ATR.

        Resolution is async — we first ask the resolver to qualify the
        SMART contract (so delayed-data feeds get a primaryExchange), then
        send ``reqHistoricalData`` from the resolve callback.
        """
        if not self.ib_app or not self.ib_app.isConnected():
            logger.error("Cannot request ATR: Not connected to IB")
            self.historical_data_error.emit(ticker, "Not connected to IB")
            return
        if not self.contract_resolver:
            logger.error("Cannot request ATR: contract resolver not configured")
            self.historical_data_error.emit(ticker, "Contract resolver not configured")
            return

        self.contract_resolver.resolve(
            ticker,
            lambda c, e, t=ticker, p=period, tf=timeframe:
                self._on_contract_resolved_atr(t, p, tf, c, e),
        )

    def _on_contract_resolved_atr(self, ticker, period, timeframe, contract, error):
        if not contract:
            logger.error(f"Contract resolution failed for {ticker}: {error}")
            self.historical_data_error.emit(ticker, error or "Contract lookup failed")
            return
        if not self.ib_app or not self.ib_app.isConnected():
            self.historical_data_error.emit(ticker, "Not connected to IB")
            return

        req_id = self.ib_app.allocate_request_id(REQ_CATEGORY_HISTORICAL)
        try:
            self.active_requests[req_id] = (ticker, f"ATR_{period}")
            self.historical_data[req_id] = []

            # Empty end_date means "now"; ATR needs at least period + 1
            # days, take double for accuracy with a 30-day floor.
            duration_days = max(period * 2, 30)
            duration = f"{duration_days} D"

            logger.info(f"Requesting historical data for {ticker} ATR calculation")
            self.ib_app.reqHistoricalData(
                req_id,
                contract,
                "",  # empty = current time
                duration,
                timeframe,
                "TRADES",
                1,  # regular trading hours
                1,  # date as yyyyMMdd HH:mm:ss
                False,  # keep up to date
                [],
            )
        except Exception as e:
            logger.error(f"Error requesting ATR for {ticker}: {e}")
            self.historical_data_error.emit(ticker, str(e))
            self.active_requests.pop(req_id, None)
            self.historical_data.pop(req_id, None)
            self.ib_app.release_request_id(req_id)
                
    def handle_historical_data(self, req_id: int, bar):
        """Handle historical data bar from IB"""
        if req_id not in self.active_requests:
            return
            
        # Store the bar data
        if req_id in self.historical_data:
            self.historical_data[req_id].append({
                'date': bar.date,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume
            })
            
    def handle_historical_data_end(self, req_id: int, start: str, end: str):
        """Handle end of historical data"""
        if req_id not in self.active_requests:
            return
            
        ticker, request_type = self.active_requests[req_id]
        bars = self.historical_data.get(req_id, [])
        
        logger.info(f"Received {len(bars)} bars for {ticker}")
        
        if not bars:
            self.historical_data_error.emit(ticker, "No historical data received")
            self._cleanup_request(req_id)
            return
            
        try:
            # Convert to DataFrame
            df = pd.DataFrame(bars)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)
            
            # Emit the raw data
            self.historical_data_received.emit(ticker, df)
            
            # Calculate ATR if that's what was requested
            if request_type.startswith("ATR_"):
                period = int(request_type.split("_")[1])
                atr_value = self._calculate_atr(df, period)
                
                if atr_value is not None:
                    logger.info(f"ATR({period}) for {ticker}: {atr_value:.4f}")
                    self.atr_calculated.emit(ticker, atr_value, period)
                else:
                    self.historical_data_error.emit(ticker, "Failed to calculate ATR")
                    
        except Exception as e:
            logger.error(f"Error processing historical data for {ticker}: {e}")
            self.historical_data_error.emit(ticker, str(e))
            
        finally:
            self._cleanup_request(req_id)
            
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate Average True Range from OHLC data"""
        try:
            # Calculate True Range
            df['h_l'] = df['high'] - df['low']
            df['h_pc'] = abs(df['high'] - df['close'].shift(1))
            df['l_pc'] = abs(df['low'] - df['close'].shift(1))
            
            df['true_range'] = df[['h_l', 'h_pc', 'l_pc']].max(axis=1)
            
            # Calculate ATR using exponential moving average
            df['atr'] = df['true_range'].ewm(span=period, adjust=False).mean()
            
            # Return the most recent ATR value
            latest_atr = df['atr'].iloc[-1]
            
            return float(latest_atr) if not pd.isna(latest_atr) else None
            
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return None
            
    def calculate_atr_percent(self, ticker: str, price: float, atr: float) -> float:
        """Calculate ATR as a percentage of current price"""
        if price > 0:
            return (atr / price) * 100
        return 0.0
        
    def handle_error(self, req_id: int, error_code: int, error_string: str):
        """Handle errors from IB"""
        if req_id in self.active_requests:
            ticker, _ = self.active_requests[req_id]
            logger.error(f"Historical data error for {ticker}: {error_code} - {error_string}")
            self.historical_data_error.emit(ticker, error_string)
            self._cleanup_request(req_id)
            
    def _cleanup_request(self, req_id: int):
        """Clean up request data and release the request ID."""
        self.active_requests.pop(req_id, None)
        self.historical_data.pop(req_id, None)
        if self.ib_app:
            self.ib_app.release_request_id(req_id)
            
    def get_active_requests(self) -> Dict[int, Tuple[str, str]]:
        """Get active historical data requests"""
        return self.active_requests.copy()