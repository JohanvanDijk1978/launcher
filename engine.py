"""
Virality scoring engine.
Scores trends across three dimensions:
  - Keyword spike (mention count normalized)
  - Engagement velocity (engagement per unit time)
  - Sentiment (positive buzz ratio)
Final score is a weighted combination, range 0.0–1.0.
"""

import logging
import re
from dataclasses import dataclass

from config import Config
from scrapers.nitter import RawTrend

logger = logging.getLogger("scoring.engine")

# Simple positive/negative word lists for lightweight sentiment
POSITIVE_WORDS = {
    "moon", "pump", "gem", "100x", "1000x", "bullish", "launch", "buy",
    "fire", "hot", "viral", "trending", "explode", "rocket", "ape", "fomo",
    "based", "king", "legendary", "massive", "huge", "insane", "epic",
    "send", "wagmi", "rich", "profit", "gain", "winning", "early", "alpha"
}

NEGATIVE_WORDS = {
    "rug", "scam", "dump", "sell", "dead", "rekt", "fraud", "fake",
    "bearish", "avoid", "warning", "honeypot", "ponzi", "ngmi", "exit",
    "crash", "collapse", "steal", "lose", "loss", "suspicious", "careful"
}


@dataclass
class ScoredTrend:
    """A trend with a computed virality score."""
    # Original trend data
    source: str
    label: str
    key: str
    mentions: int
    engagement: int
    sentiment_raw: list[str]

    # Scores
    score: float = 0.0
    keyword_score: float = 0.0
    velocity_score: float = 0.0
    sentiment_score: float = 0.0

    # Dynamic SOL amount (set by launcher based on score)
    sol_to_spend: float = 0.0


class ViralityEngine:
    def __init__(self, config: Config):
        self.config = config

        # Normalization baselines (calibrated for memecoin subreddits/Twitter)
        self.mention_baseline = 100       # mentions considered "normal"
        self.engagement_baseline = 5000   # engagement considered "normal"

    def score_all(self, trends: list[RawTrend]) -> list[ScoredTrend]:
        """Score all trends and return sorted list (highest first)."""
        scored = [self._score(t) for t in trends]
        scored.sort(key=lambda t: t.score, reverse=True)
        return scored

    def _score(self, trend: RawTrend) -> ScoredTrend:
        keyword_score = self._keyword_spike_score(trend)
        velocity_score = self._engagement_velocity_score(trend)
        sentiment_score = self._sentiment_score(trend)

        # Weighted combination
        score = (
            keyword_score * self.config.keyword_spike_weight
            + velocity_score * self.config.engagement_velocity_weight
            + sentiment_score * self.config.sentiment_weight
        )
        score = min(1.0, max(0.0, score))

        # Compute dynamic SOL spend
        sol = self._compute_sol(score)

        logger.debug(
            f"[{trend.key}] kw={keyword_score:.2f} vel={velocity_score:.2f} "
            f"sent={sentiment_score:.2f} → score={score:.2f} sol={sol:.3f}"
        )

        return ScoredTrend(
            source=trend.source,
            label=trend.label,
            key=trend.key,
            mentions=trend.mentions,
            engagement=trend.engagement,
            sentiment_raw=trend.sentiment_raw,
            score=score,
            keyword_score=keyword_score,
            velocity_score=velocity_score,
            sentiment_score=sentiment_score,
            sol_to_spend=sol,
        )

    def _keyword_spike_score(self, trend: RawTrend) -> float:
        """
        Score based on mention count relative to baseline.
        Returns 0.0–1.0.
        """
        ratio = trend.mentions / self.mention_baseline
        # Sigmoid-like normalization
        return min(1.0, ratio / (ratio + 1))

    def _engagement_velocity_score(self, trend: RawTrend) -> float:
        """
        Score based on engagement volume relative to baseline.
        Returns 0.0–1.0.
        """
        ratio = trend.engagement / self.engagement_baseline
        return min(1.0, ratio / (ratio + 1))

    def _sentiment_score(self, trend: RawTrend) -> float:
        """
        Simple bag-of-words sentiment.
        Returns 0.0 (all negative) to 1.0 (all positive).
        """
        texts = " ".join(trend.sentiment_raw).lower()
        words = re.findall(r"\b\w+\b", texts)

        pos = sum(1 for w in words if w in POSITIVE_WORDS)
        neg = sum(1 for w in words if w in NEGATIVE_WORDS)

        total = pos + neg
        if total == 0:
            return 0.5  # Neutral

        return pos / total

    def _compute_sol(self, score: float) -> float:
        """
        Dynamic SOL spend: scales from base to max based on virality score.
        """
        base = self.config.base_sol_per_launch
        max_sol = self.config.max_sol_per_launch
        factor = self.config.sol_scale_factor

        # Exponential scaling: higher score → more SOL
        sol = base + (max_sol - base) * (score ** factor)
        return round(min(max_sol, max(base, sol)), 4)
