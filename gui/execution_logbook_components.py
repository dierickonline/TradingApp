# gui/execution_logbook_components.py
"""UI components and views for execution logbook"""
import logging
from datetime import date
from typing import Dict
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QTableWidget, QTableWidgetItem,
                            QHeaderView, QDateEdit, QCalendarWidget,
                            QDialog, QDialogButtonBox, QTextEdit, QMenu,
                            QMessageBox)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QDate, QRect
from PyQt6.QtGui import QColor, QBrush, QFont, QTextCharFormat, QPainter, QPen

logger = logging.getLogger(__name__)


# ============================================================================
# Base Components
# ============================================================================

class CommentDialog(QDialog):
    """Dialog for adding/editing trade comments"""
    
    def __init__(self, exec_id: str, current_comment: str = "", parent=None):
        super().__init__(parent)
        self.exec_id = exec_id
        self.setWindowTitle("Trade Comment")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.init_ui(current_comment)
        
    def init_ui(self, current_comment):
        """Initialize the comment dialog UI"""
        layout = QVBoxLayout(self)
        
        # Label
        label = QLabel(f"Add/Edit comment for execution {self.exec_id}:")
        layout.addWidget(label)
        
        # Text edit
        self.comment_edit = QTextEdit()
        self.comment_edit.setPlainText(current_comment)
        self.comment_edit.setMaximumHeight(150)
        layout.addWidget(self.comment_edit)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_comment(self) -> str:
        """Get the entered comment"""
        return self.comment_edit.toPlainText().strip()


class ExecutionTable(QTableWidget):
    """Base table widget for execution data"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_table()
        
    def setup_table(self):
        """Setup table appearance"""
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        
        self.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
                gridline-color: #eee;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #f5f5f5;
                font-weight: bold;
                border: none;
                padding: 5px;
                border-bottom: 2px solid #ddd;
            }
        """)
        
    def add_colored_item(self, row: int, col: int, text: str, value: float):
        """Add item with color based on value"""
        item = QTableWidgetItem(text)
        if value >= 0:
            item.setForeground(QBrush(QColor(76, 175, 80)))  # Green
        else:
            item.setForeground(QBrush(QColor(244, 67, 54)))  # Red
        self.setItem(row, col, item)
        
    def clear_table(self):
        """Clear all table data"""
        self.setRowCount(0)


class DateRangeSelector(QWidget):
    """Widget for selecting date range"""
    
    date_range_changed = pyqtSignal(date, date)  # start_date, end_date
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """Initialize the date range selector"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("From:"))
        
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate().addDays(-30))
        self.from_date.dateChanged.connect(self.on_date_changed)
        layout.addWidget(self.from_date)
        
        layout.addWidget(QLabel("To:"))
        
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        self.to_date.dateChanged.connect(self.on_date_changed)
        layout.addWidget(self.to_date)
        
        layout.addStretch()
        
    def on_date_changed(self):
        """Handle date change"""
        start = self.from_date.date().toPyDate()
        end = self.to_date.date().toPyDate()
        self.date_range_changed.emit(start, end)
        
    def get_date_range(self) -> tuple:
        """Get current date range"""
        return (self.from_date.date().toPyDate(), 
                self.to_date.date().toPyDate())


class SummaryLabel(QLabel):
    """Label for displaying summary information"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QLabel {
                padding: 10px;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        self.setTextFormat(Qt.TextFormat.RichText)
        
    def update_daily_summary(self, date_str: str, trades: int, buy_value: float,
                           sell_value: float, commission: float, net_pnl: float):
        """Update with daily summary"""
        color = "green" if net_pnl >= 0 else "red"
        
        self.setText(
            f"<b>{date_str}</b> - "
            f"Trades: {trades} | "
            f"Buy Value: ${buy_value:,.2f} | "
            f"Sell Value: ${sell_value:,.2f} | "
            f"Commission: ${commission:.2f} | "
            f"Net P&L: <span style='color: {color};'>${net_pnl:,.2f}</span>"
        )
        
    def update_symbol_summary(self, date_range: str, total_symbols: int,
                            total_commission: float, total_pnl: float):
        """Update with symbol summary"""
        color = "green" if total_pnl >= 0 else "red"
        
        self.setText(
            f"<b>{date_range}</b><br>"
            f"Total Symbols: {total_symbols} | "
            f"Total Commission: ${total_commission:,.2f} | "
            f"Total Net P&L: <span style='color: {color};'>${total_pnl:,.2f}</span>"
        )
        
    def update_calendar_summary(self, total_days: int, profit_days: int,
                              loss_days: int, total_pnl: float):
        """Update with calendar summary"""
        color = "green" if total_pnl > 0 else "red"
        
        self.setText(
            f'<b>Trading Summary</b><br>'
            f'Total Days: {total_days} | Profit Days: {profit_days} | Loss Days: {loss_days}<br>'
            f'Total P&L: <span style="color: {color};">${total_pnl:,.2f}</span>'
        )


class CustomCalendarWidget(QCalendarWidget):
    """Custom calendar widget that displays P&L values in cells"""
    
    def __init__(self):
        super().__init__()
        self.trade_data = {}
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.setGridVisible(True)
        self.setMinimumSize(600, 400)
        
    def paintCell(self, painter, rect, date):
        """Custom paint method to show P&L values in cells"""
        painter.save()
        
        # Check if this date is in the current displayed month
        current_month = self.monthShown()
        current_year = self.yearShown()
        
        if date.month() != current_month or date.year() != current_year:
            # This date is from previous/next month - paint it as empty
            painter.fillRect(rect, QColor(245, 245, 245))
            painter.setPen(QColor(200, 200, 200))
            painter.drawRect(rect)
            painter.restore()
            return
        
        # Get the date
        py_date = date.toPyDate()
        
        # Determine background color based on P&L
        if py_date in self.trade_data:
            net_value = self.trade_data[py_date]['net_pnl']
            if net_value > 0:
                bg_color = QColor(144, 238, 144)  # Light green
                text_color = QColor(0, 100, 0)  # Dark green
            elif net_value < 0:
                bg_color = QColor(255, 182, 193)  # Light red
                text_color = QColor(139, 0, 0)  # Dark red
            else:
                bg_color = QColor(255, 255, 224)  # Light yellow
                text_color = QColor(100, 100, 0)  # Dark yellow
        else:
            bg_color = Qt.GlobalColor.white
            text_color = Qt.GlobalColor.black
            net_value = None
        
        # Fill background
        painter.fillRect(rect, bg_color)
        
        # Draw border
        painter.setPen(QColor(200, 200, 200))
        painter.drawRect(rect)
        
        # Draw date in top-left corner
        date_font = QFont()
        date_font.setPointSize(9)
        painter.setFont(date_font)
        painter.setPen(Qt.GlobalColor.black)
        
        date_rect = QRect(rect.x() + 3, rect.y() + 2, 30, 15)
        painter.drawText(date_rect, Qt.AlignmentFlag.AlignLeft, str(date.day()))
        
        # Draw P&L value in center if we have data
        if net_value is not None:
            value_font = QFont()
            value_font.setPointSize(10)
            value_font.setBold(True)
            painter.setFont(value_font)
            painter.setPen(text_color)
            
            # Format value
            if abs(net_value) >= 1000:
                value_text = f"${net_value/1000:.1f}k"
            else:
                value_text = f"${net_value:.0f}"
            
            # Draw text centered in cell
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, value_text)
        
        # Highlight selected date
        if date == self.selectedDate():
            painter.setPen(QPen(QColor(0, 0, 255), 2))
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
        
        painter.restore()
    
    def mousePressEvent(self, event):
        """Handle mouse clicks - only process clicks on current month dates"""
        clicked_date = self.dateAt(event.pos())
        current_month = self.monthShown()
        current_year = self.yearShown()
        
        if clicked_date.month() == current_month and clicked_date.year() == current_year:
            super().mousePressEvent(event)
        else:
            event.ignore()
            
    def update_trade_data(self, trade_data: dict):
        """Update the trade data and refresh display"""
        self.trade_data = trade_data
        self.update()


# ============================================================================
# View Widgets
# ============================================================================

class DailyExecutionsView(QWidget):
    """View for daily execution details"""
    
    comment_updated = pyqtSignal(str, str)  # exec_id, comment
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.executions_data = {}
        self.comments = {}
        self.init_ui()
        
    def init_ui(self):
        """Initialize the daily executions UI"""
        layout = QVBoxLayout(self)
        
        # Date filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Date:"))
        
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self.update_display)
        filter_layout.addWidget(self.date_edit)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # Executions table
        self.table = ExecutionTable()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Time", "Symbol", "Side", "Qty", "Price", "Value", 
            "Commission", "Net", "Exchange", "Comment"
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, header.ResizeMode.Stretch)  # Comment column
        
        # Enable context menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.table)
        
        # Summary
        self.summary_label = SummaryLabel()
        self.summary_label.setText("Select a date to view executions")
        layout.addWidget(self.summary_label)
        
    def set_data(self, daily_data: Dict, comments: Dict):
        """Set the executions data and comments"""
        self.executions_data = daily_data
        self.comments = comments
        self.update_display()
        
    def update_display(self):
        """Update the display for the selected date"""
        selected_date = self.date_edit.date().toPyDate()
        
        self.table.clear_table()
        
        if selected_date not in self.executions_data:
            self.summary_label.setText(
                f"No executions on {selected_date.strftime('%B %d, %Y')}"
            )
            return
            
        data = self.executions_data[selected_date]
        trades = data.get('trades', [])
        
        # Populate table
        for trade in trades:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Store exec_id in first item
            time_item = QTableWidgetItem(trade['time'][9:])  # HH:MM:SS
            time_item.setData(Qt.ItemDataRole.UserRole, trade.get('exec_id'))
            self.table.setItem(row, 0, time_item)
            
            # Symbol
            self.table.setItem(row, 1, QTableWidgetItem(trade['symbol']))
            
            # Side with color
            side_item = QTableWidgetItem(trade['side'])
            if trade['side'] == 'BOT':
                side_item.setForeground(QBrush(QColor(76, 175, 80)))
            else:
                side_item.setForeground(QBrush(QColor(244, 67, 54)))
            self.table.setItem(row, 2, side_item)
            
            # Other columns
            self.table.setItem(row, 3, QTableWidgetItem(f"{trade['shares']:.0f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"${trade['price']:.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"${trade['value']:.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"${trade['commission']:.2f}"))
            
            # Net value
            net = trade['value'] if trade['side'] == 'BOT' else -trade['value']
            net -= trade['commission']
            self.table.add_colored_item(row, 7, f"${net:.2f}", net)
            
            # Exchange
            self.table.setItem(row, 8, QTableWidgetItem(trade.get('exchange', '')))
            
            # Comment
            exec_id = trade.get('exec_id')
            comment = self.comments.get(exec_id, '')
            comment_item = QTableWidgetItem(comment)
            comment_item.setToolTip("Right-click to add/edit comment")
            self.table.setItem(row, 9, comment_item)
            
        # Update summary
        self.summary_label.update_daily_summary(
            selected_date.strftime('%B %d, %Y'),
            len(trades),
            data['buy_value'],
            data['sell_value'],
            data['commission'],
            data['net_pnl']
        )
        
    def show_context_menu(self, position):
        """Show context menu for trade actions"""
        item = self.table.itemAt(position)
        if not item:
            return
            
        row = item.row()
        exec_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not exec_id:
            return
            
        menu = QMenu()
        comment_action = menu.addAction("Add/Edit Comment")
        
        action = menu.exec(self.table.mapToGlobal(position))
        
        if action == comment_action:
            self.edit_comment(exec_id, row)
            
    def edit_comment(self, exec_id: str, row: int):
        """Open dialog to edit comment for a trade"""
        current_comment = self.comments.get(exec_id, '')
        
        dialog = CommentDialog(exec_id, current_comment, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            new_comment = dialog.get_comment()
            
            # Update local data
            self.comments[exec_id] = new_comment
            
            # Update table
            self.table.item(row, 9).setText(new_comment)
            
            # Emit signal for database update
            self.comment_updated.emit(exec_id, new_comment)


class SymbolAggregationView(QWidget):
    """View for P&L aggregated by symbol"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.symbol_data_callback = None
        self.init_ui()
        
    def init_ui(self):
        """Initialize the symbol aggregation UI"""
        layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("P&L by Symbol")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Date range filter
        self.date_selector = DateRangeSelector()
        self.date_selector.date_range_changed.connect(self.on_date_range_changed)
        header_layout.addWidget(self.date_selector)
        
        layout.addLayout(header_layout)
        
        # Symbol table
        self.table = ExecutionTable()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "Total Trades", "Total Shares", "Buy Value", 
            "Sell Value", "Commission", "Net P&L"
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(header.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.table)
        
        # Summary
        self.summary_label = SummaryLabel()
        layout.addWidget(self.summary_label)
        
    def set_data_callback(self, callback):
        """Set callback for getting filtered data"""
        self.symbol_data_callback = callback
        self.update_display()
        
    def on_date_range_changed(self, start_date: date, end_date: date):
        """Handle date range change"""
        self.update_display()
        
    def update_display(self):
        """Update the symbol aggregation display"""
        if not self.symbol_data_callback:
            return
            
        start_date, end_date = self.date_selector.get_date_range()
        symbol_data = self.symbol_data_callback(start_date, end_date)
        
        self.table.clear_table()
        
        total_pnl = 0
        total_commission = 0
        
        for symbol, data in sorted(symbol_data.items()):
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Add data
            self.table.setItem(row, 0, QTableWidgetItem(symbol))
            self.table.setItem(row, 1, QTableWidgetItem(str(data['trade_count'])))
            self.table.setItem(row, 2, QTableWidgetItem(f"{data['total_shares']:.0f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"${data['buy_value']:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"${data['sell_value']:.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"${data['commission']:.2f}"))
            
            # Net P&L with color
            net_pnl = data['net_pnl']
            self.table.add_colored_item(row, 6, f"${net_pnl:.2f}", net_pnl)
            
            total_pnl += net_pnl
            total_commission += data['commission']
            
        # Update summary
        date_range = f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}"
        self.summary_label.update_symbol_summary(
            date_range,
            len(symbol_data),
            total_commission,
            total_pnl
        )


class CalendarView(QWidget):
    """View for calendar P&L display"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.daily_data = {}
        self.init_ui()
        
    def init_ui(self):
        """Initialize the calendar view UI"""
        layout = QVBoxLayout(self)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.prev_month_btn = QPushButton("◀ Previous Month")
        self.prev_month_btn.clicked.connect(self.go_to_previous_month)
        nav_layout.addWidget(self.prev_month_btn)
        
        self.next_month_btn = QPushButton("Next Month ▶")
        self.next_month_btn.clicked.connect(self.go_to_next_month)
        nav_layout.addWidget(self.next_month_btn)
        
        nav_layout.addStretch()
        layout.addLayout(nav_layout)
        
        # Calendar
        self.calendar = CustomCalendarWidget()
        self.calendar.clicked.connect(self.on_date_selected)
        layout.addWidget(self.calendar)
        
        # Info label
        self.info_label = SummaryLabel()
        self.info_label.setText("Click on a date to see details")
        layout.addWidget(self.info_label)
        
    def set_data(self, daily_data: Dict):
        """Set the daily P&L data"""
        self.daily_data = daily_data
        self.calendar.update_trade_data(daily_data)
        self.update_summary()
        
    def update_summary(self):
        """Update the summary statistics"""
        if not self.daily_data:
            return
            
        total_days = len(self.daily_data)
        profit_days = sum(1 for data in self.daily_data.values() if data['net_pnl'] > 0)
        loss_days = sum(1 for data in self.daily_data.values() if data['net_pnl'] < 0)
        total_pnl = sum(data['net_pnl'] for data in self.daily_data.values())
        
        self.info_label.update_calendar_summary(
            total_days, profit_days, loss_days, total_pnl
        )
        
    def on_date_selected(self, qdate):
        """Handle date selection"""
        selected_date = date(qdate.year(), qdate.month(), qdate.day())
        
        if selected_date in self.daily_data:
            data = self.daily_data[selected_date]
            net_value = data['net_pnl']
            
            if net_value > 0:
                status = "Profit"
                color = "green"
            elif net_value < 0:
                status = "Loss"
                color = "red"
            else:
                status = "Break Even"
                color = "black"
            
            trade_count = len(data.get('trades', []))
            
            self.info_label.setText(
                f'<b>{selected_date.strftime("%B %d, %Y")}</b><br>'
                f'Net P&L: <span style="color: {color};">${net_value:.2f}</span> ({status})<br>'
                f'Trades: {trade_count} | '
                f'Buy Value: ${data["buy_value"]:,.2f} | '
                f'Sell Value: ${data["sell_value"]:,.2f} | '
                f'Commission: ${data["commission"]:.2f}'
            )
        else:
            self.info_label.setText(
                f'<b>{selected_date.strftime("%B %d, %Y")}</b><br>'
                f'No trades recorded for this date'
            )
            
    def go_to_previous_month(self):
        """Navigate to previous month"""
        current = self.calendar.selectedDate()
        new_date = current.addMonths(-1)
        self.calendar.setSelectedDate(new_date)
        
    def go_to_next_month(self):
        """Navigate to next month"""
        current = self.calendar.selectedDate()
        new_date = current.addMonths(1)
        self.calendar.setSelectedDate(new_date)