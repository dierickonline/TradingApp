# config.py
"""Application configuration settings"""
import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    """Application configuration"""
    # Logging settings
    log_level: str = "INFO"
    log_file: str = "ib_app.log"
    log_dir: str = "logs"
    
    # IB Connection defaults
    default_host: str = "127.0.0.1"
    default_port: int = 7497  # TWS Paper Trading
    default_client_id: int = 1
    
    # UI Settings
    update_interval: int = 60000  # milliseconds
    
    def __post_init__(self):
        """Create log directory if it doesn't exist"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        self.log_file = os.path.join(self.log_dir, self.log_file)


# Global configuration instance
APP_CONFIG = AppConfig()