"""
ARIS — United Kingdom Agent

Data sources (all free, no API key required):

1. UK Parliament Bills API
   - https://bills-api.parliament.uk/api/v1/Bills
   - Searches active bills with AI-related keywords
   - Returns bill stages, sponsors, and document links

2. legislation.gov.uk REST API
   - https://www.legislation.gov.uk/
   - Fetches enacted Acts of Parliament, SIs, and their full text
   - Supports Atom feed for recent publications

3. GOV.UK Search API
   - https://www.gov.uk/api/search.json
   - Searches for AI-related policy papers, guidance, consultations
   - No key required

4. GOV.UK Content API
   - https://www.gov.uk/api/content/<path>
   - Fetches full content for specific gov.uk pages

Key UK AI policy landscape (as of 2026):
  - No comprehensive AI law yet enacted
  - AI Opportunities Action Plan (Jan 2025) — strategic roadmap
  - Artificial Intelligence (Regulation) Bill [HL] — private member's bill, Lords
  - Data (Use and Access) Act 2025 — includes AI/copyright provisions
  - ICO AI and data protection guidance (updated regularly)
  - Ofcom Online Safety Act guidance covering AI chatbots (March 2025)
  - AI Growth Lab consultation (Oct 2025 — regulatory sandbox proposal)
  - Sector-specific AI guidance from FCA, MHRA, CMA ongoing
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sources.international.base import InternationalAgentBase, parse_date, strip_tags
from config.settings import AI_KEYWORDS, LOOKBACK_DAYS
_PRIVACY_FETCH_TERMS = [
    'gdpr', 'uk gdpr', 'data protection', 'personal data',
    'privacy', 'ico', 'information commissioner',
]
from utils.cache import http_get, http_get_text, is_ai_relevant, get_logger
from utils.search import is_privacy_relevant, detect_domain

log = get_logger("aris.international.uk")

# ── Endpoint constants ────────────────────────────────────────────────────────

PARLIAMENT_BILLS_API = "https://bills-api.parliament.uk/api/v1/Bills"
LEGISLATION_SEARCH   = "https://www.legislation.gov.uk/search"
LEGISLATION_FEED     = "https://www.legislation.gov.uk/new/data.feed"
GOVUK_SEARCH         = "https://www.gov.uk/api/search.json"
GOVUK_CONTENT        = "https://www.gov.uk/api/content"

# Pinned high-priority UK AI policy documents
PINNED_UK_DOCUMENTS = [
    {
        "id":       "UK-AI-OPPS-PLAN-2025",
        "title":    "UK AI Opportunities Action Plan (January 2025)",
        "doc_type": "Government Strategy",
        "date":     "2025-01-13",
        "status":   "Published",
        "url":      "https://www.gov.uk/government/publications/ai-opportunities-action-plan",
        "agency":   "Department for Science, Innovation and Technology (DSIT)",
        "abstract": (
            "The UK government's strategic plan to position the UK as an AI superpower. "
            "Sets out three pillars: AI infrastructure investment, public sector AI adoption, "
            "and supporting homegrown AI development. Includes dedicated AI Growth Zones, "
            "a National Data Library, and new compute infrastructure commitments. "
            "Companies should assess alignment with UK AI procurement and partnering opportunities."
        ),
    },
    {
        "id":       "UK-DATA-USE-ACCESS-ACT-2025",
        "title":    "Data (Use and Access) Act 2025",
        "doc_type": "Act of Parliament",
        "date":     "2025-06-19",
        "status":   "Royal Assent",
        "url":      "https://www.legislation.gov.uk/ukpga/2025/19",
        "agency":   "UK Parliament",
        "abstract": (
            "Enacted law modernising UK data frameworks. Includes provisions requiring "
            "the Secretary of State to report on AI use of copyright works and the economic "
            "impact of AI/copyright policy options by 19 March 2026. Relevant to AI companies "
            "training on UK-sourced content."
        ),
    },
    {
        "id":       "UK-AI-REGULATION-BILL-HL-2025",
        "title":    "Artificial Intelligence (Regulation) Bill [HL] (March 2025)",
        "doc_type": "Private Member's Bill",
        "date":     "2025-03-04",
        "status":   "Lords — 1st Reading",
        "url":      "https://bills.parliament.uk/bills/3942",
        "agency":   "House of Lords (Lord Holmes of Richmond)",
        "abstract": (
            "Private Member's Bill proposing creation of an AI Authority to coordinate "
            "UK AI regulation across sectors, regulatory sandboxes for AI testing, and a "
            "mandatory register of high-risk AI systems. Not government-backed; probability "
            "of passage is low, but it signals the direction of future mandatory regulation."
        ),
    },
    {
        "id":       "UK-AI-GROWTH-LAB-CONSULT-2025",
        "title":    "UK AI Growth Lab Consultation (October 2025)",
        "doc_type": "Government Consultation",
        "date":     "2025-10-21",
        "status":   "Closed — Responses Under Review",
        "url":      "https://www.gov.uk/government/consultations/ai-growth-lab",
        "agency":   "Regulatory Innovation Office (RIO) / DSIT",
        "abstract": (
            "Proposal for cross-economy regulatory sandboxes allowing businesses to test "
            "AI innovations under temporary regulatory modifications. Successful pilots could "
            "lead to permanent regulatory reform. Red lines preserved: consumer protection, "
            "safety, and fundamental rights. Companies should monitor for sandbox eligibility."
        ),
    },
    {
        "id":       "UK-ICO-AI-RECRUITMENT-2024",
        "title":    "ICO Audit Outcomes: AI in Recruitment (November 2024)",
        "doc_type": "Regulatory Guidance",
        "date":     "2024-11-01",
        "status":   "Published",
        "url":      "https://ico.org.uk/about-the-ico/research-and-reports/ai-and-data-protection/",
        "agency":   "Information Commissioner's Office (ICO)",
        "abstract": (
            "ICO audit findings and recommendations for AI providers and developers of "
            "AI-powered sourcing, screening and selection tools used in recruitment. "
            "Covers lawful basis, transparency, fairness, and automated decision-making "
            "under UK GDPR Article 22. Mandatory reading for HR-tech AI providers."
        ),
    },
]


class UKAgent(InternationalAgentBase):
    """
    United Kingdom AI regulation monitor.

    Tracks:
     - UK Parliament active AI-related bills
     - legislation.gov.uk new Acts and Statutory Instruments
     - GOV.UK policy papers, guidance, and consultations
     - Pinned critical UK AI policy documents
    """

    jurisdiction_code = "GB"
    jurisdiction_name = "United Kingdom"
    region            = "Europe"
    language          = "en"

    # ── Pinned documents ──────────────────────────────────────────────────────

    def _get_pinned_docs(self) -> List[Dict[str, Any]]:
        docs = []
        for item in PINNED_UK_DOCUMENTS:
            docs.append(self._make_doc(
                id           = item["id"],
                source       = "uk_pinned",
                doc_type     = item["doc_type"],
                title        = item["title"],
                url          = item["url"],
                published_date = parse_date(item["date"]),
                agency       = item["agency"],
                status       = item["status"],
                full_text    = item["abstract"],
                raw_json     = item,
            ))
        return docs

    # ── UK Parliament Bills API ───────────────────────────────────────────────

    def _fetch_parliament_bills(self) -> List[Dict[str, Any]]:
        """
        Search the UK Parliament Bills API for AI-related bills.
        API docs: https://bills-api.parliament.uk/index.html
        """
        results  = []
        pinned   = {d["id"] for d in PINNED_UK_DOCUMENTS}

        for term in ["artificial intelligence", "machine learning", "algorithmic"]:
            try:
                params = {
                    "SearchTerm":  term,
                    "CurrentHouse": "All",
                    "IsDefeated":  "false",
                    "Skip":        0,
                    "Take":        25,
                }
                data = http_get(PARLIAMENT_BILLS_API, params=params)
                bills = data.get("items", [])

                for bill in bills:
                    title = bill.get("shortTitle") or bill.get("longTitle") or ""
                    if not is_ai_relevant(title + " " + term):
                        continue

                    bill_id   = str(bill.get("billId", ""))
                    doc_id    = f"UK-BILL-{bill_id}"
                    if doc_id in pinned:
                        continue

                    stage     = bill.get("currentStage", {})
                    stage_str = (stage.get("description") or "") if stage else ""
                    house     = bill.get("originatingHouse") or ""
                    url       = f"https://bills.parliament.uk/bills/{bill_id}"

                    results.append(self._make_doc(
                        id           = doc_id,
                        source       = "uk_parliament_bills",
                        doc_type     = "Bill",
                        title        = title,
                        url          = url,
                        published_date = parse_date(bill.get("lastUpdate")),
                        agency       = f"UK Parliament — {house}",
                        status       = stage_str or "Active",
                        full_text    = title,
                        raw_json     = bill,
                    ))

            except Exception as e:
                log.warning("UK Parliament Bills API failed (%s): %s", term, e)

        log.info("UK Parliament: %d AI bills found", len(results))
        return results

    # ── legislation.gov.uk Atom feed ──────────────────────────────────────────

    def _fetch_legislation_feed(self, lookback_days: int) -> List[Dict[str, Any]]:
        """
        Parse the legislation.gov.uk new-items Atom feed.
        Filters for AI-relevant enacted legislation.
        """
        results = []
        since   = datetime.utcnow() - timedelta(days=lookback_days)

        try:
            xml_text = http_get_text(LEGISLATION_FEED, use_cache=True)
            root     = ET.fromstring(xml_text)
            ns       = "{http://www.w3.org/2005/Atom}"

            for entry in root.findall(f"{ns}entry"):
                title    = (entry.findtext(f"{ns}title")   or "").strip()
                link_el  = entry.find(f"{ns}link[@rel='alternate']")
                link     = link_el.get("href", "") if link_el is not None else ""
                updated  = (entry.findtext(f"{ns}updated") or "").strip()
                summary  = strip_tags(entry.findtext(f"{ns}summary") or "", 2000)

                pub_dt = parse_date(updated)
                if pub_dt and pub_dt < since:
                    continue
                if not is_ai_relevant(f"{title} {summary}"):
                    continue

                safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", link)[-60:]
                results.append(self._make_doc(
                    id           = f"UK-LEGIS-{safe_id}",
                    source       = "uk_legislation_feed",
                    doc_type     = "Enacted Legislation",
                    title        = title,
                    url          = link,
                    published_date = pub_dt,
                    agency       = "UK Parliament",
                    status       = "Enacted",
                    full_text    = summary or title,
                    raw_json     = {"title": title, "link": link},
                ))

        except Exception as e:
            log.warning("legislation.gov.uk feed failed: %s", e)

        log.info("legislation.gov.uk: %d AI entries found", len(results))
        return results

    # ── GOV.UK Search API ─────────────────────────────────────────────────────

    def _fetch_govuk_publications(self, lookback_days: int) -> List[Dict[str, Any]]:
        """
        Search GOV.UK for AI-related policy papers, guidance, and consultations.
        API: https://www.gov.uk/api/search.json
        """
        results = []
        since   = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        for term in ["artificial intelligence regulation", "AI safety", "algorithmic accountability"]:
            try:
                params = {
                    "q":              term,
                    "filter_content_purpose_supergroup[]": [
                        "guidance_and_regulation",
                        "policy_and_engagement",
                        "research_and_statistics",
                    ],
                    "order":          "-public_timestamp",
                    "count":          20,
                    "fields[]":       ["title", "link", "description", "public_timestamp",
                                       "content_purpose_supergroup", "organisations"],
                }
                data  = http_get(GOVUK_SEARCH, params=params)
                items = data.get("results", [])

                for item in items:
                    title    = item.get("title", "")
                    desc     = item.get("description", "")
                    pub_str  = item.get("public_timestamp", "")
                    link     = "https://www.gov.uk" + item.get("link", "")

                    pub_dt = parse_date(pub_str)
                    if pub_dt and pub_dt < datetime.utcnow() - timedelta(days=lookback_days):
                        continue
                    if not is_ai_relevant(f"{title} {desc}"):
                        continue

                    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", item.get("link", ""))[-60:]
                    doc_id  = f"UK-GOVUK-{safe_id}"
                    orgs    = ", ".join(
                        o.get("title", "") for o in item.get("organisations", [])
                    )

                    results.append(self._make_doc(
                        id           = doc_id,
                        source       = "uk_govuk_search",
                        doc_type     = item.get("content_purpose_supergroup", "Publication").replace("_", " ").title(),
                        title        = title,
                        url          = link,
                        published_date = pub_dt,
                        agency       = orgs or "UK Government",
                        status       = "Published",
                        full_text    = desc,
                        raw_json     = item,
                    ))

            except Exception as e:
                log.warning("GOV.UK search failed (%s): %s", term, e)

        # De-duplicate within this method
        seen, unique = set(), []
        for r in results:
            if r["id"] not in seen:
                seen.add(r["id"])
                unique.append(r)

        log.info("GOV.UK search: %d AI publications found", len(unique))
        return unique

    # ── Main fetch ────────────────────────────────────────────────────────────

    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS,
                     domain: str = 'both') -> List[Dict[str, Any]]:
        """Primary: pinned docs + Parliament bills API."""
        docs = []
        docs.extend(self._get_pinned_docs())
        docs.extend(self._fetch_parliament_bills())
        return docs

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS,
                         domain: str = 'both') -> List[Dict[str, Any]]:
        """Secondary: legislation.gov.uk feed + GOV.UK policy publications."""
        docs = []
        docs.extend(self._fetch_legislation_feed(lookback_days))
        docs.extend(self._fetch_govuk_publications(lookback_days))
        return docs
