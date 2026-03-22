"""
ARIS — South Korea Agent

South Korea has comprehensive AI and privacy regulation:
  - PIPA (Personal Information Protection Act, 2023 amendments) — in force
  - Act on the Promotion of AI Industry and Establishing Trust in AI (2024 draft)
  - ISMS-P (Information Security Management System — Personal Information)
  - AI Guidelines for companies — KISA and PIPC
  - Financial AI regulations — FSC

Key regulators:
  - PIPC (Personal Information Protection Commission) — data privacy
  - MSIT (Ministry of Science and ICT) — AI policy
  - KISA (Korea Internet & Security Agency) — implementation guidance

Sources:
  1. PIPC press releases (English)
  2. MSIT news (English summaries available)
  3. Pinned key legislation and guidelines
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sources.international.base import InternationalAgentBase, parse_date, strip_tags
from config.settings import LOOKBACK_DAYS
from utils.cache import http_get_text, http_get, is_ai_relevant, get_logger
from utils.search import is_privacy_relevant, detect_domain

log = get_logger("aris.international.kr")

PIPC_NEWS_URL = "https://www.pipc.go.kr/np/cop/bbs/selectBoardList.do?bbsId=BS074&mCode=C020020000"

PINNED_KR = [
    {
        "id":       "KR-PIPA-2023-AMENDMENTS",
        "title":    "Personal Information Protection Act — 2023 Amendments (South Korea)",
        "doc_type": "Legislation",
        "date":     "2023-09-15",
        "status":   "In Force — effective 15 September 2023",
        "url":      "https://www.pipc.go.kr/np/default/page.do?mCode=D010010000",
        "agency":   "Personal Information Protection Commission (PIPC)",
        "abstract": (
            "Major 2023 amendments to South Korea's PIPA: unified enforcement under PIPC "
            "(absorbed Ministry of Interior's role), strengthened data subject rights "
            "including automated decision-making opt-out (Article 37-2), mobile ID "
            "verification flexibility, enhanced cross-border transfer rules, "
            "and increased penalties up to 3% of annual turnover. PIPA now closely "
            "parallels GDPR in scope and enforcement. Applies to all organisations "
            "processing Korean residents' personal information."
        ),
    },
    {
        "id":       "KR-AI-PROMOTION-ACT-2024",
        "title":    "Act on the Promotion of AI Industry and Framework for AI Trust (South Korea, 2024)",
        "doc_type": "Legislation (Enacted)",
        "date":     "2024-12-26",
        "status":   "Enacted — staged implementation 2025-2026",
        "url":      "https://www.msit.go.kr/eng/bbs/view.do?sCode=eng&mId=4&mPid=2&pageIndex=1&bbsSeqNo=42&nttSeqNo=3201889",
        "agency":   "Ministry of Science and ICT (MSIT)",
        "abstract": (
            "South Korea's AI Basic Act enacted December 2024 — first comprehensive AI law "
            "in Asia. Creates a national AI committee, mandates impact assessments for "
            "high-impact AI systems, requires transparency disclosures, establishes AI "
            "safety testing frameworks, and grants the government powers to restrict "
            "dangerous AI. Covers AI developers and deployers operating in Korea. "
            "Staged implementation 2025-2026. Penalty provisions up to KRW 30M."
        ),
    },
    {
        "id":       "KR-PIPA-AUTOMATED-DECISION-GUIDANCE-2023",
        "title":    "PIPC Guidance on Automated Decision-Making under PIPA (2023)",
        "doc_type": "Regulatory Guidance",
        "date":     "2023-12-01",
        "status":   "Published",
        "url":      "https://www.pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS074&mCode=C020020000",
        "agency":   "Personal Information Protection Commission (PIPC)",
        "abstract": (
            "PIPC guidance on the Article 37-2 automated decision-making provisions: "
            "right to explanation, right to refuse automated decisions, right to human "
            "review. Applies to significant automated decisions about employment, credit, "
            "insurance, education. Operators must disclose criteria, provide explanations "
            "within 10 days of request, and offer human review within 30 days."
        ),
    },
]


class SouthKoreaAgent(InternationalAgentBase):
    jurisdiction_code    = "KR"
    jurisdiction_name    = "South Korea"
    region               = "Asia-Pacific"
    language             = "ko"
    requires_translation = True  # Source may include Korean; Claude handles inline

    def _pinned(self) -> List[Dict[str, Any]]:
        return [
            self._make_doc(
                id=d["id"], source="kr_pinned", doc_type=d["doc_type"],
                title=d["title"], url=d["url"],
                published_date=parse_date(d["date"]),
                agency=d["agency"], status=d["status"],
                full_text=d["abstract"], raw_json=d,
            )
            for d in PINNED_KR
        ]

    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        # PIPC doesn't offer a public RSS/API; return pinned key documents.
        # The 2023 PIPA amendments and 2024 AI Act are the primary instruments.
        docs = self._pinned()
        log.info("South Korea: %d docs (pinned)", len(docs))
        return docs

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        return []
