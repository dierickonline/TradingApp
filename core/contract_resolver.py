# core/contract_resolver.py
"""Resolve SMART stock symbols to fully-qualified contracts.

A bare ``SMART`` stock contract works for live data — IB silently picks a
listing. With delayed data IB refuses and returns an "ambiguous contract"
error, demanding ``primaryExchange`` be set. This resolver issues one
``reqContractDetails`` per symbol, caches the resulting ``primaryExchange``,
and hands callers a contract that delayed-data subscriptions accept.

Concurrent requests for the same symbol are coalesced — callers that ask
while a resolve is in flight wait on the same response. The cache survives
across reconnects (a stock's listing is stable); only in-flight requests
are dropped on disconnect.
"""
import logging
from typing import Callable, Dict, List, Optional, Set
from PyQt6.QtCore import QObject
from ibapi.contract import Contract

from core.ib_app import REQ_CATEGORY_CONTRACT

logger = logging.getLogger(__name__)

# (contract_or_None, error_or_None). Exactly one is non-None.
ResolveCallback = Callable[[Optional[Contract], Optional[str]], None]


class ContractResolver(QObject):
    """Async lookup + cache for SMART stock primaryExchange."""

    def __init__(self, ib_app=None):
        super().__init__()
        self.ib_app = ib_app
        self._cache: Dict[str, str] = {}
        self._min_tick: Dict[str, float] = {}
        self._pending: Dict[int, dict] = {}
        self._symbol_to_req: Dict[str, int] = {}

    def set_ib_app(self, ib_app):
        self.ib_app = ib_app

    def resolve(self, symbol: str, callback: ResolveCallback) -> None:
        """Resolve ``symbol`` and invoke ``callback(contract, error)``.

        Fires synchronously on cache hit, otherwise asynchronously after IB
        responds. ``contract`` is a fully-qualified stock ``Contract`` on
        success and ``None`` on failure; ``error`` is the inverse.
        """
        if symbol in self._cache:
            callback(self._build_contract(symbol, self._cache[symbol]), None)
            return

        if not self.ib_app or not self.ib_app.isConnected():
            callback(None, "Not connected to IB")
            return

        if symbol in self._symbol_to_req:
            req_id = self._symbol_to_req[symbol]
            self._pending[req_id]['callbacks'].append(callback)
            return

        req_id = self.ib_app.allocate_request_id(REQ_CATEGORY_CONTRACT)
        self._pending[req_id] = {
            'symbol': symbol,
            'primary_exchange': None,
            'min_tick': None,
            'callbacks': [callback],
        }
        self._symbol_to_req[symbol] = req_id

        probe = Contract()
        probe.symbol = symbol
        probe.secType = "STK"
        probe.exchange = "SMART"
        probe.currency = "USD"

        logger.info(f"Resolving contract for {symbol} (reqId {req_id})")
        try:
            self.ib_app.reqContractDetails(req_id, probe)
        except Exception as e:
            logger.error(f"reqContractDetails failed for {symbol}: {e}")
            self._fail(req_id, str(e))

    def handle_contract_details(self, req_id: int, contract_details) -> None:
        entry = self._pending.get(req_id)
        if entry is None:
            return
        primary = getattr(contract_details.contract, 'primaryExchange', '') or ''
        exchange = getattr(contract_details.contract, 'exchange', '') or ''
        min_tick = getattr(contract_details, 'minTick', None)
        logger.info(
            f"contractDetails for {entry['symbol']}: "
            f"exchange={exchange!r} primaryExchange={primary!r} minTick={min_tick!r}"
        )
        # IB normally returns one row for a USD STK; if more arrive, we trust
        # the first non-empty primaryExchange.
        if entry['primary_exchange']:
            return
        if primary:
            entry['primary_exchange'] = primary
        if entry['min_tick'] is None and isinstance(min_tick, (int, float)) and min_tick > 0:
            entry['min_tick'] = float(min_tick)

    def handle_contract_details_end(self, req_id: int) -> None:
        entry = self._pending.pop(req_id, None)
        if entry is None:
            return
        symbol = entry['symbol']
        primary = entry['primary_exchange']
        self._symbol_to_req.pop(symbol, None)

        if primary:
            self._cache[symbol] = primary
            if entry['min_tick'] is not None:
                self._min_tick[symbol] = entry['min_tick']
            logger.info(
                f"Resolved {symbol} -> primaryExchange={primary} "
                f"minTick={self._min_tick.get(symbol)}"
            )
            contract = self._build_contract(symbol, primary)
            self._dispatch(entry['callbacks'], contract, None)
        else:
            msg = f"No contract details returned for {symbol}"
            logger.warning(msg)
            self._dispatch(entry['callbacks'], None, msg)

        if self.ib_app:
            self.ib_app.release_request_id(req_id)

    def handle_error(self, req_id: int, error_code: int, error_string: str) -> None:
        if req_id not in self._pending:
            return
        # contractDetailsEnd does not fire after a hard error, so clean up
        # here. Codes 200 (no security definition) and 321 (validation) are
        # the typical ones for unknown symbols.
        self._fail(req_id, f"{error_code}: {error_string}")

    def cancel_pending(self) -> None:
        """Fail every in-flight callback. Cache is preserved."""
        for req_id in list(self._pending.keys()):
            self._fail(req_id, "Disconnected")

    def clear_cache(self) -> None:
        """Drop in-flight requests and the resolved cache."""
        self.cancel_pending()
        self._cache.clear()
        self._min_tick.clear()

    def get_min_tick(self, symbol: str) -> Optional[float]:
        """Return the cached minTick for ``symbol``, or None if unknown."""
        return self._min_tick.get(symbol)

    def _fail(self, req_id: int, error: str) -> None:
        entry = self._pending.pop(req_id, None)
        if entry is None:
            return
        self._symbol_to_req.pop(entry['symbol'], None)
        self._dispatch(entry['callbacks'], None, error)
        if self.ib_app:
            self.ib_app.release_request_id(req_id)

    @staticmethod
    def _dispatch(callbacks: List[ResolveCallback],
                  contract: Optional[Contract],
                  error: Optional[str]) -> None:
        for cb in callbacks:
            try:
                cb(contract, error)
            except Exception as e:
                logger.error(f"Contract resolve callback raised: {e}", exc_info=True)

    @staticmethod
    def _build_contract(symbol: str, primary_exchange: str) -> Contract:
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.primaryExchange = primary_exchange
        contract.currency = "USD"
        return contract
