# OI Hunter

A Telegram bot that monitors MEXC futures markets and generates trading signals based on Open Interest analysis, funding rates, order book pressure, and momentum indicators.

## What It Does

OI Hunter continuously scans 800+ MEXC perpetual futures contracts every 60 seconds, runs each token through 8 specialized analyzers, and sends a Telegram alert when multiple signals align above a confidence threshold.

**Signal types:**
- `LONG` — momentum building, short squeeze setup, OI surging with price
- `SHORT` — long liquidation cascade, distribution, OI collapsing

## How It Works

Each scan cycle fetches market data and runs it through a weighted scoring system:

| Analyzer | What it detects | Weight |
|---|---|---|
| OI/MC Ratio | Futures leverage relative to market cap | 2.0 |
| Aggression | Buy vs sell aggression (5m and 2h) | 1.5 |
| OI Nowcast | OI velocity and acceleration in real time | 1.5 |
| Funding Rate | FR level + directional velocity | 1.0 |
| Liquidation | 4 patterns: cascade, pre-cascade, distribution, bearish confirm | 1.0 |
| Volume Spike | Unusual volume vs 24h baseline | 1.0 |
| Order Book | Bid/ask imbalance, wall detection, near-term pressure | 1.0 |
| Already Pumped | Filters tokens that already moved significantly | 0.5 |

A signal is generated when:
- Combined score ≥ 6.5 / 10
- At least 1 kinetic indicator (Volume, Aggression, or OI Nowcast) scores ≥ 6.0
- No critical blockers are active

## Features

- Scans 800+ MEXC futures symbols automatically
- OI history stored in SQLite — enables velocity and acceleration tracking
- 5-minute cooldown per symbol to prevent spam
- `[LC]` flag for low market cap tokens (< $30M)
- Market cap lookup via CoinGecko with CoinPaprika fallback
- 4 liquidation patterns including pre-cascade detection
- Funding rate transition tracking (negative → positive = short covering)

## Signal Format

```
🟢🟢🟢 LONG SIGNAL: BTCUSDT
Score: 8.2/10  (7 analyzers)

Price:   $95,420
OI:      $124,500,000
OI/MC:   0.0821
OI Δ1h:  +12.3%
FR:      -0.0310%
Vol 24h: $892,340,000

[OB] Bids dominate 1.8x — moderate buy pressure
[OI Nowcast] [SURGING] Velocity: +45,200 USD/min | 5m: +1.2%
```

## Requirements

- Python 3.10+
- MEXC account (API key not required for public endpoints)
- Telegram bot token

## Installation

```bash
git clone https://github.com/br1maks/oi-hunter.git
cd oi-hunter
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

## Usage

```bash
# Analyze a single token
python -m src analyze BTCUSDT

# Start the monitor (scans all symbols, no bot)
python -m src monitor

# Start the full bot (monitor + Telegram alerts)
python -m src bot
```

## Project Structure

```
src/
├── analyzers/     # 8 signal analyzers
├── api/           # MEXC REST client
├── bot/           # Telegram bot, formatters, alerter
├── core/          # Scanner, monitor, signal generator, OI tracker
├── data/          # Data aggregator, market cap cache
├── database/      # SQLite OI history
└── models/        # Signal, MarketData, AnalyzerResult
```

## Configuration

Key thresholds (in `src/core/signal_generator.py`):

| Parameter | Default | Description |
|---|---|---|
| `MIN_SIGNAL_SCORE` | 6.5 | Minimum score to generate a signal |
| `KINETIC_MIN_SCORE` | 6.0 | Minimum kinetic indicator score required |
| `COOLDOWN_MINUTES` | 5 | Per-symbol cooldown between alerts |

## Disclaimer

This tool is for informational purposes only. Crypto futures trading involves significant risk. Always do your own research before entering any trade.
