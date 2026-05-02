"""
Nitter scraper — scrapes trending tweets/hashtags from Nitter instances.
No Twitter API key required.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from config import Config

logger = logging.getLogger("scrapers.nitter")


@dataclass
class RawTrend:
    source: str          # "twitter" or "reddit"
    label: str           # Human-readable trend label
    key: str             # Normalized dedup key
    mentions: int        # Mention/post count
    engagement: int      # Likes + shares + comments
    sentiment_raw: list[str]  # Raw text for sentiment analysis
    fetched_at: datetime = None

    def __post_init__(self):
        if self.fetched_at is None:
            self.fetched_at = datetime.now(timezone.utc)


class NitterScraper:
    def __init__(self, config: Config):
        self.config = config
        self.instances = config.nitter_instances
        self.keywords = config.nitter_keywords

    async def get_trends(self) -> list[RawTrend]:
        """Scrape trending hashtags and keyword spikes from Nitter."""
        trends = []

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            # 1. Scrape trending hashtags from each instance
            hashtag_trends = await self._scrape_trending(client)
            trends.extend(hashtag_trends)

            # 2. Search for memecoin-related keywords
            keyword_trends = await self._scrape_keywords(client)
            trends.extend(keyword_trends)

        # Merge duplicates
        merged = self._merge_trends(trends)
        logger.info(f"Twitter: found {len(merged)} trends")
        return merged

    async def _scrape_trending(self, client: httpx.AsyncClient) -> list[RawTrend]:
        """Try each Nitter instance for trending topics."""
        for instance in self.instances:
            try:
                url = f"{instance}/explore/tabs/trending"
                resp = await client.get(url, headers=self._headers())
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                trends = []

                # Nitter trending page structure
                for item in soup.select(".trend-item, .trending-card, .trend"):
                    label_el = item.select_one(".trend-name, h2, .trend-link")
                    count_el = item.select_one(".trend-count, .tweet-count")

                    if not label_el:
                        continue

                    label = label_el.get_text(strip=True)
                    count_text = count_el.get_text(strip=True) if count_el else "0"
                    count = self._parse_count(count_text)

                    if label.startswith("#"):
                        key = label.lstrip("#").lower()
                    else:
                        key = re.sub(r"[^a-z0-9]", "", label.lower())

                    trends.append(RawTrend(
                        source="twitter",
                        label=label,
                        key=key,
                        mentions=count,
                        engagement=count * 3,  # Estimate
                        sentiment_raw=[label],
                    ))

                if trends:
                    logger.info(f"Got {len(trends)} trending topics from {instance}")
                    return trends

            except Exception as e:
                logger.warning(f"Nitter instance {instance} failed: {e}")
                continue

        return []

    async def _scrape_keywords(self, client: httpx.AsyncClient) -> list[RawTrend]:
        """Search for keyword-based trends across Nitter instances."""
        trends = []
        instance = self.instances[0]  # Use primary instance

        for keyword in self.keywords[:5]:  # Limit to avoid rate limits
            try:
                url = f"{instance}/search?q={keyword}&f=tweets"
                resp = await client.get(url, headers=self._headers())
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                tweets = soup.select(".timeline-item, .tweet")

                if not tweets:
                    continue

                texts = []
                total_engagement = 0

                for tweet in tweets[:20]:
                    text_el = tweet.select_one(".tweet-content, .tweet-text")
                    stats = tweet.select(".tweet-stat")

                    if text_el:
                        texts.append(text_el.get_text(strip=True))

                    for stat in stats:
                        count_text = stat.get_text(strip=True)
                        total_engagement += self._parse_count(count_text)

                if texts:
                    trends.append(RawTrend(
                        source="twitter",
                        label=f"#{keyword}",
                        key=keyword.lower(),
                        mentions=len(tweets),
                        engagement=total_engagement,
                        sentiment_raw=texts,
                    ))

                await asyncio.sleep(1)  # Be polite

            except Exception as e:
                logger.warning(f"Keyword search failed for '{keyword}': {e}")

        return trends

    def _merge_trends(self, trends: list[RawTrend]) -> list[RawTrend]:
        """Merge duplicate trends by key."""
        merged = {}
        for t in trends:
            if t.key in merged:
                existing = merged[t.key]
                existing.mentions += t.mentions
                existing.engagement += t.engagement
                existing.sentiment_raw.extend(t.sentiment_raw)
            else:
                merged[t.key] = t
        return list(merged.values())

    def _parse_count(self, text: str) -> int:
        """Parse '1.2K', '5M', '300' into int."""
        text = text.strip().replace(",", "")
        try:
            if "K" in text.upper():
                return int(float(text.upper().replace("K", "")) * 1_000)
            if "M" in text.upper():
                return int(float(text.upper().replace("M", "")) * 1_000_000)
            return int(re.sub(r"[^\d]", "", text) or 0)
        except Exception:
            return 0

    def _headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (compatible; viral-launcher/1.0)",
            "Accept-Language": "en-US,en;q=0.9",
        }
