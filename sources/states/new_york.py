"""
ARIS — New York State Agent

New York is one of the highest-priority AI regulation states:
  - NYC Local Law 144 (2023)       — hiring AEDT bias audits (baseline already tracked)
  - RAISE Act (AB 6453 / SB 6953, 2025) — frontier model transparency, pending signature
  - S 3008 (2025)                  — algorithmic pricing disclosure (enacted)
  - AI Accountability Act (2025)   — automated employment decisions
  - Multiple healthcare AI bills   — utilisation review, prior authorisation

Sources:
  1. LegiScan API (inherited — primary)
  2. New York State Legislature Open API (no key required)
     https://legislation.nysenate.gov/api/3/ — Senate open data API
     https://assembly.state.ny.us/leg/ — Assembly (no structured API; LegiScan covers)

Notes:
  NY Senate Open API returns JSON. Only Senate bills are available via this API;
  Assembly bills are covered by LegiScan.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from sources.state_agent_base import StateAgentBase, _parse_date
from config.settings import AI_KEYWORDS, LOOKBACK_DAYS
from utils.cache import is_ai_relevant, http_get, get_logger
from utils.search import is_privacy_relevant, detect_domain

log = get_logger("aris.state.ny")

NY_SENATE_API  = "https://legislation.nysenate.gov/api/3"
NY_BILL_BASE   = "https://www.nysenate.gov/legislation/bills"
NY_SESSION     = "2025"   # current two-year session


def _senate_search(keyword: str, session: str = NY_SESSION, limit: int = 50) -> List[Dict]:
    """Query NY Senate Open API for bills matching a keyword."""
    try:
        url  = f"{NY_SENATE_API}/bills/{session}/search?term={keyword}&limit={limit}&full=false"
        data = http_get(url, timeout=15) or {}
        return data.get("result", {}).get("items", []) if isinstance(data, dict) else []
    except Exception as e:
        log.warning("NY Senate API search failed ('%s'): %s", keyword, e)
        return []


def _parse_senate_bill(item: Dict) -> Optional[Dict]:
    """Convert a NY Senate API bill item to an ARIS document dict."""
    try:
        bill   = item.get("result", item) if "result" in item else item
        bill_no= bill.get("basePrintNo", bill.get("printNo", ""))
        title  = bill.get("title", "")
        sponsor= bill.get("sponsor", {})
        if isinstance(sponsor, dict):
            sponsor_name = sponsor.get("member", {}).get("shortName", "")
        else:
            sponsor_name = ""

        summary = bill.get("summary", "")
        status  = bill.get("status", {})
        status_desc = status.get("statusDesc", "") if isinstance(status, dict) else ""

        intro_date = bill.get("publishedDateTime", bill.get("activeVersion", {}).get("publishedDateTime", ""))
        pub_date   = None
        if intro_date:
            try:
                pub_date = datetime.strptime(intro_date[:10], "%Y-%m-%d")
            except Exception:
                pub_date = _parse_date(intro_date)

        combined = f"{title} {summary}".lower()
        if not (is_ai_relevant(combined) or is_privacy_relevant(combined)):
            return None

        doc_id = f"ny_{NY_SESSION}_{bill_no.lower().replace('-', '_')}"
        url    = f"{NY_BILL_BASE}/{NY_SESSION}/{bill_no}"

        return {
            "id":            doc_id,
            "title":         f"NY {bill_no}: {title}",
            "url":           url,
            "source":        "ny_senate_api",
            "jurisdiction":  "NY",
            "doc_type":      "bill",
            "agency":        f"New York Senate — {sponsor_name}" if sponsor_name else "New York Senate",
            "published_date": pub_date,
            "status":        status_desc,
            "full_text":     summary or title,
            "domain":        detect_domain(combined),
        }
    except Exception as e:
        log.debug("NY bill parse error: %s", e)
        return None


class NewYorkAgent(StateAgentBase):
    """
    New York AI regulation and privacy legislation monitor.
    LegiScan API + New York Senate Open API.
    """

    state_code     = "NY"
    state_name     = "New York"
    legiscan_state = "NY"

    def get_native_feed_url(self) -> Optional[str]:
        return f"{NY_SENATE_API}/bills/{NY_SESSION}/search"

    def fetch_native(self) -> List[Dict[str, Any]]:
        """
        Query NY Senate Open API for AI and privacy-relevant bills in the
        current session. Assembly bills covered by LegiScan.
        """
        docs: List[Dict[str, Any]] = []
        seen: set = set()

        search_terms = [
            "artificial intelligence",
            "automated decision",
            "machine learning",
            "data privacy",
            "personal information",
            "algorithmic",
            "chatbot",
            "deepfake",
        ]

        for term in search_terms:
            for item in _senate_search(term):
                doc = _parse_senate_bill(item)
                if doc and doc["id"] not in seen:
                    seen.add(doc["id"])
                    docs.append(doc)

        log.info("New York native Senate API: %d relevant bills", len(docs))
        return docs
