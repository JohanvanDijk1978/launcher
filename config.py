"""
Configuration — loads from .env and provides typed access.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class Config:
    # Wallet
    wallet_path: str = "data/wallet.json"

    # Scraping
    nitter_instances: list[str] = field(default_factory=lambda: [
        "https://nitter.poast.org",
        "https://nitter.privacydev.net",
        "https://nitter.tiekoetter.com",
    ])
    nitter_keywords: list[str] = field(default_factory=lambda: [
        "coin", "token", "memecoin", "solana", "crypto", "pump", "moon", "rug"
    ])
    # Virality scoring thresholds
    min_virality_score: float = 0.65
    keyword_spike_weight: float = 0.35
    engagement_velocity_weight: float = 0.40
    sentiment_weight: float = 0.25

    # Launch config
    base_sol_per_launch: float = 0.1       # Minimum SOL to spend
    max_sol_per_launch: float = 1.0        # Maximum SOL to spend
    sol_scale_factor: float = 1.5          # Multiplier for virality score → SOL

    # Image generation (Replicate)
    replicate_api_token: str = ""
    image_model: str = "stability-ai/sdxl:39ed52f2319f9b7246f19a5cd3b7f58a58a49083c34c40a81b4b6b7d69c60d72"

    # Pump.fun / Solana
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    pumpfun_program_id: str = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

    # Telegram bot
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Misc
    poll_interval_seconds: int = 60
    dedup_db_path: str = "data/launched.json"
    openai_api_key: str = ""   # For name/ticker generation

    @classmethod
    def load(cls) -> "Config":
        load_dotenv()
        return cls(
            wallet_path=os.getenv("WALLET_PATH", "data/wallet.json"),
            nitter_instances=os.getenv("NITTER_INSTANCES", "").split(",") if os.getenv("NITTER_INSTANCES") else cls.__dataclass_fields__["nitter_instances"].default_factory(),
            min_virality_score=float(os.getenv("MIN_VIRALITY_SCORE", "0.65")),
            base_sol_per_launch=float(os.getenv("BASE_SOL", "0.1")),
            max_sol_per_launch=float(os.getenv("MAX_SOL", "1.0")),
            replicate_api_token=os.getenv("REPLICATE_API_TOKEN", ""),
            solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL", "60")),
            dedup_db_path=os.getenv("DEDUP_DB_PATH", "data/launched.json"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        )
