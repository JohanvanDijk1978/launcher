# 🚀 Viral Memecoin Launcher

Fully autonomous Solana bot that monitors Twitter/X and Reddit for viral trends,
then launches memecoins on Pump.fun — no human approval needed.

## Architecture

```
main.py                     ← Entry point + main loop
config.py                   ← All configuration
scrapers/
  nitter.py                 ← Twitter/X scraping (Nitter, no API key)
  reddit.py                 ← Reddit scraping (official API, free tier)
scoring/
  engine.py                 ← Virality scoring (keyword + velocity + sentiment)
generation/
  generator.py              ← AI coin names (OpenAI) + art (Replicate SDXL)
launcher/
  pumpfun.py                ← Pump.fun token creation + transaction submission
bot/
  telegram_bot.py           ← Telegram control panel + notifications
utils/
  wallet.py                 ← Solana wallet generation + management
  dedup.py                  ← Duplicate launch prevention
data/                       ← Runtime data (wallet, launch history, images)
```

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Required API keys
| Service | Purpose | Cost |
|---|---|---|
| Reddit API | Trend scraping | Free |
| OpenAI | Coin name generation | ~$0.001/launch |
| Replicate | Coin image (SDXL) | ~$0.01/launch |
| Telegram BotFather | Control panel | Free |

Nitter scraping requires **no API key**.

### 4. Solana wallet
On first run, the bot auto-generates a new Solana wallet and saves it to `data/wallet.json`.

```
⚠️  BACK UP YOUR WALLET FILE BEFORE FUNDING IT
```

Fund the wallet with SOL before running. Recommended starting balance: **2–5 SOL**.

### 5. Run
```bash
python main.py
```

## Telegram Commands
| Command | Action |
|---|---|
| `/status` | Show bot status + total launches |
| `/stop` | Pause launching |
| `/resume` | Resume launching |
| `/launches` | Show last 10 launched coins |
| `/help` | Show all commands |

## Virality Scoring

Each trend is scored 0.0–1.0 across three dimensions:

| Signal | Weight | Description |
|---|---|---|
| Keyword spike | 35% | Mention count vs baseline |
| Engagement velocity | 40% | Likes + shares + comments per cycle |
| Sentiment | 25% | Positive vs negative word ratio |

Threshold (default `0.65`) is configurable in `.env`.

## SOL Spend Strategy

SOL per launch scales dynamically with virality score:
- Score 0.65 → ~`BASE_SOL` (default 0.1 SOL)  
- Score 1.0 → up to `MAX_SOL` (default 1.0 SOL)

## Safety
- **Dedup**: Each trend key is tracked — never launched twice
- **Wallet isolation**: Dedicated bot wallet, separate from personal funds
- **Configurable limits**: Min score + max SOL enforced at all times

## Deploying to VPS
```bash
# On your VPS (same setup as memebot)
git clone https://github.com/JohanvanDijk1978/memecoin-bot  # or new repo
cd viral-launcher
pip install -r requirements.txt
cp .env.example .env && nano .env

# Run with screen or systemd
screen -S viral-launcher
python main.py
```
