# gui/trader_components.py
"""Reusable trader UI components"""
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QLineEdit, QGroupBox, QGridLayout)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QFont

logger = logging.getLogger(__name__)


class MarketDataDisplay(QGroupBox):
    """Widget to display market data for a ticker"""
    
    def __init__(self, parent=None):
        super().__init__("Market Data", parent)
        self.init_ui()
        self.calculated_position_size = 0
        
    def init_ui(self):
        """Initialize the market data display UI"""
        layout = QGridLayout(self)
        layout.setSpacing(10)
        layout.setColumnMinimumWidth(1, 120)  # Space between columns
        layout.setColumnMinimumWidth(3, 120)  # Value column width
        
        # Style the group box
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
        
        # Create labels for market data in two columns
        # Column 1: Bid, Ask, Spread
        # Column 2: Last, Volume, ATR
        data_items = [
            # Column 1
            ("Bid:", "bid", 0, 0),
            ("Ask:", "ask", 1, 0),
            ("Spread:", "spread", 2, 0),
            # Column 2
            ("Last:", "last", 0, 2),
            ("Volume:", "volume", 1, 2),
            ("ATR(14):", "atr", 2, 2),
        ]
        
        self.data_labels = {}
        
        for label_text, key, row, col in data_items:
            # Label
            label = QLabel(label_text)
            label.setStyleSheet("font-weight: 500; color: #555;")
            layout.addWidget(label, row, col)
            
            # Value
            value_label = QLabel("--")
            value_label.setStyleSheet("font-weight: bold; color: #333;")
            value_label.setMinimumWidth(100)
            layout.addWidget(value_label, row, col + 1)
            
            self.data_labels[key] = value_label
            
        # Add some spacing
        layout.setColumnStretch(4, 1)
        
    def update_data(self, data_dict):
        """Update the market data display"""
        for key, value in data_dict.items():
            if key in self.data_labels:
                self.data_labels[key].setText(str(value))
                    
    def clear_data(self):
        """Clear all market data"""
        for label in self.data_labels.values():
            label.setText("--")
            label.setStyleSheet("font-weight: bold; color: #333;")


class PriceInputWidget(QWidget):
    """Widget for price input fields"""
    
    price_changed = pyqtSignal(str, float)  # field_name, value
    
    def __init__(self, label_text: str, placeholder: str = "0.00", 
                 field_name: str = "", parent=None):
        super().__init__(parent)
        self.field_name = field_name
        self.init_ui(label_text, placeholder)
        
    def init_ui(self, label_text: str, placeholder: str):
        """Initialize the price input UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: normal; font-size: 11px; color: #666;")
        layout.addWidget(label)
        
        # Input
        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        self.input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 2px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #2196F3;
            }
        """)
        self.input.textChanged.connect(self.on_text_changed)
        layout.addWidget(self.input)
        
    def on_text_changed(self, text: str):
        """Handle text change"""
        try:
            value = float(text) if text else 0.0
            self.price_changed.emit(self.field_name, value)
        except ValueError:
            pass
            
    def set_value(self, value: float):
        """Set the input value"""
        self.input.setText(f"{value:.2f}")
        
    def get_value(self) -> float:
        """Get the input value"""
        try:
            return float(self.input.text())
        except ValueError:
            return 0.0
            
    def clear(self):
        """Clear the input"""
        self.input.clear()
        
    def set_focus_color(self, color: str):
        """Set the focus border color"""
        self.input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px;
                border: 2px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                background-color: white;
            }}
            QLineEdit:focus {{
                border-color: {color};
            }}
        """)


class OrderTypeSelector(QWidget):
    """Widget for buy/sell selection"""
    
    order_type_changed = pyqtSignal(str)  # BUY or SELL
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """Initialize the order type selector UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        self.buy_btn = QPushButton("BUY")
        self.buy_btn.setCheckable(True)
        self.buy_btn.setChecked(True)
        self.buy_btn.setMinimumHeight(40)
        self.buy_btn.setStyleSheet(self.get_button_style(True))
        self.buy_btn.clicked.connect(lambda: self.on_selection_changed("BUY"))
        
        self.sell_btn = QPushButton("SELL")
        self.sell_btn.setCheckable(True)
        self.sell_btn.setMinimumHeight(40)
        self.sell_btn.setStyleSheet(self.get_button_style(False))
        self.sell_btn.clicked.connect(lambda: self.on_selection_changed("SELL"))
        
        layout.addWidget(self.buy_btn)
        layout.addWidget(self.sell_btn)
        
    def get_button_style(self, is_buy: bool) -> str:
        """Get button style based on type"""
        if is_buy:
            return """
                QPushButton {
                    background-color: #e0e0e0;
                    color: #333;
                    border: 2px solid #ddd;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:checked {
                    background-color: #4CAF50;
                    color: white;
                    border-color: #45a049;
                }
                QPushButton:hover {
                    border-color: #999;
                }
            """
        else:
            return """
                QPushButton {
                    background-color: #e0e0e0;
                    color: #333;
                    border: 2px solid #ddd;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:checked {
                    background-color: #f44336;
                    color: white;
                    border-color: #da190b;
                }
                QPushButton:hover {
                    border-color: #999;
                }
            """
            
    def on_selection_changed(self, order_type: str):
        """Handle order type selection change"""
        if order_type == "BUY":
            self.buy_btn.setChecked(True)
            self.sell_btn.setChecked(False)
        else:
            self.buy_btn.setChecked(False)
            self.sell_btn.setChecked(True)
            
        self.order_type_changed.emit(order_type)
        
    def get_selected_type(self) -> str:
        """Get the selected order type"""
        return "BUY" if self.buy_btn.isChecked() else "SELL"
        
    def is_buy_selected(self) -> bool:
        """Check if buy is selected"""
        return self.buy_btn.isChecked()


class PositionSizeDisplay(QWidget):
    """Widget for displaying position size calculations"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """Initialize the position size display UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # First row - position size and value
        first_row = QHBoxLayout()
        first_row.setSpacing(10)
        
        position_label = QLabel("Position Size:")
        position_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        
        self.position_size_label = QLabel("-- shares")
        self.position_size_label.setStyleSheet("""
            font-weight: bold; 
            font-size: 14px; 
            color: #2196F3;
            padding: 8px;
        """)
        
        value_label = QLabel("Position Value:")
        value_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        
        self.position_value_label = QLabel("$0.00")
        self.position_value_label.setStyleSheet("""
            font-weight: bold; 
            font-size: 14px; 
            color: #333;
            padding: 8px;
        """)
        
        first_row.addWidget(position_label)
        first_row.addWidget(self.position_size_label)
        first_row.addSpacing(20)
        first_row.addWidget(value_label)
        first_row.addWidget(self.position_value_label)
        first_row.addStretch()
        
        # Second row - risk and profit
        second_row = QHBoxLayout()
        second_row.setSpacing(10)
        
        risk_label = QLabel("Risk Amount:")
        risk_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        
        self.risk_amount_label = QLabel("$0.00")
        self.risk_amount_label.setStyleSheet("""
            font-weight: bold; 
            font-size: 14px; 
            color: #f44336;
            padding: 8px;
        """)
        
        profit_label = QLabel("Potential Profit:")
        profit_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        
        self.potential_profit_label = QLabel("$0.00")
        self.potential_profit_label.setStyleSheet("""
            font-weight: bold; 
            font-size: 14px; 
            color: #4CAF50;
            padding: 8px;
        """)
        
        second_row.addWidget(risk_label)
        second_row.addWidget(self.risk_amount_label)
        second_row.addSpacing(20)
        second_row.addWidget(profit_label)
        second_row.addWidget(self.potential_profit_label)
        second_row.addStretch()
        
        layout.addLayout(first_row)
        layout.addLayout(second_row)
        
    def update_display(self, position_data: dict):
        """Update the display with calculated position data"""
        if position_data.get('error'):
            self.clear_display()
            return
            
        position_size = position_data['position_size']
        position_value = position_data['position_value']
        risk_amount = position_data['risk_amount']
        
        self.position_size_label.setText(f"{position_size} shares")
        self.position_value_label.setText(f"${position_value:,.2f}")
        self.risk_amount_label.setText(f"${risk_amount:,.2f}")
        
        # Add warning color if position is limited by funds
        if position_data.get('limited_by_funds'):
            self.position_size_label.setStyleSheet("""
                font-weight: bold; 
                font-size: 14px; 
                color: #FF9800;
                padding: 8px;
            """)
        else:
            self.position_size_label.setStyleSheet("""
                font-weight: bold; 
                font-size: 14px; 
                color: #2196F3;
                padding: 8px;
            """)
            
        # Set tooltip with detailed information
        tooltip = self.create_tooltip(position_data)
        for widget in [self.position_size_label, self.position_value_label,
                      self.risk_amount_label, self.potential_profit_label]:
            widget.setToolTip(tooltip)
            
    def update_profit(self, profit: float):
        """Update potential profit display"""
        if profit > 0:
            self.potential_profit_label.setText(f"${profit:,.2f}")
        else:
            self.potential_profit_label.setText("$0.00")
            
    def clear_display(self):
        """Clear all displays"""
        self.position_size_label.setText("-- shares")
        self.position_value_label.setText("$0.00")
        self.risk_amount_label.setText("$0.00")
        self.potential_profit_label.setText("$0.00")
        
    def create_tooltip(self, position_data: dict) -> str:
        """Create detailed tooltip"""
        tooltip = f"Position Size (by risk): {position_data['position_size_by_risk']} shares\n"
        tooltip += f"Position Size (by funds): {position_data['max_position_size_by_funds']} shares\n"
        tooltip += f"Final Position Size: {position_data['position_size']} shares"
        
        if position_data.get('limited_by_funds'):
            tooltip += " (Limited by funds)"
            
        return tooltip