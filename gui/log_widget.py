# gui/log_widget.py
"""Log widget for displaying application logs in the GUI"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, 
                            QPushButton, QHBoxLayout, QComboBox, QLabel)
from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtGui import QTextCharFormat, QColor, QFont
import logging


class LogWidget(QWidget):
    """Widget for displaying log messages with filtering capabilities"""
    
    # Color scheme for different log levels
    LEVEL_COLORS = {
        'DEBUG': QColor(128, 128, 128),      # Gray
        'INFO': QColor(0, 0, 0),             # Black
        'WARNING': QColor(255, 140, 0),      # Orange
        'ERROR': QColor(255, 0, 0),          # Red
        'CRITICAL': QColor(139, 0, 0)        # Dark Red
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.log_level_filter = logging.WARNING
        
    def init_ui(self):
        """Initialize the log widget UI"""
        layout = QVBoxLayout(self)
        
        # Controls
        controls_layout = QHBoxLayout()
        
        # Level filter
        controls_layout.addWidget(QLabel("Filter:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        self.level_combo.setCurrentText('INFO')
        self.level_combo.currentTextChanged.connect(self.on_level_filter_changed)
        controls_layout.addWidget(self.level_combo)
        
        controls_layout.addStretch()
        
        # Clear button
        self.clear_btn = QPushButton("Clear Logs")
        self.clear_btn.clicked.connect(self.clear_logs)
        controls_layout.addWidget(self.clear_btn)
        
        layout.addLayout(controls_layout)
        
        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 9))
        self.log_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.log_display.setStyleSheet("""                     
            QTextEdit {
                border: 2px solid #ddd;
                border-radius: 4px;
                padding: 4px;
                background-color: #ffffff;
            }
        """)
        
        layout.addWidget(self.log_display)
        
    @pyqtSlot(str, str)
    def add_log_message(self, message, level):
        """Add a log message to the display"""
        # Check if message passes the filter
        level_value = getattr(logging, level, logging.INFO)
        if level_value < self.log_level_filter:
            return
            
        # Move cursor to end
        cursor = self.log_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_display.setTextCursor(cursor)
        
        # Set format based on level
        format = QTextCharFormat()
        format.setForeground(self.LEVEL_COLORS.get(level, QColor(0, 0, 0)))
        
        # Insert the message
        cursor.insertText(message + '\n', format)
        
        # Auto-scroll to bottom
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def clear_logs(self):
        """Clear the log display"""
        self.log_display.clear()
        
    def on_level_filter_changed(self, level_text):
        """Handle log level filter changes"""
        self.log_level_filter = getattr(logging, level_text, logging.INFO)
        # Could re-filter existing logs here if we stored them

