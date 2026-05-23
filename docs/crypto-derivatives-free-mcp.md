# crypto-derivatives-free-mcp

## Description
Free MCP server for cryptocurrency derivatives data — open interest, funding rates, liquidations, and long/short ratios.

## Tools (7)
| Tool | Description |
|------|-------------|
| `get_open_interest` | Open interest for a symbol (Coinalyze → Binance Futures) |
| `get_funding_rate` | Current funding rate (Binance Futures → Bybit → OKX) |
| `get_liquidations` | Liquidation data (Coinalyze → Binance Futures) |
| `get_long_short_ratio` | Long/short ratio (Coinalyze → Binance Futures) |
| `get_derivatives_summary` | Aggregate summary of all metrics |
| `list_supported_symbols` | List available trading pairs |
| `health_check` | Server health and provider status |

## Required Credentials
| Variable | Required | Source | Notes |
|----------|----------|--------|-------|
| `COINALYZE_API_KEY` | No | [Coinalyze](https://coinalyze.io) | Free tier. Without it, falls back to Binance/Bybit/OKX public APIs |

## Providers (fallback chain)
1. **Coinalyze** — Free API key (recommended for best data)
2. **Binance Futures** — Public API, no key needed
3. **Bybit** — Public API, no key needed
4. **OKX** — Public API, no key needed

## Start
```bash
cd crypto-derivatives-free-mcp
uv run python3 main.py
```
