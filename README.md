# Interactive Brokers Trading Platform

A professional desktop trading application built with **Python** and **PyQt6** that interfaces with the **Interactive Brokers API** for real-time order execution, position management, and trade analytics.

This project demonstrates proficiency in **event-driven architecture**, **multithreaded desktop application design**, **financial API integration**, and **production-quality software engineering**.

---

## Key Features

**Order Execution**
- Bracket orders with synchronized entry, stop-loss, and take-profit legs
- Support for Limit, Stop, and Market order types
- Atomic order submission with deferred transmit to prevent partial fills

**Position Management**
- Real-time P&L tracking (unrealized, realized, and total)
- Partial and full position closing with automatic child-order cancellation
- Live market data subscriptions per open position

**Risk Management**
- Configurable risk/reward ratios and max risk-per-trade percentage
- ATR-based (Average True Range) volatility stop calculation from historical data
- Automatic position sizing based on account equity and risk parameters

**Execution Logbook**
- SQLite-backed trade journal with commission tracking
- Daily and per-symbol P&L aggregation with win/loss statistics
- Searchable execution history with user-annotated trade comments

**Market Data**
- Real-time bid/ask/last/volume tick streaming
- Historical OHLCV bar retrieval with technical indicator computation
- Multi-ticker watchlist management with persistent storage

---

## Architecture

```
app.py                         Entry point & global exception handler
config.py                      Centralized application configuration
logging_config.py              Rotating file + Qt signal log handler

core/                          Business logic layer (no UI dependencies)
  ib_app.py                    IBApp — EClient/EWrapper with Qt signal bridge
  order_manager.py             Bracket order creation, submission, lifecycle
  position_manager.py          Position tracking, P&L, order association
  market_data_manager.py       Tick subscription management
  historical_data_manager.py   Historical bars & ATR calculation
  trader_logic.py              TradingCalculator (static math) & TraderModel (state)
  execution_logbook_logic.py   ExecutionDatabase, ExecutionProcessor, DataModel

gui/                           Presentation layer (PyQt6 widgets)
  main_window.py               Application orchestrator — wires managers to widgets
  connection_widget.py         IB Gateway/TWS connection controls
  trader_widget.py             Trading interface with price inputs & size calculator
  positions_widget.py          Open positions table with close actions
  watchlist_widget.py          Persistent multi-tab watchlist
  risk_management_widget.py    Risk parameter configuration panel
  execution_logbook_widget.py  Logbook UI with daily/symbol/calendar views
  execution_logbook_components.py  Detail views and statistics tables
  trader_components.py         Reusable UI building blocks
  log_widget.py                Filterable application log display

data/                          Persistent storage
  executions.db                SQLite — executions, commissions, comments
  risk_parameters.json         Risk/reward and max risk settings
  watchlist*.json              Saved ticker lists
```

### Design Patterns

| Pattern | Where | Why |
|---------|-------|-----|
| **Signal-driven (Observer)** | Qt signals bridge IB API thread to UI | Thread-safe event propagation without polling |
| **Manager pattern** | `OrderManager`, `PositionManager`, `MarketDataManager` | Single-responsibility encapsulation of each domain |
| **Model-View separation** | `TraderModel` / `ExecutionDataModel` decoupled from widgets | Business logic testable independently of UI |
| **Deferred transmit** | Bracket orders set `transmit=False` until final leg | Guarantees atomic multi-leg order submission |
| **Thread isolation** | Execution fetching runs in `QThread` with handler swap | Long IB API calls don't freeze the UI |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.8+ |
| GUI Framework | PyQt6 (Fusion style) |
| Broker API | Interactive Brokers IBAPI |
| Database | SQLite3 |
| Data Processing | Pandas, NumPy |
| Logging | Python `logging` with rotating file handler + custom Qt bridge |

---

## Getting Started

### Prerequisites

- **Python 3.8+**
- **Interactive Brokers TWS or IB Gateway** running locally
  - Paper trading port: `7497` (default)
  - Live trading port: `7496`

### Installation

```bash
git clone https://github.com/<your-username>/IB-trading-app.git
cd IB-trading-app
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows
pip install PyQt6 ibapi pandas numpy python-dateutil
```

### Run

```bash
python app.py
```

The application connects to IB Gateway/TWS on `127.0.0.1:7497` by default. Host, port, and client ID are configurable from the connection panel.

---

## Screenshots

<!-- Add screenshots of the application here -->
<!-- ![Trading Interface](docs/screenshots/trader.png) -->
<!-- ![Position Manager](docs/screenshots/positions.png) -->
<!-- ![Execution Logbook](docs/screenshots/logbook.png) -->

---

## Technical Highlights

- **Thread-safe IB integration** — The IB API runs on its own thread; all UI updates flow through Qt signals, eliminating race conditions and UI freezes.
- **Atomic bracket orders** — Entry, stop-loss, and take-profit orders are submitted as a single unit using IB's `transmit` flag to prevent partial execution.
- **Robust order ID management** — Order IDs are offset by 100 from IB's `nextValidId` to avoid conflicts, with a tracked history window to prevent reuse.
- **Smart subscription management** — Market data subscriptions are reference-counted across the trader view and position tracker to avoid duplicates while keeping all active positions updated.
- **Global exception handling** — Uncaught exceptions are logged and surfaced to the user via dialog rather than silently crashing.
- **Structured logging** — Rotating file logs (10 MB, 5 backups) with a custom `QtLogHandler` that bridges Python's `logging` module to the in-app log viewer with level filtering.

---

## License

This project is for portfolio and educational purposes. It is not financial advice. Use at your own risk.
