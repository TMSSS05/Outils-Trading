# crypto-sentiment-free-mcp

## Description
Free MCP server for cryptocurrency sentiment data — Fear & Greed Index, stablecoin flows, and on-chain sentiment metrics.

## Tools (5)
| Tool | Description |
|------|-------------|
| `get_santiment_metric` | Get on-chain metric from Santiment (e.g., daily_active_addresses, network_growth) |
| `get_fear_greed_index` | Current Crypto Fear & Greed Index (Alternative.me) |
| `get_stablecoin_info` | Stablecoin supply and market cap info |
| `get_sentiment_summary` | Aggregate sentiment summary |
| `health_check` | Server health and provider status |

## Required Credentials
| Variable | Required | Source | Notes |
|----------|----------|--------|-------|
| `SANTIMENT_API_KEY` | No | [Santiment](https://app.santiment.net/) | Free tier available. Without it, falls back to Alternative.me + DefiLlama public APIs |

## Providers (fallback chain)
1. **Santiment** — Free API key (on-chain metrics)
2. **Alternative.me** — Public API, no key needed (Fear & Greed Index)
3. **DefiLlama** — Public API, no key needed (stablecoin data)

## Start
```bash
cd crypto-sentiment-free-mcp
uv run python3 main.py
```
