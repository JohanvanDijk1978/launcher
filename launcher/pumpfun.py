"""
Pump.fun launcher — creates and submits coin launch transactions on Solana.
Uses the Pump.fun program to mint and list the token.
"""

import logging
import json
import base64
from dataclasses import dataclass
from pathlib import Path

import httpx
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

from config import Config
from scoring.engine import ScoredTrend
from generation.generator import MetadataGenerator, CoinMetadata
from utils.wallet import WalletManager

logger = logging.getLogger("launcher.pumpfun")

PUMP_FUN_API = "https://pump.fun/api"
PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


@dataclass
class LaunchResult:
    success: bool
    coin_name: str = ""
    ticker: str = ""
    tx_sig: str = ""
    sol_spent: float = 0.0
    mint_address: str = ""
    error: str = ""


class PumpFunLauncher:
    def __init__(self, config: Config, wallet: WalletManager):
        self.config = config
        self.wallet = wallet
        self.generator = MetadataGenerator(config)
        self.rpc = AsyncClient(config.solana_rpc_url)

    async def launch(self, trend: ScoredTrend) -> LaunchResult:
        """Full launch pipeline: generate metadata → create token → buy initial supply."""
        try:
            # 1. Generate coin metadata (name, ticker, image)
            metadata = await self.generator.generate(trend)

            # 2. Upload metadata to IPFS via Pump.fun
            ipfs_uri = await self._upload_metadata(metadata)
            if not ipfs_uri:
                return LaunchResult(success=False, error="Metadata upload failed")

            # 3. Create the token on Pump.fun
            mint_keypair = Keypair()
            tx_sig, mint_address = await self._create_token(
                metadata=metadata,
                ipfs_uri=ipfs_uri,
                mint_keypair=mint_keypair,
                sol_amount=trend.sol_to_spend,
            )

            if not tx_sig:
                return LaunchResult(success=False, coin_name=metadata.name, error="Transaction failed")

            return LaunchResult(
                success=True,
                coin_name=metadata.name,
                ticker=metadata.ticker,
                tx_sig=tx_sig,
                sol_spent=trend.sol_to_spend,
                mint_address=mint_address,
            )

        except Exception as e:
            logger.exception(f"Launch failed for trend '{trend.label}': {e}")
            return LaunchResult(success=False, error=str(e))

    async def _upload_metadata(self, metadata: CoinMetadata) -> str | None:
        """
        Upload coin image + metadata to Pump.fun's IPFS endpoint.
        Returns the metadata URI.
        """
        try:
            image_path = Path(metadata.image_path)
            if not image_path.exists():
                raise FileNotFoundError(f"Image not found: {metadata.image_path}")

            async with httpx.AsyncClient(timeout=30) as client:
                with open(image_path, "rb") as img_file:
                    files = {
                        "file": (image_path.name, img_file, "image/png"),
                        "name": (None, metadata.name),
                        "symbol": (None, metadata.ticker),
                        "description": (None, metadata.description),
                        "twitter": (None, ""),
                        "telegram": (None, ""),
                        "website": (None, ""),
                        "showName": (None, "true"),
                    }
                    resp = await client.post(
                        f"{PUMP_FUN_API}/ipfs",
                        files=files,
                    )

                if resp.status_code != 200:
                    logger.error(f"IPFS upload failed: {resp.status_code} {resp.text}")
                    return None

                data = resp.json()
                uri = data.get("metadataUri", "")
                logger.info(f"Metadata uploaded: {uri}")
                return uri

        except Exception as e:
            logger.error(f"Metadata upload error: {e}")
            return None

    async def _create_token(
        self,
        metadata: CoinMetadata,
        ipfs_uri: str,
        mint_keypair: Keypair,
        sol_amount: float,
    ) -> tuple[str, str]:
        """
        Call Pump.fun API to get a create transaction, sign it, and submit.
        Returns (tx_signature, mint_address).
        """
        try:
            sol_lamports = int(sol_amount * 1_000_000_000)
            payer = self.wallet.keypair

            payload = {
                "publicKey": str(payer.pubkey()),
                "action": "create",
                "tokenMetadata": {
                    "name": metadata.name,
                    "symbol": metadata.ticker,
                    "uri": ipfs_uri,
                },
                "mint": str(mint_keypair.pubkey()),
                "denominatedInSol": "true",
                "amount": sol_amount,
                "slippage": 10,
                "priorityFee": 0.0005,
                "pool": "pump",
            }

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{PUMP_FUN_API}/trade-local",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

            if resp.status_code != 200:
                logger.error(f"Pump.fun API error: {resp.status_code} {resp.text}")
                return "", ""

            # Deserialize + sign transaction
            tx_bytes = resp.content
            tx = VersionedTransaction.from_bytes(tx_bytes)

            # Sign with both payer and mint keypair
            tx.sign([payer, mint_keypair])

            # Submit to Solana RPC
            result = await self.rpc.send_transaction(
                tx,
                opts={"skip_preflight": False, "preflight_commitment": Confirmed},
            )

            sig = str(result.value)
            mint_addr = str(mint_keypair.pubkey())

            logger.info(f"Transaction submitted: {sig}")
            logger.info(f"Mint address: {mint_addr}")

            return sig, mint_addr

        except Exception as e:
            logger.error(f"Token creation error: {e}")
            return "", ""
