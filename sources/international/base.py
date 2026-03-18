"""
ARIS — International Agent Base Class

All country/supranational agents inherit from InternationalAgentBase.
This is intentionally kept separate from StateAgentBase so that:
  - US state logic (LegiScan, PA XML feeds) never bleeds into international
  - International agents can carry region/language/currency metadata
  - Each country's unique document taxonomy can be expressed clearly

To add a new country:
  1. Create sources/international/<country_code>.py
  2. Subclass InternationalAgentBase
  3. Set the class-level metadata fields
  4. Implement fetch_native() (required) and optionally fetch_secondary()
  5. Register in config/jurisdictions.py under ENABLED_INTERNATIONAL
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional

from config.settings import AI_KEYWORDS, LOOKBACK_DAYS
from utils.cache import http_get, http_get_text, is_ai_relevant, get_logger

log = get_logger("aris.international")


class InternationalAgentBase(ABC):
    """
    Abstract base for international AI regulation monitoring.

    Required class attributes:
        jurisdiction_code : str  — ISO 3166 / custom code e.g. "EU", "GB", "CA"
        jurisdiction_name : str  — Human-readable name e.g. "European Union"
        region            : str  — Grouping label e.g. "Europe", "North America"
        language          : str  — Primary language of source (ISO 639-1 e.g. "en", "fr")

    Optional:
        requires_translation : bool — Set True if source is non-English;
                                       Claude will handle translation inline.
        secondary_sources    : list — Additional feeds beyond the primary API.
    """

    jurisdiction_code:    str  = ""
    jurisdiction_name:    str  = ""
    region:               str  = ""
    language:             str  = "en"
    requires_translation: bool = False
    secondary_sources:    list = []

    # ── Primary data fetch (must implement) ───────────────────────────────────

    @abstractmethod
    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        """
        Fetch AI-relevant documents from the primary official source.
        Must return a list of normalised document dicts.
        """
        ...

    # ── Secondary sources (override if needed) ────────────────────────────────

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        """
        Fetch from any supplementary sources (e.g. government AI office,
        regulatory body RSS feeds). Default: empty list.
        """
        return []

    # ── Translation hook ──────────────────────────────────────────────────────

    def translate_if_needed(self, text: str) -> str:
        """
        If the document language is not English, Claude will handle
        translation inline during interpretation. This hook is available
        for subclasses to plug in a dedicated translation API
        (e.g. DeepL, Google Translate) if preferred.
        """
        return text  # default: pass through, let Claude interpret

    # ── Main entry point ──────────────────────────────────────────────────────

    def fetch_all(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        """
        Fetch all AI-relevant documents from all sources for this jurisdiction.
        De-duplicates by document ID before returning.
        """
        log.info("Starting %s fetch (%s)…", self.jurisdiction_name, self.jurisdiction_code)

        docs = self.fetch_native(lookback_days)
        docs.extend(self.fetch_secondary(lookback_days))

        # Translate non-English text snippets if needed
        if self.requires_translation:
            for doc in docs:
                doc["full_text"] = self.translate_if_needed(doc.get("full_text") or "")

        # De-duplicate
        seen, unique = set(), []
        for d in docs:
            if d["id"] not in seen:
                seen.add(d["id"])
                unique.append(d)

        log.info("%s fetch complete — %d documents", self.jurisdiction_name, len(unique))
        return unique

    # ── Shared normalisation helper ───────────────────────────────────────────

    def _make_doc(self, **kwargs) -> Dict[str, Any]:
        """
        Build a document dict with all required fields set to safe defaults.
        Subclasses call this instead of building dicts by hand.
        """
        return {
            "id":            kwargs.get("id", ""),
            "source":        kwargs.get("source", f"intl_{self.jurisdiction_code.lower()}"),
            "jurisdiction":  self.jurisdiction_code,
            "doc_type":      kwargs.get("doc_type", ""),
            "title":         kwargs.get("title", ""),
            "url":           kwargs.get("url", ""),
            "published_date": kwargs.get("published_date"),
            "agency":        kwargs.get("agency", self.jurisdiction_name),
            "status":        kwargs.get("status", ""),
            "full_text":     kwargs.get("full_text", ""),
            "raw_json":      kwargs.get("raw_json", {}),
        }


# ── Shared date parser ────────────────────────────────────────────────────────

def parse_date(s: Optional[str]) -> Optional[datetime]:
    """Parse a date string in several common formats."""
    if not s:
        return None
    s = s.strip()
    for fmt in (
        "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S", "%d %B %Y", "%B %d, %Y",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            return datetime.strptime(s[:26], fmt)
        except ValueError:
            continue
    return None


# ── Shared HTML/XML text cleaner ──────────────────────────────────────────────

def strip_tags(html: str, max_chars: int = 6000) -> str:
    """Remove HTML/XML tags and return plain text, capped at max_chars."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text[:max_chars]
