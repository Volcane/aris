"""
ARIS — India Agent

India has enacted its first comprehensive data privacy law and is developing
AI governance frameworks:
  - Digital Personal Data Protection Act 2023 (DPDPA) — enacted, rules pending
  - MEITY AI Advisory (April 2024) — platform accountability for AI outputs
  - National Strategy for AI (2018, updated 2023) — NITI Aayog
  - Telecom Act 2023 — AI-relevant provisions for telecom AI
  - Draft frameworks for AI in healthcare, financial services

Key regulators:
  - MEITY (Ministry of Electronics & IT) — AI and digital policy
  - TRAI (Telecom Regulatory Authority of India) — telecom AI
  - RBI (Reserve Bank of India) — financial AI guidance
  - CERT-In — cybersecurity and AI security

Sources:
  1. MEITY press releases / notifications (English)
  2. Pinned key legislation and advisories
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sources.international.base import InternationalAgentBase, parse_date, strip_tags
from config.settings import LOOKBACK_DAYS
from utils.cache import http_get_text, is_ai_relevant, get_logger
from utils.search import is_privacy_relevant, detect_domain

log = get_logger("aris.international.in")

MEITY_RSS = "https://www.meity.gov.in/rss-feeds/press-releases"

PINNED_IN = [
    {
        "id":       "IN-DPDPA-2023",
        "title":    "Digital Personal Data Protection Act 2023 (India)",
        "doc_type": "Legislation",
        "date":     "2023-08-11",
        "status":   "Enacted — Rules pending (expected 2025-2026)",
        "url":      "https://www.meity.gov.in/writereaddata/files/Digital%20Personal%20Data%20Protection%20Act%202023.pdf",
        "agency":   "Ministry of Electronics & Information Technology (MEITY)",
        "abstract": (
            "India's Digital Personal Data Protection Act 2023 — first comprehensive "
            "data privacy law. Key provisions: consent-based processing, data principal "
            "rights (access, correction, erasure, grievance), data fiduciary obligations "
            "including security safeguards and breach notification, significant data "
            "fiduciary requirements (DPIAs, audits), cross-border transfer restrictions, "
            "and the Data Protection Board as enforcement body. Penalties up to INR 250 "
            "crore (~$30M) per instance. Rules defining implementation timelines are "
            "expected 2025. Applies to processing of personal data of Indian residents."
        ),
    },
    {
        "id":       "IN-MEITY-AI-ADVISORY-2024",
        "title":    "MEITY Advisory on AI Platform Accountability (March 2024)",
        "doc_type": "Government Advisory",
        "date":     "2024-03-01",
        "status":   "Published",
        "url":      "https://www.meity.gov.in/writereaddata/files/Advisory%20for%20Intermediaries%20and%20Platforms%20on%20AI%20compliance.pdf",
        "agency":   "Ministry of Electronics & Information Technology (MEITY)",
        "abstract": (
            "MEITY advisory requiring AI platforms operating in India to: ensure AI "
            "outputs do not threaten integrity of electoral process, take explicit "
            "government permission before deploying under-tested AI, label AI-generated "
            "content, and ensure AI models cannot be used to produce content violating "
            "IT Act rules. Targeted at large AI platforms. Raises significant questions "
            "about advance permission requirements for AI deployment in India."
        ),
    },
    {
        "id":       "IN-NITI-AAYOG-AI-STRATEGY-2023",
        "title":    "National Strategy for Artificial Intelligence — Updated Framework (India, 2023)",
        "doc_type": "Government Strategy",
        "date":     "2023-07-01",
        "status":   "Published",
        "url":      "https://www.niti.gov.in/sites/default/files/2023-07/National-Strategy-for-AI.pdf",
        "agency":   "NITI Aayog",
        "abstract": (
            "Updated India AI strategy covering: AI for social good in 5 priority sectors "
            "(healthcare, agriculture, education, smart cities, smart mobility), "
            "responsible AI principles, data governance, compute infrastructure "
            "requirements, and skilling initiatives. Establishes India's aspiration "
            "to become an AI powerhouse. Relevant for companies seeking to understand "
            "India's long-term AI regulatory direction and government AI procurement."
        ),
    },
]


class IndiaAgent(InternationalAgentBase):
    jurisdiction_code = "IN"
    jurisdiction_name = "India"
    region            = "Asia-Pacific"
    language          = "en"

    def _pinned(self) -> List[Dict[str, Any]]:
        return [
            self._make_doc(
                id=d["id"], source="in_pinned", doc_type=d["doc_type"],
                title=d["title"], url=d["url"],
                published_date=parse_date(d["date"]),
                agency=d["agency"], status=d["status"],
                full_text=d["abstract"], raw_json=d,
            )
            for d in PINNED_IN
        ]

    def _fetch_meity_rss(self, lookback_days: int) -> List[Dict[str, Any]]:
        docs  = []
        since = datetime.utcnow() - timedelta(days=lookback_days)
        try:
            xml_text = http_get_text(MEITY_RSS, use_cache=True)
            if not xml_text:
                return docs
            root    = ET.fromstring(xml_text)
            channel = root.find("channel") or root
            for item in channel.findall("item"):
                title  = (item.findtext("title")       or "").strip()
                link   = (item.findtext("link")         or "").strip()
                desc   = strip_tags(item.findtext("description") or "", 2000)
                pub    = parse_date(item.findtext("pubDate") or "")
                if pub and pub < since:
                    continue
                combined = f"{title} {desc}".lower()
                if not (is_ai_relevant(combined) or is_privacy_relevant(combined)):
                    continue
                safe = re.sub(r"[^a-z0-9]", "_", title.lower())[:50]
                docs.append(self._make_doc(
                    id=f"IN-MEITY-{safe}", source="in_meity_rss",
                    doc_type="MEITY Press Release / Notification",
                    title=title, url=link, published_date=pub,
                    agency="MEITY India", status="Published",
                    full_text=desc or title,
                    raw_json={"title": title, "link": link},
                ))
        except Exception as e:
            log.warning("MEITY RSS failed: %s", e)
        return docs

    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        docs = self._pinned()
        docs.extend(self._fetch_meity_rss(lookback_days))
        log.info("India: %d docs", len(docs))
        return docs

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        return []
