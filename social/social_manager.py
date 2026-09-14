"""
ARIA — Social Media Manager
==============================
Aria handles all social posting as @migikonokami.

After each match she posts clip teasers.
After each YouTube upload she cross-posts everywhere.
She writes as herself — not as a bot.

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

import os
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from loguru import logger

try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class SocialManager:
    """
    Posts to Twitter/X, Reddit, TikTok, and Instagram as Aria.

    Usage:
        sm = SocialManager(config)
        sm.post_match_highlight(clip_path, analysis)
        sm.post_youtube_drop(youtube_url, title, description)
        sm.post_rank_update(new_rank, rp)
    """

    PLAYER      = "Hidarikikinoaku"
    HANDLE      = "LeftHandDevil"
    COACH       = "@migikonokami"
    SUBREDDIT   = "apexlegends"

    def __init__(self, config: dict):
        self.config = config
        self._twitter  = None
        self._reddit   = None
        self._setup_twitter()
        self._setup_reddit()

    # ── Setup ──────────────────────────────────────────────────

    def _setup_twitter(self):
        if not TWEEPY_AVAILABLE:
            return
        api_key    = self.config.get("twitter_api_key", "")
        api_secret = self.config.get("twitter_api_secret", "")
        token      = self.config.get("twitter_access_token", "")
        secret     = self.config.get("twitter_access_secret", "")
        if not all([api_key, api_secret, token, secret]):
            return
        try:
            client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=token,
                access_token_secret=secret,
            )
            self._twitter = client
            logger.info("Twitter connected ✅")
        except Exception as e:
            logger.warning(f"Twitter setup failed: {e}")

    def _setup_reddit(self):
        if not PRAW_AVAILABLE:
            return
        client_id     = self.config.get("reddit_client_id", "")
        client_secret = self.config.get("reddit_client_secret", "")
        if not all([client_id, client_secret]):
            return
        try:
            self._reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=f"Aria coach bot for {self.PLAYER}",
            )
            logger.info("Reddit connected ✅")
        except Exception as e:
            logger.warning(f"Reddit setup failed: {e}")

    # ── Public posting methods ─────────────────────────────────

    def post_match_highlight(self, clip_path: str, analysis) -> dict:
        """
        Post a clip highlight after a match.
        analysis is a FightAnalysis object.
        Returns dict of {platform: success/error}.
        """
        score   = getattr(analysis, "overall_score",  5.0)
        verdict = getattr(analysis, "overall_verdict", "")
        fix     = getattr(analysis, "primary_fix",     "")

        tweet = self._write_highlight_tweet(verdict, fix, score)
        results = {}

        results["twitter"] = self._tweet(tweet)

        logger.info(f"Social post complete: {results}")
        return results

    def post_youtube_drop(self, youtube_url: str, title: str, description: str) -> dict:
        """Post when a new YouTube video goes live."""
        tweet = (
            f"New video just dropped 🎥\n\n"
            f"{title}\n\n"
            f"{youtube_url}\n\n"
            f"Full match breakdown. Every mistake, every correct play.\n"
            f"#{self.HANDLE} #ApexLegends #RoadToPredator"
        )

        reddit_title = f"[{self.HANDLE}] {title} — AI coach breaks down every fight"
        reddit_body  = (
            f"Aria ({self.COACH}) reviewed every clip from this session.\n\n"
            f"Video: {youtube_url}\n\n"
            f"{description}\n\n"
            f"Currently {self.config.get('current_rank','Gold 4')} → targeting Predator."
        )

        results = {}
        results["twitter"] = self._tweet(tweet)
        results["reddit"]  = self._reddit_post(reddit_title, reddit_body, youtube_url)

        logger.info(f"YouTube cross-post: {results}")
        return results

    def post_rank_update(self, new_rank: str, rp: int) -> dict:
        """Post when rank changes."""
        tweet = (
            f"Rank update 📈\n\n"
            f"{new_rank} — {rp} RP\n\n"
            f"Aria had notes. I fixed it.\n"
            f"#ApexLegends #{self.HANDLE} #RoadToPredator"
        )
        results = {"twitter": self._tweet(tweet)}
        logger.info(f"Rank update posted: {results}")
        return results

    def post_session_stats(self, session_summary: dict, coaching_report: str) -> dict:
        """Post a quick session recap after a match."""
        k   = session_summary.get("knock_count", 0)
        d   = session_summary.get("death_count", 0)
        kd  = round(k / max(d, 1), 2)

        tweet = (
            f"Session: {k} knocks / {d} deaths (KD {kd})\n\n"
            f"Aria's note: {coaching_report[:140] if coaching_report else 'Review pending.'}\n\n"
            f"#{self.HANDLE} #ApexLegends"
        )
        results = {"twitter": self._tweet(tweet)}
        return results

    # ── Internal posting ───────────────────────────────────────

    def _tweet(self, text: str) -> str:
        if not self._twitter:
            return "skipped (no Twitter credentials)"
        try:
            # Enforce 280 char limit
            if len(text) > 280:
                text = text[:277] + "..."
            resp = self._twitter.create_tweet(text=text)
            tweet_id = resp.data.get("id", "?")
            logger.info(f"Tweet posted: {tweet_id}")
            return f"ok:{tweet_id}"
        except Exception as e:
            logger.warning(f"Tweet failed: {e}")
            return f"error:{e}"

    def _reddit_post(self, title: str, body: str, url: str = None) -> str:
        if not self._reddit:
            return "skipped (no Reddit credentials)"
        try:
            sub = self._reddit.subreddit(self.SUBREDDIT)
            if url:
                post = sub.submit(title=title, url=url)
            else:
                post = sub.submit(title=title, selftext=body)
            logger.info(f"Reddit post: {post.url}")
            return f"ok:{post.url}"
        except Exception as e:
            logger.warning(f"Reddit post failed: {e}")
            return f"error:{e}"

    # ── Tweet writer ───────────────────────────────────────────

    def _write_highlight_tweet(self, verdict: str, fix: str, score: float) -> str:
        """Write Aria's tweet for a match highlight."""
        if score >= 8:
            tone = "clean"
            opener = f"Clean fight from {self.HANDLE} 🔥"
        elif score >= 6:
            tone = "decent"
            opener = f"Decent fight. Room to improve."
        else:
            tone = "mistake"
            opener = f"Mistake caught. Noted. Fixed."

        lines = [opener]

        if verdict:
            lines.append(f"Aria's read: {verdict[:100]}")

        if fix and tone != "clean":
            lines.append(f"Fix: {fix[:80]}")

        lines.append(f"\n#{self.HANDLE} #ApexLegends #RoadToPredator")

        return "\n".join(lines)

    # ── Save queue for async posting ───────────────────────────

    def queue_post(self, post_type: str, data: dict):
        """
        Queue a post to be sent later (e.g. during off-peak hours).
        Saved to data/social_queue.json.
        """
        queue_file = Path("data") / "social_queue.json"
        queue      = []

        if queue_file.exists():
            try:
                queue = json.loads(queue_file.read_text())
            except Exception:
                queue = []

        queue.append({
            "type":      post_type,
            "data":      data,
            "queued_at": datetime.now().isoformat(),
        })

        queue_file.write_text(json.dumps(queue, indent=2))
        logger.debug(f"Post queued: {post_type}")

    def flush_queue(self):
        """Send all queued posts."""
        queue_file = Path("data") / "social_queue.json"
        if not queue_file.exists():
            return

        try:
            queue = json.loads(queue_file.read_text())
        except Exception:
            return

        sent = []
        for item in queue:
            try:
                if item["type"] == "highlight":
                    self._tweet(item["data"].get("tweet", ""))
                    sent.append(item)
                elif item["type"] == "youtube":
                    self.post_youtube_drop(
                        item["data"].get("url", ""),
                        item["data"].get("title", ""),
                        item["data"].get("description", ""),
                    )
                    sent.append(item)
            except Exception as e:
                logger.warning(f"Queue flush error: {e}")

        remaining = [i for i in queue if i not in sent]
        queue_file.write_text(json.dumps(remaining, indent=2))
        logger.info(f"Flushed {len(sent)} queued posts")
