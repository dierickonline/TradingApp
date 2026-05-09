# gui/watchlist_widget.py
"""Watchlist widget for managing a list of ticker symbols"""
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QLineEdit, QGroupBox, QListWidget,
                            QListWidgetItem, QMenu, QMessageBox)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QAction

from config import APP_CONFIG
from core.persistence import atomic_write_json, safe_read_json

logger = logging.getLogger(__name__)


class WatchlistWidget(QGroupBox):
    """Widget for managing a watchlist of tickers"""
    
    ticker_selected = pyqtSignal(str)  # Emitted when a ticker is clicked
    
    def __init__(self, parent=None, title="Watchlist", filename="watchlist.json"):
        super().__init__(title, parent)
        self.filename = filename  # Allow different filenames for multiple watchlists
        self.init_ui()
        self.load_watchlist()
        
    def init_ui(self):
        """Initialize the watchlist UI"""
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
        
        # Add ticker input
        add_layout = QHBoxLayout()
        self.add_input = QLineEdit()
        self.add_input.setPlaceholderText("Add ticker...")
        self.add_input.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border: 2px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #2196F3;
            }
        """)
        self.add_input.returnPressed.connect(self.add_ticker)
        
        self.add_btn = QPushButton("Add")
        self.add_btn.setStyleSheet("""
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
        self.add_btn.clicked.connect(self.add_ticker)
        
        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
        """)
        self.clear_all_btn.clicked.connect(self.clear_watchlist)
        
        add_layout.addWidget(self.add_input)
        add_layout.addWidget(self.add_btn)
        add_layout.addWidget(self.clear_all_btn)
        layout.addLayout(add_layout)
        
        # Watchlist
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
                outline: none;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
                font-size: 14px;
                font-weight: normal;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976D2;
            }
        """)
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.list_widget)
        
    @pyqtSlot()
    def add_ticker(self):
        """Add a ticker to the watchlist"""
        ticker = self.add_input.text().strip().upper()
        if ticker and ticker not in self.get_tickers():
            self.list_widget.addItem(ticker)
            self.add_input.clear()
            self.save_watchlist()
            logger.info(f"Added {ticker} to watchlist")
            
    def remove_ticker(self, ticker):
        """Remove a ticker from the watchlist"""
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).text() == ticker:
                self.list_widget.takeItem(i)
                self.save_watchlist()
                logger.info(f"Removed {ticker} from watchlist")
                break
                
    def get_tickers(self):
        """Get all tickers in the watchlist"""
        return [self.list_widget.item(i).text() 
                for i in range(self.list_widget.count())]
                
    def on_item_clicked(self, item):
        """Handle item click"""
        ticker = item.text()
        self.ticker_selected.emit(ticker)
        
    def show_context_menu(self, position):
        """Show context menu for watchlist items"""
        item = self.list_widget.itemAt(position)
        if item:
            menu = QMenu()
            remove_action = menu.addAction("Remove")
            action = menu.exec(self.list_widget.mapToGlobal(position))
            
            if action == remove_action:
                self.remove_ticker(item.text())
                
    def clear_watchlist(self):
        """Clear all tickers from the watchlist after confirmation"""
        if self.list_widget.count() == 0:
            return
            
        reply = QMessageBox.question(
            self, 
            "Clear Watchlist", 
            f"Are you sure you want to remove all {self.list_widget.count()} tickers from the watchlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.list_widget.clear()
            self.save_watchlist()
            logger.info("Cleared entire watchlist")
                
    def save_watchlist(self):
        """Save watchlist to file atomically."""
        path = APP_CONFIG.watchlist_path(self.filename)
        try:
            atomic_write_json(path, self.get_tickers())
        except OSError as e:
            logger.error(f"Error saving watchlist to {path}: {e}")

    def load_watchlist(self):
        """Load watchlist from file with graceful fallback to empty list."""
        path = APP_CONFIG.watchlist_path(self.filename)
        tickers = safe_read_json(path, default=[])
        if not isinstance(tickers, list):
            logger.warning(f"Watchlist {path} is not a JSON list; ignoring")
            return
        for ticker in tickers:
            if isinstance(ticker, str):
                self.list_widget.addItem(ticker)
            
    def set_enabled(self, enabled: bool):
        """Enable or disable the watchlist widget"""
        self.add_input.setEnabled(enabled)
        self.add_btn.setEnabled(enabled)
        self.clear_all_btn.setEnabled(enabled)
        self.list_widget.setEnabled(enabled)