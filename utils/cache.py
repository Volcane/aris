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


def _cache_key(url: str, params: Optional[dict] = None) -> str:
    raw = url + json.dumps(params or {}, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def get_cached(url: str, params: Optional[dict] = None) -> Optional[Any]:
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


def set_cached(url: str, params: Optional[dict], data: Any) -> None:
    key  = _cache_key(url, params)
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps({
        "expires": (datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)).isoformat(),
        "data":    data,
    }))


# ── Resilient HTTP GET ────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(min=RETRY_WAIT_SECONDS))
def http_get(url: str, params: Optional[dict] = None,
             headers: Optional[dict] = None, use_cache: bool = True) -> Any:
    """
    GET a URL, returning parsed JSON. Uses disk cache to avoid re-fetching.
    Raises on HTTP errors after MAX_RETRIES attempts.
    """
    if use_cache:
        cached = get_cached(url, params)
        if cached is not None:
            log.debug("Cache hit: %s", url)
            return cached

    resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
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

    resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.text

    if use_cache:
        set_cached(url, params, data)

    return data


# ── Keyword relevance pre-filter ──────────────────────────────────────────────

from config.settings import AI_KEYWORDS


def is_ai_relevant(text: str, threshold: int = 1) -> bool:
    """Quick keyword scan before sending to Claude for full analysis."""
    lower = text.lower()
    hits  = sum(1 for kw in AI_KEYWORDS if kw in lower)
    return hits >= threshold


def keyword_score(text: str) -> float:
    """Returns a 0–1 score based on keyword density."""
    if not text:
        return 0.0
    lower     = text.lower()
    hits      = sum(1 for kw in AI_KEYWORDS if kw in lower)
    max_score = min(len(AI_KEYWORDS), 10)      # cap at 10 for normalisation
    return min(hits / max_score, 1.0)
