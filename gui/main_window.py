# gui/main_window.py
import threading
import logging
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QGroupBox, QSplitter,
                            QTabWidget, QTextEdit, QMessageBox)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont
from core.ib_app import IBApp, IBSignals
from core.contract_resolver import ContractResolver
from core.market_data_manager import MarketDataManager
from core.historical_data_manager import HistoricalDataManager
from core.order_manager import OrderManager
from core.position_manager import PositionManager
from gui.log_widget import LogWidget
from gui.connection_widget import ConnectionWidget
from gui.trader_widget import TraderWidget
from config import APP_CONFIG

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Main window for the IB connection application.
    Handles UI setup and interaction with the IB API.
    """
    
    def __init__(self, qt_log_handler=None):
        super().__init__()
        self.ib_app = None
        self.qt_log_handler = qt_log_handler
        self.contract_resolver = ContractResolver()
        self.market_data_manager = MarketDataManager(contract_resolver=self.contract_resolver)
        self.historical_data_manager = HistoricalDataManager(contract_resolver=self.contract_resolver)
        self.order_manager = OrderManager(contract_resolver=self.contract_resolver)
        self.position_manager = PositionManager()
        # Distinguishes user-initiated disconnects from unplanned drops so we
        # can warn the user only in the latter case.
        self._user_initiated_disconnect = False
        # Open chart windows, keyed by id(window). Held to prevent garbage
        # collection while the window is alive — the closeEvent handler emits
        # back to us so we can drop the reference.
        self._chart_windows: dict = {}
        self.init_ui()
        logger.info("MainWindow initialized")
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Interactive Brokers Connection")
        self.setGeometry(100, 100, 1400, 1000)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # Create vertical splitter for top and bottom sections
        vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Top section: Connection and Log panels
        top_widget = QWidget()
        top_widget.setFixedHeight(220)
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create horizontal splitter for connection and logs
        horizontal_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        
        # Connection widget (left side)
        self.connection_widget = ConnectionWidget()
        self.connection_widget.connect_requested.connect(self.connect_to_ib)
        self.connection_widget.disconnect_requested.connect(self.disconnect_from_ib)
        
        # Log widget (right side)
        log_group = QGroupBox("Application Logs")
        log_group.setStyleSheet("""
            QGroupBox {
                background-color: #FCFCFC;
                border: 2px solid #ddd;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 8px;
                font-weight: bold;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                color: #333;
                font-weight: bold;
                font-size: 13px;
            }
        """)
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(10, 15, 10, 10)
        self.log_widget = LogWidget()
        log_layout.addWidget(self.log_widget)
        log_group.setLayout(log_layout)
        
        # Connect log handler if provided
        if self.qt_log_handler:
            self.qt_log_handler.log_message.connect(self.log_widget.add_log_message)
        
        # Add widgets to horizontal splitter
        horizontal_splitter.addWidget(self.connection_widget)
        horizontal_splitter.addWidget(log_group)
        horizontal_splitter.setSizes([400, 800])  # Set initial sizes
        
        top_layout.addWidget(horizontal_splitter)
        
        # Bottom section: Tab widget
        self.tab_widget = self.create_tab_widget()
        
        # Add sections to vertical splitter
        vertical_splitter.addWidget(top_widget)
        vertical_splitter.addWidget(self.tab_widget)
        vertical_splitter.setSizes([300, 500])  # Set initial sizes
        
        main_layout.addWidget(vertical_splitter)
        
        # Setup timer for periodic updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.request_account_updates)
        
        # Load and apply risk parameters on startup
        self.load_risk_parameters()

    def create_tab_widget(self):
        """Create the tab widget with 3 tabs"""
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #ddd;
                background-color: #FCFCFC;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #FCFCFC;
                border: 2px solid #ddd;
                border-bottom: none;
            }
            QTabBar::tab:hover {
                background-color: #f0f0f0;
            }
        """)
        
        # Tab 1: Trader (Manual Trade)
        self.trader_widget = TraderWidget()
        # Updated signal connection to handle the is_position parameter
        self.trader_widget.subscribe_ticker.connect(
            lambda ticker, is_position: self.market_data_manager.subscribe_market_data(ticker, is_position)
        )
        self.trader_widget.unsubscribe_ticker.connect(self.market_data_manager.unsubscribe_market_data)
        self.trader_widget.request_atr.connect(self.historical_data_manager.request_atr)
        self.trader_widget.execute_bracket_order.connect(self.execute_bracket_order)
        self.trader_widget.open_chart_requested.connect(self.open_chart_window)
        
        # Connect market data manager signals to trader widget
        self.market_data_manager.market_data_update.connect(self.trader_widget.update_market_data)
        self.market_data_manager.subscription_error.connect(self.trader_widget.show_error)
        
        # Also connect market data updates to position manager for P&L updates
        self.market_data_manager.market_data_update.connect(self.update_position_prices)
        
        # Connect historical data manager signals to trader widget
        self.historical_data_manager.atr_calculated.connect(self.trader_widget.update_atr)
        self.historical_data_manager.historical_data_error.connect(self.trader_widget.show_error)
        
        # Connect order manager signals
        self.order_manager.order_error.connect(self.show_order_error)
        
        # Connect position widget signals
        self.trader_widget.positions_widget.refresh_positions.connect(self.position_manager.request_positions)
        self.trader_widget.positions_widget.close_position.connect(self.position_manager.close_position)
        
        # Connect position manager signals
        self.position_manager.position_update.connect(self.trader_widget.positions_widget.update_position)
        self.position_manager.position_removed.connect(self.trader_widget.positions_widget.remove_position)
        self.position_manager.all_positions_updated.connect(self.on_all_positions_updated)
        self.position_manager.close_position_error.connect(self.show_order_error)
        
        tab_widget.addTab(self.trader_widget, "📈 Manual Trade")
        
        # Tab 2: Execution Log Book
        from gui.execution_logbook_widget import ExecutionLogBookWidget
        self.logbook_widget = ExecutionLogBookWidget()
        
        # Set IB app when available
        if hasattr(self, 'ib_app') and self.ib_app:
            self.logbook_widget.set_ib_app(self.ib_app)
        
        tab_widget.addTab(self.logbook_widget, "📖 Log Book")
        
        # Tab 3: Risk Management
        from gui.risk_management_widget import RiskManagementWidget
        self.risk_widget = RiskManagementWidget()
        self.risk_widget.risk_params_widget.parameters_changed.connect(self.on_risk_parameters_changed)
        tab_widget.addTab(self.risk_widget, "🛡️ Risk Management")
        
        return tab_widget
        
    def connect_to_ib(self, host, port, client_id, market_data_type=None):
        """Connect to Interactive Brokers"""
        try:
            if market_data_type is None:
                market_data_type = APP_CONFIG.default_market_data_type
            logger.info(
                f"Attempting to connect to IB (market data type={market_data_type})"
            )
            
            # Create signals for thread-safe communication
            self.signals = IBSignals()
            self.signals.connection_status.connect(self.update_connection_status)
            self.signals.account_value.connect(self.update_account_value)
            self.signals.error_message.connect(self.handle_error)
            
            # Connect contract resolver signals (used to qualify SMART
            # contracts with primaryExchange — required for delayed data).
            self.signals.contract_details.connect(self.contract_resolver.handle_contract_details)
            self.signals.contract_details_end.connect(self.contract_resolver.handle_contract_details_end)

            # Connect market data signals
            self.signals.tick_price.connect(self.market_data_manager.handle_tick_price)
            self.signals.tick_size.connect(self.market_data_manager.handle_tick_size)
            
            # Connect historical data signals
            self.signals.historical_data.connect(self.historical_data_manager.handle_historical_data)
            self.signals.historical_data_end.connect(self.historical_data_manager.handle_historical_data_end)
            self.signals.historical_data_update.connect(self.historical_data_manager.handle_historical_data_update)
            
            # Connect order signals
            self.signals.next_valid_id.connect(self.order_manager.set_next_order_id)
            self.signals.order_status.connect(self.order_manager.handle_order_status)
            
            # Connect position signals
            self.signals.position.connect(self.position_manager.handle_position)
            self.signals.position_end.connect(self.position_manager.handle_position_end)
            self.signals.commission_report.connect(self.position_manager.handle_commission_report)
            self.signals.open_order.connect(self.position_manager.handle_open_order)
            
            # Also update position manager with order IDs and status
            self.signals.next_valid_id.connect(self.position_manager.set_next_order_id)
            self.signals.order_status.connect(self.position_manager.handle_order_status)
            
            # Create IB app instance
            self.ib_app = IBApp(self.signals)
            # Apply selected market data type before connect() — IBApp.connectAck
            # reads this and calls reqMarketDataType once the socket is up.
            self.ib_app.market_data_type = market_data_type

            # Set IB app in managers
            self.contract_resolver.set_ib_app(self.ib_app)
            self.market_data_manager.set_ib_app(self.ib_app)
            self.historical_data_manager.set_ib_app(self.ib_app)
            self.order_manager.set_ib_app(self.ib_app)
            self.position_manager.set_ib_app(self.ib_app)
            
            # Set IB app in logbook widget
            if hasattr(self, 'logbook_widget'):
                self.logbook_widget.set_ib_app(self.ib_app)
            
            logger.info(f"Connecting to {host}:{port} with client ID {client_id}")
            
            # Connect to IB
            self.ib_app.connect(host, port, client_id)
            
            # Start the socket in a separate thread
            api_thread = threading.Thread(target=self.run_loop, daemon=True)
            api_thread.start()
            
            # Give connection time to establish
            QTimer.singleShot(1000, self.request_account_updates)
            
            # Start periodic updates
            self.update_timer.start(APP_CONFIG.update_interval)
            
            # Request initial positions after a short delay
            QTimer.singleShot(2000, self.position_manager.request_positions)
            
            # Request account summary to get available funds
            QTimer.singleShot(1500, lambda: self.ib_app.reqAccountSummary(1, "All", "AvailableFunds"))
            
        except Exception as e:
            error_msg = f"Connection error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.connection_widget.show_error(error_msg)
            
    def run_loop(self):
        """Run the IB API event loop"""
        self.ib_app.run()
        
    def disconnect_from_ib(self):
        """Disconnect from Interactive Brokers.

        If there are open positions, prompt the user first — disconnecting
        only stops local tracking; the positions continue to exist at IB and
        any active stop-loss / take-profit orders remain in force.
        """
        open_positions = self.position_manager.get_positions_list()
        if open_positions:
            symbols = ", ".join(sorted({p.symbol for p in open_positions}))
            reply = QMessageBox.warning(
                self,
                "Disconnect with open positions?",
                f"You have {len(open_positions)} open position(s) ({symbols}).\n\n"
                "Disconnecting only stops local tracking — positions and any "
                "stop-loss/take-profit orders remain active at IB.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                logger.info("Disconnect cancelled by user (open positions)")
                return

        logger.info("Disconnecting from IB")
        self._user_initiated_disconnect = True

        # Clear all market data subscriptions
        self.market_data_manager.clear_all_subscriptions()
        self.contract_resolver.cancel_pending()
        self.position_manager.reset_order_ids()

        if self.ib_app:
            self.update_timer.stop()
            self.ib_app.disconnect()
            self.ib_app = None
            
    def request_account_updates(self):
        """Request account summary updates"""
        if self.ib_app and self.ib_app.isConnected():
            logger.debug("Requesting account summary update")
            # Request account summary for AvailableFunds
            self.ib_app.reqAccountSummary(1, "All", "AvailableFunds")
            
    def update_connection_status(self, connected):
        """Update connection status in UI and clean up on unplanned drops.

        ``self.ib_app`` is set to ``None`` by ``disconnect_from_ib`` before it
        triggers the underlying IB ``disconnect()``, so when this slot fires
        for a user-initiated disconnect, ``self.ib_app`` is already ``None``.
        Anything else with ``connected=False`` is an unplanned drop (network,
        gateway shutdown, etc.) — clean up state and warn the user.
        """
        self.connection_widget.update_connection_status(connected)
        self.trader_widget.set_connection_status(connected)

        if connected:
            self._user_initiated_disconnect = False
            return

        if self._user_initiated_disconnect:
            self._user_initiated_disconnect = False
            return

        if self.ib_app is not None:
            logger.warning("Unplanned disconnect from IB; clearing local state")
            self.market_data_manager.clear_all_subscriptions()
            self.contract_resolver.cancel_pending()
            self.position_manager.reset_order_ids()
            self.update_timer.stop()
            self.ib_app = None
            self.connection_widget.show_error(
                "Connection to IB was lost. Click Connect to reconnect."
            )
            
    def update_account_value(self, account, tag, value, currency):
        """Update account value in UI"""
        self.connection_widget.update_account_value(account, tag, value, currency)

        # Pass available funds to trader widget for position sizing
        if tag == "AvailableFunds":
            try:
                funds_value = float(value)
                self.trader_widget.set_available_funds(funds_value)
                # Keep open chart windows in sync so their position-sizing
                # default uses the latest funds, not the value at open.
                for window in self._chart_windows.values():
                    window.update_risk_context(available_funds=funds_value)
            except ValueError:
                logger.error(f"Error parsing available funds: {value}")
                
    def handle_error(self, reqId, errorCode, errorString):
        """Route an IB error to the right manager based on request category.

        Categories are assigned by ``IBApp.allocate_request_id`` when the
        original request was made; we look them up here rather than relying
        on hardcoded numeric ranges, which used to cap market data at 999
        concurrent subscriptions before colliding with historical data.
        """
        # Filter out common non-critical errors and warnings.
        # 10167/10168 = "Displaying delayed market data" — informational
        #   confirmation that IB accepted the subscription at delayed tier.
        # 300 = "Can't find EId" — stale cancel, see IBApp.error.
        if errorCode in [2104, 2106, 2158, 2174, 2176, 10167, 10168, 300]:
            logger.debug(f"IB Info/Warning {errorCode}: {errorString}")
            return

        # 10089/10090/10091 = "subscription required for this market data".
        # When IB has no fallback (no free delayed entitlement for this feed)
        # no ticks will follow, so we must surface this to the user instead
        # of leaving the trader stuck on "Subscribing to ...". Route to the
        # market data manager so it emits subscription_error → trader widget.
        # IBApp.error already logs these at INFO level upstream.

        category = self.ib_app.request_category(reqId) if self.ib_app else None

        if category == "market":
            self.market_data_manager.handle_error(reqId, errorCode, errorString)
        elif category == "historical":
            self.historical_data_manager.handle_error(reqId, errorCode, errorString)
        elif category == "contract":
            self.contract_resolver.handle_error(reqId, errorCode, errorString)
        elif category == "execution":
            # IBExecutionFetcher consumes errors via its own signal handler.
            logger.debug(
                f"IB Error for execution request {reqId}: {errorCode} {errorString}"
            )
        else:
            # Unknown reqId or single-shot request (e.g. account summary).
            self.connection_widget.show_error(f"Error {errorCode}: {errorString}")
            
    def execute_bracket_order(self, ticker, action, entry_price, stop_loss, take_profit, quantity, entry_order_type="LMT", trailing_percent=0.0):
        """Execute a bracket order"""
        order_type_text = "LIMIT" if entry_order_type == "LMT" else "STOP"
        if trailing_percent > 0:
            stop_text = f"trailing {trailing_percent}% (initial trigger {stop_loss})"
        else:
            stop_text = f"stop: {stop_loss}"
        logger.info(f"Executing bracket order: {ticker} {action} {quantity} shares @ {entry_price} ({order_type_text}), {stop_text}, target: {take_profit}")
        self.order_manager.create_bracket_order(ticker, action, entry_price, stop_loss, take_profit, quantity, entry_order_type, trailing_percent)
        
    def show_order_error(self, error_msg):
        """Show order error in a message box"""
        QMessageBox.critical(self, "Order Error", error_msg)
        
    def update_position_prices(self, ticker, bid, ask, last=None, volume=None):
        """Update position prices for P&L calculation"""
        # Use last price if available, otherwise mid-point
        price = last if last else (bid + ask) / 2
        self.position_manager.update_market_price(ticker, price)
        
    def on_risk_parameters_changed(self, params):
        """Handle risk parameters change"""
        logger.info(f"Risk parameters updated: {params}")
        # Pass parameters to trader widget
        if hasattr(self, 'trader_widget'):
            self.trader_widget.set_trade_confirmation(params.get('confirm_trades', True))
            rr = params.get('risk_reward_ratio', 2.0)
            max_risk = params.get('max_risk_percentage', 2.0)
            self.trader_widget.set_risk_parameters(rr, max_risk)
            for window in self._chart_windows.values():
                window.update_risk_context(
                    max_risk_percentage=max_risk, risk_reward_ratio=rr
                )
            
    def load_risk_parameters(self):
        """Load risk parameters on startup"""
        try:
            if hasattr(self, 'risk_widget'):
                params = self.risk_widget.get_risk_parameters()
                self.trader_widget.set_trade_confirmation(params.get('confirm_trades', True))
                self.trader_widget.set_risk_parameters(
                    params.get('risk_reward_ratio', 2.0),
                    params.get('max_risk_percentage', 2.0)
                )
                logger.info(f"Risk parameters loaded on startup: {params}")
        except Exception as e:
            logger.error(f"Error loading risk parameters on startup: {e}")
            
    def on_all_positions_updated(self):
        """Handle when all positions have been updated"""
        # Update the positions widget total P&L
        self.trader_widget.positions_widget.update_total_pnl()
        
        # Refresh market data subscriptions for all positions
        position_tickers = set(self.position_manager.positions.keys())
        self.market_data_manager.refresh_position_subscriptions(position_tickers)
        
    def open_chart_window(self, ticker: str):
        """Open a 5-minute Lightweight Charts window for the given ticker.

        Refuses if not connected to IB — the historical data request would
        fail anyway, and we want a clear message rather than a silent
        empty chart.
        """
        if not self.ib_app or not self.ib_app.isConnected():
            QMessageBox.warning(
                self,
                "Not Connected",
                "Connect to IB before opening a chart.",
            )
            return

        # Snapshot the trader's risk context so the chart's position-sizing
        # default matches the trader widget. Live updates are pushed via
        # update_risk_context as funds / risk params change later.
        model = self.trader_widget.trading_controls.model
        from gui.chart_widget import ChartWindow
        window = ChartWindow(
            ticker, self.historical_data_manager, parent=None,
            available_funds=model.available_funds,
            max_risk_percentage=model.max_risk_percentage,
            risk_reward_ratio=model.risk_reward_ratio,
        )
        window.closed.connect(self._on_chart_window_closed)
        window.submit_bracket_order.connect(self._on_chart_submit_bracket_order)
        self._chart_windows[id(window)] = window
        window.show()
        window.raise_()
        window.activateWindow()

    def _on_chart_window_closed(self, window):
        """Drop the reference so the window can be garbage-collected."""
        self._chart_windows.pop(id(window), None)

    def _on_chart_submit_bracket_order(self, order_data: dict):
        """Confirm and submit a bracket order originated from a chart window.

        The chart already validates ordering (long: stop<entry<target,
        short: stop>entry>target) and a positive quantity, so we treat the
        payload as well-formed and just verify the fields parse cleanly
        before showing the user a confirmation dialog.
        """
        try:
            ticker = str(order_data['ticker']).upper()
            action = str(order_data['action']).upper()
            entry = float(order_data['entry'])
            stop = float(order_data['stop'])
            target = float(order_data['target'])
            quantity = int(order_data['quantity'])
            entry_order_type = str(order_data.get('entry_order_type', 'LMT'))
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Chart order payload invalid: {e} -- {order_data}")
            QMessageBox.warning(
                self, "Invalid Order", "Order data from the chart was invalid."
            )
            return

        if action not in ("BUY", "SELL") or quantity <= 0 or entry <= 0:
            QMessageBox.warning(
                self, "Invalid Order", "Action / quantity / entry are out of range."
            )
            return

        msg = (
            f"Submit {action} bracket order from chart?\n\n"
            f"Ticker: {ticker}\n"
            f"Entry ({entry_order_type}): ${entry:.2f}\n"
            f"Stop Loss: ${stop:.2f}\n"
            f"Take Profit: ${target:.2f}\n"
            f"Quantity: {quantity} shares"
        )
        reply = QMessageBox.question(
            self, "Confirm Bracket Order", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.execute_bracket_order(
            ticker, action, entry, stop, target, quantity,
            entry_order_type, 0.0,
        )

    def closeEvent(self, event):
        """Handle window close event"""
        # Close any open chart windows so their IB requests are cancelled
        # before we tear down the connection.
        for window in list(self._chart_windows.values()):
            window.close()
        self.disconnect_from_ib()
        if hasattr(self.connection_widget, 'cleanup'):
            self.connection_widget.cleanup()
        event.accept()