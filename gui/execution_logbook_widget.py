# gui/execution_logbook_widget.py
"""Main execution logbook widget"""
import logging
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QTabWidget, QProgressDialog, QMessageBox)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer

from core.execution_logbook_logic import ExecutionDataModel, IBExecutionFetcher
from gui.execution_logbook_components import (DailyExecutionsView, SymbolAggregationView, 
                                            CalendarView)

logger = logging.getLogger(__name__)


class ExecutionLogBookWidget(QWidget):
    """Main execution logbook widget orchestrating views and data"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ib_app = None
        self.model = ExecutionDataModel()
        self.auto_refresh_enabled = True
        self.auto_refresh_interval = 5 * 60 * 1000  # 5 minutes in milliseconds
        self.init_ui()
        self.connect_signals()
        self.setup_auto_refresh()
        
        # Load data on startup
        QTimer.singleShot(100, self.load_initial_data)
        
    def init_ui(self):
        """Initialize the main logbook UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Header
        header_layout = QHBoxLayout()
        
        title_label = QLabel("Execution Log Book")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #333;
            }
        """)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Last update label
        self.last_update_label = QLabel("Loading...")
        self.last_update_label.setStyleSheet("color: #666; font-style: italic;")
        header_layout.addWidget(self.last_update_label)
        
        # Refresh button
        self.refresh_btn = QPushButton("Refresh Today's Data")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.refresh_btn.clicked.connect(self.refresh_data)
        header_layout.addWidget(self.refresh_btn)
        
        # Auto-refresh toggle button
        self.auto_refresh_btn = QPushButton("Auto-Refresh: ON")
        self.auto_refresh_btn.setCheckable(True)
        self.auto_refresh_btn.setChecked(True)
        self.auto_refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 130px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:!checked {
                background-color: #9E9E9E;
            }
            QPushButton:!checked:hover {
                background-color: #757575;
            }
        """)
        self.auto_refresh_btn.clicked.connect(self.toggle_auto_refresh)
        header_layout.addWidget(self.auto_refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                background-color: white;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #2196F3;
                color: white;
            }
        """)
        
        # Create views
        self.daily_view = DailyExecutionsView()
        self.symbol_view = SymbolAggregationView()
        self.calendar_view = CalendarView()
        
        # Add tabs
        self.tab_widget.addTab(self.daily_view, "📅 Daily Executions")
        self.tab_widget.addTab(self.symbol_view, "📊 By Symbol")
        self.tab_widget.addTab(self.calendar_view, "📆 Calendar View")
        
        layout.addWidget(self.tab_widget)
        
    def connect_signals(self):
        """Connect internal signals"""
        # Model signals
        self.model.data_updated.connect(self.on_data_updated)
        self.model.error_occurred.connect(self.on_error)
        
        # View signals
        self.daily_view.comment_updated.connect(self.model.update_comment)
        
        # Set callback for symbol view
        self.symbol_view.set_data_callback(self.model.get_filtered_symbol_data)
        
    def set_ib_app(self, ib_app):
        """Set the IB app instance"""
        self.ib_app = ib_app
        
    def load_initial_data(self):
        """Load data from database on startup"""
        self.model.load_from_database()
        
    @pyqtSlot()
    def on_data_updated(self):
        """Handle data update from model"""
        # Update views
        self.daily_view.set_data(self.model.daily_data, self.model.comments)
        self.symbol_view.update_display()
        self.calendar_view.set_data(self.model.daily_data)
        
        # Update last update label
        latest_time = self.model.get_latest_execution_time()
        if latest_time:
            self.last_update_label.setText(f"Last update: {latest_time}")
        elif self.model.executions:
            self.last_update_label.setText("Data loaded")
        else:
            self.last_update_label.setText("No data. Click Refresh to load.")
            
        # Update statistics
        stats = self.model.get_statistics()
        logger.info(f"Loaded {len(self.model.executions)} executions, "
                   f"{stats['total_days']} trading days, "
                   f"Total P&L: ${stats['total_pnl']:,.2f}")
        
    @pyqtSlot(str)
    def on_error(self, error_msg: str):
        """Handle error from model"""
        logger.error(f"Model error: {error_msg}")
        self.last_update_label.setText("Error loading data")
        
    def setup_auto_refresh(self):
        """Setup automatic refresh timer"""
        self.auto_refresh_timer = QTimer()
        self.auto_refresh_timer.timeout.connect(self.auto_refresh_data)
        if self.auto_refresh_enabled:
            self.auto_refresh_timer.start(self.auto_refresh_interval)
            
    def toggle_auto_refresh(self):
        """Toggle automatic refresh on/off"""
        self.auto_refresh_enabled = self.auto_refresh_btn.isChecked()
        
        if self.auto_refresh_enabled:
            self.auto_refresh_btn.setText("Auto-Refresh: ON")
            self.auto_refresh_timer.start(self.auto_refresh_interval)
            logger.info("Auto-refresh enabled (5 minute interval)")
        else:
            self.auto_refresh_btn.setText("Auto-Refresh: OFF")
            self.auto_refresh_timer.stop()
            logger.info("Auto-refresh disabled")
            
    def auto_refresh_data(self):
        """Automatically refresh data if connected"""
        if self.ib_app and self.ib_app.isConnected():
            logger.info("Auto-refreshing execution data...")
            self.refresh_data(show_dialog=False)
        else:
            logger.debug("Skipping auto-refresh - not connected to IB")
            
    def refresh_data(self, show_dialog=True):
        """Fetch today's execution data from IB"""
        if not self.ib_app or not self.ib_app.isConnected():
            if show_dialog:
                QMessageBox.warning(self, "Not Connected", 
                                  "Please connect to Interactive Brokers first.")
            return
            
        # Create progress dialog only if requested
        if show_dialog:
            self.progress = QProgressDialog(
                "Fetching today's executions from IB...", 
                "Cancel", 0, 0, self
            )
            self.progress.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress.setWindowTitle("Loading Data")
            self.progress.show()
        else:
            # Update status in last update label for background refresh
            self.last_update_label.setText("Refreshing...")
        
        # Clear today's data
        self.model.clear_today_data()
        
        # Start fetcher thread
        today = datetime.now().date()
        self.fetcher = IBExecutionFetcher(self.ib_app, start_date=today)
        
        # Store whether to show dialog in fetcher for later use
        self.fetcher.show_dialog = show_dialog
        
        self.fetcher.dataReady.connect(self.on_ib_data_received)
        self.fetcher.statusUpdate.connect(self.on_fetch_status_update)
        self.fetcher.errorOccurred.connect(self.on_fetch_error)
        self.fetcher.start()
        
    @pyqtSlot(str)
    def on_fetch_status_update(self, message: str):
        """Update progress dialog"""
        if hasattr(self, 'progress') and self.progress:
            self.progress.setLabelText(message)
            
    @pyqtSlot(str)
    def on_fetch_error(self, error_message: str):
        """Handle fetch error"""
        if hasattr(self, 'progress') and self.progress:
            self.progress.close()
            
        # Check if this was a background refresh
        show_dialog = getattr(self.fetcher, 'show_dialog', True)
        
        logger.error(f"Execution fetch error: {error_message}")
        
        if show_dialog:
            QMessageBox.warning(self, "Error", error_message)
        else:
            # For background refresh, just update the status label
            self.last_update_label.setText(f"Refresh failed: {datetime.now().strftime('%H:%M:%S')}")
        
    @pyqtSlot(dict, dict)
    def on_ib_data_received(self, new_executions: dict, new_commissions: dict):
        """Process received execution data from IB"""
        if hasattr(self, 'progress') and self.progress:
            self.progress.close()
            
        # Check if this was a background refresh
        show_dialog = getattr(self.fetcher, 'show_dialog', True)
            
        try:
            # Store new executions
            self.model.store_new_executions(new_executions, new_commissions)
            
            # Show result only for manual refresh
            if show_dialog:
                if new_executions:
                    QMessageBox.information(
                        self, "Update Complete", 
                        f"Added {len(new_executions)} new executions."
                    )
                else:
                    QMessageBox.information(
                        self, "No New Data", 
                        "No new executions found for today."
                    )
            else:
                # For background refresh, update the status with timestamp
                current_time = datetime.now().strftime('%H:%M:%S')
                if new_executions:
                    logger.info(f"Auto-refresh: Added {len(new_executions)} new executions")
                    self.last_update_label.setText(f"Last update: {current_time} ({len(new_executions)} new)")
                else:
                    logger.debug("Auto-refresh: No new executions found")
                    self.last_update_label.setText(f"Last update: {current_time}")
                
        except Exception as e:
            logger.error(f"Error processing IB data: {e}", exc_info=True)
            if show_dialog:
                QMessageBox.critical(
                    self, "Error", 
                    f"Failed to update data: {str(e)}"
                )
            else:
                self.last_update_label.setText(f"Update error: {datetime.now().strftime('%H:%M:%S')}")
                
    def closeEvent(self, event):
        """Clean up when widget is closed"""
        if hasattr(self, 'auto_refresh_timer'):
            try:
                self.auto_refresh_timer.timeout.disconnect()
            except TypeError:
                pass
            self.auto_refresh_timer.stop()
        event.accept()