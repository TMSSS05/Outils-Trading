# crypto-market-free-mcp

## Description
Free MCP server for cryptocurrency market data — prices, market caps, trending coins, and DeFi TVL.

## Tools (8)
| Tool | Description |
|------|-------------|
| `get_coin_price` | Current price for a coin (CoinGecko) |
| `get_coin_market_data` | Full market data (price, mcap, volume, supply) |
| `get_top_coins` | Top N coins by market cap |
| `get_trending_coins` | Currently trending coins |
| `get_defi_tvl` | Total Value Locked for a protocol (DefiLlama) |
| `get_market_summary` | Aggregate market summary |
| `list_supported_coins` | List available coins |
| `health_check` | Server health and provider status |

## Required Credentials
| Variable | Required | Source | Notes |
|----------|----------|--------|-------|
| `COINGECKO_API_KEY` | No | [CoinGecko](https://www.coingecko.com/en/api) | Free demo key (30 req/min). Without it, uses DefiLlama + Binance public APIs |

## Providers (fallback chain)
1. **CoinGecko** — Free demo API key (recommended for best data)
2. **DefiLlama** — Public API, no key needed
3. **Binance Spot** — Public API, no key needed

## Start
```bash
cd crypto-market-free-mcp
uv run python3 main.py
```
