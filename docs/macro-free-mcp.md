# macro-free-mcp

## Description
Free MCP server for macroeconomic data — interest rates, GDP, inflation, and central bank rates.

## Tools (6)
| Tool | Description |
|------|-------------|
| `get_fred_series` | Get FRED economic series (e.g., FEDFUNDS, GDP, CPI) |
| `get_fred_series_info` | Get metadata about a FRED series |
| `get_world_bank_indicator` | Get World Bank development indicators |
| `get_ecb_interest_rate` | Get ECB key interest rates |
| `get_macro_summary` | Aggregate macro summary |
| `health_check` | Server health and provider status |

## Required Credentials
| Variable | Required | Source | Notes |
|----------|----------|--------|-------|
| `FRED_API_KEY` | Yes* | [FRED API](https://fred.stlouisfed.org/docs/api/api_key.html) | Free key, 1000 requests/day. *Only needed for FRED tools — World Bank and ECB work without it |

## Providers
1. **FRED (St. Louis Fed)** — Free API key required
2. **World Bank** — Public API, no key needed
3. **ECB** — Public API, no key needed

## Start
```bash
cd macro-free-mcp
uv run python3 main.py
```
