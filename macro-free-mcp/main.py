"""
macro-free-mcp — MCP server for macroeconomic data
Sources: FRED (free key), World Bank (free, no key), ECB (free, no key)
Replaces: tradingeconomics-mcp (paid)
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

mcp = FastMCP("macro-free-mcp")

MCP_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(MCP_DIR)
ENV_FILE = os.path.join(PARENT_DIR, ".env")

_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 300  # 5 min for macro data (slower to change)

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
    for k in ["FRED_API_KEY"]:
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env

_env = _load_env()
FRED_API_KEY = _env.get("FRED_API_KEY", "")

_fred: Optional[httpx.AsyncClient] = None
_wb: Optional[httpx.AsyncClient] = None
_ecb: Optional[httpx.AsyncClient] = None

def _fred_client() -> httpx.AsyncClient:
    global _fred
    if _fred is None:
        _fred = httpx.AsyncClient(
            base_url="https://api.stlouisfed.org/fred",
            timeout=15.0
        )
    return _fred

def _wb_client() -> httpx.AsyncClient:
    global _wb
    if _wb is None:
        _wb = httpx.AsyncClient(
            base_url="https://api.worldbank.org/v2",
            timeout=15.0
        )
    return _wb

def _ecb_client() -> httpx.AsyncClient:
    global _ecb
    if _ecb is None:
        _ecb = httpx.AsyncClient(
            base_url="https://data-api.ecb.europa.eu/service",
            timeout=15.0
        )
    return _ecb

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
# TOOLS — FRED
# ══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_fred_series(series_id: str = "FEDFUNDS") -> Dict[str, Any]:
    """Get economic data series from FRED (Federal Reserve Economic Data).
    
    Common series IDs:
    - FEDFUNDS: Federal Funds Rate
    - CPIAUCSL: Consumer Price Index (CPI)
    - UNRATE: Unemployment Rate
    - GDP: Gross Domestic Product
    - DGS10: 10-Year Treasury Rate
    - DGS2: 2-Year Treasury Rate
    - T10Y2Y: 10Y-2Y Treasury Yield Spread
    - M2SL: M2 Money Supply
    - SP500: S&P 500
    
    Args:
        series_id: FRED series ID
    """
    if not FRED_API_KEY:
        return _resp(False, "fred", "series", None,
                   series_id=series_id,
                   error="FRED_API_KEY not configured")
    
    try:
        resp = await _fred_client().get("/series/observations", params={
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 10
        })
        resp.raise_for_status()
        result = resp.json()
        
        observations = result.get("observations", [])
        if not observations:
            return _resp(False, "fred", "series", None,
                       series_id=series_id,
                       error="No data found for series")

        latest = observations[0]
        value_str = latest.get("value", "")
        value = float(value_str) if value_str and value_str != "." else None
        
        formatted = []
        for obs in observations[:5]:
            v = obs.get("value", "")
            formatted.append({
                "date": obs.get("date"),
                "value": float(v) if v and v != "." else None
            })
        
        return _resp(True, "fred", "series",
                    series_id=series_id,
                    data={
                        "series_id": series_id,
                        "latest_value": value,
                        "latest_date": latest.get("date"),
                        "recent": formatted,
                        "realtime_start": latest.get("realtime_start"),
                        "realtime_end": latest.get("realtime_end"),
                    },
                    value=value)
    
    except httpx.HTTPStatusError as e:
        return _resp(False, "fred", "series", None,
                   series_id=series_id,
                   error=f"FRED API error: HTTP {e.response.status_code}")
    except Exception as e:
        return _resp(False, "fred", "series", None,
                   series_id=series_id,
                   error=str(e))


@mcp.tool()
async def get_fred_series_info(series_id: str = "FEDFUNDS") -> Dict[str, Any]:
    """Get metadata about a FRED series.
    
    Args:
        series_id: FRED series ID
    """
    if not FRED_API_KEY:
        return _resp(False, "fred", "series_info", None,
                   series_id=series_id,
                   error="FRED_API_KEY not configured")
    
    try:
        resp = await _fred_client().get("/series", params={
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json"
        })
        resp.raise_for_status()
        result = resp.json()
        seriess = result.get("seriess", [])
        if not seriess:
            return _resp(False, "fred", "series_info", None,
                       series_id=series_id,
                       error="Series not found")
        
        s = seriess[0]
        return _resp(True, "fred", "series_info",
                    series_id=series_id,
                    data={
                        "id": s.get("id"),
                        "title": s.get("title"),
                        "frequency": s.get("frequency"),
                        "units": s.get("units"),
                        "seasonal_adjustment": s.get("seasonal_adjustment"),
                        "last_updated": s.get("last_updated"),
                        "observation_start": s.get("observation_start"),
                        "observation_end": s.get("observation_end"),
                        "popularity": s.get("popularity"),
                        "notes": s.get("notes", "")[:500],
                    })
    
    except Exception as e:
        return _resp(False, "fred", "series_info", None,
                   series_id=series_id,
                   error=str(e))


# ══════════════════════════════════════════════════════════════════
# TOOLS — World Bank
# ══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_world_bank_indicator(indicator: str = "NY.GDP.MKTP.CD",
                                    country: str = "US",
                                    limit: int = 5) -> Dict[str, Any]:
    """Get World Bank data indicator for a country.
    
    Common indicators:
    - NY.GDP.MKTP.CD: GDP (current US$)
    - NY.GDP.PCAP.CD: GDP per capita (current US$)
    - FP.CPI.TOTL.ZG: Inflation (CPI %)
    - SL.UEM.TOTL.ZS: Unemployment (% of labor force)
    - BX.KLT.DINV.WD.GD.ZS: Foreign Direct Investment (% of GDP)
    - NY.GDP.DEFL.KD.ZG: GDP Deflator (annual %)
    
    Country codes: US, CN, JP, DE, FR, GB, CH, etc.
    
    Args:
        indicator: World Bank indicator code
        country: 2-letter country code
        limit: Number of years to return
    """
    try:
        url = f"/country/{country}/indicator/{indicator}"
        resp = await _wb_client().get(url, params={
            "format": "json",
            "per_page": str(limit),
            "sort": "desc"
        })
        resp.raise_for_status()
        result = resp.json()
        
        if not isinstance(result, list) or len(result) < 2:
            return _resp(False, "worldbank", "indicator", None,
                       series_id=indicator,
                       error="No data found")
        
        data_points = []
        for entry in result[1]:
            if entry.get("value"):
                data_points.append({
                    "year": entry.get("date"),
                    "value": float(entry["value"]) if entry["value"] else None,
                })
        
        if not data_points:
            return _resp(False, "worldbank", "indicator", None,
                       series_id=indicator,
                       error="No data values found")
        
        latest = data_points[0] if data_points else {}
        
        return _resp(True, "worldbank", "indicator",
                    series_id=indicator,
                    symbol=country,
                    data={
                        "indicator": indicator,
                        "country": country,
                        "latest_value": latest.get("value"),
                        "latest_year": latest.get("year"),
                        "data": data_points,
                    },
                    value=latest.get("value"))
    
    except Exception as e:
        return _resp(False, "worldbank", "indicator", None,
                   series_id=indicator, error=str(e))


# ══════════════════════════════════════════════════════════════════
# TOOLS — ECB
# ══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_ecb_interest_rate() -> Dict[str, Any]:
    """Get ECB main refinancing rate (key interest rate)."""
    try:
        # ECB SDMX API for key interest rate
        url = "/data/DFM/B.E.U2.EUR.4F.KR.DFR.LEV"
        resp = await _ecb_client().get(url, params={
            "format": "jsondata",
            "startPeriod": "2024-01-01",
        })
        resp.raise_for_status()
        result = resp.json()
        
        data_structure = result.get("structure", {})
        data_sets = result.get("dataSets", [])
        
        if data_sets and len(data_sets) > 0:
            series = data_sets[0].get("series", {})
            obs_dict = {}
            for key, val in series.get("0:0:0:0:0:0:0", {}).items():
                obs_dict[key] = val
            
            # Parse observations
            observations_map = {}
            for ds in data_sets:
                ser = ds.get("series", {})
                for sk, sv in ser.items():
                    obs = sv.get("observations", {})
                    for ok, ov in obs.items():
                        observations_map[ok] = ov[0] if ov else None
            
            return _resp(True, "ecb", "interest_rate",
                        data={
                            "rate_type": "Main Refinancing Rate",
                            "latest_value": list(observations_map.values())[-1] if observations_map else None,
                            "raw_observations": observations_map,
                        },
                        value=list(observations_map.values())[-1] if observations_map else None)
        
        return _resp(False, "ecb", "interest_rate", None,
                   error="Could not parse ECB data")
    
    except Exception as e:
        logger.error(f"ECB error: {e}")
        return _resp(False, "ecb", "interest_rate", None,
                   error=f"ECB API error: {str(e)[:200]}")


# ══════════════════════════════════════════════════════════════════
# TOOLS — Combined
# ══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_macro_summary() -> Dict[str, Any]:
    """Get a combined macroeconomic summary from all providers."""
    import asyncio
    
    fed_task = get_fred_series("FEDFUNDS")
    cpi_task = get_fred_series("CPIAUCSL")
    unemp_task = get_fred_series("UNRATE")
    gdp_task = get_fred_series("GDP")
    dgs10_task = get_fred_series("DGS10")
    ecb_task = get_ecb_interest_rate()
    
    results = await asyncio.gather(
        fed_task, cpi_task, unemp_task, gdp_task, dgs10_task, ecb_task,
        return_exceptions=True
    )
    
    def _safe(idx):
        return results[idx] if not isinstance(results[idx], Exception) else {"ok": False}
    
    return _resp(True, "combined", "macro_summary", data={
        "fed_funds_rate": _safe(0),
        "cpi": _safe(1),
        "unemployment": _safe(2),
        "gdp": _safe(3),
        "treasury_10y": _safe(4),
        "ecb_rate": _safe(5),
    })


@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check if the MCP server and its providers are reachable."""
    results = {}
    
    # FRED
    try:
        if FRED_API_KEY:
            resp = await _fred_client().get("/series", params={
                "series_id": "FEDFUNDS",
                "api_key": FRED_API_KEY,
                "file_type": "json"
            })
            results["fred"] = {"status": "ok" if resp.status_code == 200 else "error"}
        else:
            results["fred"] = {"status": "disabled", "reason": "No FRED_API_KEY"}
    except Exception as e:
        results["fred"] = {"status": "error", "error": str(e)}
    
    # World Bank
    try:
        resp = await _wb_client().get("/country/US/indicator/NY.GDP.MKTP.CD",
                                       params={"format": "json", "per_page": "1"})
        results["worldbank"] = {"status": "ok" if resp.status_code == 200 else "error"}
    except Exception as e:
        results["worldbank"] = {"status": "error", "error": str(e)}
    
    # ECB
    try:
        resp = await _ecb_client().get("/data/DFM/B.E.U2.EUR.4F.KR.DFR.LEV",
                                         params={"format": "jsondata"})
        results["ecb"] = {"status": "ok" if resp.status_code in (200, 400) else "error"}
    except Exception as e:
        results["ecb"] = {"status": "error", "error": str(e)}
    
    all_ok = all(r.get("status") == "ok" for r in results.values())
    return _resp(all_ok, "macro-free-mcp", "health_check",
                data=results,
                error="" if all_ok else "Some providers unreachable or missing API key")


def main():
    logger.info("Starting macro-free-mcp...")
    logger.info(f"FRED API key configured: {bool(FRED_API_KEY)}")
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
