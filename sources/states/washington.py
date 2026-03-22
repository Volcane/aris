"""
ARIS — Washington State Agent

Washington is a major AI and privacy regulation state:
  - My Health MY Data Act (2023) — broad health data privacy, in force
  - SB 5838 / WAIPIA (2024)     — Washington AI Act (vetoed, reintroduced 2025)
  - HB 1149 (2025)              — AI-generated deepfake disclosures
  - HB 1991 (2025)              — Chatbot disclosure requirements
  - SB 5062 / WA Privacy Act    — comprehensive consumer data privacy
  - Active 2026 pipeline: chatbot regulation, agentic AI governance

Sources:
  1. LegiScan API (inherited — primary)
  2. Washington State Legislature native API (no key required)
     https://wslwebservices.leg.wa.gov/legislationservice.asmx
     SOAP/REST hybrid — returns XML for bill search by keyword/year
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

from sources.state_agent_base import StateAgentBase, _parse_date
from config.settings import AI_KEYWORDS, LOOKBACK_DAYS
from utils.cache import is_ai_relevant, http_get_text, get_logger
from utils.search import is_privacy_relevant, detect_domain

log = get_logger("aris.state.wa")

WSL_BASE    = "https://wslwebservices.leg.wa.gov"
WA_BILL_URL = "https://app.leg.wa.gov/billsummary"


def _wsl_search(keyword: str, biennium: str = "2025-26") -> str:
    """Call WSL legislation search service."""
    endpoint = f"{WSL_BASE}/legislationservice.asmx/GetLegislationByKeyword"
    params   = urlencode({"keyword": keyword, "biennium": biennium})
    return http_get_text(f"{endpoint}?{params}", timeout=15) or ""


def _parse_wsl_xml(xml_text: str, domain_hint: str = "ai") -> List[Dict[str, Any]]:
    """Parse WSL XML response into document dicts."""
    docs = []
    if not xml_text.strip():
        return docs
    try:
        root = ET.fromstring(xml_text)
        ns   = {"ws": "http://WSLWebServices.leg.wa.gov/"}
        for leg in root.findall(".//ws:Legislation", ns) or root.findall(".//Legislation"):
            def _t(tag):
                el = leg.find(f"ws:{tag}", ns) or leg.find(tag)
                return (el.text or "").strip() if el is not None else ""

            bill_id   = _t("BillId")
            bill_num  = _t("BillNumber")
            bill_type = _t("BillType")          # "HB", "SB", etc.
            short_des = _t("ShortDescription")
            long_des  = _t("LongDescription")
            intro_date= _t("IntroducedDate")
            sponsor   = _t("PrimeSponsorName")

            combined = f"{short_des} {long_des}".lower()
            if not (is_ai_relevant(combined) or is_privacy_relevant(combined)):
                continue

            pub_date = None
            if intro_date:
                try:
                    pub_date = datetime.strptime(intro_date[:10], "%Y-%m-%d")
                except Exception:
                    pub_date = _parse_date(intro_date)

            doc_id = f"wa_2025_{bill_type.lower()}{bill_num}".replace(" ", "")
            url    = f"{WA_BILL_URL}?BillNumber={bill_num}&Year=2025&Initiative=False"

            docs.append({
                "id":            doc_id,
                "title":         f"WA {bill_type} {bill_num}: {short_des}",
                "url":           url,
                "source":        "wa_legislature",
                "jurisdiction":  "WA",
                "doc_type":      "bill",
                "agency":        f"Washington Legislature — {sponsor}" if sponsor else "Washington Legislature",
                "published_date": pub_date,
                "full_text":     long_des or short_des,
                "domain":        detect_domain(combined),
            })
    except Exception as e:
        log.warning("WSL XML parse error: %s", e)
    return docs


class WashingtonAgent(StateAgentBase):
    """
    Washington AI regulation and privacy legislation monitor.
    LegiScan API + Washington State Legislature WSL web services.
    """

    state_code     = "WA"
    state_name     = "Washington"
    legiscan_state = "WA"

    def get_native_feed_url(self) -> Optional[str]:
        return f"{WSL_BASE}/legislationservice.asmx/GetLegislationByKeyword"

    def fetch_native(self) -> List[Dict[str, Any]]:
        """
        Query WSL web services for AI and privacy-relevant bills in the
        current biennium (2025-26).
        """
        docs: List[Dict[str, Any]] = []
        seen: set = set()

        search_terms = [
            "artificial intelligence",
            "automated decision",
            "machine learning",
            "data privacy",
            "personal information",
            "chatbot",
        ]

        for term in search_terms:
            try:
                xml_text = _wsl_search(term, biennium="2025-26")
                for doc in _parse_wsl_xml(xml_text):
                    if doc["id"] not in seen:
                        seen.add(doc["id"])
                        docs.append(doc)
            except Exception as e:
                log.warning("WSL search failed for '%s': %s", term, e)

        log.info("Washington native WSL: %d relevant bills", len(docs))
        return docs
