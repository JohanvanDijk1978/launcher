"""
Viral Memecoin Launcher — Main Entry Point
Monitors Twitter/X (Nitter) + Reddit for viral trends,
then autonomously launches memecoins on Pump.fun.
"""

import asyncio
import logging
from config import Config
from scrapers.nitter import NitterScraper
from scoring.engine import ViralityEngine
from launcher.pumpfun import PumpFunLauncher
from bot.telegram_bot import TelegramBot
from utils.wallet import WalletManager
from utils.dedup import DedupStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


async def main():
    config = Config.load()

    # Init wallet (generates one if not found)
    wallet = WalletManager(config)
    wallet.ensure_wallet()

    # Init dedup store (tracks launched trends)
    dedup = DedupStore(config.dedup_db_path)

    # Init scrapers
    nitter = NitterScraper(config)

    # Init scoring engine
    engine = ViralityEngine(config)

    # Init launcher
    launcher = PumpFunLauncher(config, wallet)

    # Init Telegram control bot
    tg_bot = TelegramBot(config, launcher, dedup)

    logger.info("🚀 Viral Launcher starting up...")
    logger.info(f"Wallet: {wallet.public_key}")

    # Run Telegram bot + main loop concurrently
    await asyncio.gather(
        tg_bot.start(),
        run_loop(config, nitter, engine, launcher, dedup, tg_bot),
    )


async def run_loop(config, nitter, engine, launcher, dedup, tg_bot):
    """Main polling loop — scrape → score → launch."""
    while True:
        try:
            logger.info("🔍 Scraping for trends...")

            all_trends = await nitter.get_trends()

            # Score each trend
            scored = engine.score_all(all_trends)

            # Filter by threshold + dedup
            candidates = [
                t for t in scored
                if t.score >= config.min_virality_score
                and not dedup.is_launched(t.key)
            ]

            if not candidates:
                logger.info("No viral candidates this cycle.")
            else:
                # Pick the highest-scoring trend
                best = max(candidates, key=lambda t: t.score)
                logger.info(f"🔥 Viral trend detected: '{best.label}' (score={best.score:.2f})")

                # Launch it
                result = await launcher.launch(best)

                if result.success:
                    dedup.mark_launched(best.key)
                    msg = (
                        f"✅ Launched *{result.coin_name}* (${result.ticker})\n"
                        f"Trend: {best.label}\n"
                        f"Score: {best.score:.2f}\n"
                        f"SOL spent: {result.sol_spent}\n"
                        f"Tx: `{result.tx_sig}`"
                    )
                    await tg_bot.notify(msg)
                    logger.info(f"✅ Launch success: {result.coin_name} | tx={result.tx_sig}")
                else:
                    logger.error(f"❌ Launch failed: {result.error}")
                    await tg_bot.notify(f"❌ Launch failed for *{best.label}*: {result.error}")

        except Exception as e:
            logger.exception(f"Loop error: {e}")

        await asyncio.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
