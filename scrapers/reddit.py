"""
Reddit scraper — uses asyncpraw (official Reddit API, free tier).
Monitors crypto/memecoin subreddits for viral posts.
"""

import re
import logging

import asyncpraw
from asyncprawcore.exceptions import AsyncPrawcoreException

from config import Config
from scrapers.nitter import RawTrend

logger = logging.getLogger("scrapers.reddit")


class RedditScraper:
    def __init__(self, config: Config):
        self.config = config
        self.subreddits = config.reddit_subreddits

    def _make_client(self):
        return asyncpraw.Reddit(
            client_id=self.config.reddit_client_id,
            client_secret=self.config.reddit_client_secret,
            user_agent=self.config.reddit_user_agent,
        )

    async def get_trends(self) -> list[RawTrend]:
        trends = []
        async with self._make_client() as reddit:
            for sub_name in self.subreddits:
                try:
                    sub_trends = await self._scrape_subreddit(reddit, sub_name)
                    trends.extend(sub_trends)
                except AsyncPrawcoreException as e:
                    logger.warning(f"Reddit API error on r/{sub_name}: {e}")
                except Exception as e:
                    logger.warning(f"Unexpected error on r/{sub_name}: {e}")

        merged = self._merge_trends(trends)
        logger.info(f"Reddit: found {len(merged)} trends")
        return merged

    async def _scrape_subreddit(self, reddit, sub_name: str) -> list[RawTrend]:
        trends = []
        sub = await reddit.subreddit(sub_name)

        async for post in sub.hot(limit=25):
            trend = await self._post_to_trend(post, sub_name)
            if trend:
                trends.append(trend)

        async for post in sub.rising(limit=15):
            trend = await self._post_to_trend(post, sub_name)
            if trend:
                trends.append(trend)

        return trends

    async def _post_to_trend(self, post, sub_name: str) -> RawTrend | None:
        try:
            engagement = post.score + (post.num_comments * 5)
            key = self._extract_key(post.title)
            if not key:
                return None

            texts = [post.title]
            try:
                await post.comments.replace_more(limit=0)
                for comment in list(post.comments)[:10]:
                    if hasattr(comment, "body"):
                        texts.append(comment.body)
            except Exception:
                pass

            return RawTrend(
                source="reddit",
                label=post.title[:80],
                key=key,
                mentions=1,
                engagement=engagement,
                sentiment_raw=texts,
            )
        except Exception as e:
            logger.debug(f"Failed to parse post: {e}")
            return None

    def _extract_key(self, title: str) -> str | None:
        ticker_match = re.search(r"\$([A-Z]{2,8})", title)
        if ticker_match:
            return ticker_match.group(1).lower()

        caps_match = re.search(r"\b([A-Z]{3,10})\b", title)
        if caps_match:
            return caps_match.group(1).lower()

        hashtag_match = re.search(r"#(\w+)", title)
        if hashtag_match:
            return hashtag_match.group(1).lower()

        words = re.findall(r"\b[a-zA-Z]{4,}\b", title)
        if words:
            return words[0].lower()

        return None

    def _merge_trends(self, trends: list[RawTrend]) -> list[RawTrend]:
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
