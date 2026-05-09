"""Atomic JSON persistence with optional schema versioning.

All JSON reads through this module fall back to defaults on a missing or
corrupt file (logged, not raised). All writes go through ``atomic_write_json``
which writes to a temp file and then ``os.replace``-s into place, so a crash
mid-write leaves the destination either at the old valid contents or the new
valid contents -- never partial.
"""
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_KEY = "__schema__"


def atomic_write_json(path: str, data: Any) -> None:
    """Write JSON atomically via temp file + os.replace.

    ``os.replace`` is atomic on the same filesystem on both Windows and POSIX.
    Errors during write surface as ``OSError`` so callers can decide whether to
    raise or swallow; the temp file is cleaned up on failure best-effort.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def safe_read_json(path: str, default: Any) -> Any:
    """Read JSON; on missing/corrupt file, log and return ``default``.

    Never raises. Caller-supplied default is returned by reference, so if it
    might be mutated, pass a fresh copy per call.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Could not read JSON from {path}: {e}; using defaults")
        return default


def load_versioned_settings(path: str, defaults: dict, current_version: int) -> dict:
    """Load a versioned dict-based settings file.

    Behavior:
      - Missing file: returns a copy of ``defaults`` stamped with ``current_version``.
      - Corrupt file: logs, returns defaults.
      - Stored ``__schema__`` newer than ``current_version``: logs a warning and
        loads anyway. Forward-compat is best-effort.
      - Stored ``__schema__`` older (or absent): logs and merges over defaults.
        Real migrations are the caller's responsibility; this helper only flags
        the mismatch and ensures the returned dict carries the current version.

    Returns ``defaults`` merged with the on-disk values (on-disk wins).
    """
    settings = dict(defaults)
    settings[SCHEMA_KEY] = current_version

    stored = safe_read_json(path, default=None)
    if stored is None:
        return settings
    if not isinstance(stored, dict):
        logger.warning(f"Settings at {path} not a JSON object; using defaults")
        return settings

    stored_version = stored.get(SCHEMA_KEY, 0)
    if stored_version > current_version:
        logger.warning(
            f"Settings at {path} have schema version {stored_version}, but "
            f"this app supports {current_version}. Loading anyway."
        )
    elif stored_version < current_version:
        logger.info(
            f"Settings at {path} have schema version {stored_version}; "
            f"migrating to {current_version}."
        )

    settings.update(stored)
    settings[SCHEMA_KEY] = current_version
    return settings
