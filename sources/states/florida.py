"""
ARIS — Florida State Agent

Florida is active on AI and privacy regulation:
  - Florida Digital Bill of Rights (SB 262, 2023) — in force, large controller threshold
  - Multiple AI in elections bills (2024-2025)
  - Deepfake legislation — sexual content and elections
  - SB 1824 (2024) — AI disclosure in political advertising
  - Active 2026 pipeline: chatbot disclosure, healthcare AI, employment AI

Sources:
  1. LegiScan API (primary)
  2. Florida Legislature Official site RSS
     https://www.flsenate.gov/Session/Bills/2026 — JSON available
     https://www.myfloridahouse.gov/rss — House RSS feeds
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional

from sources.state_agent_base import StateAgentBase, _parse_date
from utils.cache import is_ai_relevant, http_get_text, get_logger
from utils.search import is_privacy_relevant, detect_domain

log = get_logger("aris.state.fl")

FL_SENATE_RSS  = "https://www.flsenate.gov/rss/bills.xml"
FL_ENACTED_RSS = "https://www.flsenate.gov/rss/chaptered.xml"
FL_BILL_BASE   = "https://www.flsenate.gov/Session/Bill"
FL_SESSION     = "2026"


class FloridaAgent(StateAgentBase):
    """Florida AI regulation and privacy legislation monitor."""

    state_code     = "FL"
    state_name     = "Florida"
    legiscan_state = "FL"

    def get_native_feed_url(self) -> Optional[str]:
        return FL_SENATE_RSS

    def fetch_native(self) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for feed_url, feed_type in [
            (FL_SENATE_RSS,  "introduced"),
            (FL_ENACTED_RSS, "enacted"),
        ]:
            try:
                xml_text = http_get_text(feed_url, timeout=15)
                if not xml_text:
                    continue
                root = ET.fromstring(xml_text)
                channel = root.find("channel") or root
                for item in channel.findall("item"):
                    title  = (item.findtext("title")       or "").strip()
                    link   = (item.findtext("link")         or "").strip()
                    desc   = (item.findtext("description") or "").strip()
                    pub    = _parse_date(item.findtext("pubDate") or "")
                    combined = f"{title} {desc}".lower()
                    if not (is_ai_relevant(combined) or is_privacy_relevant(combined)):
                        continue
                    bill_m = re.search(r'\b([SH][BRJ]\s*\d+)\b', title, re.I)
                    bill_n = bill_m.group(1).replace(" ", "").upper() if bill_m else ""
                    doc_id = f"fl_{FL_SESSION}_{bill_n or re.sub(r'[^a-z0-9]','_',title[:40].lower())}"
                    docs.append({
                        "id":            doc_id,
                        "title":         title,
                        "url":           link or f"{FL_BILL_BASE}/{FL_SESSION}/{bill_n}",
                        "source":        "fl_senate_rss",
                        "jurisdiction":  "FL",
                        "doc_type":      f"bill_{feed_type}",
                        "agency":        "Florida Legislature",
                        "published_date": pub,
                        "full_text":     desc,
                        "domain":        detect_domain(combined),
                    })
            except Exception as e:
                log.warning("Florida RSS failed (%s): %s", feed_url, e)
        log.info("Florida native: %d docs", len(docs))
        return docs
