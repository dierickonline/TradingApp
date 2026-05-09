# gui/risk_management_widget.py
"""Risk management widget for setting trading risk parameters"""
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QLineEdit, QGroupBox, QGridLayout,
                            QCheckBox, QSpacerItem, QSizePolicy, QMessageBox,
                            QDoubleSpinBox, QSpinBox)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QFont

from config import APP_CONFIG
from core.persistence import atomic_write_json, load_versioned_settings

logger = logging.getLogger(__name__)


RISK_PARAMS_SCHEMA = 1

DEFAULT_RISK_PARAMS = {
    "risk_reward_ratio": 2.0,
    "max_risk_percentage": 2.0,
    "confirm_trades": True,
}


class RiskParametersWidget(QGroupBox):
    """Widget for risk management parameters"""

    # Signals
    parameters_changed = pyqtSignal(dict)  # Emitted when parameters are saved

    def __init__(self, parent=None):
        super().__init__("Risk Management Parameters", parent)
        self.init_ui()
        self.load_parameters()
        
    def init_ui(self):
        """Initialize the risk parameters UI"""
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #ddd;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Parameters grid
        params_layout = QGridLayout()
        params_layout.setColumnMinimumWidth(0, 200)
        params_layout.setHorizontalSpacing(20)
        params_layout.setVerticalSpacing(15)
        
        # Risk/Reward Ratio
        rr_label = QLabel("Risk/Reward Ratio:")
        rr_label.setStyleSheet("font-weight: normal; font-size: 13px;")
        self.risk_reward_input = QDoubleSpinBox()
        self.risk_reward_input.setRange(0.1, 10.0)
        self.risk_reward_input.setSingleStep(0.1)
        self.risk_reward_input.setDecimals(1)
        self.risk_reward_input.setValue(2.0)
        self.risk_reward_input.setSuffix(":1")
        self.risk_reward_input.setStyleSheet("""
            QDoubleSpinBox {
                padding: 5px;
                border: 2px solid #ddd;
                border-radius: 4px;
                font-size: 13px;
                background-color: white;
                min-width: 100px;
            }
            QDoubleSpinBox:focus {
                border-color: #2196F3;
            }
        """)
        self.risk_reward_input.setToolTip("Target profit relative to risk (e.g., 2:1 means target 2x the risk)")
        
        params_layout.addWidget(rr_label, 0, 0)
        params_layout.addWidget(self.risk_reward_input, 0, 1)
        
        # Risk/Reward Info
        rr_info = QLabel("Target profit = Risk × Ratio")
        rr_info.setStyleSheet("font-weight: normal; font-size: 11px; color: #666; font-style: italic;")
        params_layout.addWidget(rr_info, 0, 2)
        
        # Maximum Risk Percentage
        risk_label = QLabel("Maximum Risk per Position:")
        risk_label.setStyleSheet("font-weight: normal; font-size: 13px;")
        self.max_risk_input = QDoubleSpinBox()
        self.max_risk_input.setRange(0.1, 10.0)
        self.max_risk_input.setSingleStep(0.1)
        self.max_risk_input.setDecimals(1)
        self.max_risk_input.setValue(2.0)
        self.max_risk_input.setSuffix("%")
        self.max_risk_input.setStyleSheet("""
            QDoubleSpinBox {
                padding: 5px;
                border: 2px solid #ddd;
                border-radius: 4px;
                font-size: 13px;
                background-color: white;
                min-width: 100px;
            }
            QDoubleSpinBox:focus {
                border-color: #2196F3;
            }
        """)
        self.max_risk_input.setToolTip("Maximum percentage of account to risk on a single position")
        
        params_layout.addWidget(risk_label, 1, 0)
        params_layout.addWidget(self.max_risk_input, 1, 1)
        
        # Max Risk Info
        risk_info = QLabel("% of account balance")
        risk_info.setStyleSheet("font-weight: normal; font-size: 11px; color: #666; font-style: italic;")
        params_layout.addWidget(risk_info, 1, 2)
        
        # Trade Confirmation Checkbox
        self.confirm_trades_checkbox = QCheckBox("Show confirmation before executing trades")
        self.confirm_trades_checkbox.setChecked(True)
        self.confirm_trades_checkbox.setStyleSheet("""
            QCheckBox {
                font-weight: normal;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.confirm_trades_checkbox.setToolTip("Enable/disable trade confirmation dialogs")
        
        params_layout.addWidget(self.confirm_trades_checkbox, 2, 0, 1, 2)
        
        # Add parameters layout to main layout
        layout.addLayout(params_layout)
        
        # Add some vertical spacing
        layout.addSpacing(30)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        # Save button
        self.save_btn = QPushButton("Save Parameters")
        self.save_btn.setMinimumWidth(150)
        self.save_btn.setMinimumHeight(35)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.save_btn.clicked.connect(self.save_parameters)
        
        # Reset button
        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.setMinimumWidth(150)
        self.reset_btn.setMinimumHeight(35)
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #9E9E9E;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #757575;
            }
            QPushButton:pressed {
                background-color: #616161;
            }
        """)
        self.reset_btn.clicked.connect(self.reset_to_defaults)
        
        buttons_layout.addWidget(self.reset_btn)
        buttons_layout.addWidget(self.save_btn)
        
        layout.addLayout(buttons_layout)
        
        # Add stretch to push everything to top
        layout.addStretch()
        
    def get_parameters(self) -> dict:
        """Get current parameter values"""
        return {
            "risk_reward_ratio": self.risk_reward_input.value(),
            "max_risk_percentage": self.max_risk_input.value(),
            "confirm_trades": self.confirm_trades_checkbox.isChecked()
        }
        
    def set_parameters(self, params: dict):
        """Set parameter values"""
        if "risk_reward_ratio" in params:
            self.risk_reward_input.setValue(params["risk_reward_ratio"])
        if "max_risk_percentage" in params:
            self.max_risk_input.setValue(params["max_risk_percentage"])
        if "confirm_trades" in params:
            self.confirm_trades_checkbox.setChecked(params["confirm_trades"])
            
    def save_parameters(self):
        """Save parameters to file atomically."""
        params = self.get_parameters()
        payload = dict(params)
        payload["__schema__"] = RISK_PARAMS_SCHEMA
        try:
            atomic_write_json(APP_CONFIG.risk_parameters_path, payload)
            logger.info(f"Risk parameters saved: {params}")
            self.parameters_changed.emit(params)
            QMessageBox.information(self, "Success", "Risk parameters saved successfully!")
        except OSError as e:
            logger.error(f"Error saving risk parameters: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save parameters: {e}")

    def load_parameters(self):
        """Load parameters from file with graceful fallback."""
        params = load_versioned_settings(
            APP_CONFIG.risk_parameters_path, DEFAULT_RISK_PARAMS, RISK_PARAMS_SCHEMA
        )
        # Strip the schema key before applying to the widget — set_parameters
        # only knows about real parameter keys.
        widget_params = {k: v for k, v in params.items() if not k.startswith("__")}
        self.set_parameters(widget_params)
        logger.info(f"Risk parameters loaded: {widget_params}")
            
    def reset_to_defaults(self):
        """Reset parameters to default values"""
        reply = QMessageBox.question(self, "Reset Parameters", 
                                   "Are you sure you want to reset all parameters to defaults?",
                                   QMessageBox.StandardButton.Yes | 
                                   QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.risk_reward_input.setValue(2.0)
            self.max_risk_input.setValue(2.0)
            self.confirm_trades_checkbox.setChecked(True)
            logger.info("Risk parameters reset to defaults")


class RiskManagementWidget(QWidget):
    """Main risk management tab widget"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """Initialize the risk management UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Title
        title_label = QLabel("Risk Management Settings")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #333;
                padding-bottom: 10px;
            }
        """)
        layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel("Configure risk management parameters for your trading strategy. "
                          "These settings help control position sizing and risk exposure.")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #666;
                padding-bottom: 20px;
            }
        """)
        layout.addWidget(desc_label)
        
        # Risk parameters widget
        self.risk_params_widget = RiskParametersWidget()
        layout.addWidget(self.risk_params_widget)
        
        # Future expansion area
        future_group = QGroupBox("Additional Settings (Coming Soon)")
        future_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #ddd;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 20px;
                background-color: #f9f9f9;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
            }
        """)
        
        future_layout = QVBoxLayout(future_group)
        future_label = QLabel("• Position sizing calculator\n"
                            "• Daily loss limits\n"
                            "• Correlation risk management\n"
                            "• Portfolio heat mapping")
        future_label.setStyleSheet("""
            QLabel {
                font-weight: normal;
                font-size: 12px;
                color: #999;
                padding: 20px;
            }
        """)
        future_layout.addWidget(future_label)
        
        layout.addWidget(future_group)
        
        # Add stretch to push everything to top
        layout.addStretch()
        
    def get_risk_parameters(self) -> dict:
        """Get current risk parameters"""
        return self.risk_params_widget.get_parameters()