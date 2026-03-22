# logging_config.py
"""Centralized logging configuration"""
import logging
import logging.handlers
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal
from config import APP_CONFIG


class QtLogHandler(logging.Handler, QObject):
    """Custom logging handler that emits Qt signals for GUI updates"""
    log_message = pyqtSignal(str, str)  # message, level
    
    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self._is_closed = False
        
    def emit(self, record):
        if not self._is_closed:
            try:
                msg = self.format(record)
                level = record.levelname
                self.log_message.emit(msg, level)
            except RuntimeError:
                # Qt object has been deleted
                self._is_closed = True
    
    def close(self):
        """Properly close the handler"""
        self._is_closed = True
        super().close()
    
    def flush(self):
        """Override flush to prevent Qt errors"""
        if not self._is_closed:
            super().flush()


def setup_logging():
    """Setup logging with both file and Qt handler"""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, APP_CONFIG.log_level))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        APP_CONFIG.log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)
    
    # Qt handler (to be connected to GUI)
    qt_handler = QtLogHandler()
    qt_handler.setFormatter(simple_formatter)
    logger.addHandler(qt_handler)
    
    return qt_handler