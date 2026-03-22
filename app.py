# main.py
import sys
import logging
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from gui.main_window import MainWindow
from logging_config import setup_logging

# Setup logging before creating any other objects
qt_log_handler = setup_logging()
logger = logging.getLogger(__name__)


def handle_exception(exc_type, exc_value, exc_traceback):
    """Handle uncaught exceptions"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
        
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    
    # Format the error message
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    # Show error dialog
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle("Critical Error")
    msg_box.setText("An unexpected error occurred:")
    msg_box.setDetailedText(error_msg)
    msg_box.exec()


def main():
    # Install exception handler
    sys.excepthook = handle_exception
    
    logger.info("Starting IB PyQt6 Application")
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Create main window
    try:
        window = MainWindow(qt_log_handler)
        window.show()
        
        logger.info("Application window displayed")
        
        sys.exit(app.exec())
        
    except Exception as e:
        logger.critical(f"Failed to create main window: {e}", exc_info=True)
        QMessageBox.critical(None, "Startup Error", 
                           f"Failed to start application:\n{str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()