"""
ARIS — Singapore Agent

Singapore has one of the most developed AI governance frameworks in Asia:
  - PDPA (Personal Data Protection Act, 2012, amended 2020) — in force
  - Model AI Governance Framework (2019, 2nd Ed 2020) — voluntary
  - AI Governance Framework for Financial Industry — MAS
  - Companion documents: Compendium of Use Cases, Implementation Guide
  - Project Moonshot / AI Verify — testing toolkit for AI governance

Key regulators:
  - PDPC (Personal Data Protection Commission) — data privacy
  - IMDA (Infocomm Media Development Authority) — AI governance
  - MAS (Monetary Authority of Singapore) — financial AI

Sources:
  1. PDPC news RSS feed
  2. IMDA news feed
  3. Pinned key documents
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

log = get_logger("aris.international.sg")

PDPC_RSS  = "https://www.pdpc.gov.sg/rss/rss.xml"
IMDA_NEWS = "https://www.imda.gov.sg/resources/press-releases-factsheets-and-speeches"

PINNED_SG = [
    {
        "id":       "SG-MODEL-AI-GOVERNANCE-2020",
        "title":    "Model AI Governance Framework — Second Edition (Singapore, 2020)",
        "doc_type": "Government Framework (Voluntary)",
        "date":     "2020-01-21",
        "status":   "Published — Voluntary",
        "url":      "https://www.pdpc.gov.sg/help-and-resources/2020/01/model-ai-governance-framework",
        "agency":   "IMDA / PDPC Singapore",
        "abstract": (
            "Singapore's Model AI Governance Framework covers 11 areas including human "
            "involvement, operations/risk management, customer communication, and data "
            "management. While voluntary, it is widely adopted and forms the basis for "
            "Singapore's AI Verify testing toolkit. Companies operating in Singapore's "
            "financial, healthcare, or tech sectors should align with this framework."
        ),
    },
    {
        "id":       "SG-PDPA-2020-AMENDMENTS",
        "title":    "Personal Data Protection Act — 2020 Amendments (Singapore)",
        "doc_type": "Legislation",
        "date":     "2020-11-02",
        "status":   "In Force",
        "url":      "https://www.pdpc.gov.sg/overview-of-pdpa/the-legislation/personal-data-protection-act",
        "agency":   "Personal Data Protection Commission (PDPC)",
        "abstract": (
            "The 2020 PDPA amendments significantly strengthened Singapore's data protection "
            "regime: mandatory breach notification (3 days for significant breaches), "
            "deemed consent for legitimate interests, data portability right, increased "
            "financial penalties (up to SGD 1M or 10% of annual Singapore turnover), "
            "and new offences for data misuse. Relevant for all organisations processing "
            "personal data of Singapore residents."
        ),
    },
    {
        "id":       "SG-AI-VERIFY-2023",
        "title":    "AI Verify — AI Governance Testing Framework and Toolkit (Singapore, 2023)",
        "doc_type": "Government Standard",
        "date":     "2023-06-06",
        "status":   "Published",
        "url":      "https://aiverifyfoundation.sg/",
        "agency":   "IMDA / AI Verify Foundation",
        "abstract": (
            "AI Verify is Singapore's testing framework for responsible AI, aligning with "
            "major international frameworks (EU AI Act, OECD, NIST). It provides 11 testable "
            "governance principles with automated tests for transparency, explainability, "
            "fairness, safety, accountability, and security. Companies can use AI Verify "
            "to generate audit reports demonstrating responsible AI deployment."
        ),
    },
]


class SingaporeAgent(InternationalAgentBase):
    jurisdiction_code = "SG"
    jurisdiction_name = "Singapore"
    region            = "Asia-Pacific"
    language          = "en"

    def _pinned(self) -> List[Dict[str, Any]]:
        return [
            self._make_doc(
                id=d["id"], source="sg_pinned", doc_type=d["doc_type"],
                title=d["title"], url=d["url"],
                published_date=parse_date(d["date"]),
                agency=d["agency"], status=d["status"],
                full_text=d["abstract"], raw_json=d,
            )
            for d in PINNED_SG
        ]

    def _fetch_pdpc_rss(self, lookback_days: int) -> List[Dict[str, Any]]:
        docs  = []
        since = datetime.utcnow() - timedelta(days=lookback_days)
        try:
            xml_text = http_get_text(PDPC_RSS, use_cache=True)
            if not xml_text:
                return docs
            root    = ET.fromstring(xml_text)
            channel = root.find("channel") or root
            for item in channel.findall("item"):
                title  = (item.findtext("title")       or "").strip()
                link   = (item.findtext("link")         or "").strip()
                desc   = strip_tags(item.findtext("description") or "", 2000)
                pubstr = item.findtext("pubDate") or ""
                pub    = parse_date(pubstr)
                if pub and pub < since:
                    continue
                combined = f"{title} {desc}".lower()
                if not (is_ai_relevant(combined) or is_privacy_relevant(combined)):
                    continue
                safe = re.sub(r"[^a-z0-9]", "_", title.lower())[:50]
                docs.append(self._make_doc(
                    id=f"SG-PDPC-{safe}", source="sg_pdpc_rss",
                    doc_type="PDPC News / Guidance",
                    title=title, url=link, published_date=pub,
                    agency="PDPC Singapore", status="Published",
                    full_text=desc or title,
                    raw_json={"title": title, "link": link},
                ))
        except Exception as e:
            log.warning("PDPC RSS failed: %s", e)
        return docs

    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        docs = self._pinned()
        docs.extend(self._fetch_pdpc_rss(lookback_days))
        log.info("Singapore: %d docs", len(docs))
        return docs

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        return []
