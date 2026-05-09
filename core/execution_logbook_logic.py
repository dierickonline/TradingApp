# core/execution_logbook_logic.py
"""All business logic for execution tracking and P&L calculations"""
import logging
import sqlite3
import os
import threading
from datetime import datetime, date
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal, QThread, Qt
from ibapi.execution import ExecutionFilter

from core.ib_app import REQ_CATEGORY_EXECUTION

logger = logging.getLogger(__name__)


class ExecutionDatabase:
    """Handles SQLite storage for execution data"""
    
    def __init__(self, db_path: str = "data/executions.db"):
        self.db_path = db_path
        self.ensure_database()
        
    def ensure_database(self):
        """Create database and tables if they don't exist"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Executions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    exec_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    time TEXT NOT NULL,
                    side TEXT NOT NULL,
                    shares REAL NOT NULL,
                    price REAL NOT NULL,
                    avg_price REAL,
                    order_id INTEGER,
                    account TEXT,
                    exchange TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Commissions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS commissions (
                    exec_id TEXT PRIMARY KEY,
                    commission REAL NOT NULL,
                    currency TEXT,
                    realized_pnl REAL,
                    FOREIGN KEY (exec_id) REFERENCES executions(exec_id)
                )
            """)
            
            # Comments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_comments (
                    exec_id TEXT PRIMARY KEY,
                    comment TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (exec_id) REFERENCES executions(exec_id)
                )
            """)
            
            # Create indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_time ON executions(time)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_symbol ON executions(symbol)")
            
            conn.commit()
            
    def store_executions(self, executions: Dict, commissions: Dict):
        """Store executions and commissions in the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Store executions
            for exec_id, exec_data in executions.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO executions 
                    (exec_id, symbol, time, side, shares, price, avg_price, order_id, account, exchange)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    exec_id,
                    exec_data['symbol'],
                    exec_data['time'],
                    exec_data['side'],
                    exec_data['shares'],
                    exec_data['price'],
                    exec_data.get('avgPrice'),
                    exec_data.get('orderId'),
                    exec_data.get('account'),
                    exec_data.get('exchange')
                ))
            
            # Store commissions
            for exec_id, comm_data in commissions.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO commissions
                    (exec_id, commission, currency, realized_pnl)
                    VALUES (?, ?, ?, ?)
                """, (
                    exec_id,
                    comm_data['commission'],
                    comm_data.get('currency'),
                    comm_data.get('realizedPNL')
                ))
            
            conn.commit()
            logger.info(f"Stored {len(executions)} executions and {len(commissions)} commissions")
            
    def get_all_executions(self) -> Tuple[Dict, Dict, Dict]:
        """Get all executions, commissions, and comments from the database"""
        executions = {}
        commissions = {}
        comments = {}
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get executions
            cursor.execute("SELECT * FROM executions ORDER BY time DESC")
            for row in cursor.fetchall():
                exec_id = row['exec_id']
                executions[exec_id] = {
                    'symbol': row['symbol'],
                    'time': row['time'],
                    'side': row['side'],
                    'shares': row['shares'],
                    'price': row['price'],
                    'avgPrice': row['avg_price'],
                    'orderId': row['order_id'],
                    'account': row['account'],
                    'exchange': row['exchange']
                }
            
            # Get commissions
            cursor.execute("SELECT * FROM commissions")
            for row in cursor.fetchall():
                exec_id = row['exec_id']
                commissions[exec_id] = {
                    'commission': row['commission'],
                    'currency': row['currency'],
                    'realizedPNL': row['realized_pnl']
                }
                
            # Get comments
            cursor.execute("SELECT * FROM trade_comments")
            for row in cursor.fetchall():
                comments[row['exec_id']] = row['comment']
        
        logger.info(f"Loaded {len(executions)} executions, {len(commissions)} commissions, and {len(comments)} comments from database")
        return executions, commissions, comments
        
    def save_comment(self, exec_id: str, comment: str):
        """Save or update a comment for an execution"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if comment:
                cursor.execute("""
                    INSERT OR REPLACE INTO trade_comments (exec_id, comment, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (exec_id, comment))
            else:
                # Delete comment if empty
                cursor.execute("DELETE FROM trade_comments WHERE exec_id = ?", (exec_id,))
                
            conn.commit()
            logger.info(f"Updated comment for execution {exec_id}")
            
    def get_latest_execution_time(self) -> Optional[str]:
        """Get the timestamp of the most recent execution"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(time) FROM executions")
            result = cursor.fetchone()
            return result[0] if result and result[0] else None
            
    def clear_today_data(self):
        """Clear today's data before refreshing from IB"""
        today = datetime.now().strftime("%Y%m%d")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Delete today's executions
            cursor.execute("DELETE FROM executions WHERE time LIKE ?", (f"{today}%",))
            deleted_count = cursor.rowcount
            
            # Delete orphaned commissions
            cursor.execute("""
                DELETE FROM commissions 
                WHERE exec_id NOT IN (SELECT exec_id FROM executions)
            """)
            
            conn.commit()
            logger.info(f"Cleared {deleted_count} executions from today before refresh")


class ExecutionProcessor:
    """Processes execution data into daily and symbol aggregations"""
    
    @staticmethod
    def process_executions(executions: Dict, commissions: Dict) -> Tuple[Dict, Dict]:
        """Process executions into daily and symbol aggregations"""
        daily_data = {}
        symbol_data = defaultdict(lambda: {
            'buy_value': 0,
            'sell_value': 0,
            'commission': 0,
            'trade_count': 0,
            'total_shares': 0,
            'trades': []
        })
        
        # Process by day
        daily_trades = defaultdict(lambda: {
            'buy_value': 0,
            'sell_value': 0,
            'commission': 0,
            'trades': []
        })
        
        for exec_id, exec in executions.items():
            # Parse execution date
            try:
                exec_datetime = datetime.strptime(exec['time'], "%Y%m%d %H:%M:%S")
                exec_date = exec_datetime.date()
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Could not parse date {exec.get('time')!r}: {e}")
                continue
                
            # Get commission
            commission = 0
            if exec_id in commissions:
                commission = commissions[exec_id]['commission']
                
            value = exec['shares'] * exec['price']
            symbol = exec['symbol']
            
            # Create trade record
            trade = {
                'exec_id': exec_id,
                'symbol': symbol,
                'side': exec['side'],
                'shares': exec['shares'],
                'price': exec['price'],
                'value': value,
                'commission': commission,
                'time': exec['time'],
                'exchange': exec.get('exchange', '')
            }
            
            # Add to daily data
            if exec['side'] == 'BOT':
                daily_trades[exec_date]['buy_value'] += value
            else:
                daily_trades[exec_date]['sell_value'] += value
                
            daily_trades[exec_date]['commission'] += commission
            daily_trades[exec_date]['trades'].append(trade)
            
            # Add to symbol data
            if exec['side'] == 'BOT':
                symbol_data[symbol]['buy_value'] += value
            else:
                symbol_data[symbol]['sell_value'] += value
                
            symbol_data[symbol]['commission'] += commission
            symbol_data[symbol]['trade_count'] += 1
            symbol_data[symbol]['total_shares'] += exec['shares']
            symbol_data[symbol]['trades'].append(trade)
            
        # Calculate net P&L for daily data
        for day, data in daily_trades.items():
            net_pnl = data['sell_value'] - data['buy_value'] - data['commission']
            daily_data[day] = {
                'net_pnl': net_pnl,
                'buy_value': data['buy_value'],
                'sell_value': data['sell_value'],
                'commission': data['commission'],
                'trades': sorted(data['trades'], key=lambda x: x['time'])
            }
            
        # Calculate net P&L for symbol data
        for symbol in symbol_data:
            data = symbol_data[symbol]
            data['net_pnl'] = data['sell_value'] - data['buy_value'] - data['commission']
            
        return daily_data, dict(symbol_data)
        
    @staticmethod
    def filter_by_date_range(executions: Dict, commissions: Dict, 
                           start_date: date, end_date: date) -> Tuple[Dict, Dict]:
        """Filter executions by date range"""
        filtered_executions = {}
        filtered_commissions = {}
        
        for exec_id, exec in executions.items():
            try:
                exec_datetime = datetime.strptime(exec['time'], "%Y%m%d %H:%M:%S")
                exec_date = exec_datetime.date()

                if start_date <= exec_date <= end_date:
                    filtered_executions[exec_id] = exec
                    if exec_id in commissions:
                        filtered_commissions[exec_id] = commissions[exec_id]
            except (ValueError, TypeError, KeyError) as e:
                logger.debug(f"Skipping unparseable execution {exec_id}: {e}")
                continue
                
        return filtered_executions, filtered_commissions
        
    @staticmethod
    def calculate_statistics(daily_data: Dict) -> Dict:
        """Calculate trading statistics"""
        if not daily_data:
            return {
                'total_days': 0,
                'profit_days': 0,
                'loss_days': 0,
                'total_pnl': 0,
                'avg_daily_pnl': 0,
                'best_day': 0,
                'worst_day': 0
            }
            
        total_days = len(daily_data)
        profit_days = sum(1 for data in daily_data.values() if data['net_pnl'] > 0)
        loss_days = sum(1 for data in daily_data.values() if data['net_pnl'] < 0)
        total_pnl = sum(data['net_pnl'] for data in daily_data.values())
        
        pnl_values = [data['net_pnl'] for data in daily_data.values()]
        best_day = max(pnl_values) if pnl_values else 0
        worst_day = min(pnl_values) if pnl_values else 0
        avg_daily_pnl = total_pnl / total_days if total_days > 0 else 0
        
        return {
            'total_days': total_days,
            'profit_days': profit_days,
            'loss_days': loss_days,
            'total_pnl': total_pnl,
            'avg_daily_pnl': avg_daily_pnl,
            'best_day': best_day,
            'worst_day': worst_day
        }


class IBExecutionFetcher(QThread):
    """Fetches IB execution + commission data without blocking the UI.

    Subscribes to ``IBSignals.execution_details``, ``commission_report``, and
    ``execution_details_end`` for the duration of one ``reqExecutions`` call,
    then disconnects. This replaces the older approach of monkey-patching
    ``self.ib_app.execDetails`` / ``commissionReport`` / ``execDetailsEnd``,
    which silently broke other listeners (notably PositionManager's commission
    tracking) for as long as the fetcher was running.

    Signal slots are connected with ``Qt.DirectConnection`` so they execute on
    the emitting thread (the IB message-pump thread); the fetcher's own
    ``run()`` blocks on a ``threading.Event`` waiting for ``execDetailsEnd``.
    """

    dataReady = pyqtSignal(dict, dict)  # executions, commissions
    statusUpdate = pyqtSignal(str)
    errorOccurred = pyqtSignal(str)
    progressUpdate = pyqtSignal(int, int)  # current, total

    TIMEOUT_SECONDS = 30

    def __init__(self, ib_app, start_date=None, end_date=None):
        super().__init__()
        self.ib_app = ib_app
        self.start_date = start_date
        self.end_date = end_date
        self.executions: Dict[str, dict] = {}
        # All commission reports we observe during our window, keyed by execId.
        # Filtered down to just our executions after execDetailsEnd.
        self._all_commissions: Dict[str, dict] = {}
        self.commissions: Dict[str, dict] = {}
        self._req_id: Optional[int] = None
        self._done = threading.Event()

    def run(self):
        """Run the execution fetch in this QThread."""
        if not self.ib_app or not self.ib_app.isConnected():
            self.errorOccurred.emit("Not connected to Interactive Brokers")
            return

        self.statusUpdate.emit("Fetching executions from IB...")
        self._req_id = self.ib_app.allocate_request_id(REQ_CATEGORY_EXECUTION)

        signals = self.ib_app.signals
        # DirectConnection so slots run on the IB run-loop thread that emits
        # them. Our slots only mutate dicts owned by this fetcher, which is
        # safe given a single emitter thread.
        signals.execution_details.connect(
            self._on_execution_details, Qt.ConnectionType.DirectConnection
        )
        signals.commission_report.connect(
            self._on_commission_report, Qt.ConnectionType.DirectConnection
        )
        signals.execution_details_end.connect(
            self._on_execution_details_end, Qt.ConnectionType.DirectConnection
        )

        try:
            exec_filter = ExecutionFilter()
            if self.start_date:
                exec_filter.time = self.start_date.strftime("%Y%m%d-00:00:00")

            self.ib_app.reqExecutions(self._req_id, exec_filter)

            if not self._done.wait(timeout=self.TIMEOUT_SECONDS):
                self.errorOccurred.emit("Timeout waiting for executions")
                return

            # Filter commissions to just the executions we received. Other
            # commissions seen during our window belong to live trading and
            # are owned by PositionManager via the same signal.
            self.commissions = {
                exec_id: data
                for exec_id, data in self._all_commissions.items()
                if exec_id in self.executions
            }
            self.dataReady.emit(self.executions, self.commissions)

        except Exception as e:
            logger.error(f"Error fetching executions: {e}", exc_info=True)
            self.errorOccurred.emit(f"Error: {e}")

        finally:
            try:
                signals.execution_details.disconnect(self._on_execution_details)
            except TypeError:
                pass
            try:
                signals.commission_report.disconnect(self._on_commission_report)
            except TypeError:
                pass
            try:
                signals.execution_details_end.disconnect(self._on_execution_details_end)
            except TypeError:
                pass
            if self._req_id is not None:
                self.ib_app.release_request_id(self._req_id)
                self._req_id = None

    def _on_execution_details(self, reqId, contract, execution):
        """Slot for IBSignals.execution_details. Filtered by our reqId."""
        if reqId != self._req_id:
            return
        self.executions[execution.execId] = {
            'symbol': contract.symbol,
            'time': execution.time,
            'side': execution.side,
            'shares': execution.shares,
            'price': execution.price,
            'avgPrice': execution.avgPrice,
            'orderId': execution.orderId,
            'account': execution.acctNumber,
            'exchange': execution.exchange,
            'contract': contract
        }

    def _on_commission_report(self, commissionReport):
        """Slot for IBSignals.commission_report. Captures all; filtered later."""
        self._all_commissions[commissionReport.execId] = {
            'commission': abs(commissionReport.commission),
            'currency': commissionReport.currency,
            'realizedPNL': commissionReport.realizedPNL,
        }

    def _on_execution_details_end(self, reqId):
        """Slot for IBSignals.execution_details_end. Filtered by our reqId."""
        if reqId != self._req_id:
            return
        self._done.set()


class ExecutionDataModel(QObject):
    """Model for execution data management"""
    
    # Signals
    data_updated = pyqtSignal()
    comment_updated = pyqtSignal(str, str)  # exec_id, comment
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.db = ExecutionDatabase()
        self.processor = ExecutionProcessor()
        self.executions = {}
        self.commissions = {}
        self.comments = {}
        self.daily_data = {}
        self.symbol_data = {}
        
    def load_from_database(self):
        """Load all data from database"""
        try:
            self.executions, self.commissions, self.comments = self.db.get_all_executions()
            
            if self.executions:
                self.daily_data, self.symbol_data = self.processor.process_executions(
                    self.executions, self.commissions
                )
                
            self.data_updated.emit()
            
        except Exception as e:
            logger.error(f"Error loading from database: {e}", exc_info=True)
            self.error_occurred.emit(f"Error loading data: {str(e)}")
            
    def store_new_executions(self, new_executions: Dict, new_commissions: Dict):
        """Store new executions and update data"""
        try:
            if new_executions:
                self.db.store_executions(new_executions, new_commissions)
                self.load_from_database()
                
        except Exception as e:
            logger.error(f"Error storing executions: {e}", exc_info=True)
            self.error_occurred.emit(f"Error storing data: {str(e)}")
            
    def update_comment(self, exec_id: str, comment: str):
        """Update comment for an execution"""
        self.db.save_comment(exec_id, comment)
        self.comments[exec_id] = comment
        self.comment_updated.emit(exec_id, comment)
        
    def clear_today_data(self):
        """Clear today's data from database"""
        self.db.clear_today_data()
        
    def get_latest_execution_time(self) -> Optional[str]:
        """Get latest execution time"""
        return self.db.get_latest_execution_time()
        
    def get_filtered_symbol_data(self, start_date: date, end_date: date) -> Dict:
        """Get symbol data filtered by date range"""
        filtered_exec, filtered_comm = self.processor.filter_by_date_range(
            self.executions, self.commissions, start_date, end_date
        )
        _, symbol_data = self.processor.process_executions(filtered_exec, filtered_comm)
        return symbol_data
        
    def get_statistics(self) -> Dict:
        """Get trading statistics"""
        return self.processor.calculate_statistics(self.daily_data)