# gui/positions_widget.py
"""Widget for displaying and managing open positions"""
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QTableWidget, QTableWidgetItem,
                            QHeaderView, QGroupBox, QMessageBox)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer
from PyQt6.QtGui import QColor, QBrush

logger = logging.getLogger(__name__)


class PositionsWidget(QGroupBox):
    """Widget for displaying open positions"""
    
    # Signals
    close_position = pyqtSignal(str, float)  # symbol, percentage
    refresh_positions = pyqtSignal()
    subscribe_position_ticker = pyqtSignal(str)  # symbol - to get real-time prices
    
    def __init__(self, parent=None):
        super().__init__("Open Positions", parent)
        self.positions = {}  # symbol -> position data
        self.updating = False  # Flag to prevent recursive updates
        self.show_trade_confirmation = True  # Default to showing confirmation
        self.init_ui()
        
    def init_ui(self):
        """Initialize the positions widget UI"""
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
        
        # Refresh button
        refresh_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Positions")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.refresh_btn.clicked.connect(self.on_refresh_clicked)
        refresh_layout.addWidget(self.refresh_btn)
        refresh_layout.addStretch()
        layout.addLayout(refresh_layout)
        
        # Positions table
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "Qty", "Avg Cost", "Current", "Position Value",
            "Unrealized P&L", "Total P&L", 
            "Close 50%", "Close 100%"
        ])
        
        # Set column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Symbol
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Qty
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Avg Cost
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Current
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Position Value
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Unrealized P&L
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Total P&L
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)  # Close 50%
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)  # Close 100%
        
        # Set fixed width for button columns
        header.resizeSection(7, 100)  # Close 50% button width
        header.resizeSection(8, 100)  # Close 100% button width
        
        # Style the table
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
                gridline-color: #eee;
            }
            QTableWidget::item {
                padding: 5px;
                font-weight: normal;
            }
            QHeaderView::section {
                background-color: #f5f5f5;
                font-weight: bold;
                border: none;
                padding: 5px;
                border-bottom: 2px solid #ddd;
            }
        """)
        
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        layout.addWidget(self.table)
        
        # Summary row
        summary_layout = QHBoxLayout()
        summary_layout.addStretch()
        self.total_pnl_label = QLabel("Total P&L: $0.00")
        self.total_pnl_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
            }
        """)
        summary_layout.addWidget(self.total_pnl_label)
        layout.addLayout(summary_layout)
        
    @pyqtSlot()
    def on_refresh_clicked(self):
        """Handle refresh button click"""
        logger.info("Refreshing positions")
        self.refresh_positions.emit()
        
    def update_position(self, symbol: str, position_data):
        """Update or add a position in the table"""
        if self.updating:
            return
            
        try:
            self.updating = True
            
            # Check if position already exists
            row = self.find_position_row(symbol)
            
            if row == -1:
                # Add new row
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                # Subscribe to market data for this symbol
                self.subscribe_position_ticker.emit(symbol)
                
            # Safely update row data
            self._set_table_item(row, 0, symbol)
            self._set_table_item(row, 1, str(int(position_data.quantity)))
            self._set_table_item(row, 2, f"${position_data.avg_cost:.2f}")
            self._set_table_item(row, 3, f"${position_data.current_price:.2f}")
            
            # Position Value
            position_value = abs(position_data.quantity) * position_data.current_price
            self._set_table_item(row, 4, f"${position_value:,.2f}")
            
            # Unrealized P&L with color
            unrealized_pnl = position_data.unrealized_pnl
            unrealized_item = QTableWidgetItem(f"${unrealized_pnl:,.2f}")
            if unrealized_pnl >= 0:
                unrealized_item.setForeground(QBrush(QColor(76, 175, 80)))  # Green
            else:
                unrealized_item.setForeground(QBrush(QColor(244, 67, 54)))  # Red
            self.table.setItem(row, 5, unrealized_item)
            
            # Total P&L with color
            total_pnl = position_data.total_pnl
            total_item = QTableWidgetItem(f"${total_pnl:,.2f}")
            if total_pnl >= 0:
                total_item.setForeground(QBrush(QColor(76, 175, 80)))  # Green
            else:
                total_item.setForeground(QBrush(QColor(244, 67, 54)))  # Red
            self.table.setItem(row, 6, total_item)
            
            # Close buttons - only create if they don't exist
            if not self.table.cellWidget(row, 7):
                close_50_btn = self._create_close_button("Close 50%", "#FF9800", "#F57C00", 
                                                        lambda: self.on_close_position(symbol, 50))
                self.table.setCellWidget(row, 7, close_50_btn)
            
            if not self.table.cellWidget(row, 8):
                close_100_btn = self._create_close_button("Close 100%", "#f44336", "#da190b",
                                                         lambda: self.on_close_position(symbol, 100))
                self.table.setCellWidget(row, 8, close_100_btn)
            
            # Store position data
            self.positions[symbol] = position_data
            
            # Update total P&L
            self.update_total_pnl()
            
        except Exception as e:
            logger.error(f"Error updating position for {symbol}: {e}", exc_info=True)
        finally:
            self.updating = False
            
    def _set_table_item(self, row: int, col: int, text: str):
        """Safely set a table item"""
        try:
            item = QTableWidgetItem(text)
            self.table.setItem(row, col, item)
        except Exception as e:
            logger.error(f"Error setting table item at ({row}, {col}): {e}")
            
    def _create_close_button(self, text: str, bg_color: str, hover_color: str, callback):
        """Create a close button with proper styling"""
        btn = QPushButton(text)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
        """)
        btn.clicked.connect(callback)
        return btn
        
    def remove_position(self, symbol: str):
        """Remove a position from the table"""
        if self.updating:
            return
            
        try:
            self.updating = True
            
            row = self.find_position_row(symbol)
            if row != -1:
                # Disconnect any signals from buttons before removing
                for col in [7, 8]:  # Close button columns
                    widget = self.table.cellWidget(row, col)
                    if widget:
                        try:
                            widget.clicked.disconnect()
                        except:
                            pass
                
                # Remove the row
                self.table.removeRow(row)
                logger.info(f"Removed position row for {symbol}")
                
            if symbol in self.positions:
                del self.positions[symbol]
                
            self.update_total_pnl()
            
        except Exception as e:
            logger.error(f"Error removing position {symbol}: {e}", exc_info=True)
        finally:
            self.updating = False
        
    def find_position_row(self, symbol: str) -> int:
        """Find the row index for a symbol"""
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item and item.text() == symbol:
                    return row
            return -1
        except Exception as e:
            logger.error(f"Error finding position row for {symbol}: {e}")
            return -1
        
    def update_total_pnl(self):
        """Update the total P&L display"""
        try:
            total_pnl = sum(pos.total_pnl for pos in self.positions.values())
            
            self.total_pnl_label.setText(f"Total P&L: ${total_pnl:,.2f}")
            
            if total_pnl >= 0:
                self.total_pnl_label.setStyleSheet("""
                    QLabel {
                        font-size: 14px;
                        font-weight: bold;
                        padding: 5px;
                        color: #4CAF50;
                    }
                """)
            else:
                self.total_pnl_label.setStyleSheet("""
                    QLabel {
                        font-size: 14px;
                        font-weight: bold;
                        padding: 5px;
                        color: #f44336;
                    }
                """)
        except Exception as e:
            logger.error(f"Error updating total P&L: {e}")
            
    def on_close_position(self, symbol: str, percentage: float):
        """Handle close position button click"""
        try:
            position = self.positions.get(symbol)
            if not position:
                logger.warning(f"Position not found for {symbol}")
                return
                
            # Show confirmation dialog if enabled
            if self.show_trade_confirmation:
                qty_to_close = int(abs(position.quantity) * (percentage / 100.0))
                action = "Sell" if position.quantity > 0 else "Buy"
                
                # Add position validation info
                msg = f"Confirm {percentage}% Position Close:\n\n"
                msg += f"Symbol: {symbol}\n"
                msg += f"Current Position: {int(position.quantity)} shares\n"
                msg += f"Action: {action} {qty_to_close} shares\n"
                msg += f"Type: Market Order\n\n"
                
                # Add warning for short sale issues
                if position.quantity > 0 and qty_to_close > position.quantity:
                    msg += "⚠️ WARNING: Order quantity exceeds position size!\n\n"
                    
                msg += "Execute this order?"
                
                reply = QMessageBox.question(self, "Confirm Close Position", msg,
                                           QMessageBox.StandardButton.Yes | 
                                           QMessageBox.StandardButton.No)
                
                if reply != QMessageBox.StandardButton.Yes:
                    return
                
            self.close_position.emit(symbol, percentage)
            logger.info(f"Closing {percentage}% of {symbol} position")
                
        except Exception as e:
            logger.error(f"Error in on_close_position for {symbol}: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to close position: {str(e)}")
            
    def clear_all_positions(self):
        """Clear all positions from the table"""
        try:
            # Disconnect all button signals first
            for row in range(self.table.rowCount()):
                for col in [7, 8]:  # Close button columns
                    widget = self.table.cellWidget(row, col)
                    if widget:
                        try:
                            widget.clicked.disconnect()
                        except:
                            pass
            
            self.table.setRowCount(0)
            self.positions.clear()
            self.update_total_pnl()
            
        except Exception as e:
            logger.error(f"Error clearing all positions: {e}", exc_info=True)
            
    def set_trade_confirmation(self, enabled: bool):
        """Set whether to show trade confirmation dialogs"""
        self.show_trade_confirmation = enabled
        logger.info(f"Position close confirmation dialogs: {'enabled' if enabled else 'disabled'}")
        
    def set_connection_status(self, connected: bool):
        """Update widget based on connection status"""
        self.refresh_btn.setEnabled(connected)
        
        if not connected:
            self.clear_all_positions()