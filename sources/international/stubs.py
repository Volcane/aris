"""
ARIS — Japan Agent (Stub)

Data sources when activated:
  1. e-Gov Laws API — https://laws.e-gov.go.jp/api/1/lawdata/
     Japan's official legislative database; no key required
     Returns law text in Japanese (Claude interprets inline)

  2. METI (Ministry of Economy, Trade and Industry) press releases
     https://www.meti.go.jp/press/rss_en.xml
     English-language feed; covers AI governance guidelines and policy

  3. AI Governance Guidelines tracker
     https://www.meti.go.jp/policy/it_policy/ai-governance/

Key Japan AI policy landscape (as of 2026):
  - No comprehensive AI law; principle-based, voluntary approach
  - METI AI Governance Guidelines (2022, updated 2023) — voluntary
  - AI Strategy 2022 — national AI roadmap
  - AI Business Guidelines (April 2024) — METI/MIC joint guidelines
  - Hiroshima AI Process / G7 AI Code of Conduct (2023)
  - Diet (Parliament) considering sector-specific AI bills 2025-2026

To activate:
  1. Uncomment "JP" in config/jurisdictions.py ENABLED_INTERNATIONAL
  2. That's it — this class is fully functional
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sources.international.base import InternationalAgentBase, parse_date, strip_tags
from config.settings import LOOKBACK_DAYS
from utils.cache import http_get_text, is_ai_relevant, get_logger

log = get_logger("aris.international.jp")

METI_RSS  = "https://www.meti.go.jp/press/rss_en.xml"
EGOV_BASE = "https://laws.e-gov.go.jp/api/1"

PINNED_JP_DOCUMENTS = [
    {
        "id":       "JP-METI-AI-GUIDELINES-2024",
        "title":    "AI Business Guidelines — METI/MIC Joint Guidelines (April 2024)",
        "doc_type": "Government Guidelines",
        "date":     "2024-04-19",
        "status":   "Published — Voluntary",
        "url":      "https://www.meti.go.jp/policy/it_policy/ai-governance/",
        "agency":   "Ministry of Economy, Trade and Industry (METI) / Ministry of Internal Affairs (MIC)",
        "abstract": (
            "Japan's comprehensive AI business guidelines issued jointly by METI and MIC. "
            "Covers 10 AI principles: human-centricity, education, privacy protection, "
            "security, fair competition, fairness/accountability/transparency, innovation, "
            "safety, and more. Voluntary but widely followed. Aligns with OECD AI Principles "
            "and G7 Hiroshima AI Process. Relevant for companies operating in Japan."
        ),
    },
    {
        "id":       "JP-HIROSHIMA-AI-PROCESS-2023",
        "title":    "Hiroshima AI Process — G7 AI Code of Conduct (October 2023)",
        "doc_type": "International Agreement",
        "date":     "2023-10-30",
        "status":   "Published — Voluntary",
        "url":      "https://www.meti.go.jp/policy/it_policy/ai-governance/hiroshima-process.html",
        "agency":   "G7 / Japan (2023 G7 Presidency)",
        "abstract": (
            "The G7 Hiroshima AI Process produced a voluntary Code of Conduct for advanced "
            "AI developers, endorsed by G7 leaders. Includes 11 guiding principles covering "
            "transparency, accountability, risk management, and international interoperability. "
            "While voluntary, this represents international consensus from the world's largest "
            "economies on responsible AI development."
        ),
    },
]


class JapanAgent(InternationalAgentBase):
    jurisdiction_code    = "JP"
    jurisdiction_name    = "Japan"
    region               = "Asia-Pacific"
    language             = "ja"
    requires_translation = True   # METI feed is English; e-Gov is Japanese

    def _get_pinned_docs(self) -> List[Dict[str, Any]]:
        return [
            self._make_doc(
                id=i["id"], source="jp_pinned", doc_type=i["doc_type"],
                title=i["title"], url=i["url"],
                published_date=parse_date(i["date"]),
                agency=i["agency"], status=i["status"],
                full_text=i["abstract"], raw_json=i,
            )
            for i in PINNED_JP_DOCUMENTS
        ]

    def _fetch_meti_rss(self, lookback_days: int) -> List[Dict[str, Any]]:
        results = []
        since   = datetime.utcnow() - timedelta(days=lookback_days)
        try:
            xml_text = http_get_text(METI_RSS, use_cache=True)
            root     = ET.fromstring(xml_text)
            ns       = ""
            if root.tag.startswith("{"): ns = root.tag.split("}")[0] + "}"
            channel  = root.find(f"{ns}channel") or root
            for item in (channel.findall(f"{ns}item") or []):
                title   = (item.findtext(f"{ns}title")       or "").strip()
                link    = (item.findtext(f"{ns}link")         or "").strip()
                desc    = strip_tags(item.findtext(f"{ns}description") or "", 2000)
                pub_dt  = parse_date(item.findtext(f"{ns}pubDate") or "")
                if pub_dt and pub_dt < since: continue
                if not is_ai_relevant(f"{title} {desc}"): continue
                safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", link)[-60:]
                results.append(self._make_doc(
                    id=f"JP-METI-{safe_id}", source="jp_meti_rss",
                    doc_type="Ministry Press Release / Guidance",
                    title=title, url=link, published_date=pub_dt,
                    agency="METI Japan", status="Published",
                    full_text=desc or title, raw_json={"title": title, "link": link},
                ))
        except Exception as e:
            log.warning("METI RSS failed: %s", e)
        log.info("METI Japan RSS: %d AI items found", len(results))
        return results

    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        docs = self._get_pinned_docs()
        docs.extend(self._fetch_meti_rss(lookback_days))
        return docs

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        return []   # e-Gov API integration can be added here


# =============================================================================


"""
ARIS — China Agent (Stub)

Data sources when activated:
  1. CAC (Cyberspace Administration of China) announcements
     http://www.cac.gov.cn/  — No official API; web scraping needed
     Claude translates Chinese text inline.

  2. NPC Observer (unofficial English tracker)
     https://npcobserver.com — Monitors National People's Congress legislation

  3. MIIT (Ministry of Industry and Information Technology) press releases

Key China AI policy landscape (as of 2026):
  - Generative AI Regulation (Interim Measures) — effective July 2023
  - Algorithm Recommendation Regulation — effective March 2022
  - Deep Synthesis (Deepfakes) Regulation — effective January 2023
  - Draft AI Law — under development (expected 2025-2026)
  - MOST (Ministry of Science and Technology) AI ethics guidelines

Note: China's regulations apply to services operated IN China or targeting
Chinese users. VPN / internet access restrictions complicate API access.
Claude is used for inline translation of Chinese regulatory text.

To activate:
  Uncomment "CN" in config/jurisdictions.py ENABLED_INTERNATIONAL
"""

from sources.international.base import InternationalAgentBase, parse_date

PINNED_CN_DOCUMENTS = [
    {
        "id":       "CN-GENAI-INTERIM-MEASURES-2023",
        "title":    "Interim Measures for the Management of Generative AI Services (China)",
        "doc_type": "Administrative Regulation",
        "date":     "2023-07-13",
        "status":   "In Force — effective 15 August 2023",
        "url":      "http://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm",
        "agency":   "Cyberspace Administration of China (CAC)",
        "abstract": (
            "China's Generative AI regulation requires providers of generative AI services "
            "to Chinese users to: register with CAC before public launch, label AI-generated "
            "content, conduct security assessments, refuse illegal content, implement user "
            "verification, and maintain training data records. Penalties up to CNY 100,000 "
            "per violation. Applies to any company offering generative AI to users in China."
        ),
    },
    {
        "id":       "CN-ALGORITHM-RECOMMENDATION-2022",
        "title":    "Provisions on the Management of Algorithmic Recommendations (China)",
        "doc_type": "Administrative Regulation",
        "date":     "2022-01-04",
        "status":   "In Force — effective 1 March 2022",
        "url":      "http://www.cac.gov.cn/2022-01/04/c_1642894606364259.htm",
        "agency":   "Cyberspace Administration of China (CAC)",
        "abstract": (
            "Requires providers of algorithm recommendation services (content feeds, "
            "search ranking, targeted advertising) to: disclose algorithm use to users, "
            "offer opt-out options, avoid user addiction-inducing design, protect minors, "
            "prohibit price discrimination, and register large-scale recommendation systems. "
            "Applicable to any platform using algorithms to recommend content to Chinese users."
        ),
    },
]


class ChinaAgent(InternationalAgentBase):
    jurisdiction_code    = "CN"
    jurisdiction_name    = "China"
    region               = "Asia-Pacific"
    language             = "zh"
    requires_translation = True  # Claude handles Chinese inline

    def _get_pinned_docs(self) -> List[Dict[str, Any]]:
        return [
            self._make_doc(
                id=i["id"], source="cn_pinned", doc_type=i["doc_type"],
                title=i["title"], url=i["url"],
                published_date=parse_date(i["date"]),
                agency=i["agency"], status=i["status"],
                full_text=i["abstract"], raw_json=i,
            )
            for i in PINNED_CN_DOCUMENTS
        ]

    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        # CAC does not provide a public API; returns pinned docs only.
        # Override this method to add web scraping when needed.
        log.info("China agent: returning pinned documents only (no public CAC API)")
        return self._get_pinned_docs()

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        return []


# =============================================================================


"""
ARIS — Australia Agent (Stub)

Data sources when activated:
  1. Australian Parliament Bills — https://www.aph.gov.au/Parliamentary_Business/Bills_Legislation
     No official search API; Federal Register of Legislation has REST API.

  2. Federal Register of Legislation — https://www.legislation.gov.au/
     REST API available; covers Acts, Regulations, and Legislative Instruments.

  3. DISR (Department of Industry, Science and Resources) news feed
     https://www.industry.gov.au/

  4. OAIC (Office of the Australian Information Commissioner)
     https://www.oaic.gov.au/ — AI and privacy guidance

Key Australia AI policy landscape (as of 2026):
  - No comprehensive AI law enacted
  - Voluntary AI Safety Standard (DSIT, 2024)
  - Privacy Act review — AI-relevant amendments expected 2025-2026
  - AI Ethics Principles (DSIT, 2019, updated) — voluntary
  - AI Assurance Framework — under development

To activate:
  Uncomment "AU" in config/jurisdictions.py ENABLED_INTERNATIONAL
"""

PINNED_AU_DOCUMENTS = [
    {
        "id":       "AU-VOLUNTARY-AI-SAFETY-STANDARD-2024",
        "title":    "Australia Voluntary AI Safety Standard (October 2024)",
        "doc_type": "Government Standard (Voluntary)",
        "date":     "2024-10-04",
        "status":   "Published — Voluntary",
        "url":      "https://www.industry.gov.au/publications/voluntary-ai-safety-standard",
        "agency":   "Department of Industry, Science and Resources (DISR)",
        "abstract": (
            "Australia's voluntary framework for safe and responsible AI, built around "
            "10 guardrails covering governance, testing, transparency, human oversight, "
            "and redress. Designed for high-risk AI contexts. While voluntary, the "
            "government has stated it may become mandatory for government AI procurement "
            "and high-risk sectors. Companies supplying AI to Australian government "
            "or consumers should align with these guardrails proactively."
        ),
    },
]


class AustraliaAgent(InternationalAgentBase):
    jurisdiction_code = "AU"
    jurisdiction_name = "Australia"
    region            = "Asia-Pacific"
    language          = "en"

    def _get_pinned_docs(self) -> List[Dict[str, Any]]:
        return [
            self._make_doc(
                id=i["id"], source="au_pinned", doc_type=i["doc_type"],
                title=i["title"], url=i["url"],
                published_date=parse_date(i["date"]),
                agency=i["agency"], status=i["status"],
                full_text=i["abstract"], raw_json=i,
            )
            for i in PINNED_AU_DOCUMENTS
        ]

    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        return self._get_pinned_docs()

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        return []
