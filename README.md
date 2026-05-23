<div align="center">

# 🛠️ Outils Trading

### *Free, self-hosted MCP servers for traders & quantitative analysts*

<br/>

![Status](https://img.shields.io/badge/Status-Active-00D4AA?style=for-the-badge&labelColor=0c1118)
![License](https://img.shields.io/badge/License-MIT-00D4AA?style=for-the-badge&labelColor=0c1118)
![MCP](https://img.shields.io/badge/Protocol-MCP-7C3AED?style=for-the-badge&labelColor=0c1118)
![Python](https://img.shields.io/badge/Python-3.12+-0891B2?style=for-the-badge&labelColor=0c1118)

<br/>

<p align="center">
  <strong>📊 4 MCP Servers · 26 Tools · 11 Providers · Zero Cost</strong>
</p>

<p align="center">
  Market data, derivatives, macroeconomics, and sentiment analysis —<br/>
  all free, all local, all yours.
</p>

<br/>

---

[📦 Servers](#-servers) •
[🚀 Quick Start](#-quick-start) •
[🔧 Configuration](#-configuration) •
[📖 Docs](#-documentation) •
[🏗️ Architecture](#-architecture) •
[📊 Providers](#-providers)

---

<br/>

</div>

## 📦 Servers

This repository provides **4 free MCP servers** that replace expensive paid trading data APIs:

| Server | Tools | Data Type | Replaces |
|--------|:-----:|-----------|----------|
| [**crypto-derivatives-free-mcp**](./crypto-derivatives-free-mcp/) | 7 | Open interest, funding rates, liquidations, long/short ratios | CoinGlass (paid) |
| [**crypto-market-free-mcp**](./crypto-market-free-mcp/) | 8 | Coin prices, market caps, trending coins, DeFi TVL | CoinGecko Pro (paid) |
| [**macro-free-mcp**](./macro-free-mcp/) | 6 | Interest rates, GDP, CPI, ECB rates | TradingEconomics (paid) |
| [**crypto-sentiment-free-mcp**](./crypto-sentiment-free-mcp/) | 5 | Fear & Greed, on-chain metrics, stablecoin flows | Santiment (paid) |
| **Total** | **26** | — | — |

Each server follows the **MCP (Model Context Protocol)** and can be used with any MCP-compatible client (Claude Desktop, OpenCode, Cursor, etc.).

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)

### 1. Clone
```bash
git clone https://github.com/vakandi/outils-trading.git
cd outils-trading
```

### 2. Start a server
```bash
# For example, start the market data server
cd crypto-market-free-mcp
uv run python3 main.py
```

### 3. Configure your MCP client
Add the server to your MCP config (e.g., `mcp_servers.json`):

```json
{
  "mcpServers": {
    "crypto-market-free-mcp": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/outils-trading/crypto-market-free-mcp",
        "run", "python", "main.py"
      ],
      "transport": "stdio-python",
      "env": {
        "COINGECKO_API_KEY": "your-demo-key-here"
      }
    }
  }
}
```

### 4. (Optional) Set API keys
```bash
export COINGECKO_API_KEY="your-key"
export FRED_API_KEY="your-key"
# Then start the server
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Used By | Required | Get It |
|----------|---------|:--------:|--------|
| `COINGECKO_API_KEY` | crypto-market-free-mcp | No | [CoinGecko API](https://www.coingecko.com/en/api) — free demo key |
| `FRED_API_KEY` | macro-free-mcp | Yes* | [FRED API](https://fred.stlouisfed.org/docs/api/api_key.html) — free |
| `COINALYZE_API_KEY` | crypto-derivatives-free-mcp | No | [Coinalyze](https://coinalyze.io) — free tier |
| `SANTIMENT_API_KEY` | crypto-sentiment-free-mcp | No | [Santiment](https://app.santiment.net/) — free tier |

*\*FRED key is only required for FRED tools. World Bank and ECB work without any key.*

### Fallback Chains
Every server has a **fallback chain** — if the primary provider fails, it tries the next one automatically. No key = no problem for most tools.

| Server | Primary | Fallback 1 | Fallback 2 |
|--------|---------|------------|------------|
| crypto-derivatives | Coinalyze | Binance Futures | Bybit / OKX |
| crypto-market | CoinGecko | DefiLlama | Binance Spot |
| macro | FRED | World Bank | ECB |
| crypto-sentiment | Santiment | Alternative.me | DefiLlama |

---

## 📖 Documentation

Each server has its own documentation file in the [`docs/`](./docs/) directory:

| Server | Doc | Details |
|--------|:---:|---------|
| crypto-derivatives-free-mcp | [📄](./docs/crypto-derivatives-free-mcp.md) | All 7 tools, credentials, fallback chain |
| crypto-market-free-mcp | [📄](./docs/crypto-market-free-mcp.md) | All 8 tools, credentials, fallback chain |
| macro-free-mcp | [📄](./docs/macro-free-mcp.md) | All 6 tools, credentials, provider details |
| crypto-sentiment-free-mcp | [📄](./docs/crypto-sentiment-free-mcp.md) | All 5 tools, credentials, fallback chain |

---

## 🏗️ Architecture

```
                    ┌─────────────────────────────┐
                    │     MCP Client (Claude)      │
                    │   OpenCode · Cursor · etc.    │
                    └──────────┬──────────────────┘
                               │ MCP stdio protocol
                               ▼
     ┌─────────────────────────────────────────────┐
     │              outils-trading/                 │
     ├──────────────────┬────────────────┬─────────┤
     │ Derivatives      │ Market         │ Macro   │
     │ Free MCP         │ Free MCP       │ Free MCP│
     ├──────────────────┼────────────────┼─────────┤
     │ Sentiment        │                │         │
     │ Free MCP         │                │         │
     └──────────────────┴────────────────┴─────────┘
            │              │          │        │
       ┌────┴────┐   ┌────┴───┐  ┌───┴────┐  └──────┐
       │Coinalyze│   │Coin-   │  │FRED    │  Santiment│
       │Binance  │   │Gecko   │  │World   │  Alt.me   │
       │Bybit    │   │Defi-   │  │Bank    │  DefiLlama│
       │OKX      │   │Llama   │  │ECB     │           │
       └─────────┘   └────────┘  └────────┘  ────────┘
```

### Normalized Response Format

All tools return data in a consistent JSON format:

```json
{
  "ok": true,
  "source": "binance_futures",
  "metric": "open_interest",
  "symbol": "BTCUSDT",
  "data": { "openInterest": "123456.78", "timestamp": "2026-05-23T18:18:42Z" },
  "value": 123456.78,
  "cache_used": false,
  "fallback_used": true
}
```

| Field | Description |
|-------|-------------|
| `ok` | Success status |
| `source` | Which provider served the data |
| `metric` | What was requested |
| `symbol` / `series_id` | What instrument or series |
| `data` | Payload with relevant fields |
| `value` | Numeric value (when applicable) |
| `cache_used` | Whether response came from cache |
| `fallback_used` | Whether a fallback provider was used |

### Caching

All servers implement in-memory caching:
- **60s TTL** — Fast-changing data (derivatives, market prices)
- **300s TTL** — Slow-changing data (macro, sentiment)

This prevents hitting rate limits and improves response times.

---

## 📊 Providers

| Provider | Type | Key Needed | Reliability | Limits |
|----------|------|:----------:|:-----------:|--------|
| **Binance** | Crypto Exchange | No | 🟢 High | 1200 req/min |
| **CoinGecko** | Market Data | Free demo | 🟢 High | 30 req/min |
| **DefiLlama** | DeFi Data | No | 🟢 High | Unlimited |
| **Alternative.me** | Sentiment | No | 🟢 High | Unlimited |
| **FRED** | Macro Data | Free | 🟢 High | 1000 req/day |
| **World Bank** | Macro Data | No | 🟢 High | Unlimited |
| **ECB** | Interest Rates | No | 🟢 High | Unlimited |
| **Coinalyze** | Derivatives | Free tier | 🟡 Medium | ~30 req/min |
| **Bybit** | Crypto Exchange | No | 🟢 High | Unlimited |
| **OKX** | Crypto Exchange | No | 🟢 High | Unlimited |
| **Santiment** | On-chain | Free tier | 🟡 Medium | 10 req/min |

---

## 🛡️ Security

- **No API keys in source code** — all keys loaded from environment variables
- **No hardcoded credentials** — each server uses `os.getenv()` at runtime
- **Graceful degradation** — if a key is missing, the server uses fallback providers or returns a clear error
- **Rate limit aware** — caching prevents hitting provider limits

---

## 🤝 Contributing

PRs welcome! Ideas for additional free providers:
- Yahoo Finance (stocks, ETFs)
- Alpha Vantage (forex, stocks)
- Glassnode (on-chain, free tier)
- Messari (crypto fundamentals)

---

## 📜 License

```
MIT License — Free for everyone, forever.

Copyright (c) 2026 Vakandi
```

<div align="center">
  <br/>
  <sub>Made with ❤️ for the trading community.</sub>
  <br/>
  <sub>Not financial advice. Trade at your own risk.</sub>
</div>
