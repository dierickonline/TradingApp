# core/app_settings.py
"""Persistence for top-level app settings (e.g. market data type).

Lives next to risk_parameters.json under the data/ folder. Always returns a
dict; never raises. Missing or corrupt file => defaults.
"""
import logging

from config import APP_CONFIG
from core.persistence import atomic_write_json, load_versioned_settings

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _defaults() -> dict:
    return {
        "market_data_type": APP_CONFIG.default_market_data_type,
    }


def load_app_settings() -> dict:
    """Load persisted app settings, merging over defaults."""
    return load_versioned_settings(
        APP_CONFIG.app_settings_path, _defaults(), SCHEMA_VERSION
    )


def save_app_settings(settings: dict) -> None:
    """Persist app settings to JSON. Errors are logged, not raised."""
    payload = dict(settings)
    payload.setdefault("__schema__", SCHEMA_VERSION)
    path = APP_CONFIG.app_settings_path
    try:
        atomic_write_json(path, payload)
        logger.info(f"App settings saved to {path}: {payload}")
    except OSError as e:
        logger.error(f"Could not save app settings to {path}: {e}")
