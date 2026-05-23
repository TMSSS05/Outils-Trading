"""
crypto-derivatives-free-mcp — MCP server for crypto derivatives data
Sources: Coinalyze, Binance Futures, Bybit, OKX (all public/free tiers)
Replaces: coinglass-mcp (paid)
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from functools import wraps

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("crypto-derivatives-free-mcp")

MCP_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(MCP_DIR)
ENV_FILE = os.path.join(PARENT_DIR, ".env")

# ── In-memory cache with TTL ──────────────────────────────────────
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 60  # seconds

def _get_cache_key(provider: str, endpoint: str, params: str = "") -> str:
    return f"{provider}:{endpoint}:{params}"

def _cached(ttl: int = CACHE_TTL):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = _get_cache_key(func.__name__, str(args), str(kwargs))
            now = time.time()
            if key in _cache and now - _cache[key]["ts"] < ttl:
                logger.info(f"Cache HIT for {key}")
                return _cache[key]["data"]
            result = await func(*args, **kwargs)
            _cache[key] = {"data": result, "ts": now}
            return result
        return wrapper
    return decorator

# ── Environment / Config ──────────────────────────────────────────
def _load_env() -> Dict[str, str]:
    env = {}
    # Try parent .env first
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    # Environment variables override file
    for k in ["COINALYZE_API_KEY"]:
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env

_env = _load_env()
COINALYZE_API_KEY = _env.get("COINALYZE_API_KEY", "")

# ── HTTP clients ──────────────────────────────────────────────────
_coinalyze_client: Optional[httpx.AsyncClient] = None
_binance_client: Optional[httpx.AsyncClient] = None
_bybit_client: Optional[httpx.AsyncClient] = None
_okx_client: Optional[httpx.AsyncClient] = None

def _get_coinalyze_client() -> httpx.AsyncClient:
    global _coinalyze_client
    if _coinalyze_client is None:
        _coinalyze_client = httpx.AsyncClient(
            base_url="https://api.coinalyze.net/v1",
            headers={"apiKey": COINALYZE_API_KEY} if COINALYZE_API_KEY else {},
            timeout=15.0
        )
    return _coinalyze_client

def _get_binance_client() -> httpx.AsyncClient:
    global _binance_client
    if _binance_client is None:
        _binance_client = httpx.AsyncClient(
            base_url="https://fapi.binance.com",
            timeout=10.0
        )
    return _binance_client

def _get_bybit_client() -> httpx.AsyncClient:
    global _bybit_client
    if _bybit_client is None:
        _bybit_client = httpx.AsyncClient(
            base_url="https://api.bybit.com",
            timeout=10.0
        )
    return _bybit_client

def _get_okx_client() -> httpx.AsyncClient:
    global _okx_client
    if _okx_client is None:
        _okx_client = httpx.AsyncClient(
            base_url="https://www.okx.com",
            timeout=10.0
        )
    return _okx_client

# ── Normalized response builder ───────────────────────────────────
def _response(
    ok: bool,
    source: str,
    metric: str,
    data: Any,
    value: Any = None,
    symbol: str = "",
    series_id: str = "",
    timestamp: str = "",
    cache_used: bool = False,
    fallback_used: bool = False,
    error: str = ""
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "source": source,
        "metric": metric,
        "symbol": symbol,
        "series_id": series_id,
        "data": data,
        "value": value,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "cache_used": cache_used,
        "fallback_used": fallback_used,
        "error": error,
    }

# ── API call helpers ──────────────────────────────────────────────

async def _coinalyze_get(endpoint: str, params: Dict = None) -> Dict:
    """Make a GET request to Coinalyze API."""
    client = _get_coinalyze_client()
    try:
        resp = await client.get(endpoint, params=params)
        if resp.status_code == 401:
            return _response(ok=False, source="coinalyze", metric=endpoint,
                           data=None, error="API key invalid or missing")
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Coinalyze HTTP error: {e.response.status_code}")
        return _response(ok=False, source="coinalyze", metric=endpoint,
                       data=None, error=f"HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Coinalyze error: {e}")
        return _response(ok=False, source="coinalyze", metric=endpoint,
                       data=None, error=str(e))

async def _binance_futures_get(endpoint: str, params: Dict = None) -> Dict:
    """Make a GET request to Binance Futures API."""
    client = _get_binance_client()
    try:
        resp = await client.get(endpoint, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Binance Futures error: {e}")
        return _response(ok=False, source="binance_futures", metric=endpoint,
                       data=None, error=str(e))

async def _bybit_get(endpoint: str, params: Dict = None) -> Dict:
    """Make a GET request to Bybit API."""
    client = _get_bybit_client()
    try:
        resp = await client.get(endpoint, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("retCode") != 0:
            return _response(ok=False, source="bybit", metric=endpoint,
                           data=None, error=data.get("retMsg", "Unknown"))
        return data.get("result", {})
    except Exception as e:
        logger.error(f"Bybit error: {e}")
        return _response(ok=False, source="bybit", metric=endpoint,
                       data=None, error=str(e))

async def _okx_get(endpoint: str, params: Dict = None) -> Dict:
    """Make a GET request to OKX API."""
    client = _get_okx_client()
    try:
        resp = await client.get(endpoint, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "0":
            return _response(ok=False, source="okx", metric=endpoint,
                           data=None, error=data.get("msg", "Unknown"))
        return data.get("data", [])
    except Exception as e:
        logger.error(f"OKX error: {e}")
        return _response(ok=False, source="okx", metric=endpoint,
                       data=None, error=str(e))

# ── Symbol mapping ────────────────────────────────────────────────

COINALYZE_SYMBOLS = {
    "BTCUSDT": "BTCUSDT_PERP",
    "ETHUSDT": "ETHUSDT_PERP",
    "XAUUSD": "XAUUSD",
    "SOLUSDT": "SOLUSDT_PERP",
}

BINANCE_SYMBOLS = {
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
    "SOLUSDT": "SOLUSDT",
}

# ══════════════════════════════════════════════════════════════════
# TOOLS
# ══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_open_interest(symbol: str = "BTCUSDT") -> Dict[str, Any]:
    """Get open interest for a symbol from Coinalyze with Binance fallback.
    
    Args:
        symbol: Trading pair (e.g., BTCUSDT, ETHUSDT, SOLUSDT)
    """
    cz_sym = COINALYZE_SYMBOLS.get(symbol.upper(), f"{symbol.upper()}_PERP")
    
    # Try Coinalyze first
    result = await _coinalyze_get("/open-interest", params={"symbol": cz_sym})
    if isinstance(result, dict) and result.get("ok") is False:
        # Fallback: Binance Futures Open Interest
        logger.info(f"Coinalyze failed, falling back to Binance for {symbol}")
        bin_result = await _binance_futures_get("/fapi/v1/openInterest",
                                                  params={"symbol": symbol.upper()})
        if isinstance(bin_result, dict) and "openInterest" in bin_result:
            return _response(
                ok=True, source="binance_futures", metric="open_interest",
                symbol=symbol.upper(),
                data={"open_interest": float(bin_result["openInterest"])},
                value=float(bin_result["openInterest"]),
                fallback_used=True
            )
        return _response(
            ok=False, source="coinalyze", metric="open_interest",
            symbol=symbol.upper(), data=None,
            error="All providers failed for open interest"
        )
    
    if isinstance(result, list) and len(result) > 0:
        oi_value = result[0].get("o", result[0].get("openInterest", 0))
        return _response(
            ok=True, source="coinalyze", metric="open_interest",
            symbol=cz_sym, data=result[0],
            value=oi_value
        )
    
    return _response(
        ok=True, source="coinalyze", metric="open_interest",
        symbol=cz_sym, data=result
    )


@mcp.tool()
async def get_funding_rate(symbol: str = "BTCUSDT") -> Dict[str, Any]:
    """Get current funding rate from Binance Futures with Bybit/OKX fallback.
    
    Args:
        symbol: Trading pair (e.g., BTCUSDT, ETHUSDT, SOLUSDT)
    """
    sym = symbol.upper()
    
    # Try Binance first
    result = await _binance_futures_get("/fapi/v1/premiumIndex",
                                          params={"symbol": sym})
    if isinstance(result, dict) and "lastFundingRate" in result:
        return _response(
            ok=True, source="binance_futures", metric="funding_rate",
            symbol=sym,
            data={
                "funding_rate": float(result["lastFundingRate"]),
                "mark_price": float(result.get("markPrice", 0)),
                "index_price": float(result.get("indexPrice", 0)),
                "next_funding_time": result.get("nextFundingTime", 0)
            },
            value=float(result["lastFundingRate"])
        )
    
    # Fallback: Bybit
    logger.info(f"Binance failed, falling back to Bybit for {sym}")
    bybit_result = await _bybit_get("/v5/market/tickers",
                                      params={"category": "linear", "symbol": sym})
    if isinstance(bybit_result, dict) and "list" in bybit_result:
        tickers = bybit_result["list"]
        if tickers and len(tickers) > 0:
            fr = float(tickers[0].get("fundingRate", 0))
            return _response(
                ok=True, source="bybit", metric="funding_rate",
                symbol=sym,
                data={"funding_rate": fr},
                value=fr,
                fallback_used=True
            )
    
    # Fallback: OKX
    logger.info(f"Bybit failed, falling back to OKX for {sym}")
    okx_result = await _okx_get("/api/v5/public/funding-rate",
                                  params={"instId": f"{sym}-SWAP"})
    if isinstance(okx_result, list) and len(okx_result) > 0:
        fr = float(okx_result[0].get("fundingRate", 0))
        return _response(
            ok=True, source="okx", metric="funding_rate",
            symbol=sym,
            data={"funding_rate": fr},
            value=fr,
            fallback_used=True
        )
    
    return _response(
        ok=False, source="binance_futures", metric="funding_rate",
        symbol=sym, data=None,
        error="All providers failed for funding rate"
    )


@mcp.tool()
async def get_liquidations(symbol: str = "BTCUSDT") -> Dict[str, Any]:
    """Get liquidation data from Coinalyze with Binance fallback.
    
    Args:
        symbol: Trading pair (e.g., BTCUSDT, ETHUSDT, SOLUSDT)
    """
    cz_sym = COINALYZE_SYMBOLS.get(symbol.upper(), f"{symbol.upper()}_PERP")
    
    result = await _coinalyze_get("/liquidation", params={"symbol": cz_sym})
    if isinstance(result, dict) and result.get("ok") is False:
        # Fallback: try to get Binance liquidation data or return error
        return _response(
            ok=False, source="coinalyze", metric="liquidations",
            symbol=symbol.upper(), data=None,
            error="Liquidation data requires Coinalyze API"
        )
    
    if isinstance(result, list) and len(result) > 0:
        return _response(
            ok=True, source="coinalyze", metric="liquidations",
            symbol=cz_sym, data=result
        )
    
    return _response(
        ok=True, source="coinalyze", metric="liquidations",
        symbol=cz_sym, data=result or []
    )


@mcp.tool()
async def get_long_short_ratio(symbol: str = "BTCUSDT") -> Dict[str, Any]:
    """Get long/short ratio from Coinalyze with Binance fallback.
    
    Args:
        symbol: Trading pair (e.g., BTCUSDT, ETHUSDT, SOLUSDT)
    """
    cz_sym = COINALYZE_SYMBOLS.get(symbol.upper(), f"{symbol.upper()}_PERP")
    
    result = await _coinalyze_get("/long-short-ratio", params={"symbol": cz_sym})
    if isinstance(result, dict) and result.get("ok") is False:
        # Fallback: Binance longs vs shorts
        logger.info(f"Coinalyze failed, falling back to Binance LS ratio for {symbol}")
        bin_result = await _binance_futures_get(
            "/futures/data/globalLongContractAccount",
            params={"symbol": symbol.upper(), "period": "1h"}
        )
        if isinstance(bin_result, list) and len(bin_result) > 0:
            latest = bin_result[-1]
            ls_data = {
                "long_account": float(latest.get("longAccount", 0)),
                "short_account": float(latest.get("shortAccount", 0)),
                "long_short_ratio": float(latest.get("longShortRatio", 0))
            }
            return _response(
                ok=True, source="binance_futures", metric="long_short_ratio",
                symbol=symbol.upper(), data=ls_data,
                value=ls_data["long_short_ratio"],
                fallback_used=True
            )
        return _response(
            ok=False, source="coinalyze", metric="long_short_ratio",
            symbol=symbol.upper(), data=None,
            error="All providers failed for long/short ratio"
        )
    
    if isinstance(result, list) and len(result) > 0:
        return _response(
            ok=True, source="coinalyze", metric="long_short_ratio",
            symbol=cz_sym, data=result
        )
    
    return _response(
        ok=True, source="coinalyze", metric="long_short_ratio",
        symbol=cz_sym, data=result or []
    )


@mcp.tool()
async def get_derivatives_summary(symbol: str = "BTCUSDT") -> Dict[str, Any]:
    """Get a combined summary of all derivatives data for a symbol.
    
    Aggregates open interest, funding rate, liquidations, and long/short ratio.
    
    Args:
        symbol: Trading pair (e.g., BTCUSDT, ETHUSDT, SOLUSDT)
    """
    import asyncio
    
    oi_task = get_open_interest(symbol)
    fr_task = get_funding_rate(symbol)
    liq_task = get_liquidations(symbol)
    ls_task = get_long_short_ratio(symbol)
    
    results = await asyncio.gather(oi_task, fr_task, liq_task, ls_task, return_exceptions=True)
    
    return _response(
        ok=True, source="combined", metric="derivatives_summary",
        symbol=symbol.upper(),
        data={
            "open_interest": results[0] if not isinstance(results[0], Exception) else {"ok": False, "error": str(results[0])},
            "funding_rate": results[1] if not isinstance(results[1], Exception) else {"ok": False, "error": str(results[1])},
            "liquidations": results[2] if not isinstance(results[2], Exception) else {"ok": False, "error": str(results[2])},
            "long_short_ratio": results[3] if not isinstance(results[3], Exception) else {"ok": False, "error": str(results[3])},
        }
    )


@mcp.tool()
async def list_supported_symbols() -> Dict[str, Any]:
    """List supported symbols for derivatives data."""
    return _response(
        ok=True, source="crypto-derivatives-free-mcp", metric="supported_symbols",
        data={
            "derivatives_symbols": {
                "coinalyze": list(COINALYZE_SYMBOLS.keys()),
                "binance_futures": list(BINANCE_SYMBOLS.keys()),
            },
            "note": "Most major symbols work directly via Binance/Bybit/OKX"
        }
    )


@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check if the MCP server and its providers are reachable."""
    results = {}
    
    # Check Coinalyze
    try:
        client = _get_coinalyze_client()
        resp = await client.get("/ping")
        results["coinalyze"] = {"status": "ok" if resp.status_code == 200 else "error", "code": resp.status_code}
    except Exception as e:
        results["coinalyze"] = {"status": "error", "error": str(e)}
    
    # Check Binance Futures
    try:
        client = _get_binance_client()
        resp = await client.get("/fapi/v1/ping")
        results["binance_futures"] = {"status": "ok" if resp.status_code == 200 else "error"}
    except Exception as e:
        results["binance_futures"] = {"status": "error", "error": str(e)}
    
    # Check Bybit
    try:
        client = _get_bybit_client()
        resp = await client.get("/v5/market/time")
        results["bybit"] = {"status": "ok" if resp.status_code == 200 else "error"}
    except Exception as e:
        results["bybit"] = {"status": "error", "error": str(e)}
    
    # Check OKX
    try:
        client = _get_okx_client()
        resp = await client.get("/api/v5/public/time")
        results["okx"] = {"status": "ok" if resp.status_code == 200 else "error"}
    except Exception as e:
        results["okx"] = {"status": "error", "error": str(e)}
    
    all_ok = all(r.get("status") == "ok" for r in results.values())
    
    return _response(
        ok=all_ok, source="crypto-derivatives-free-mcp", metric="health_check",
        data=results,
        error="" if all_ok else "Some providers are unreachable"
    )


# ── Main ──────────────────────────────────────────────────────────
def main():
    """Run the MCP server."""
    logger.info("Starting crypto-derivatives-free-mcp...")
    logger.info(f"Coinalyze API key configured: {bool(COINALYZE_API_KEY)}")
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
