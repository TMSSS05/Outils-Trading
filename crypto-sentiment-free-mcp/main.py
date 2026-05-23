"""
crypto-sentiment-free-mcp — MCP server for crypto sentiment data
Sources: Santiment (free tier), Alternative.me Fear & Greed (free),
         DefiLlama (free)
Replaces/Complements: santiment-mcp (paid)
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

mcp = FastMCP("crypto-sentiment-free-mcp")

MCP_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(MCP_DIR)
ENV_FILE = os.path.join(PARENT_DIR, ".env")

_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 300  # 5 min for sentiment

def _ck(provider: str, endpoint: str, params: str = "") -> str:
    return f"{provider}:{endpoint}:{params}"

def _cached(ttl: int = CACHE_TTL):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = _ck(func.__name__, str(args), str(kwargs))
            now = time.time()
            if key in _cache and now - _cache[key]["ts"] < ttl:
                logger.info(f"Cache HIT for {key}")
                return _cache[key]["data"]
            result = await func(*args, **kwargs)
            _cache[key] = {"data": result, "ts": now}
            return result
        return wrapper
    return decorator

def _load_env() -> Dict[str, str]:
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    for k in ["SANTIMENT_API_KEY"]:
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env

_env = _load_env()
SANTIMENT_API_KEY = _env.get("SANTIMENT_API_KEY", "")

_santiment: Optional[httpx.AsyncClient] = None
_altme: Optional[httpx.AsyncClient] = None
_defillama: Optional[httpx.AsyncClient] = None

def _sant_client() -> httpx.AsyncClient:
    global _santiment
    if _santiment is None:
        _santiment = httpx.AsyncClient(
            base_url="https://api.santiment.net/graphql",
            timeout=15.0
        )
    return _santiment

def _alt_client() -> httpx.AsyncClient:
    global _altme
    if _altme is None:
        _altme = httpx.AsyncClient(
            base_url="https://api.alternative.me",
            timeout=10.0
        )
    return _altme

def _dl_client() -> httpx.AsyncClient:
    global _defillama
    if _defillama is None:
        _defillama = httpx.AsyncClient(
            base_url="https://api.llama.fi",
            timeout=15.0
        )
    return _defillama

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

# ══════════════════════════════════════════════════════════════════
# TOOLS — Santiment
# ══════════════════════════════════════════════════════════════════

SANTIMENT_QUERIES = {
    "dev_activity": """
        query($slug: String!, $from: DateTime!, $to: DateTime!) {
            devActivity(slug: $slug, from: $from, to: $to, interval: "1d") {
                datetime activity
            }
        }
    """,
    "social_volume": """
        query($slug: String!, $from: DateTime!, $to: DateTime!) {
            socialVolume(slug: $slug, from: $from, to: $to, interval: "1d") {
                datetime socialVolume
            }
        }
    """,
    "price_volume_diff": """
        query($slug: String!, $from: DateTime!, $to: DateTime!) {
            priceVolumeDiff(slug: $slug, from: $from, to: $to, interval: "1d") {
                datetime priceVolumeDiff
            }
        }
    """,
    "daily_active_addresses": """
        query($slug: String!, $from: DateTime!, $to: DateTime!) {
            dailyActiveAddresses(slug: $slug, from: $from, to: $to, interval: "1d") {
                datetime dailyActiveAddresses
            }
        }
    """,
}

@mcp.tool()
async def get_santiment_metric(metric: str = "dev_activity",
                                slug: str = "bitcoin",
                                days: int = 7) -> Dict[str, Any]:
    """Get on-chain/metric data from Santiment.
    
    Available metrics:
    - dev_activity: GitHub developer activity
    - social_volume: Social media mention volume
    - price_volume_diff: Price vs volume divergence
    - daily_active_addresses: Daily active addresses
    
    Args:
        metric: Metric name (see above)
        slug: Asset slug (bitcoin, ethereum, solana, etc.)
        days: Number of days to look back
    """
    if not SANTIMENT_API_KEY:
        return _resp(False, "santiment", metric, None,
                   symbol=slug,
                   error="SANTIMENT_API_KEY not configured")
    
    if metric not in SANTIMENT_QUERIES:
        return _resp(False, "santiment", metric, None,
                   symbol=slug,
                   error=f"Unknown metric: {metric}. Available: {list(SANTIMENT_QUERIES.keys())}")
    
    import datetime as dt
    now = datetime.now(timezone.utc)
    from_dt = (now - dt.timedelta(days=days)).isoformat()
    to_dt = now.isoformat()
    
    query = SANTIMENT_QUERIES[metric]
    
    try:
        resp = await _sant_client().post("", json={
            "query": query,
            "variables": {
                "slug": slug,
                "from": from_dt,
                "to": to_dt,
            }
        })
        resp.raise_for_status()
        result = resp.json()
        
        if "errors" in result:
            error_msg = result["errors"][0].get("message", "Santiment API error")
            return _resp(False, "santiment", metric, None,
                       symbol=slug, error=error_msg)
        
        data_key = metric
        data_entries = result.get("data", {}).get(data_key, [])
        
        formatted = []
        for entry in data_entries[-10:]:
            formatted.append({
                "date": entry.get("datetime", entry.get("datetime")),
                "value": entry.get(data_key, entry.get(list(entry.keys() - {"datetime"})[0]))
            })
        
        latest = formatted[-1] if formatted else {}
        
        return _resp(True, "santiment", metric,
                    symbol=slug,
                    data={
                        "metric": metric,
                        "slug": slug,
                        "days": days,
                        "data_points": len(formatted),
                        "latest": latest.get("value"),
                        "latest_date": latest.get("date"),
                        "recent": formatted,
                    },
                    value=latest.get("value"))
    
    except Exception as e:
        return _resp(False, "santiment", metric, None,
                   symbol=slug, error=str(e))


# ══════════════════════════════════════════════════════════════════
# TOOLS — Alternative.me (Fear & Greed)
# ══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_fear_greed_index(limit: int = 1) -> Dict[str, Any]:
    """Get Crypto Fear & Greed Index from Alternative.me.
    
    The Fear & Greed Index ranges from 0 (Extreme Fear) to 100 (Extreme Greed).
    0-24: Extreme Fear | 25-44: Fear | 45-54: Neutral | 55-74: Greed | 75-100: Extreme Greed
    
    Args:
        limit: Number of days to return (1 = today only, max 30)
    """
    limit = min(max(limit, 1), 30)
    
    try:
        resp = await _alt_client().get("/fng/", params={"limit": str(limit)})
        resp.raise_for_status()
        result = resp.json()
        
        data_entries = result.get("data", [])
        if not data_entries:
            return _resp(False, "alternative.me", "fear_greed_index", None,
                       error="No data returned")
        
        formatted = []
        for entry in data_entries:
            formatted.append({
                "value": int(entry.get("value", 0)),
                "value_classification": entry.get("value_classification", ""),
                "timestamp": entry.get("timestamp"),
            })
        
        latest = formatted[0]
        
        # Classification label
        val = latest["value"]
        if val <= 24: classification = "Extreme Fear"
        elif val <= 44: classification = "Fear"
        elif val <= 54: classification = "Neutral"
        elif val <= 74: classification = "Greed"
        else: classification = "Extreme Greed"
        
        return _resp(True, "alternative.me", "fear_greed_index",
                    data={
                        "current_value": latest["value"],
                        "classification": classification,
                        "history": formatted,
                    },
                    value=latest["value"])
    
    except Exception as e:
        return _resp(False, "alternative.me", "fear_greed_index", None,
                   error=str(e))


# ══════════════════════════════════════════════════════════════════
# TOOLS — DefiLlama (Stablecoin data as sentiment proxy)
# ══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_stablecoin_info() -> Dict[str, Any]:
    """Get stablecoin market data from DefiLlama as a market sentiment proxy.
    
    Stablecoin supply expansion suggests bullish sentiment.
    Stablecoin contraction suggests bearish sentiment.
    """
    try:
        resp = await _dl_client().get("/stablecoins")
        resp.raise_for_status()
        result = resp.json()
        
        if isinstance(result, dict):
            pegged_assets = result.get("peggedAssets", [])
            total_mcap = sum(a.get("circulating", {}).get("peggedUSD", 0)
                           for a in pegged_assets[:10])
            
            top_stablecoins = []
            for a in sorted(pegged_assets,
                          key=lambda x: x.get("circulating", {}).get("peggedUSD", 0),
                          reverse=True)[:5]:
                top_stablecoins.append({
                    "name": a.get("name"),
                    "symbol": a.get("symbol"),
                    "circulating_usd": a.get("circulating", {}).get("peggedUSD", 0),
                    "price": a.get("price"),
                })
            
            return _resp(True, "defillama", "stablecoin_market",
                        data={
                            "total_stablecoin_mcap": total_mcap,
                            "top_stablecoins": top_stablecoins,
                            "stablecoin_count": len(pegged_assets),
                        },
                        value=total_mcap)
        
        return _resp(False, "defillama", "stablecoin_market", None,
                   error="Unexpected response format")
    
    except Exception as e:
        return _resp(False, "defillama", "stablecoin_market", None,
                   error=str(e))


# ══════════════════════════════════════════════════════════════════
# TOOLS — Combined
# ══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_sentiment_summary() -> Dict[str, Any]:
    """Get combined sentiment overview from all providers."""
    import asyncio
    
    fng_task = get_fear_greed_index(1)
    stable_task = get_stablecoin_info()
    btc_social_task = get_santiment_metric("social_volume", "bitcoin", 1)
    
    results = await asyncio.gather(
        fng_task, stable_task, btc_social_task,
        return_exceptions=True
    )
    
    def _safe(idx):
        return results[idx] if not isinstance(results[idx], Exception) else {"ok": False}
    
    return _resp(True, "combined", "sentiment_summary", data={
        "fear_greed_index": _safe(0),
        "stablecoin_market": _safe(1),
        "btc_social_volume": _safe(2),
    })


@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check if the MCP server and its providers are reachable."""
    results = {}
    
    # Alternative.me
    try:
        resp = await _alt_client().get("/fng/", params={"limit": "1"})
        results["alternative.me"] = {"status": "ok" if resp.status_code == 200 else "error"}
    except Exception as e:
        results["alternative.me"] = {"status": "error", "error": str(e)}
    
    # DefiLlama
    try:
        resp = await _dl_client().get("/stablecoins")
        results["defillama"] = {"status": "ok" if resp.status_code == 200 else "error"}
    except Exception as e:
        results["defillama"] = {"status": "error", "error": str(e)}
    
    # Santiment
    if SANTIMENT_API_KEY:
        try:
            resp = await _sant_client().post("", json={
                "query": "{ projects(page: 1, pageSize: 1) { slug } }"
            })
            results["santiment"] = {"status": "ok" if resp.status_code == 200 else "error"}
        except Exception as e:
            results["santiment"] = {"status": "error", "error": str(e)}
    else:
        results["santiment"] = {"status": "disabled", "reason": "No SANTIMENT_API_KEY"}
    
    all_ok = all(r.get("status") == "ok" for r in results.values())
    return _resp(all_ok, "crypto-sentiment-free-mcp", "health_check",
                data=results,
                error="" if all_ok else "Some providers unreachable")


def main():
    logger.info("Starting crypto-sentiment-free-mcp...")
    logger.info(f"Santiment API key configured: {bool(SANTIMENT_API_KEY)}")
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
