# gui/connection_widget.py
"""Connection widget for managing IB connection settings and status"""
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QLineEdit, QGroupBox, QGridLayout,
                            QFrame, QDialog, QDialogButtonBox, QRadioButton,
                            QButtonGroup, QSpinBox, QMessageBox)
from PyQt6.QtCore import pyqtSignal, QTimer, pyqtSlot, Qt
from PyQt6.QtGui import QFont
from config import APP_CONFIG, MARKET_DATA_LIVE, MARKET_DATA_DELAYED
from core.app_settings import load_app_settings, save_app_settings
from gui.styles import (
    GROUP_BOX_QSS,
    success_button_qss,
    danger_button_qss,
    primary_button_qss,
)

logger = logging.getLogger(__name__)


def market_data_label(value: int) -> str:
    """Short human label for the market data type setting."""
    return "Live" if value == MARKET_DATA_LIVE else "Delayed"


class ConnectionSettingsDialog(QDialog):
    """Dialog for connection settings"""
    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Connection Settings")
        self.setModal(True)
        self._current_settings = current_settings or {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Settings group
        settings_group = QGroupBox("IB Gateway/TWS Settings")
        settings_layout = QGridLayout()

        host_value = self._current_settings.get('host', APP_CONFIG.default_host)
        port_value = self._current_settings.get('port', APP_CONFIG.default_port)
        client_id_value = self._current_settings.get('client_id', APP_CONFIG.default_client_id)
        market_data_value = self._current_settings.get(
            'market_data_type', APP_CONFIG.default_market_data_type
        )

        # Host
        settings_layout.addWidget(QLabel("Host:"), 0, 0)
        self.host_input = QLineEdit(str(host_value))
        settings_layout.addWidget(self.host_input, 0, 1)

        # Port
        settings_layout.addWidget(QLabel("Port:"), 1, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(int(port_value))
        self.port_input.setToolTip("TWS Paper: 7497 · Live: 7496 · IB Gateway Paper: 4002 · Live: 4001")
        settings_layout.addWidget(self.port_input, 1, 1)

        # Client ID
        settings_layout.addWidget(QLabel("Client ID:"), 2, 0)
        self.client_id_input = QSpinBox()
        self.client_id_input.setRange(0, 999)
        self.client_id_input.setValue(int(client_id_value))
        self.client_id_input.setToolTip("Distinct ID for this connection. 0-999.")
        settings_layout.addWidget(self.client_id_input, 2, 1)

        # Market Data Type — Live vs Delayed
        settings_layout.addWidget(QLabel("Market Data:"), 3, 0)
        market_data_frame = QFrame()
        market_data_layout = QHBoxLayout(market_data_frame)
        market_data_layout.setContentsMargins(0, 0, 0, 0)
        self.delayed_radio = QRadioButton("Delayed (free)")
        self.delayed_radio.setToolTip(
            "15-20 minute delayed quotes. Use this for swing trading without a "
            "live data subscription."
        )
        self.live_radio = QRadioButton("Live (subscription required)")
        self.live_radio.setToolTip(
            "Real-time streaming quotes. Requires an active IB market data "
            "subscription for the relevant exchange."
        )
        self.market_data_group = QButtonGroup(self)
        self.market_data_group.addButton(self.delayed_radio, MARKET_DATA_DELAYED)
        self.market_data_group.addButton(self.live_radio, MARKET_DATA_LIVE)
        if market_data_value == MARKET_DATA_LIVE:
            self.live_radio.setChecked(True)
        else:
            self.delayed_radio.setChecked(True)
        market_data_layout.addWidget(self.delayed_radio)
        market_data_layout.addWidget(self.live_radio)
        market_data_layout.addStretch()
        settings_layout.addWidget(market_data_frame, 3, 1)

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
        market_data_type = self.market_data_group.checkedId()
        if market_data_type not in (MARKET_DATA_LIVE, MARKET_DATA_DELAYED):
            market_data_type = APP_CONFIG.default_market_data_type
        return {
            'host': self.host_input.text(),
            'port': self.port_input.value(),
            'client_id': self.client_id_input.value(),
            'market_data_type': market_data_type,
        }


class ConnectionWidget(QGroupBox):
    """Connection control panel for Interactive Brokers"""

    # Signals
    # host, port, client_id, market_data_type
    connect_requested = pyqtSignal(str, int, int, int)
    disconnect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Connection to Interactive Brokers", parent)
        self.logger = logging.getLogger(__name__)

        # Status labels storage
        self.status_labels = {}
        # Tracks whether IB is connected so the settings dialog can warn that
        # changes only take effect on the next connection.
        self._connected = False

        # Connection settings — start with persisted market data type so the
        # default truly is what the user last picked (or Delayed on first run).
        persisted = load_app_settings()
        self.connection_settings = {
            'host': APP_CONFIG.default_host,
            'port': APP_CONFIG.default_port,
            'client_id': APP_CONFIG.default_client_id,
            'market_data_type': persisted.get(
                'market_data_type', APP_CONFIG.default_market_data_type
            ),
        }

        self.setup_ui()
        self.setup_market_timer()
        self.setFixedWidth(400)

        # Initial market status update
        self.update_market_status()
        self._refresh_market_data_type_label()
        
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
        self.connect_btn.setStyleSheet(success_button_qss())
        self.connect_btn.clicked.connect(self.on_connect_clicked)

        # Disconnect button
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setMinimumHeight(35)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet(danger_button_qss())
        self.disconnect_btn.clicked.connect(self.on_disconnect_clicked)

        # Settings button
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(35, 35)
        self.settings_btn.setToolTip("Connection Settings")
        self.settings_btn.setStyleSheet(primary_button_qss())
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
            ("Available Funds:", "Not connected", "available_funds"),
            ("Market Data:", "Delayed", "market_data_type"),
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
            self.connection_settings['client_id'],
            self.connection_settings.get(
                'market_data_type', APP_CONFIG.default_market_data_type
            ),
        )

    @pyqtSlot()
    def on_disconnect_clicked(self):
        """Handle disconnect button click"""
        self.logger.info("Disconnect button clicked")
        self.disconnect_requested.emit()

    @pyqtSlot()
    def on_settings_clicked(self):
        """Handle settings button click"""
        dialog = ConnectionSettingsDialog(self, current_settings=self.connection_settings)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        settings = dialog.get_settings()
        previous = self.connection_settings.copy()
        self.connection_settings = settings
        self.logger.info(f"Connection settings updated: {settings}")
        # Persist only the settings that should survive restarts.
        save_app_settings({'market_data_type': settings['market_data_type']})
        self._refresh_market_data_type_label()

        # If the connection is open, settings changes don't apply until next
        # connect. Warn the user once instead of silently storing the change.
        if self._connected and previous != settings:
            QMessageBox.information(
                self,
                "Settings saved",
                "Connection settings have been saved. Changes will take effect "
                "the next time you connect to IB.",
            )

    def _refresh_market_data_type_label(self):
        """Update the Market Data status row to reflect current selection."""
        if "market_data_type" not in self.status_labels:
            return
        value = self.connection_settings.get(
            'market_data_type', APP_CONFIG.default_market_data_type
        )
        label = market_data_label(value)
        # Color: live = orange (warns it costs / needs subscription), delayed = neutral blue
        color = "#E67E22" if value == MARKET_DATA_LIVE else "#1976D2"
        self.status_labels["market_data_type"].setText(label)
        self.status_labels["market_data_type"].setStyleSheet(
            f"color: {color}; font-weight: bold;"
        )
                
    def update_connection_status(self, connected):
        """Update connection status display"""
        self._connected = connected
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
        """Get consistent group styling. Sourced from :mod:`gui.styles`."""
        return GROUP_BOX_QSS
        
    def cleanup(self):
        """Clean up resources"""
        try:
            if hasattr(self, 'market_timer'):
                try:
                    self.market_timer.timeout.disconnect()
                except TypeError:
                    pass
                self.market_timer.stop()
            self.logger.info("Connection widget cleaned up")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")