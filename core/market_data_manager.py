# core/market_data_manager.py
"""Market data manager for handling IB market data subscriptions"""
import logging
from typing import Dict, Optional, Set
from PyQt6.QtCore import QObject, pyqtSignal
from ibapi.ticktype import TickTypeEnum

from core.ib_app import REQ_CATEGORY_MARKET

logger = logging.getLogger(__name__)


class MarketDataManager(QObject):
    """Manages market data subscriptions and updates.

    Subscriptions are reference-counted per ticker, with two distinct roles:

    - The **trader** role: at most one ticker at a time, replaced when the
      user picks a new symbol in the trader panel.
    - The **position** role: any number of tickers, one ref per call, used
      to keep live quotes flowing for tickers the user has open positions
      in (independent of what's currently in the trader panel).

    The IB ``reqMktData`` call only fires when the first ref (of either role)
    is added, and ``cancelMktData`` only fires when the last ref drops. This
    is what lets a position keep streaming after the trader switches away,
    while still avoiding duplicate subscriptions when both roles want the
    same ticker.
    """

    # Signals
    market_data_update = pyqtSignal(str, float, float, float, int)  # ticker, bid, ask, last, volume
    subscription_error = pyqtSignal(str, str)  # ticker, error message

    def __init__(self, ib_app=None, contract_resolver=None):
        super().__init__()
        self.ib_app = ib_app
        self.contract_resolver = contract_resolver
        self.active_subscriptions: Dict[str, int] = {}  # ticker -> req_id
        self.market_data: Dict[int, dict] = {}  # req_id -> market data dict
        # Per-role refcounts. The trader role has at most one ticker; the
        # position role can have any number. Total refs for a ticker is the
        # sum, and the IB subscription is alive iff total > 0.
        self._position_refs: Dict[str, int] = {}
        self._trader_ticker: Optional[str] = None
        # Tickers we've kicked off a contract resolve for. Prevents
        # duplicate resolves while one is in flight, and lets the resolve
        # callback know whether to proceed with reqMktData.
        self._pending_resolve: Set[str] = set()

    def set_ib_app(self, ib_app):
        """Set the IB app instance"""
        self.ib_app = ib_app

    def set_contract_resolver(self, resolver):
        """Set the contract resolver used to qualify SMART contracts."""
        self.contract_resolver = resolver

    def _total_refs(self, ticker: str) -> int:
        return self._position_refs.get(ticker, 0) + (1 if self._trader_ticker == ticker else 0)

    def _ensure_ib_subscribed(self, ticker: str) -> bool:
        """Schedule ``reqMktData`` for ``ticker`` if not already streaming.

        Returns ``True`` if either the ticker is already subscribed or a
        contract resolve has been kicked off (so callers may keep their
        optimistic refcount). Returns ``False`` only on synchronous failure
        — disconnected, or no resolver configured. Async failure (IB
        rejected the symbol) is reported later via
        ``subscription_error`` and rolls back refs in
        ``_on_contract_resolved``.
        """
        if ticker in self.active_subscriptions:
            return True
        if ticker in self._pending_resolve:
            return True
        if not self.ib_app or not self.ib_app.isConnected():
            logger.error("Cannot subscribe: Not connected to IB")
            self.subscription_error.emit(ticker, "Not connected to IB")
            return False
        if not self.contract_resolver:
            logger.error("Cannot subscribe: contract resolver not configured")
            self.subscription_error.emit(ticker, "Contract resolver not configured")
            return False

        self._pending_resolve.add(ticker)
        self.contract_resolver.resolve(
            ticker,
            lambda c, e, t=ticker: self._on_contract_resolved(t, c, e),
        )
        return True

    def _on_contract_resolved(self, ticker: str, contract, error):
        """Send ``reqMktData`` once the resolver has a primaryExchange.

        Drops silently if every ref was released between the resolve being
        scheduled and the response arriving (e.g. user switched trader
        ticker mid-flight).
        """
        self._pending_resolve.discard(ticker)

        if self._total_refs(ticker) == 0:
            return

        if not contract:
            logger.error(f"Contract resolution failed for {ticker}: {error}")
            self.subscription_error.emit(ticker, error or "Contract lookup failed")
            self._position_refs.pop(ticker, None)
            if self._trader_ticker == ticker:
                self._trader_ticker = None
            return

        if not self.ib_app or not self.ib_app.isConnected():
            return
        if ticker in self.active_subscriptions:
            return

        req_id = self.ib_app.allocate_request_id(REQ_CATEGORY_MARKET)
        try:
            self.active_subscriptions[ticker] = req_id
            self.market_data[req_id] = {
                'ticker': ticker,
                'bid': None,
                'ask': None,
                'last': None,
                'volume': None,
            }
            logger.info(f"Requesting market data for {ticker} with req_id {req_id}")
            self.ib_app.reqMktData(req_id, contract, "", False, False, [])
        except Exception as e:
            logger.error(f"Error subscribing to {ticker}: {e}")
            self.subscription_error.emit(ticker, str(e))
            self.active_subscriptions.pop(ticker, None)
            self.market_data.pop(req_id, None)
            self.ib_app.release_request_id(req_id)

    def subscribe_market_data(self, ticker: str, is_position: bool = False):
        """Add a subscription ref for ``ticker``.

        ``is_position=True`` adds a position ref (any number allowed).
        ``is_position=False`` sets the trader ref. The trader ref is unique:
        a non-position subscribe to a different ticker first releases the
        previous trader ticker's ref. This matches how callers behave today
        (the trader emits one subscribe per active ticker) and means callers
        don't need to remember to unsubscribe before switching.
        """
        if not self.ib_app or not self.ib_app.isConnected():
            logger.error("Cannot subscribe: Not connected to IB")
            self.subscription_error.emit(ticker, "Not connected to IB")
            return

        if is_position:
            # Bump position ref first so _ensure_ib_subscribed sees the ref;
            # if the IB call fails, we roll back below.
            self._position_refs[ticker] = self._position_refs.get(ticker, 0) + 1
            if not self._ensure_ib_subscribed(ticker):
                self._position_refs[ticker] -= 1
                if self._position_refs[ticker] == 0:
                    self._position_refs.pop(ticker)
            return

        # Trader role — single-slot.
        previous = self._trader_ticker
        if previous == ticker:
            return  # already the active trader ticker
        self._trader_ticker = ticker
        if not self._ensure_ib_subscribed(ticker):
            self._trader_ticker = previous
            return
        # Replacing a previous trader ticker: drop its ref, possibly cancel.
        if previous and previous != ticker:
            self._cancel_if_unrefd(previous)

    def unsubscribe_market_data(self, ticker: str):
        """Drop the trader ref for ``ticker``; cancel only if no refs remain."""
        if self._trader_ticker == ticker:
            self._trader_ticker = None
            self._cancel_if_unrefd(ticker)
            return
        # Caller asked to unsubscribe a ticker the trader doesn't currently
        # hold. This is benign — log at debug rather than warning — usually
        # a stale unsubscribe from a prior trader switch.
        logger.debug(f"unsubscribe_market_data: {ticker} is not the current trader ticker")

    def unsubscribe_position_data(self, ticker: str):
        """Drop one position ref for ``ticker``; cancel only if no refs remain."""
        count = self._position_refs.get(ticker, 0)
        if count <= 0:
            logger.debug(f"unsubscribe_position_data: no position ref for {ticker}")
            return
        if count == 1:
            self._position_refs.pop(ticker)
        else:
            self._position_refs[ticker] = count - 1
        self._cancel_if_unrefd(ticker)

    def _cancel_if_unrefd(self, ticker: str):
        """Cancel the IB subscription if no role still holds a ref."""
        if self._total_refs(ticker) > 0:
            return
        self._unsubscribe_ticker(ticker)

    def _unsubscribe_ticker(self, ticker: str):
        """Cancel the IB request and clear bookkeeping for ``ticker``."""
        if ticker not in self.active_subscriptions:
            return

        req_id = self.active_subscriptions[ticker]

        try:
            if self.ib_app and self.ib_app.isConnected():
                logger.info(f"Canceling market data for {ticker} with req_id {req_id}")
                self.ib_app.cancelMktData(req_id)
        except Exception as e:
            logger.error(f"Error cancelling market data for {ticker}: {e}")
        finally:
            self.active_subscriptions.pop(ticker, None)
            self.market_data.pop(req_id, None)
            if self.ib_app:
                self.ib_app.release_request_id(req_id)
            
    def handle_tick_price(self, req_id: int, tick_type: int, price: float, attrib):
        """Handle tick price updates from IB.

        Accepts both real-time tick types and their DELAYED_* counterparts so
        the same handler works whether the user has a live data subscription
        or is using the free 15-20 minute delayed feed.

        IB uses ``-1.0`` as a sentinel for "no data available" — we treat that
        as missing rather than recording it as a real price.
        """
        if req_id not in self.market_data:
            return

        data = self.market_data[req_id]
        ticker = data['ticker']

        recognised = True
        if tick_type in (TickTypeEnum.BID, TickTypeEnum.DELAYED_BID):
            data['bid'] = None if price < 0 else price
            logger.debug(f"{ticker} Bid: {price}")
        elif tick_type in (TickTypeEnum.ASK, TickTypeEnum.DELAYED_ASK):
            data['ask'] = None if price < 0 else price
            logger.debug(f"{ticker} Ask: {price}")
        elif tick_type in (TickTypeEnum.LAST, TickTypeEnum.DELAYED_LAST):
            data['last'] = None if price < 0 else price
            logger.debug(f"{ticker} Last: {price}")
        else:
            recognised = False

        # Emit on any recognised price tick. Delayed feeds sometimes deliver
        # only LAST (no bid/ask), and we don't want to leave the trader stuck
        # on "Subscribing to ..." while waiting for ticks that never come.
        if recognised:
            self.market_data_update.emit(
                ticker,
                data['bid'] or 0,
                data['ask'] or 0,
                data['last'] or 0,
                data['volume'] or 0,
            )
            
    def handle_tick_size(self, req_id: int, tick_type: int, size: int):
        """Handle tick size updates from IB"""
        if req_id not in self.market_data:
            return
            
        data = self.market_data[req_id]
        
        # Update size based on tick type (accept delayed equivalents too)
        if tick_type in (TickTypeEnum.VOLUME, TickTypeEnum.DELAYED_VOLUME):
            data['volume'] = size
            logger.debug(f"{data['ticker']} Volume: {size}")
            
    # IB error codes that mean "this account doesn't have a market data
    # subscription for the requested feed". When these arrive, IB sends no
    # ticks at all (no fallback to delayed), so we surface them to the user
    # with a clear, actionable message instead of the raw IB error string.
    _SUBSCRIPTION_REQUIRED_CODES = {10089, 10090, 10091}

    # Codes meaning IB rejected the request on creation — the subscription
    # was never registered server-side, so calling cancelMktData would just
    # produce error 300. Clean up local state without canceling.
    # 200: No security definition for the request
    # 321: Validation error (bad contract field)
    # 354: Requested market data is not subscribed (terminal variant)
    _REJECTED_CODES = {200, 321, 354}

    def handle_error(self, req_id: int, error_code: int, error_string: str):
        """Handle errors from IB and surface them to the relevant ticker."""
        if req_id not in self.market_data:
            return

        ticker = self.market_data[req_id]['ticker']

        # Order matters: clean up local state *before* emitting the error
        # signal. The trader widget's error handler synchronously emits
        # ``unsubscribe_ticker``, which would otherwise re-enter
        # ``_unsubscribe_ticker`` and fire a ``cancelMktData`` for the
        # same dead subscription — producing IB error 300.
        if error_code in self._SUBSCRIPTION_REQUIRED_CODES:
            logger.info(
                f"No market data subscription for {ticker} ({error_code}): {error_string}"
            )
            message = (
                f"Delayed market data not available for {ticker}. "
                "Enable a free delayed feed in IB Account Management → "
                "Market Data Subscriptions."
            )
            self._cleanup_local_subscription(ticker)
            self.subscription_error.emit(ticker, message)
            return

        if error_code in self._REJECTED_CODES:
            logger.info(
                f"IB rejected market data for {ticker} ({error_code}): {error_string}"
            )
            self._cleanup_local_subscription(ticker)
            self.subscription_error.emit(
                ticker, f"Cannot subscribe to {ticker}: {error_string}"
            )
            return

        logger.error(f"Market data error for {ticker}: {error_code} - {error_string}")
        self.subscription_error.emit(ticker, error_string)

    def _cleanup_local_subscription(self, ticker: str):
        """Drop local state for a subscription IB never registered or
        already discarded. Skips ``cancelMktData`` to avoid error 300."""
        req_id = self.active_subscriptions.pop(ticker, None)
        self._position_refs.pop(ticker, None)
        if self._trader_ticker == ticker:
            self._trader_ticker = None
        if req_id is not None:
            self.market_data.pop(req_id, None)
            if self.ib_app:
                self.ib_app.release_request_id(req_id)
            
    def clear_all_subscriptions(self):
        """Clear all active subscriptions, regardless of refcount."""
        for ticker in list(self.active_subscriptions.keys()):
            self._unsubscribe_ticker(ticker)
        self._position_refs.clear()
        self._trader_ticker = None
        self._pending_resolve.clear()

    def get_active_tickers(self) -> list:
        """Get list of actively subscribed tickers"""
        return list(self.active_subscriptions.keys())
        
    def is_subscribed(self, ticker: str) -> bool:
        """Check if subscribed to a ticker"""
        return ticker in self.active_subscriptions
        
    def get_position_subscriptions(self) -> Set[str]:
        """Get the set of tickers currently held by a position ref."""
        return set(self._position_refs.keys())

    def refresh_position_subscriptions(self, position_tickers: Set[str]):
        """Reconcile position-role subs with the given set of tickers.

        Only touches the position role: adds a position ref for any new
        ticker, drops one for any removed ticker. The trader's active ticker
        is never affected, even if it overlaps with ``position_tickers`` —
        that's handled by the per-role refcount.
        """
        current = self.get_position_subscriptions()

        for ticker in position_tickers - current:
            logger.info(f"Adding position subscription for {ticker}")
            self.subscribe_market_data(ticker, is_position=True)

        for ticker in current - position_tickers:
            logger.info(f"Removing position subscription for {ticker}")
            self.unsubscribe_position_data(ticker)