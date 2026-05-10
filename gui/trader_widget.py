# gui/trader_widget_refactored.py
"""Refactored trader widget with separated concerns"""
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QLineEdit, QGroupBox, QMessageBox,
                            QSpacerItem, QSizePolicy, QRadioButton, QCheckBox)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt

from core.trader_logic import TradingCalculator, TraderModel
from gui.trader_components import (PriceInputWidget, OrderTypeSelector, 
                                  PositionSizeDisplay, MarketDataDisplay)

logger = logging.getLogger(__name__)


class TickerInputSection(QGroupBox):
    """Ticker input section widget"""
    
    subscribe_clicked = pyqtSignal(str)
    unsubscribe_clicked = pyqtSignal()
    chart_clicked = pyqtSignal(str)  # ticker entered/selected at click time

    def __init__(self, parent=None):
        super().__init__("Ticker Selection", parent)
        self.init_ui()
        
    def init_ui(self):
        """Initialize the ticker input UI"""
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #ddd;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
                background-color: #f5f5f5;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # Controls
        controls_layout = QHBoxLayout()
        
        # Ticker input
        self.ticker_input = QLineEdit()
        self.ticker_input.setPlaceholderText("Enter ticker (e.g., AAPL)")
        self.ticker_input.setMaximumWidth(150)
        self.ticker_input.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border: 2px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #2196F3;
            }
        """)
        self.ticker_input.returnPressed.connect(self.on_subscribe)
        
        # Subscribe button
        self.subscribe_btn = QPushButton("Subscribe")
        self.subscribe_btn.setStyleSheet(self.get_button_style("#4CAF50", "#45a049"))
        self.subscribe_btn.clicked.connect(self.on_subscribe)
        
        # Unsubscribe button
        self.unsubscribe_btn = QPushButton("Unsubscribe")
        self.unsubscribe_btn.setEnabled(False)
        self.unsubscribe_btn.setStyleSheet(self.get_button_style("#f44336", "#da190b"))
        self.unsubscribe_btn.clicked.connect(self.on_unsubscribe)

        # Chart button — opens a 5-min Lightweight Charts window for the
        # currently entered ticker (or the active subscription).
        self.chart_btn = QPushButton("Chart")
        self.chart_btn.setStyleSheet(self.get_button_style("#2196F3", "#1976D2"))
        self.chart_btn.clicked.connect(self.on_chart)

        controls_layout.addWidget(QLabel("Ticker Symbol:"))
        controls_layout.addWidget(self.ticker_input)
        controls_layout.addWidget(self.subscribe_btn)
        controls_layout.addWidget(self.unsubscribe_btn)
        controls_layout.addWidget(self.chart_btn)
        controls_layout.addStretch()
        
        layout.addLayout(controls_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        self.status_label.setMinimumHeight(20)
        layout.addWidget(self.status_label)
        
    def get_button_style(self, color: str, hover_color: str) -> str:
        """Get button style"""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 12px;
                min-width: 100px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:disabled {{
                background-color: #cccccc;
                color: #666666;
            }}
        """
        
    def on_subscribe(self):
        """Handle subscribe"""
        ticker = self.ticker_input.text().strip().upper()
        if ticker:
            self.subscribe_clicked.emit(ticker)
            
    def on_unsubscribe(self):
        """Handle unsubscribe"""
        self.unsubscribe_clicked.emit()

    def on_chart(self):
        """Open a chart for the entered ticker."""
        ticker = self.ticker_input.text().strip().upper()
        if ticker:
            self.chart_clicked.emit(ticker)
        
    def set_subscribed(self, subscribed: bool, ticker: str = ""):
        """Update UI for subscription state"""
        self.ticker_input.setEnabled(not subscribed)
        self.subscribe_btn.setEnabled(not subscribed)
        self.unsubscribe_btn.setEnabled(subscribed)
        
        if subscribed:
            self.status_label.setText(f"Subscribing to {ticker}...")
            self.status_label.setStyleSheet("color: #2196F3; font-style: italic;")
        else:
            self.status_label.setText("")
            
    def set_status(self, message: str, is_error: bool = False):
        """Set status message"""
        self.status_label.setText(message)
        color = "#f44336" if is_error else "#4CAF50"
        self.status_label.setStyleSheet(f"color: {color}; font-style: italic;")
        
    def set_ticker(self, ticker: str):
        """Set ticker in input field"""
        self.ticker_input.setText(ticker)


class TradingControlsSection(QGroupBox):
    """Trading controls section widget"""
    
    execute_order = pyqtSignal(dict)  # order data
    
    def __init__(self, parent=None):
        super().__init__("Trading Controls", parent)
        self.model = TraderModel()
        self.calculator = TradingCalculator()
        self.init_ui()
        self.connect_signals()
        
    def init_ui(self):
        """Initialize the trading controls UI"""
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #ddd;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Order type selector (BUY/SELL)
        self.order_type_selector = OrderTypeSelector()
        layout.addWidget(self.order_type_selector)
        
        # Add spacing before radio buttons
        layout.addSpacing(15)  # Add 15 pixels of space above radio buttons
        
        # Entry order type selector (LIMIT/STOP)
        entry_type_layout = QHBoxLayout()
        entry_type_layout.setSpacing(20)
        
        entry_type_label = QLabel("Entry Order Type:")
        entry_type_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        entry_type_layout.addWidget(entry_type_label)
        
        # Radio button style
        radio_style = """
            QRadioButton {
                font-size: 12px;
                font-weight: normal;
                spacing: 5px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
            QRadioButton::indicator:checked {
                background-color: #2196F3;
                border: 2px solid #1976D2;
                border-radius: 8px;
            }
            QRadioButton::indicator:unchecked {
                background-color: white;
                border: 2px solid #ccc;
                border-radius: 8px;
            }
        """
        
        self.limit_radio = QRadioButton("LIMIT Order")
        self.limit_radio.setChecked(True)
        self.limit_radio.setStyleSheet(radio_style)
        entry_type_layout.addWidget(self.limit_radio)
        
        self.stop_radio = QRadioButton("STOP Order")
        self.stop_radio.setStyleSheet(radio_style)
        entry_type_layout.addWidget(self.stop_radio)
        
        entry_type_layout.addStretch()
        layout.addLayout(entry_type_layout)
        
        # Add spacing after radio buttons
        layout.addSpacing(15)  # Add 15 pixels of space below radio buttons
        
        # Price inputs
        price_layout = QHBoxLayout()
        price_layout.setSpacing(10)
        
        self.entry_input = PriceInputWidget("Entry Price", "0.00", "entry")
        self.stop_input = PriceInputWidget("Stop Loss", "0.00", "stop")
        self.stop_input.set_focus_color("#f44336")
        self.profit_input = PriceInputWidget("Take Profit", "0.00", "profit")
        self.profit_input.set_focus_color("#4CAF50")
        
        price_layout.addWidget(self.entry_input)
        price_layout.addWidget(self.stop_input)
        price_layout.addWidget(self.profit_input)
        layout.addLayout(price_layout)

        # Trailing stop option — when enabled, the Stop Loss field becomes
        # the initial trigger and the stop trails by the given percentage.
        trailing_layout = QHBoxLayout()
        trailing_layout.setSpacing(10)

        self.trailing_checkbox = QCheckBox("Trailing Stop")
        self.trailing_checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 12px;
                font-weight: bold;
                color: #333;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                background-color: white;
                border: 2px solid #ccc;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #f44336;
                border: 2px solid #da190b;
                border-radius: 3px;
            }
        """)
        self.trailing_checkbox.toggled.connect(self.on_trailing_toggled)

        self.trailing_percent_label = QLabel("Trail %:")
        self.trailing_percent_label.setStyleSheet("font-size: 12px; color: #666;")
        self.trailing_percent_label.setEnabled(False)

        self.trailing_percent_input = QLineEdit()
        self.trailing_percent_input.setPlaceholderText("2.0")
        self.trailing_percent_input.setMaximumWidth(80)
        self.trailing_percent_input.setEnabled(False)
        self.trailing_percent_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 2px solid #ddd;
                border-radius: 4px;
                font-size: 13px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #f44336;
            }
            QLineEdit:disabled {
                background-color: #f0f0f0;
                color: #999;
            }
        """)

        trailing_layout.addWidget(self.trailing_checkbox)
        trailing_layout.addSpacing(20)
        trailing_layout.addWidget(self.trailing_percent_label)
        trailing_layout.addWidget(self.trailing_percent_input)
        trailing_layout.addStretch()
        layout.addLayout(trailing_layout)

        # Position size display
        self.position_display = PositionSizeDisplay()
        layout.addWidget(self.position_display)
        
        # Execute button
        self.execute_btn = QPushButton("EXECUTE ORDER")
        self.execute_btn.setMinimumHeight(50)
        self.execute_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.execute_btn.clicked.connect(self.on_execute_order)
        layout.addWidget(self.execute_btn)
        
        # Bottom buttons
        bottom_layout = QHBoxLayout()
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setStyleSheet(self.get_bottom_button_style("#9E9E9E", "#757575"))
        self.clear_btn.clicked.connect(self.clear_all)
        
        self.market_price_btn = QPushButton("Use Market Price")
        self.market_price_btn.setEnabled(False)
        self.market_price_btn.setStyleSheet(self.get_bottom_button_style("#2196F3", "#1976D2"))
        self.market_price_btn.clicked.connect(self.use_market_price)
        
        bottom_layout.addWidget(self.clear_btn)
        bottom_layout.addWidget(self.market_price_btn)
        layout.addLayout(bottom_layout)
        
    def get_bottom_button_style(self, color: str, hover_color: str) -> str:
        """Get bottom button style"""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
                min-height: 35px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:disabled {{
                background-color: #cccccc;
                color: #666666;
            }}
        """
        
    def connect_signals(self):
        """Connect internal signals"""
        self.order_type_selector.order_type_changed.connect(self.on_order_type_changed)
        self.entry_input.price_changed.connect(self.on_price_changed)
        self.stop_input.price_changed.connect(self.on_price_changed)
        self.profit_input.price_changed.connect(self.on_price_changed)
        
    def on_order_type_changed(self, order_type: str):
        """Handle order type change"""
        self.recalculate()
        
    def on_price_changed(self, field: str, value: float):
        """Handle price input changes"""
        if field == "entry" or field == "stop":
            self.calculate_take_profit()
        self.calculate_position_size()
        
    def calculate_take_profit(self):
        """Calculate and update take profit"""
        try:
            entry = self.entry_input.get_value()
            stop = self.stop_input.get_value()
            
            if entry > 0 and stop > 0:
                is_buy = self.order_type_selector.is_buy_selected()
                take_profit = self.calculator.calculate_take_profit(
                    entry, stop, self.model.risk_reward_ratio, is_buy
                )
                self.profit_input.set_value(take_profit)
        except Exception as e:
            logger.error(f"Error calculating take profit: {e}")
            
    def calculate_position_size(self):
        """Calculate and update position size"""
        try:
            entry = self.entry_input.get_value()
            stop = self.stop_input.get_value()
            
            if entry > 0 and stop > 0:
                result = self.calculator.calculate_position_size(
                    entry, stop, self.model.available_funds, self.model.max_risk_percentage
                )
                
                self.model.calculated_position_size = result['position_size']
                self.position_display.update_display(result)
                
                # Calculate profit
                profit_value = self.profit_input.get_value()
                if profit_value > 0:
                    is_buy = self.order_type_selector.is_buy_selected()
                    profit = self.calculator.calculate_potential_profit(
                        entry, profit_value, result['position_size'], is_buy
                    )
                    self.position_display.update_profit(profit)
                    
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            self.position_display.clear_display()
            
    def recalculate(self):
        """Recalculate all values"""
        self.calculate_take_profit()
        self.calculate_position_size()
        
    def get_entry_order_type(self) -> str:
        """Get selected entry order type"""
        return "LMT" if self.limit_radio.isChecked() else "STP"

    def on_trailing_toggled(self, checked: bool):
        """Enable/disable the trail percent input alongside the checkbox."""
        self.trailing_percent_label.setEnabled(checked)
        self.trailing_percent_input.setEnabled(checked)
        if checked and not self.trailing_percent_input.text():
            self.trailing_percent_input.setFocus()

    def get_trailing_percent(self) -> float:
        """Return the configured trailing percent, or 0.0 if disabled.

        Raises ValueError on a checked-but-invalid input so the caller can
        surface a single warning instead of silently submitting a fixed stop.
        """
        if not self.trailing_checkbox.isChecked():
            return 0.0
        text = self.trailing_percent_input.text().strip()
        if not text:
            raise ValueError("Enter a trail percent (e.g. 2.0) or uncheck Trailing Stop.")
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"Invalid trail percent: {text!r}")
        if value <= 0 or value >= 100:
            raise ValueError(f"Trail percent must be between 0 and 100 (got {value}).")
        return value

    def on_execute_order(self):
        """Handle execute order button"""
        try:
            # Get values
            entry = self.entry_input.get_value()
            stop = self.stop_input.get_value()
            profit = self.profit_input.get_value()
            is_buy = self.order_type_selector.is_buy_selected()
            entry_order_type = self.get_entry_order_type()

            try:
                trailing_percent = self.get_trailing_percent()
            except ValueError as e:
                QMessageBox.warning(self, "Invalid Trailing Stop", str(e))
                return

            # Validate
            valid, error = self.calculator.validate_order_prices(entry, stop, profit, is_buy)
            if not valid:
                QMessageBox.warning(self, "Invalid Order", error)
                return

            if not self.model.current_ticker:
                QMessageBox.warning(self, "No Ticker", "Please subscribe to a ticker first.")
                return

            if self.model.calculated_position_size <= 0:
                QMessageBox.warning(self, "Invalid Position", "Position size is zero.")
                return

            # Create order data
            order_data = self.model.create_order_data(
                "BUY" if is_buy else "SELL",
                entry, stop, profit,
                self.model.calculated_position_size
            )
            # Add entry order type
            order_data['entry_order_type'] = entry_order_type
            order_data['trailing_percent'] = trailing_percent
            
            # Show confirmation if enabled
            if self.model.show_trade_confirmation:
                if not self.confirm_order(order_data):
                    return
                    
            # Emit order
            self.execute_order.emit(order_data)
            
            # Clear inputs
            self.clear_all()
            
        except Exception as e:
            logger.error(f"Error executing order: {e}")
            QMessageBox.critical(self, "Error", f"Failed to execute order: {str(e)}")
            
    def confirm_order(self, order_data: dict) -> bool:
        """Show order confirmation dialog"""
        order_type_text = "LIMIT" if order_data['entry_order_type'] == "LMT" else "STOP"
        trailing_percent = order_data.get('trailing_percent', 0.0)
        if trailing_percent > 0:
            stop_line = (f"Stop Loss: ${order_data['stop_loss']:.2f} "
                         f"(trailing {trailing_percent}%)\n")
        else:
            stop_line = f"Stop Loss: ${order_data['stop_loss']:.2f}\n"
        msg = f"Confirm {order_data['action']} Order:\n\n"
        msg += f"Ticker: {order_data['ticker']}\n"
        msg += f"Entry Type: {order_type_text}\n"
        msg += f"Entry Price: ${order_data['entry_price']:.2f}\n"
        msg += stop_line
        msg += f"Take Profit: ${order_data['take_profit']:.2f}\n"
        msg += f"Quantity: {order_data['quantity']} shares\n\n"
        msg += "Execute this bracket order?"
        
        reply = QMessageBox.question(self, "Confirm Order", msg,
                                   QMessageBox.StandardButton.Yes | 
                                   QMessageBox.StandardButton.No)
        
        return reply == QMessageBox.StandardButton.Yes
        
    def clear_all(self):
        """Clear all inputs"""
        self.entry_input.clear()
        self.stop_input.clear()
        self.profit_input.clear()
        self.trailing_checkbox.setChecked(False)
        self.trailing_percent_input.clear()
        self.position_display.clear_display()
        
    def use_market_price(self):
        """Use current market price for entry"""
        is_buy = self.order_type_selector.is_buy_selected()
        price = self.model.get_market_price(is_buy)
        if price:
            self.entry_input.set_value(price)
            self.recalculate()
            
    def set_market_data(self, bid: float, ask: float, last: float = None):
        """Update market data in model"""
        self.model.set_market_data(bid, ask, last)
        self.market_price_btn.setEnabled(True)
        
    def set_ticker(self, ticker: str):
        """Set current ticker"""
        self.model.set_ticker(ticker)
        
    def set_available_funds(self, funds: float):
        """Set available funds"""
        self.model.set_available_funds(funds)
        self.recalculate()
        
    def set_risk_parameters(self, risk_reward_ratio: float, max_risk_percentage: float):
        """Set risk parameters"""
        self.model.set_risk_parameters(risk_reward_ratio, max_risk_percentage)
        self.recalculate()
        
    def set_trade_confirmation(self, enabled: bool):
        """Set trade confirmation"""
        self.model.show_trade_confirmation = enabled
        
    def set_connection_status(self, connected: bool):
        """Update based on connection status"""
        self.execute_btn.setEnabled(connected)
        self.market_price_btn.setEnabled(connected and self.model.current_price is not None)
        if not connected:
            self.clear_all()


class TraderWidget(QWidget):
    """Simplified main trader widget"""
    
    # External signals
    subscribe_ticker = pyqtSignal(str, bool)  # ticker, is_position
    unsubscribe_ticker = pyqtSignal(str)
    request_atr = pyqtSignal(str)
    execute_bracket_order = pyqtSignal(str, str, float, float, float, int, str, float)  # Added entry_order_type, trailing_percent
    open_chart_requested = pyqtSignal(str)  # ticker
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_ticker = None
        self._first_data_received = False  # Track if we've received data for current ticker
        self.init_ui()
        self.connect_signals()
        
    def init_ui(self):
        """Initialize the UI"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Left column
        left_column = QWidget()
        left_column.setFixedWidth(600)
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Ticker input
        self.ticker_section = TickerInputSection()
        left_layout.addWidget(self.ticker_section)
        
        # Market data
        self.market_data_display = MarketDataDisplay()
        left_layout.addWidget(self.market_data_display)
        
        # Trading controls
        self.trading_controls = TradingControlsSection()
        left_layout.addWidget(self.trading_controls)
        
        left_layout.addStretch()
        
        # Right column - Watchlists and Positions
        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Watchlists
        watchlists_layout = QHBoxLayout()
        
        from gui.watchlist_widget import WatchlistWidget
        self.watchlist_widget = WatchlistWidget(title="Watchlist 1", filename="watchlist1.json")
        self.watchlist_widget2 = WatchlistWidget(title="Watchlist 2", filename="watchlist2.json")
        
        watchlists_layout.addWidget(self.watchlist_widget)
        watchlists_layout.addWidget(self.watchlist_widget2)
        right_layout.addLayout(watchlists_layout)
        
        # Positions
        from gui.positions_widget import PositionsWidget
        self.positions_widget = PositionsWidget()
        right_layout.addWidget(self.positions_widget)
        
        right_layout.addStretch()
        
        # Add to main layout
        main_layout.addWidget(left_column)
        main_layout.addWidget(right_column, 1)
        
    def connect_signals(self):
        """Connect internal signals to external signals"""
        # Ticker section
        self.ticker_section.subscribe_clicked.connect(self.on_subscribe)
        self.ticker_section.unsubscribe_clicked.connect(self.on_unsubscribe)
        self.ticker_section.chart_clicked.connect(self.open_chart_requested)
        
        # Trading controls
        self.trading_controls.execute_order.connect(self.on_execute_order)
        
        # Watchlists
        self.watchlist_widget.ticker_selected.connect(self.on_watchlist_ticker_selected)
        self.watchlist_widget2.ticker_selected.connect(self.on_watchlist_ticker_selected)
        
        # Position widget signals
        self.positions_widget.subscribe_position_ticker.connect(self.on_position_ticker_subscribe)
        
    def on_subscribe(self, ticker: str):
        """Handle subscribe - for trader ticker selection"""
        self.ticker_section.set_subscribed(True, ticker)
        self.trading_controls.set_ticker(ticker)
        self._current_ticker = ticker  # Store the current ticker
        self._first_data_received = False  # Reset data received flag
        # False indicates this is NOT a position subscription
        self.subscribe_ticker.emit(ticker, False)
        self.request_atr.emit(ticker)
        
    def on_position_ticker_subscribe(self, ticker: str):
        """Handle position ticker subscription"""
        # True indicates this IS a position subscription
        self.subscribe_ticker.emit(ticker, True)
        
    def on_unsubscribe(self):
        """Handle unsubscribe"""
        if hasattr(self, '_current_ticker'):
            self.unsubscribe_ticker.emit(self._current_ticker)
        self.ticker_section.set_subscribed(False)
        self.market_data_display.clear_data()
        self.trading_controls.set_ticker("")
        self._current_ticker = None
        
    def on_watchlist_ticker_selected(self, ticker: str):
        """Handle watchlist ticker selection"""
        self.ticker_section.set_ticker(ticker)
        if hasattr(self, '_current_ticker') and self._current_ticker:
            self.unsubscribe_ticker.emit(self._current_ticker)
        self.on_subscribe(ticker)
        
    def on_execute_order(self, order_data: dict):
        """Handle execute order"""
        self.execute_bracket_order.emit(
            order_data['ticker'],
            order_data['action'],
            order_data['entry_price'],
            order_data['stop_loss'],
            order_data['take_profit'],
            order_data['quantity'],
            order_data.get('entry_order_type', 'LMT'),  # Default to LIMIT if not specified
            order_data.get('trailing_percent', 0.0),    # 0 means fixed stop
        )
        
    def update_market_data(self, ticker: str, bid: float, ask: float, 
                          last: float = None, volume: int = None):
        """Update market data display for any ticker"""
        # Update trader display only if it's the current trader ticker
        if hasattr(self, '_current_ticker') and ticker == self._current_ticker:
            # Update displays for trader ticker
            spread = round(ask - bid, 4) if bid and ask else "--"
            data = {
                "bid": f"${bid:.2f}" if bid else "--",
                "ask": f"${ask:.2f}" if ask else "--",
                "spread": f"${spread}" if isinstance(spread, (int, float)) else spread,
                "last": f"${last:.2f}" if last else "--",
                "volume": f"{volume:,}" if volume else "--"
            }
            
            self.market_data_display.update_data(data)
            self.trading_controls.set_market_data(bid, ask, last)
            
            # Update status to show connected after first data
            if not self._first_data_received:
                self.ticker_section.set_status(f"Connected - Live data for {ticker}")
                self._first_data_received = True
            else:
                self.ticker_section.set_status(f"Live data for {ticker}")
        
        # Always update positions widget for any ticker (position updates)
        # The position manager will handle the price update
        
    def update_atr(self, ticker: str, atr_value: float, period: int):
        """Update ATR display"""
        if ticker == getattr(self, '_current_ticker', None):
            self.market_data_display.update_data({"atr": f"${atr_value:.2f}"})
            
    def show_error(self, ticker: str, error_msg: str):
        """Show error message for a specific ticker.

        Order matters: ``on_unsubscribe`` calls ``set_subscribed(False)`` which
        wipes the status label, so the error message must be set *after* the
        unsubscribe — otherwise it flickers in and disappears.
        """
        if hasattr(self, '_current_ticker') and ticker == self._current_ticker:
            self.on_unsubscribe()
            self.ticker_section.set_status(f"Error: {error_msg}", is_error=True)
        
    def set_connection_status(self, connected: bool):
        """Update based on connection status"""
        self.ticker_section.set_subscribed(False)
        self.trading_controls.set_connection_status(connected)
        self.positions_widget.set_connection_status(connected)
        
        if not connected:
            self.ticker_section.set_status("Not connected to IB", is_error=True)
            self.market_data_display.clear_data()
            self._current_ticker = None
            
    def set_available_funds(self, funds: float):
        """Set available funds"""
        self.trading_controls.set_available_funds(funds)
        
    def set_risk_parameters(self, risk_reward_ratio: float, max_risk_percentage: float):
        """Set risk parameters"""
        self.trading_controls.set_risk_parameters(risk_reward_ratio, max_risk_percentage)
        
    def set_trade_confirmation(self, enabled: bool):
        """Set trade confirmation"""
        self.trading_controls.set_trade_confirmation(enabled)
        self.positions_widget.set_trade_confirmation(enabled)