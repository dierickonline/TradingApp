# gui/connection_widget.py
"""Connection widget for managing IB connection settings and status"""
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QLineEdit, QGroupBox, QGridLayout,
                            QFrame, QDialog, QDialogButtonBox)
from PyQt6.QtCore import pyqtSignal, QTimer, pyqtSlot, Qt
from PyQt6.QtGui import QFont
from config import APP_CONFIG

logger = logging.getLogger(__name__)


class ConnectionSettingsDialog(QDialog):
    """Dialog for connection settings"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connection Settings")
        self.setModal(True)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Settings group
        settings_group = QGroupBox("IB Gateway/TWS Settings")
        settings_layout = QGridLayout()
        
        # Host
        settings_layout.addWidget(QLabel("Host:"), 0, 0)
        self.host_input = QLineEdit(APP_CONFIG.default_host)
        settings_layout.addWidget(self.host_input, 0, 1)
        
        # Port
        settings_layout.addWidget(QLabel("Port:"), 1, 0)
        self.port_input = QLineEdit(str(APP_CONFIG.default_port))
        settings_layout.addWidget(self.port_input, 1, 1)
        
        # Client ID
        settings_layout.addWidget(QLabel("Client ID:"), 2, 0)
        self.client_id_input = QLineEdit(str(APP_CONFIG.default_client_id))
        settings_layout.addWidget(self.client_id_input, 2, 1)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_settings(self):
        """Get the connection settings"""
        return {
            'host': self.host_input.text(),
            'port': int(self.port_input.text()),
            'client_id': int(self.client_id_input.text())
        }


class ConnectionWidget(QGroupBox):
    """Connection control panel for Interactive Brokers"""
    
    # Signals
    connect_requested = pyqtSignal(str, int, int)  # host, port, client_id
    disconnect_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__("Connection to Interactive Brokers", parent)
        self.logger = logging.getLogger(__name__)
        
        # Status labels storage
        self.status_labels = {}
        
        # Connection settings
        self.connection_settings = {
            'host': APP_CONFIG.default_host,
            'port': APP_CONFIG.default_port,
            'client_id': APP_CONFIG.default_client_id
        }
        
        self.setup_ui()
        self.setup_market_timer()
        self.setFixedWidth(400)
        
        # Initial market status update
        self.update_market_status()
        
    def setup_ui(self):
        """Setup the connection panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 15, 10, 10)
        layout.setSpacing(6)
        
        # Connection buttons
        self.create_connection_buttons(layout)
        
        # Status section
        self.create_status_section(layout)
        
        # Apply styling
        self.setStyleSheet(self.get_group_style())
        
    def create_connection_buttons(self, layout):
        """Create connection control buttons"""
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setMinimumHeight(35)
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.connect_btn.clicked.connect(self.on_connect_clicked)
        
        # Disconnect button
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setMinimumHeight(35)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.disconnect_btn.clicked.connect(self.on_disconnect_clicked)
        
        # Settings button
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(35, 35)
        self.settings_btn.setToolTip("Connection Settings")
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.settings_btn.clicked.connect(self.on_settings_clicked)
        
        button_layout.addWidget(self.connect_btn)
        button_layout.addWidget(self.disconnect_btn)
        button_layout.addWidget(self.settings_btn)
        layout.addWidget(button_frame)
        
    def create_status_section(self, layout):
        """Create status display section"""
        # Status header
        status_header = QLabel("Connection Status")
        status_header.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        status_header.setStyleSheet("color: #333; margin-bottom: 5px;")
        layout.addWidget(status_header)
        
        # Status rows
        status_items = [
            ("IB Connection:", "Disconnected", "connection_status"),
            ("NYC Market:", "Checking...", "market_status"),
            ("Available Funds:", "Not connected", "available_funds")
        ]
        
        for label_text, initial_value, key in status_items:
            row_frame = QFrame()
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(0, 2, 0, 2)
            
            # Label
            label = QLabel(label_text)
            label.setStyleSheet("color: #555; font-weight: 500;")
            label.setMinimumWidth(120)
            
            # Value
            value_label = QLabel(initial_value)
            value_label.setStyleSheet("color: #333; font-weight: bold;")
            
            # Set initial color for connection status
            if key == "connection_status":
                value_label.setStyleSheet("color: red; font-weight: bold;")
            
            row_layout.addWidget(label)
            row_layout.addWidget(value_label)
            row_layout.addStretch()
            
            # Store reference to value label
            self.status_labels[key] = value_label
            
            layout.addWidget(row_frame)
        
        # Add some spacing at the bottom
        layout.addStretch()
        
    def setup_market_timer(self):
        """Setup market status update timer"""
        self.market_timer = QTimer()
        self.market_timer.timeout.connect(self.update_market_status)
        self.market_timer.start(30000)  # Update every 30 seconds
        
    def update_market_status(self):
        """Update NYC market status"""
        try:
            from datetime import datetime
            import pytz
            
            # Get NYC time
            nyc_tz = pytz.timezone('America/New_York')
            nyc_time = datetime.now(nyc_tz)
            
            # Check if weekend
            if nyc_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
                display_text = f"Weekend ({nyc_time.strftime('%I:%M %p')})"
                color = "orange"
            else:
                # Check market hours (simplified)
                hour = nyc_time.hour
                minute = nyc_time.minute
                
                if hour < 4:  # Before pre-market
                    display_text = f"Closed ({nyc_time.strftime('%I:%M %p')})"
                    color = "red"
                elif hour < 9 or (hour == 9 and minute < 30):  # Pre-market
                    display_text = f"Pre-Market ({nyc_time.strftime('%I:%M %p')})"
                    color = "blue"
                elif hour < 16:  # Regular trading hours
                    display_text = f"Open ({nyc_time.strftime('%I:%M %p')})"
                    color = "green"
                elif hour < 20:  # After-market
                    display_text = f"After-Market ({nyc_time.strftime('%I:%M %p')})"
                    color = "blue"
                else:  # Closed
                    display_text = f"Closed ({nyc_time.strftime('%I:%M %p')})"
                    color = "red"
            
            if "market_status" in self.status_labels:
                self.status_labels["market_status"].setText(display_text)
                self.status_labels["market_status"].setStyleSheet(f"color: {color}; font-weight: bold;")
                
        except Exception as e:
            self.logger.error(f"Error updating market status: {e}")
            if "market_status" in self.status_labels:
                self.status_labels["market_status"].setText("Error")
                self.status_labels["market_status"].setStyleSheet("color: red;")
                
    @pyqtSlot()
    def on_connect_clicked(self):
        """Handle connect button click"""
        self.logger.info("Connect button clicked")
        self.connect_requested.emit(
            self.connection_settings['host'],
            self.connection_settings['port'],
            self.connection_settings['client_id']
        )
        
    @pyqtSlot()
    def on_disconnect_clicked(self):
        """Handle disconnect button click"""
        self.logger.info("Disconnect button clicked")
        self.disconnect_requested.emit()
        
    @pyqtSlot()
    def on_settings_clicked(self):
        """Handle settings button click"""
        dialog = ConnectionSettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                settings = dialog.get_settings()
                self.connection_settings = settings
                self.logger.info(f"Connection settings updated: {settings}")
            except ValueError as e:
                self.logger.error(f"Invalid settings: {e}")
                
    def update_connection_status(self, connected):
        """Update connection status display"""
        if connected:
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.status_labels["connection_status"].setText("Connected")
            self.status_labels["connection_status"].setStyleSheet("color: green; font-weight: bold;")
        else:
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.status_labels["connection_status"].setText("Disconnected")
            self.status_labels["connection_status"].setStyleSheet("color: red; font-weight: bold;")
            self.clear_account_data()
            
    def update_account_value(self, account, tag, value, currency):
        """Update account information display"""
        try:
            if tag == "AvailableFunds":
                funds_value = float(value)
                display_text = f"{currency} {funds_value:,.2f}"
                self.status_labels["available_funds"].setText(display_text)
                self.status_labels["available_funds"].setStyleSheet("color: green; font-weight: bold;")
        except ValueError:
            self.logger.error(f"Error parsing {tag} value: {value}")
            
    def clear_account_data(self):
        """Clear account-related data"""
        self.status_labels["available_funds"].setText("not connected")
        self.status_labels["available_funds"].setStyleSheet("color: #666; font-weight: normal;")
        
    def show_error(self, error_message):
        """Update status to show error"""
        self.status_labels["connection_status"].setText("Error")
        self.status_labels["connection_status"].setStyleSheet("color: red; font-weight: bold;")
        self.logger.error(f"Connection error: {error_message}")
        
    def get_group_style(self) -> str:
        """Get consistent group styling"""
        return """
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
        """
        
    def cleanup(self):
        """Clean up resources"""
        try:
            if hasattr(self, 'market_timer'):
                self.market_timer.stop()
            self.logger.info("Connection widget cleaned up")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")