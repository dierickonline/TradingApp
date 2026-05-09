# config.py
"""Application configuration settings"""
import os
from dataclasses import dataclass


# IB API marketDataType values
MARKET_DATA_LIVE = 1
MARKET_DATA_DELAYED = 3


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
    # Market data: 1=Live (subscription required), 3=Delayed (free, 15-20 min)
    default_market_data_type: int = MARKET_DATA_DELAYED

    # UI Settings
    update_interval: int = 60000  # milliseconds

    # Persisted user data directory
    app_settings_dir: str = "data"
    app_settings_file: str = "app_settings.json"
    risk_parameters_file: str = "risk_parameters.json"

    def __post_init__(self):
        """Create required directories and resolve absolute paths"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        self.log_file = os.path.join(self.log_dir, self.log_file)

        if not os.path.exists(self.app_settings_dir):
            os.makedirs(self.app_settings_dir)
        self.app_settings_path = os.path.join(self.app_settings_dir, self.app_settings_file)
        self.risk_parameters_path = os.path.join(self.app_settings_dir, self.risk_parameters_file)

    def watchlist_path(self, filename: str) -> str:
        """Resolve a watchlist filename to its absolute path under the data directory."""
        return os.path.join(self.app_settings_dir, filename)


# Global configuration instance
APP_CONFIG = AppConfig()