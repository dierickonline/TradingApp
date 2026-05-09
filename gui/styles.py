"""Central design tokens and reusable QSS strings.

This module is the single source of truth for the app's color palette and
the most-frequently-duplicated stylesheet snippets. New widgets should
import from here rather than redefining colors inline; existing widgets are
being migrated incrementally as they're touched.
"""


# Color palette ----------------------------------------------------------------

# Primary action / link colors (Material-ish blue ramp).
COLOR_PRIMARY = "#2196F3"
COLOR_PRIMARY_HOVER = "#1976D2"
COLOR_PRIMARY_PRESSED = "#1565C0"

# Semantic colors used for P&L and status indicators.
COLOR_SUCCESS = "#4CAF50"
COLOR_SUCCESS_HOVER = "#45a049"
COLOR_SUCCESS_PRESSED = "#3d8b40"

COLOR_DANGER = "#f44336"
COLOR_DANGER_HOVER = "#da190b"

COLOR_WARNING = "#FF9800"
COLOR_WARNING_HOVER = "#F57C00"

# P&L cell foreground colors. Keep the integer RGB tuples around because
# QColor(r, g, b) is the form used in QTableWidgetItem styling.
RGB_PNL_POSITIVE = (76, 175, 80)
RGB_PNL_NEGATIVE = (244, 67, 54)

# Neutral surfaces and borders.
COLOR_SURFACE = "#FCFCFC"
COLOR_BORDER = "#ddd"
COLOR_TEXT = "#333"
COLOR_TEXT_MUTED = "#666"
COLOR_DISABLED_BG = "#cccccc"
COLOR_DISABLED_FG = "#666666"


# Reusable QSS snippets --------------------------------------------------------

# Canonical QGroupBox frame used by most panels (connection, positions,
# watchlist, risk, etc.). Matches the look the app already shipped with.
GROUP_BOX_QSS = f"""
    QGroupBox {{
        background-color: {COLOR_SURFACE};
        border: 2px solid {COLOR_BORDER};
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 8px;
        font-weight: bold;
        font-size: 12px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 15px;
        padding: 0 8px 0 8px;
        color: {COLOR_TEXT};
        font-weight: bold;
        font-size: 13px;
    }}
"""


def primary_button_qss() -> str:
    """Stylesheet for the primary call-to-action buttons (Connect, Add, etc.)."""
    return f"""
        QPushButton {{
            background-color: {COLOR_PRIMARY};
            color: white;
            border: none;
            border-radius: 4px;
            padding: 5px 15px;
            font-weight: bold;
            font-size: 12px;
        }}
        QPushButton:hover {{
            background-color: {COLOR_PRIMARY_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {COLOR_PRIMARY_PRESSED};
        }}
        QPushButton:disabled {{
            background-color: {COLOR_DISABLED_BG};
            color: {COLOR_DISABLED_FG};
        }}
    """


def success_button_qss() -> str:
    """Stylesheet for affirmative actions (Save, Connect-confirmed)."""
    return f"""
        QPushButton {{
            background-color: {COLOR_SUCCESS};
            color: white;
            border: none;
            border-radius: 5px;
            font-weight: bold;
            font-size: 12px;
        }}
        QPushButton:hover {{
            background-color: {COLOR_SUCCESS_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {COLOR_SUCCESS_PRESSED};
        }}
        QPushButton:disabled {{
            background-color: {COLOR_DISABLED_BG};
            color: {COLOR_DISABLED_FG};
        }}
    """


def danger_button_qss() -> str:
    """Stylesheet for destructive actions (Disconnect, Close 100%)."""
    return f"""
        QPushButton {{
            background-color: {COLOR_DANGER};
            color: white;
            border: none;
            border-radius: 5px;
            font-weight: bold;
            font-size: 12px;
        }}
        QPushButton:hover {{
            background-color: {COLOR_DANGER_HOVER};
        }}
        QPushButton:disabled {{
            background-color: {COLOR_DISABLED_BG};
            color: {COLOR_DISABLED_FG};
        }}
    """
