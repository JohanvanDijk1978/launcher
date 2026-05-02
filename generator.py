"""
Generation module — creates coin name, ticker, description, and logo image
based on a viral trend using OpenAI (names) and Replicate SDXL (images).
"""

import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx
import replicate
from openai import AsyncOpenAI

from config import Config
from scoring.engine import ScoredTrend

logger = logging.getLogger("generation")


@dataclass
class CoinMetadata:
    name: str
    ticker: str
    description: str
    image_path: str   # Local path to generated image file


class MetadataGenerator:
    def __init__(self, config: Config):
        self.config = config
        self.openai = AsyncOpenAI(api_key=config.openai_api_key)
        self.replicate_token = config.replicate_api_token

    async def generate(self, trend: ScoredTrend) -> CoinMetadata:
        """Generate full coin metadata for a trend."""
        logger.info(f"Generating metadata for trend: {trend.label}")

        # Generate name + ticker + description via Claude/OpenAI
        name, ticker, description = await self._generate_name(trend)
        logger.info(f"Generated: {name} (${ticker})")

        # Generate coin art
        image_path = await self._generate_image(trend, name)
        logger.info(f"Image saved: {image_path}")

        return CoinMetadata(
            name=name,
            ticker=ticker,
            description=description,
            image_path=image_path,
        )

    async def _generate_name(self, trend: ScoredTrend) -> tuple[str, str, str]:
        """
        Use OpenAI to generate a creative coin name + ticker based on the trend.
        Mix of: using the trend name directly + creative spin.
        """
        prompt = f"""You are a memecoin naming expert. A trend is going viral: "{trend.label}"

Generate a memecoin name, ticker, and short description. Rules:
- Name: 1-4 words, punchy and meme-worthy. Sometimes use the trend name directly (e.g. "PEPE"), sometimes put a funny spin on it (e.g. "Pepe on Solana" → "SPEPE"). Be creative.
- Ticker: 3-6 uppercase letters, derived from the name
- Description: 1-2 sentences, hype-y and fun, max 200 chars

Respond ONLY in this exact format (no other text):
NAME: <name>
TICKER: <ticker>
DESCRIPTION: <description>"""

        try:
            response = await self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.9,
            )
            text = response.choices[0].message.content.strip()
            return self._parse_name_response(text, trend)
        except Exception as e:
            logger.warning(f"OpenAI name generation failed: {e}, using fallback")
            return self._fallback_name(trend)

    def _parse_name_response(self, text: str, trend: ScoredTrend) -> tuple[str, str, str]:
        """Parse OpenAI response into (name, ticker, description)."""
        try:
            name_match = re.search(r"NAME:\s*(.+)", text)
            ticker_match = re.search(r"TICKER:\s*([A-Z]{2,8})", text)
            desc_match = re.search(r"DESCRIPTION:\s*(.+)", text, re.DOTALL)

            name = name_match.group(1).strip() if name_match else trend.label
            ticker = ticker_match.group(1).strip() if ticker_match else trend.key[:5].upper()
            description = desc_match.group(1).strip()[:200] if desc_match else f"The official memecoin of {trend.label}"

            return name, ticker, description
        except Exception:
            return self._fallback_name(trend)

    def _fallback_name(self, trend: ScoredTrend) -> tuple[str, str, str]:
        """Simple fallback if AI generation fails."""
        label = trend.label.lstrip("#$").strip()
        name = label[:30]
        ticker = re.sub(r"[^A-Z]", "", label.upper())[:6] or "MEME"
        description = f"The viral memecoin inspired by {label}. To the moon! 🚀"
        return name, ticker, description

    async def _generate_image(self, trend: ScoredTrend, coin_name: str) -> str:
        """
        Generate coin art using Replicate SDXL.
        Returns path to saved image file.
        """
        prompt = (
            f"A funny, colorful meme coin logo for a cryptocurrency called '{coin_name}'. "
            f"Inspired by the viral trend: {trend.label}. "
            "Cartoon style, bright colors, simple design, circular logo format, "
            "white background, professional crypto token art, no text."
        )

        try:
            import replicate as rep
            client = rep.Client(api_token=self.replicate_token)

            output = client.run(
                self.config.image_model,
                input={
                    "prompt": prompt,
                    "negative_prompt": "text, words, letters, blurry, dark, realistic photo",
                    "width": 512,
                    "height": 512,
                    "num_outputs": 1,
                    "num_inference_steps": 25,
                    "guidance_scale": 7.5,
                }
            )

            # Download the image
            image_url = output[0] if isinstance(output, list) else str(output)
            return await self._download_image(image_url, trend.key)

        except Exception as e:
            logger.warning(f"Replicate image generation failed: {e}, using placeholder")
            return await self._create_placeholder_image(coin_name)

    async def _download_image(self, url: str, key: str) -> str:
        """Download image from URL and save locally."""
        path = Path("data") / f"img_{key}.png"
        path.parent.mkdir(exist_ok=True)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            path.write_bytes(resp.content)

        return str(path)

    async def _create_placeholder_image(self, coin_name: str) -> str:
        """Create a simple placeholder PNG if image generation fails."""
        from PIL import Image, ImageDraw, ImageFont
        import io

        img = Image.new("RGB", (512, 512), color=(255, 165, 0))
        draw = ImageDraw.Draw(img)

        # Draw text in center
        initial = (coin_name[0] if coin_name else "?").upper()
        draw.ellipse([56, 56, 456, 456], fill=(255, 200, 0), outline=(200, 100, 0), width=8)
        draw.text((256, 256), initial, fill=(100, 50, 0), anchor="mm")

        path = Path("data") / f"placeholder_{coin_name[:8]}.png"
        path.parent.mkdir(exist_ok=True)
        img.save(str(path))
        return str(path)
