"""
Wallet manager — generates and loads a Solana keypair.
Saves to disk on first run; loads on subsequent runs.
"""

import json
import logging
from pathlib import Path

from solders.keypair import Keypair

from config import Config

logger = logging.getLogger("utils.wallet")


class WalletManager:
    def __init__(self, config: Config):
        self.config = config
        self._keypair: Keypair | None = None

    def ensure_wallet(self):
        """Load wallet from disk, or generate a new one."""
        path = Path(self.config.wallet_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            self._load(path)
        else:
            self._generate(path)

    def _generate(self, path: Path):
        """Generate a fresh keypair and save to disk."""
        kp = Keypair()
        data = {"private_key": list(bytes(kp))}
        path.write_text(json.dumps(data, indent=2))
        self._keypair = kp

        logger.info("=" * 60)
        logger.info("NEW WALLET GENERATED")
        logger.info(f"Public key:  {kp.pubkey()}")
        logger.info(f"Saved to:    {path}")
        logger.warning("⚠️  BACK UP YOUR WALLET FILE BEFORE FUNDING IT!")
        logger.info("=" * 60)

    def _load(self, path: Path):
        """Load existing keypair from disk."""
        try:
            data = json.loads(path.read_text())
            raw = bytes(data["private_key"])
            self._keypair = Keypair.from_bytes(raw)
            logger.info(f"Wallet loaded: {self._keypair.pubkey()}")
        except Exception as e:
            raise RuntimeError(f"Failed to load wallet from {path}: {e}")

    @property
    def keypair(self) -> Keypair:
        if not self._keypair:
            raise RuntimeError("Wallet not initialized. Call ensure_wallet() first.")
        return self._keypair

    @property
    def public_key(self) -> str:
        return str(self.keypair.pubkey())
