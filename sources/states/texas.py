"""
ARIS — Texas State Agent

Texas enacted TRAIGA (Texas Responsible AI Governance Act) effective Jan 1, 2026,
making it one of the first states with a comprehensive AI governance framework.
Active on deepfakes, employment AI, and data privacy.

Key legislation:
  - SB 2103 / TRAIGA (2025)      — AI governance, prohibited practices, AG enforcement
  - HB 4 (2023)                  — Texas Data Privacy and Security Act (TDPSA)
  - SB 1709 (2025)               — AI-generated deepfakes in elections
  - Multiple 2025 healthcare AI bills

Sources:
  1. LegiScan API (inherited — primary discovery)
  2. Texas Legislature Online RSS feeds (no key required)
     https://capitol.texas.gov/MyTLO/RSS/RSSFeeds.aspx
     - New bills, enrolled bills, signed acts by session

Notes:
  Texas holds biennial sessions (odd years only), so the 89th Legislature
  (2025) adjourned May 2025. Next regular session: January 2027.
  LegiScan coverage is reliable; RSS supplements with enrolled/signed status.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional

from sources.state_agent_base import StateAgentBase, _parse_date
from config.settings import AI_KEYWORDS, LOOKBACK_DAYS
from utils.cache import is_ai_relevant, http_get_text, get_logger
from utils.search import is_privacy_relevant, detect_domain

log = get_logger("aris.state.tx")

# Texas Legislature Online RSS — signed acts and enrolled bills
TX_SIGNED_RSS   = "https://capitol.texas.gov/MyTLO/RSS/billsSignedByGovernor.xml"
TX_ENROLLED_RSS = "https://capitol.texas.gov/MyTLO/RSS/billsEnrolled.xml"
TX_BILL_BASE    = "https://capitol.texas.gov/BillLookup/History.aspx"
TX_SESSION      = "89R"   # 89th Regular Session (2025)


class TexasAgent(StateAgentBase):
    """
    Texas AI regulation and privacy legislation monitor.
    Primary: LegiScan API. Supplementary: TLO RSS for signed/enrolled status.
    """

    state_code     = "TX"
    state_name     = "Texas"
    legiscan_state = "TX"

    def get_native_feed_url(self) -> Optional[str]:
        return TX_SIGNED_RSS

    def fetch_native(self) -> List[Dict[str, Any]]:
        """
        Fetch recently signed/enrolled bills from Texas Legislature Online RSS.
        Supplements LegiScan with official enactment status.
        """
        docs: List[Dict[str, Any]] = []

        for feed_url, feed_type in [
            (TX_SIGNED_RSS,   "signed"),
            (TX_ENROLLED_RSS, "enrolled"),
        ]:
            try:
                xml_text = http_get_text(feed_url, timeout=15)
                if not xml_text:
                    continue
                root = ET.fromstring(xml_text)
                channel = root.find("channel")
                if channel is None:
                    channel = root

                for item in channel.findall("item"):
                    title_el = item.find("title")
                    link_el  = item.find("link")
                    desc_el  = item.find("description")
                    pub_el   = item.find("pubDate")

                    title = (title_el.text or "").strip() if title_el is not None else ""
                    url   = (link_el.text  or "").strip() if link_el  is not None else ""
                    desc  = (desc_el.text  or "").strip() if desc_el  is not None else ""
                    pub   = (pub_el.text   or "").strip() if pub_el   is not None else ""

                    combined = f"{title} {desc}".lower()
                    if not (is_ai_relevant(combined) or is_privacy_relevant(combined)):
                        continue

                    # Extract bill number from title e.g. "HB 1234"
                    bill_match = re.search(r'\b([HS][BJR]\s*\d+)\b', title, re.I)
                    bill_num   = bill_match.group(1).replace(" ", "").upper() if bill_match else ""

                    doc_id = f"tx_{TX_SESSION}_{bill_num or re.sub(r'[^a-z0-9]', '_', title[:40].lower())}"
                    pub_date = None
                    if pub:
                        try:
                            pub_date = datetime.strptime(pub[:25], "%a, %d %b %Y %H:%M:%S")
                        except Exception:
                            pub_date = _parse_date(pub)

                    docs.append({
                        "id":            doc_id,
                        "title":         title,
                        "url":           url or f"{TX_BILL_BASE}?LegSess={TX_SESSION}&Bill={bill_num}",
                        "source":        "tx_tlo_rss",
                        "jurisdiction":  "TX",
                        "doc_type":      f"bill_{feed_type}",
                        "agency":        "Texas Legislature",
                        "published_date": pub_date,
                        "full_text":     desc,
                        "domain":        detect_domain(combined),
                    })

            except Exception as e:
                log.warning("Texas RSS fetch failed (%s): %s", feed_url, e)

        log.info("Texas native RSS: %d relevant bills", len(docs))
        return docs
