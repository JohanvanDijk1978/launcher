"""
Reddit scraper — uses PRAW (official Reddit API, free tier).
Monitors crypto/memecoin subreddits for viral posts.
"""

import logging
from dataclasses import dataclass

import praw
from prawcore.exceptions import PrawcoreException

from config import Config
from scrapers.nitter import RawTrend

logger = logging.getLogger("scrapers.reddit")


class RedditScraper:
    def __init__(self, config: Config):
        self.config = config
        self.reddit = praw.Reddit(
            client_id=config.reddit_client_id,
            client_secret=config.reddit_client_secret,
            user_agent=config.reddit_user_agent,
        )
        self.subreddits = config.reddit_subreddits

    async def get_trends(self) -> list[RawTrend]:
        """
        Pull hot/rising posts from configured subreddits.
        Returns RawTrend objects for the virality engine.
        """
        trends = []

        for sub_name in self.subreddits:
            try:
                sub_trends = self._scrape_subreddit(sub_name)
                trends.extend(sub_trends)
            except PrawcoreException as e:
                logger.warning(f"Reddit API error on r/{sub_name}: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error on r/{sub_name}: {e}")

        merged = self._merge_trends(trends)
        logger.info(f"Reddit: found {len(merged)} trends")
        return merged

    def _scrape_subreddit(self, sub_name: str) -> list[RawTrend]:
        """Scrape hot + rising posts from a subreddit."""
        trends = []
        sub = self.reddit.subreddit(sub_name)

        # Hot posts
        for post in sub.hot(limit=25):
            trend = self._post_to_trend(post, sub_name)
            if trend:
                trends.append(trend)

        # Rising posts (early signals)
        for post in sub.rising(limit=15):
            trend = self._post_to_trend(post, sub_name)
            if trend:
                trends.append(trend)

        return trends

    def _post_to_trend(self, post, sub_name: str) -> RawTrend | None:
        """Convert a Reddit post to a RawTrend."""
        try:
            title = post.title
            score = post.score
            num_comments = post.num_comments
            upvote_ratio = post.upvote_ratio

            # Engagement = upvotes + comments (weighted)
            engagement = score + (num_comments * 5)

            # Extract potential coin/meme keywords from title
            key = self._extract_key(title)
            if not key:
                return None

            # Collect top-level comment text for sentiment
            texts = [title]
            try:
                post.comments.replace_more(limit=0)
                for comment in list(post.comments)[:10]:
                    if hasattr(comment, "body"):
                        texts.append(comment.body)
            except Exception:
                pass

            return RawTrend(
                source="reddit",
                label=title[:80],
                key=key,
                mentions=1,
                engagement=engagement,
                sentiment_raw=texts,
            )

        except Exception as e:
            logger.debug(f"Failed to parse post: {e}")
            return None

    def _extract_key(self, title: str) -> str | None:
        """
        Extract a normalized trend key from a post title.
        Looks for $TICKER patterns, ALL CAPS words, or prominent nouns.
        """
        import re

        # $TICKER pattern (highest priority)
        ticker_match = re.search(r"\$([A-Z]{2,8})", title)
        if ticker_match:
            return ticker_match.group(1).lower()

        # ALL CAPS word (likely a coin name)
        caps_match = re.search(r"\b([A-Z]{3,10})\b", title)
        if caps_match:
            return caps_match.group(1).lower()

        # Hashtag
        hashtag_match = re.search(r"#(\w+)", title)
        if hashtag_match:
            return hashtag_match.group(1).lower()

        # Fallback: first 2 significant words
        words = re.findall(r"\b[a-zA-Z]{4,}\b", title)
        if words:
            return words[0].lower()

        return None

    def _merge_trends(self, trends: list[RawTrend]) -> list[RawTrend]:
        """Merge duplicate trends by key, summing engagement."""
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
