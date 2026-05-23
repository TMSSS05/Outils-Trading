"""
crypto-market-free-mcp — MCP server for crypto market data
Sources: CoinGecko (demo key), DefiLlama (free), Binance spot (public)
Replaces/Complements: coingecko-mcp (paid Pro key required)
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

mcp = FastMCP("crypto-market-free-mcp")

MCP_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(MCP_DIR)
ENV_FILE = os.path.join(PARENT_DIR, ".env")

# ── Cache ─────────────────────────────────────────────────────────
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 60

def _cache_key(provider: str, endpoint: str, params: str = "") -> str:
    return f"{provider}:{endpoint}:{params}"

def _cached(ttl: int = CACHE_TTL):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = _cache_key(func.__name__, str(args), str(kwargs))
            now = time.time()
            if key in _cache and now - _cache[key]["ts"] < ttl:
                logger.info(f"Cache HIT for {key}")
                return _cache[key]["data"]
            result = await func(*args, **kwargs)
            _cache[key] = {"data": result, "ts": now}
            return result
        return wrapper
    return decorator

# ── Config ────────────────────────────────────────────────────────
def _load_env() -> Dict[str, str]:
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    for k in ["COINGECKO_API_KEY"]:
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env

_env = _load_env()
COINGECKO_API_KEY = _env.get("COINGECKO_API_KEY", "")

# ── Clients ───────────────────────────────────────────────────────
_coingecko: Optional[httpx.AsyncClient] = None
_defillama: Optional[httpx.AsyncClient] = None
_binance: Optional[httpx.AsyncClient] = None

def _cg_client() -> httpx.AsyncClient:
    global _coingecko
    if _coingecko is None:
        headers = {"accept": "application/json"}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
        _coingecko = httpx.AsyncClient(
            base_url="https://api.coingecko.com/api/v3",
            headers=headers, timeout=15.0
        )
    return _coingecko

def _dl_client() -> httpx.AsyncClient:
    global _defillama
    if _defillama is None:
        _defillama = httpx.AsyncClient(
            base_url="https://api.llama.fi",
            timeout=15.0
        )
    return _defillama

def _bn_client() -> httpx.AsyncClient:
    global _binance
    if _binance is None:
        _binance = httpx.AsyncClient(
            base_url="https://api.binance.com",
            timeout=10.0
        )
    return _binance

# ── Response ──────────────────────────────────────────────────────
def _resp(ok: bool, source: str, metric: str, data: Any,
          value: Any = None, symbol: str = "", series_id: str = "",
          timestamp: str = "",
          cache_used: bool = False, fallback_used: bool = False,
          error: str = "") -> Dict[str, Any]:
    return {
        "ok": ok, "source": source, "metric": metric,
        "symbol": symbol, "series_id": series_id,
        "data": data, "value": value,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "cache_used": cache_used, "fallback_used": fallback_used,
        "error": error,
    }

async def _cg_get(endpoint: str, params: Dict = None) -> Dict:
    try:
        resp = await _cg_client().get(endpoint, params=params)
        if resp.status_code == 429:
            return _resp(False, "coingecko", endpoint, None,
                       error="Rate limited (429). Retry later.")
        if resp.status_code == 401:
            return _resp(False, "coingecko", endpoint, None,
                       error="API key invalid or missing")
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return _resp(False, "coingecko", endpoint, None,
                   error=f"HTTP {e.response.status_code}")
    except Exception as e:
        return _resp(False, "coingecko", endpoint, None, error=str(e))

async def _dl_get(endpoint: str) -> Dict:
    try:
        resp = await _dl_client().get(endpoint)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return _resp(False, "defillama", endpoint, None, error=str(e))

async def _bn_get(endpoint: str, params: Dict = None) -> Dict:
    try:
        resp = await _bn_client().get(endpoint, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return _resp(False, "binance", endpoint, None, error=str(e))

# ══════════════════════════════════════════════════════════════════
# TOOLS
# ══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_coin_price(coin: str = "bitcoin", vs_currency: str = "usd") -> Dict[str, Any]:
    """Get current price for a cryptocurrency.
    
    Args:
        coin: CoinGecko coin ID (e.g., bitcoin, ethereum, solana)
        vs_currency: Target currency (usd, eur, etc.)
    """
    result = await _cg_get(f"/simple/price", {
        "ids": coin, "vs_currencies": vs_currency,
        "include_24hr_change": "true", "include_market_cap": "true"
    })
    
    if isinstance(result, dict) and coin in result:
        cd = result[coin]
        return _resp(True, "coingecko", "price",
                    symbol=coin,
                    data={
                        "price": cd.get(vs_currency),
                        "24h_change": cd.get(f"{vs_currency}_24h_change"),
                        "market_cap": cd.get(f"{vs_currency}_market_cap")
                    },
                    value=cd.get(vs_currency))
    
    if isinstance(result, dict) and result.get("ok") is False:
        # Fallback: Binance ticker price
        bn_sym = coin.upper()[:3] + vs_currency.upper()
        bn_result = await _bn_get("/api/v3/ticker/price",
                                    {"symbol": bn_sym})
        if isinstance(bn_result, dict) and "price" in bn_result:
            return _resp(True, "binance", "price",
                        symbol=bn_sym,
                        data={"price": float(bn_result["price"])},
                        value=float(bn_result["price"]),
                        fallback_used=True)
    
    return _resp(False, "coingecko", "price", None,
               symbol=coin, error="Could not fetch price")


@mcp.tool()
async def get_coin_market_data(coin: str = "bitcoin") -> Dict[str, Any]:
    """Get detailed market data for a cryptocurrency.
    
    Args:
        coin: CoinGecko coin ID (e.g., bitcoin, ethereum, solana)
    """
    result = await _cg_get(f"/coins/{coin}", {
        "localization": "false",
        "tickers": "false",
        "community_data": "false",
        "developer_data": "false"
    })
    
    if isinstance(result, dict) and "market_data" in result:
        md = result["market_data"]
        return _resp(True, "coingecko", "market_data",
                    symbol=coin,
                    data={
                        "current_price": md.get("current_price", {}),
                        "market_cap": md.get("market_cap", {}),
                        "total_volume": md.get("total_volume", {}),
                        "high_24h": md.get("high_24h", {}),
                        "low_24h": md.get("low_24h", {}),
                        "price_change_24h": md.get("price_change_24h"),
                        "price_change_percentage_24h": md.get("price_change_percentage_24h"),
                        "circulating_supply": md.get("circulating_supply"),
                        "total_supply": md.get("total_supply"),
                        "max_supply": md.get("max_supply"),
                        "ath": md.get("ath", {}),
                        "ath_date": md.get("ath_date", {}),
                    })
    
    return _resp(False, "coingecko", "market_data", None,
               symbol=coin,
               error=result.get("error", "Could not fetch market data"))


@mcp.tool()
async def get_top_coins(limit: int = 10) -> Dict[str, Any]:
    """Get top cryptocurrencies by market cap.
    
    Args:
        limit: Number of coins (max 50)
    """
    limit = min(limit, 50)
    result = await _cg_get("/coins/markets", {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": str(limit),
        "page": "1",
        "sparkline": "false",
    })
    
    if isinstance(result, list):
        coins = []
        for c in result:
            coins.append({
                "id": c.get("id"),
                "symbol": c.get("symbol"),
                "name": c.get("name"),
                "current_price": c.get("current_price"),
                "market_cap": c.get("market_cap"),
                "volume_24h": c.get("total_volume"),
                "price_change_24h": c.get("price_change_percentage_24h"),
            })
        return _resp(True, "coingecko", "top_coins",
                    data={"coins": coins, "count": len(coins)})
    
    return _resp(False, "coingecko", "top_coins", None,
               error="Could not fetch top coins")


@mcp.tool()
async def get_trending_coins() -> Dict[str, Any]:
    """Get trending coins on CoinGecko."""
    result = await _cg_get("/search/trending")
    
    if isinstance(result, dict) and "coins" in result:
        trending = []
        for c in result["coins"][:15]:
            item = c.get("item", {})
            trending.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "symbol": item.get("symbol"),
                "market_cap_rank": item.get("market_cap_rank"),
                "price_btc": item.get("price_btc"),
                "score": item.get("score"),
            })
        return _resp(True, "coingecko", "trending",
                    data={"trending": trending})
    
    return _resp(False, "coingecko", "trending", None,
               error=result.get("error", "Could not fetch trending"))


@mcp.tool()
async def get_defi_tvl() -> Dict[str, Any]:
    """Get total TVL across all DeFi protocols from DefiLlama."""
    result = await _dl_get("/v2/chains")
    
    if isinstance(result, list):
        chains = []
        total_tvl = 0
        for chain in result[:30]:
            tvl = chain.get("tvl", 0)
            total_tvl += tvl
            chains.append({
                "name": chain.get("name"),
                "tvl": tvl,
                "change_1d": chain.get("change_1d"),
                "change_7d": chain.get("change_7d"),
                "change_1m": chain.get("change_1m"),
            })
        return _resp(True, "defillama", "defi_tvl",
                    data={"chains": chains, "total_tvl": total_tvl,
                          "total_tvl_formatted": f"${total_tvl:,.0f}"})
    
    return _resp(False, "defillama", "defi_tvl", None,
               error="Could not fetch DeFi TVL data")


@mcp.tool()
async def get_market_summary() -> Dict[str, Any]:
    """Get a combined crypto market summary from all providers."""
    import asyncio
    
    btc_task = get_coin_price("bitcoin")
    eth_task = get_coin_price("ethereum")
    top_task = get_top_coins(5)
    tvl_task = get_defi_tvl()
    
    btc_r, eth_r, top_r, tvl_r = await asyncio.gather(
        btc_task, eth_task, top_task, tvl_task, return_exceptions=True
    )
    
    return _resp(True, "combined", "market_summary", data={
        "bitcoin": btc_r if not isinstance(btc_r, Exception) else {"ok": False},
        "ethereum": eth_r if not isinstance(eth_r, Exception) else {"ok": False},
        "top_coins": top_r if not isinstance(top_r, Exception) else {"ok": False},
        "defi_tvl": tvl_r if not isinstance(tvl_r, Exception) else {"ok": False},
    })


@mcp.tool()
async def list_supported_coins() -> Dict[str, Any]:
    """List commonly used CoinGecko coin IDs."""
    common = {
        "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
        "ripple": "XRP", "cardano": "ADA", "polkadot": "DOT",
        "dogecoin": "DOGE", "avalanche-2": "AVAX", "chainlink": "LINK",
        "polygon": "MATIC", "litecoin": "LTC", "bitcoin-cash": "BCH",
        "stellar": "XLM", "monero": "XMR", "ethereum-classic": "ETC",
        "tron": "TRX", "filecoin": "FIL", "aptos": "APT",
        "sui": "SUI", "arbitrum": "ARB", "optimism": "OP",
    }
    return _resp(True, "crypto-market-free-mcp", "supported_coins",
               data={"coins": common,
                     "note": "Use full CoinGecko ID (e.g., 'bitcoin' not 'BTC')"})


@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check if the MCP server and its providers are reachable."""
    results = {}
    
    for name, client_fn, test_path in [
        ("coingecko", _cg_client, "/ping"),
        ("defillama", _dl_client, "/"),
        ("binance", _bn_client, "/api/v3/ping"),
    ]:
        try:
            resp = await client_fn().get(test_path)
            results[name] = {"status": "ok" if resp.status_code in (200, 429) else "error"}
        except Exception as e:
            results[name] = {"status": "error", "error": str(e)}
    
    all_ok = all(r.get("status") == "ok" for r in results.values())
    return _resp(all_ok, "crypto-market-free-mcp", "health_check",
                data=results,
                error="" if all_ok else "Some providers unreachable")


def main():
    logger.info("Starting crypto-market-free-mcp...")
    logger.info(f"CoinGecko API key configured: {bool(COINGECKO_API_KEY)}")
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
