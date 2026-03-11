from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import yfinance as yf
from fastapi import HTTPException, status

CACHE_TTL_SECONDS = 600
MARKET_SOURCE = 'Yahoo Finance'
MARKET_SYMBOLS = {
    'gold': {'symbol': 'GC=F', 'unit': 'USD/oz'},
    'wti': {'symbol': 'CL=F', 'unit': 'USD/bbl'},
    'sp500': {'symbol': '^GSPC', 'unit': 'USD'},
}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ''):
            return None
        return float(value)
    except Exception:
        return None


def _history_to_series(history) -> list[dict[str, Any]]:
    if history is None or history.empty:
        return []

    close_series = history.get('Close')
    if close_series is None:
        return []

    rows: list[dict[str, Any]] = []
    for idx, value in close_series.dropna().tail(30).items():
        price = _safe_float(value)
        if price is None:
            continue
        timestamp = idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx
        if hasattr(timestamp, 'date'):
            x_value = timestamp.date().isoformat()
        else:
            x_value = str(timestamp)
        rows.append({'x': x_value, 'y': round(price, 2)})
    return rows


class MarketService:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[datetime, dict[str, Any]]] = {}

    def _get_cached(self, key: str) -> dict[str, Any] | None:
        cached = self._cache.get(key)
        if not cached:
            return None
        cached_at, payload = cached
        if (datetime.now(timezone.utc) - cached_at).total_seconds() > CACHE_TTL_SECONDS:
            self._cache.pop(key, None)
            return None
        return payload

    def _set_cache(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._cache[key] = (datetime.now(timezone.utc), payload)
        return payload

    def _load_market_payload(self, key: str) -> dict[str, Any]:
        config = MARKET_SYMBOLS[key]
        try:
            ticker = yf.Ticker(config['symbol'])
            history = ticker.history(period='1mo', interval='1d', auto_adjust=False)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f'Yahoo Finance connection is blocked on this machine: {exc}',
            ) from exc

        series = _history_to_series(history)
        if not series:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f'Yahoo Finance data is not available for {config["symbol"]}.',
            )

        latest = series[-1]
        previous = series[-2]['y'] if len(series) >= 2 else None
        payload = {
            'symbol': config['symbol'],
            'price': latest['y'],
            'timestamp': latest['x'],
            'series': series,
            'unit': config['unit'],
            'source': MARKET_SOURCE,
        }
        if previous is not None:
            payload['previous_close'] = previous
        return payload

    async def get_gold(self) -> dict[str, Any]:
        cached = self._get_cached('gold')
        if cached:
            return cached
        return self._set_cache('gold', self._load_market_payload('gold'))

    async def get_wti(self) -> dict[str, Any]:
        cached = self._get_cached('wti')
        if cached:
            return cached
        return self._set_cache('wti', self._load_market_payload('wti'))

    async def get_sp500(self) -> dict[str, Any]:
        cached = self._get_cached('sp500')
        if cached:
            return cached
        return self._set_cache('sp500', self._load_market_payload('sp500'))


market_service = MarketService()
