# core/trader_logic.py
"""Trading logic separated from GUI components"""
import logging
from typing import Optional, Tuple, Dict
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class TradingCalculator:
    """Handles all trading calculations"""
    
    @staticmethod
    def calculate_take_profit(entry_price: float, stop_loss: float, 
                            risk_reward_ratio: float, is_buy: bool) -> float:
        """Calculate take profit based on risk/reward ratio"""
        risk_per_share = abs(entry_price - stop_loss)
        reward = risk_per_share * risk_reward_ratio
        
        if is_buy:
            return entry_price + reward
        else:
            return entry_price - reward
    
    @staticmethod
    def calculate_position_size(entry_price: float, stop_loss: float,
                              available_funds: float, max_risk_percentage: float) -> Dict:
        """Calculate position size based on risk management parameters"""
        if available_funds <= 0 or entry_price <= 0:
            return {
                'position_size': 0,
                'position_value': 0,
                'risk_amount': 0,
                'limited_by_funds': False,
                'error': 'Invalid funds or price'
            }
            
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0:
            return {
                'position_size': 0,
                'position_value': 0,
                'risk_amount': 0,
                'limited_by_funds': False,
                'error': 'Risk per share is zero'
            }
            
        # Calculate maximum risk amount
        max_risk_amount = available_funds * (max_risk_percentage / 100.0)
        
        # Calculate position size based on risk
        position_size_by_risk = int(max_risk_amount / risk_per_share)
        
        # Calculate maximum position size based on available funds
        max_position_size_by_funds = int(available_funds / entry_price)
        
        # Use the smaller of the two
        position_size = min(position_size_by_risk, max_position_size_by_funds)
        limited_by_funds = position_size < position_size_by_risk
        
        # Calculate values
        position_value = position_size * entry_price
        actual_risk_amount = position_size * risk_per_share
        
        return {
            'position_size': position_size,
            'position_value': position_value,
            'risk_amount': actual_risk_amount,
            'risk_per_share': risk_per_share,
            'max_risk_amount': max_risk_amount,
            'position_size_by_risk': position_size_by_risk,
            'max_position_size_by_funds': max_position_size_by_funds,
            'limited_by_funds': limited_by_funds,
            'error': None
        }
    
    @staticmethod
    def calculate_potential_profit(entry_price: float, take_profit: float,
                                 position_size: int, is_buy: bool) -> float:
        """Calculate potential profit for a position"""
        if position_size <= 0 or take_profit <= 0:
            return 0.0
            
        profit_per_share = abs(take_profit - entry_price)
        return position_size * profit_per_share
    
    @staticmethod
    def validate_order_prices(entry_price: float, stop_loss: float, 
                            take_profit: float, is_buy: bool) -> Tuple[bool, str]:
        """Validate order prices based on order direction"""
        if is_buy:
            if stop_loss >= entry_price:
                return False, "For buy orders, stop loss must be below entry price."
            if take_profit <= entry_price:
                return False, "For buy orders, take profit must be above entry price."
        else:  # SELL
            if stop_loss <= entry_price:
                return False, "For sell orders, stop loss must be above entry price."
            if take_profit >= entry_price:
                return False, "For sell orders, take profit must be below entry price."
                
        return True, ""


class TraderModel(QObject):
    """Model for trader data and state management"""
    
    # Signals for state changes
    market_data_updated = pyqtSignal(dict)
    position_calculated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.current_ticker = None
        self.is_subscribed = False
        self.current_price = None
        self.last_bid = None
        self.last_ask = None
        self.available_funds = 0.0
        self.risk_reward_ratio = 2.0
        self.max_risk_percentage = 2.0
        self.show_trade_confirmation = True
        self.calculated_position_size = 0
        
    def set_ticker(self, ticker: str):
        """Set the current ticker"""
        self.current_ticker = ticker.upper() if ticker else None
        
    def set_market_data(self, bid: float, ask: float, last: Optional[float] = None):
        """Update market data"""
        self.last_bid = bid
        self.last_ask = ask
        
        if last:
            self.current_price = last
        elif bid and ask:
            self.current_price = (bid + ask) / 2
            
    def set_risk_parameters(self, risk_reward_ratio: float, max_risk_percentage: float):
        """Update risk management parameters"""
        self.risk_reward_ratio = risk_reward_ratio
        self.max_risk_percentage = max_risk_percentage
        
    def set_available_funds(self, funds: float):
        """Update available funds"""
        self.available_funds = funds
        
    def get_market_price(self, is_buy: bool) -> Optional[float]:
        """Get appropriate market price based on order type"""
        if is_buy and self.last_ask:
            return self.last_ask
        elif not is_buy and self.last_bid:
            return self.last_bid
        else:
            return self.current_price
            
    def create_order_data(self, action: str, entry_price: float, 
                         stop_loss: float, take_profit: float, quantity: int) -> dict:
        """Create order data dictionary"""
        return {
            'ticker': self.current_ticker,
            'action': action,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'quantity': quantity
        }