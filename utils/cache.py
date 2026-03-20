"""
ARIS — Shared Utilities: logger, HTTP cache, retry wrapper
"""

import json
import hashlib
import logging
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import (
    LOG_LEVEL, REQUEST_TIMEOUT, MAX_RETRIES,
    RETRY_WAIT_SECONDS, CACHE_TTL_HOURS, OUTPUT_DIR
)

# ── Logger ────────────────────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    return logger


log = get_logger("aris.utils")

# ── Disk-based HTTP response cache ───────────────────────────────────────────

CACHE_DIR = OUTPUT_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_key(url: str, params=None) -> str:
    # params may be a dict or a list of (key, value) tuples (for repeated keys)
    if isinstance(params, list):
        raw = url + json.dumps(sorted(params))
    else:
        raw = url + json.dumps(params or {}, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def get_cached(url: str, params=None) -> Optional[Any]:
    key  = _cache_key(url, params)
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    meta = json.loads(path.read_text())
    expires = datetime.fromisoformat(meta["expires"])
    if datetime.utcnow() > expires:
        path.unlink(missing_ok=True)
        return None
    return meta["data"]


def set_cached(url: str, params, data: Any) -> None:
    key  = _cache_key(url, params)
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps({
        "expires": (datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)).isoformat(),
        "data":    data,
    }))


# ── Resilient HTTP GET ────────────────────────────────────────────────────────

# Default headers that make requests look like a real browser.
# Federal agency sites (FTC, SEC, CFPB, EEOC, etc.) return 403 for
# the default Python/requests User-Agent string.
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(min=RETRY_WAIT_SECONDS))
def http_get(url: str, params=None,
             headers: Optional[dict] = None, use_cache: bool = True) -> Any:
    """
    GET a URL, returning parsed JSON. Uses disk cache to avoid re-fetching.
    params may be a dict or a list of (key, value) tuples (needed for
    repeated query parameters like fields[]=x&fields[]=y).
    Raises on HTTP errors after MAX_RETRIES attempts.
    """
    if use_cache:
        cached = get_cached(url, params)
        if cached is not None:
            log.debug("Cache hit: %s", url)
            return cached

    merged = {**_DEFAULT_HEADERS, **(headers or {})}
    resp = requests.get(url, params=params, headers=merged, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    try:
        data = resp.json()
    except Exception:
        data = resp.text  # XML / plain text fallback

    if use_cache:
        set_cached(url, params, data)

    return data


def http_get_text(url: str, params: Optional[dict] = None,
                  headers: Optional[dict] = None, use_cache: bool = True) -> str:
    """
    GET a URL, returning raw text (for XML feeds, HTML).
    """
    if use_cache:
        cached = get_cached(url, params)
        if cached is not None:
            return cached

    merged = {**_DEFAULT_HEADERS, **(headers or {})}
    resp = requests.get(url, params=params, headers=merged, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.text

    if use_cache:
        set_cached(url, params, data)

    return data


# ── Keyword relevance pre-filter ──────────────────────────────────────────────
# Delegates to utils.search for richer scoring.
# Call sites throughout the codebase are unchanged.

from config.settings import AI_KEYWORDS


def is_ai_relevant(text: str, threshold: int = 1) -> bool:
    """
    Return True if text is likely AI-regulation-related.
    Uses the expanded 150+ term taxonomy in utils.search.
    threshold=1 preserved for backward compatibility but interpreted as 0.08 score.
    """
    try:
        from utils.search import is_ai_relevant as _search_relevant
        # threshold=1 → 0.08 score; threshold=2 → 0.15; etc.
        score_thresh = max(0.05, (threshold - 1) * 0.07 + 0.08)
        return _search_relevant(text, threshold=score_thresh)
    except Exception:
        # Hard fallback to original logic
        lower = text.lower()
        hits  = sum(1 for kw in AI_KEYWORDS if kw in lower)
        return hits >= threshold


def keyword_score(text: str) -> float:
    """
    Return a 0-1 relevance score. Delegates to utils.search.relevance_score.
    """
    try:
        from utils.search import relevance_score
        return relevance_score(text)
    except Exception:
        # Hard fallback to original logic
        if not text:
            return 0.0
        lower     = text.lower()
        hits      = sum(1 for kw in AI_KEYWORDS if kw in lower)
        max_score = min(len(AI_KEYWORDS), 10)
        return min(hits / max_score, 1.0)
