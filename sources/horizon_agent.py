"""
ARIS — Horizon Agent

Monitors forward-looking regulatory calendars to surface regulations that are
PLANNED or ADVANCING but not yet published — giving weeks or months of
preparation time rather than reaction time.

Four source tracks, all free and public:

1. UNIFIED REGULATORY AGENDA (reginfo.gov)
   Published twice per year by OMB, lists every planned US federal rulemaking
   with the responsible agency, rule title, anticipated publication stage
   (pre-rule / proposed / final rule), and anticipated date.
   No API key required.

2. CONGRESS.GOV HEARING SCHEDULES
   Uses the existing Congress.gov API key to fetch committee hearing schedules.
   Bills with upcoming markup hearings are significantly more likely to advance.
   Filters for AI-relevant bills already in the document DB or matching keywords.

3. EU COMMISSION WORK PROGRAMME
   Annual document listing all planned EU legislative initiatives. Fetched once
   per quarter from the Commission website. Parsed for AI-relevant entries.
   No API key required.

4. UK PARLIAMENT UPCOMING BUSINESS
   The whatson.parliament.uk API provides upcoming bill stage dates.
   Uses the existing Parliament Bills API (no key required).

All horizon items are:
  - Scored with the existing keyword_score() filter before storage
  - Stored in the regulatory_horizon table (not documents table)
  - Assigned a stage: planned | pre-rule | proposed | hearing | final | enacted
  - Given an anticipated_date for the timeline view
  - Never sent to Claude — keyword scoring is sufficient

Design:
  - Fails gracefully per source — one source error never blocks others
  - Deduplicates by (source, external_id) — safe to run repeatedly
  - Respects HTTP cache to avoid hammering government APIs
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from utils.cache import http_get, http_get_text, keyword_score, is_ai_relevant, get_logger
from utils.search import is_privacy_relevant, detect_domain
from config.settings import CONGRESS_GOV_KEY, CONGRESS_BASE, AI_KEYWORDS

log = get_logger("aris.horizon")


# Module-level re-exports so tests can patch them cleanly
def upsert_horizon_item(item: dict) -> bool:
    from utils.db import upsert_horizon_item as _fn
    return _fn(item)


def get_horizon_items(**kwargs):
    from utils.db import get_horizon_items as _fn
    return _fn(**kwargs)

# ── Stage vocabulary ──────────────────────────────────────────────────────────

STAGES = {
    "planned":  "Planned",
    "pre-rule": "Pre-Rule",
    "proposed": "Proposed Rule",
    "hearing":  "Hearing Scheduled",
    "final":    "Final Rule Pending",
    "enacted":  "Enacted",
}


# ── Seeded horizon items ──────────────────────────────────────────────────────
# Known upcoming regulatory events with confirmed dates or strong signals.
# These seed the horizon view so it always has meaningful content, and serve
# as the test baseline for the horizon feature.
# Sources: reginfo.gov Unified Agenda, EUR-Lex prep, UK Parliament, ANPD, PIPC
# Last verified: March 2026

SEEDED_HORIZON = [
    # ── US Federal ────────────────────────────────────────────────────────────
    {
        "source": "seeded", "external_id": "seed-ftc-ai-surveillance-2026",
        "jurisdiction": "Federal", "stage": "proposed",
        "title": "FTC Commercial Surveillance and Data Security Rulemaking",
        "description": "FTC rulemaking on commercial data surveillance practices, including AI-driven profiling and automated decision-making. Anticipated NPRM 2026.",
        "agency": "Federal Trade Commission (FTC)",
        "anticipated_date": "2026-06-01",
        "url": "https://www.ftc.gov/legal-library/browse/rules/commercial-surveillance-rulemaking",
        "ai_score": 0.45,
    },
    {
        "source": "seeded", "external_id": "seed-cfpb-ai-credit-2026",
        "jurisdiction": "Federal", "stage": "proposed",
        "title": "CFPB AI/Automated Underwriting Fair Lending Guidance",
        "description": "CFPB guidance on use of AI in credit underwriting under ECOA and Fair Housing Act. Addresses explainability and adverse action requirements.",
        "agency": "Consumer Financial Protection Bureau (CFPB)",
        "anticipated_date": "2026-04-01",
        "url": "https://www.consumerfinance.gov/",
        "ai_score": 0.40,
    },
    {
        "source": "seeded", "external_id": "seed-hhs-ai-health-2026",
        "jurisdiction": "Federal", "stage": "proposed",
        "title": "HHS Algorithmic Decision-Making in Healthcare Coverage Rules",
        "description": "HHS proposed rule restricting use of AI/algorithms in prior authorisation and coverage determinations for Medicare/Medicaid managed care.",
        "agency": "Dept of Health and Human Services (HHS) / CMS",
        "anticipated_date": "2026-07-01",
        "url": "https://www.cms.gov/",
        "ai_score": 0.38,
    },
    {
        "source": "seeded", "external_id": "seed-eeoc-ai-employment-2026",
        "jurisdiction": "Federal", "stage": "planned",
        "title": "EEOC AI and Automated Employment Decision Tools Guidance",
        "description": "EEOC guidance on employer liability for AI hiring tools under Title VII and ADA. Addresses adverse impact, validation, and candidate notice.",
        "agency": "Equal Employment Opportunity Commission (EEOC)",
        "anticipated_date": "2026-09-01",
        "url": "https://www.eeoc.gov/ai",
        "ai_score": 0.42,
    },
    {
        "source": "seeded", "external_id": "seed-nist-ai-rmf-2-2026",
        "jurisdiction": "Federal", "stage": "planned",
        "title": "NIST AI Risk Management Framework 2.0",
        "description": "NIST update to the AI RMF 1.0 (2023), incorporating lessons learned and addressing generative AI, agentic AI, and synthetic content risks.",
        "agency": "National Institute of Standards and Technology (NIST)",
        "anticipated_date": "2026-12-01",
        "url": "https://www.nist.gov/artificial-intelligence",
        "ai_score": 0.50,
    },
    # ── Colorado ──────────────────────────────────────────────────────────────
    {
        "source": "seeded", "external_id": "seed-co-ai-act-effective-2026",
        "jurisdiction": "CO", "stage": "enacted",
        "title": "Colorado AI Act (SB 24-205) — Compliance Effective Date",
        "description": "Colorado Artificial Intelligence Act enters full enforcement. Developers and deployers of high-risk AI systems must have impact assessments, consumer disclosures, and governance programmes in place.",
        "agency": "Colorado Attorney General",
        "anticipated_date": "2026-06-30",
        "url": "https://leg.colorado.gov/bills/sb24-205",
        "ai_score": 0.60,
    },
    # ── California ────────────────────────────────────────────────────────────
    {
        "source": "seeded", "external_id": "seed-ca-sb942-effective-2026",
        "jurisdiction": "CA", "stage": "enacted",
        "title": "California AI Transparency Act (SB 942) — Effective Date",
        "description": "SB 942 requires generative AI providers with 1M+ monthly visitors to implement watermarks, latent disclosures, and AI content detection tools. Effective August 2, 2026.",
        "agency": "California Attorney General",
        "anticipated_date": "2026-08-02",
        "url": "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240SB942",
        "ai_score": 0.55,
    },
    # ── EU ────────────────────────────────────────────────────────────────────
    {
        "source": "seeded", "external_id": "seed-eu-ai-act-gp-ai-2026",
        "jurisdiction": "EU", "stage": "enacted",
        "title": "EU AI Act — GPAI Model Obligations Apply",
        "description": "General Purpose AI (GPAI) model provisions of the EU AI Act become applicable. Providers of GPAI models must publish technical documentation, comply with copyright law, and publish training data summaries.",
        "agency": "EU AI Office / European Commission",
        "anticipated_date": "2026-08-02",
        "url": "https://artificialintelligenceact.eu/",
        "ai_score": 0.65,
    },
    {
        "source": "seeded", "external_id": "seed-eu-ai-act-highrisk-2027",
        "jurisdiction": "EU", "stage": "enacted",
        "title": "EU AI Act — High-Risk AI System Obligations Apply",
        "description": "Annex III high-risk AI system requirements become fully applicable. Conformity assessments, technical documentation, human oversight, and CE marking required for covered systems.",
        "agency": "EU AI Office / European Commission",
        "anticipated_date": "2027-08-02",
        "url": "https://artificialintelligenceact.eu/",
        "ai_score": 0.65,
    },
    {
        "source": "seeded", "external_id": "seed-eu-eidas2-ai-2026",
        "jurisdiction": "EU", "stage": "enacted",
        "title": "EU eIDAS 2.0 — European Digital Identity Wallet Deployment",
        "description": "EU member states must make European Digital Identity Wallet available to all citizens. AI-relevant for identity verification, authentication systems, and automated KYC.",
        "agency": "European Commission / Member States",
        "anticipated_date": "2026-11-01",
        "url": "https://ec.europa.eu/digital-single-market/en/trust-services-and-eid",
        "ai_score": 0.35,
    },
    {
        "source": "seeded", "external_id": "seed-eu-data-act-dataspc-2026",
        "jurisdiction": "EU", "stage": "enacted",
        "title": "EU Data Act — Data Sharing Obligations Apply",
        "description": "EU Data Act fully applicable. Connected product manufacturers must provide data access. AI services using connected device data must comply with sharing and switching obligations.",
        "agency": "European Commission",
        "anticipated_date": "2026-09-12",
        "url": "https://digital-strategy.ec.europa.eu/en/policies/data-act",
        "ai_score": 0.40,
    },
    # ── UK ────────────────────────────────────────────────────────────────────
    {
        "source": "seeded", "external_id": "seed-uk-ai-bill-2026",
        "jurisdiction": "GB", "stage": "proposed",
        "title": "UK Artificial Intelligence (Regulation) Bill — Parliamentary Progress",
        "description": "Private member's bill establishing sector-specific AI regulatory framework progressing through Parliament. Builds on the government's pro-innovation approach with targeted safety duties.",
        "agency": "UK Parliament",
        "anticipated_date": "2026-06-01",
        "url": "https://bills.parliament.uk/",
        "ai_score": 0.52,
    },
    {
        "source": "seeded", "external_id": "seed-uk-dpdi-2026",
        "jurisdiction": "GB", "stage": "enacted",
        "title": "UK Data Protection and Digital Information Act — Secondary Legislation",
        "description": "Secondary legislation and ICO codes of practice under the DPDI Act covering AI and automated decision-making, including updated Article 22 equivalent provisions.",
        "agency": "ICO / DSIT",
        "anticipated_date": "2026-10-01",
        "url": "https://www.gov.uk/government/collections/data-protection-and-digital-information-bill",
        "ai_score": 0.45,
    },
    # ── Brazil ────────────────────────────────────────────────────────────────
    {
        "source": "seeded", "external_id": "seed-br-ai-bill-vote-2026",
        "jurisdiction": "BR", "stage": "proposed",
        "title": "Brazil AI Bill (PL 2338/2023) — Full Senate Vote Expected",
        "description": "Brazil's comprehensive AI regulation bill expected to reach full Senate floor vote. Risk-based classification, prohibited uses, high-risk obligations, and creation of National AI Authority.",
        "agency": "Senado Federal do Brasil",
        "anticipated_date": "2026-06-01",
        "url": "https://www25.senado.leg.br/web/atividade/materias/-/materia/157233",
        "ai_score": 0.50,
    },
    # ── India ─────────────────────────────────────────────────────────────────
    {
        "source": "seeded", "external_id": "seed-in-dpdp-rules-2026",
        "jurisdiction": "IN", "stage": "proposed",
        "title": "India DPDP Rules — Draft Rules Under Digital Personal Data Protection Act",
        "description": "Ministry of Electronics and IT expected to finalise draft rules under the DPDP Act 2023, covering consent managers, data fiduciary obligations, children's data, and the Data Protection Board constitution.",
        "agency": "Ministry of Electronics and IT (MEITY)",
        "anticipated_date": "2026-06-30",
        "url": "https://www.meity.gov.in/",
        "ai_score": 0.42,
    },
    # ── South Korea ───────────────────────────────────────────────────────────
    {
        "source": "seeded", "external_id": "seed-kr-ai-act-vote-2026",
        "jurisdiction": "KR", "stage": "proposed",
        "title": "South Korea AI Promotion Act — National Assembly Vote",
        "description": "Korea's comprehensive AI bill expected to pass National Assembly in 2026. Mandatory risk assessment for high-impact AI, transparency for generative AI, National AI Commission establishment.",
        "agency": "Korean National Assembly / MSIT",
        "anticipated_date": "2026-09-01",
        "url": "https://www.msit.go.kr/eng/",
        "ai_score": 0.48,
    },
    # ── Singapore ─────────────────────────────────────────────────────────────
    {
        "source": "seeded", "external_id": "seed-sg-model-ai-v3-2026",
        "jurisdiction": "SG", "stage": "planned",
        "title": "Singapore Model AI Governance Framework 3rd Edition",
        "description": "IMDA/PDPC expected to release updated Model AI Governance Framework covering generative AI, agentic AI, and updated accountability structures for AI developers and deployers.",
        "agency": "IMDA / PDPC Singapore",
        "anticipated_date": "2026-12-01",
        "url": "https://www.imda.gov.sg/",
        "ai_score": 0.45,
    },
]

# Minimum keyword score to store a horizon item.
# Intentionally low — horizon items are short titles; the keyword scorer
# normalises against a large vocabulary so even "artificial intelligence"
# alone scores ~0.10. We use is_ai_relevant / is_privacy_relevant as the
# primary gate and keep MIN_SCORE as a backstop against total irrelevance.
MIN_SCORE = 0.04


# ── Horizon Agent ─────────────────────────────────────────────────────────────

class HorizonAgent:
    """
    Fetches and stores forward-looking regulatory horizon items.
    """

    def run(self, days_ahead: int = 365) -> Dict[str, int]:
        """
        Fetch horizon items from all sources.
        Returns {source: new_items_count} for each source attempted.
        """
        counts: Dict[str, int] = {}

        for name, method in [
            ("seeded",              self._fetch_seeded_items),
            ("unified_agenda",      self._fetch_unified_agenda),
            ("congress_hearings",   self._fetch_congress_hearings),
            ("eu_work_programme",   self._fetch_eu_work_programme),
            ("uk_upcoming",         self._fetch_uk_upcoming),
        ]:
            try:
                items = method(days_ahead=days_ahead)
                saved = self._save_items(items)
                counts[name] = saved
                if items:
                    log.info("Horizon %s: %d fetched, %d new", name, len(items), saved)
            except Exception as e:
                log.warning("Horizon source %s failed: %s", name, e)
                counts[name] = 0

        return counts

    # ── Seeded known items ────────────────────────────────────────────────────

    def _fetch_seeded_items(self, days_ahead: int = 365) -> List[Dict]:
        """
        Return curated known upcoming regulatory events.
        These seed the horizon view so it is always meaningful and testable,
        regardless of external API availability.
        Updates should be made to SEEDED_HORIZON when new major events are confirmed.
        """
        items = []
        for seed in SEEDED_HORIZON:
            date_val = seed.get("anticipated_date")
            if isinstance(date_val, str):
                date_val = _parse_date(date_val)
            items.append({
                "source":          seed["source"],
                "external_id":     seed["external_id"],
                "jurisdiction":    seed["jurisdiction"],
                "title":           seed["title"],
                "description":     seed["description"],
                "agency":          seed["agency"],
                "stage":           seed["stage"],
                "anticipated_date": date_val,
                "url":             seed.get("url", ""),
                "ai_score":        seed.get("ai_score", 0.5),
            })
        return items

    # ── Source 1: Unified Regulatory Agenda ──────────────────────────────────

    def _fetch_unified_agenda(self, days_ahead: int = 365) -> List[Dict]:
        """
        Fetch from the Unified Regulatory Agenda XML feed at reginfo.gov.
        The agenda is published twice per year. We parse the XML for AI-relevant
        rulemakings and extract their anticipated action dates.
        """
        items = []

        # The agenda XML is large; use the search endpoint instead
        # reginfo.gov provides a JSON search API for agenda entries
        url = "https://www.reginfo.gov/public/do/XMLViewPublishedDocsPublic"
        params = {
            "operation": "MAIN",
            "type":      "UNIFIED",
            "publish_date": "current",
        }

        try:
            # Try the lighter-weight search endpoint first
            search_url = "https://www.reginfo.gov/public/do/eAgendaMain"
            # Fetch the agency-filtered search for AI-related terms
            for keyword in ["artificial intelligence", "machine learning", "automated decision"]:
                search_params = {
                    "operation":       "MAIN",
                    "agenda_term":     keyword,
                    "agenda_status":   "active",
                }
                try:
                    data = http_get(search_url, params=search_params, timeout=15)
                    if isinstance(data, dict):
                        entries = data.get("entries") or data.get("results") or []
                        for entry in entries:
                            item = self._parse_agenda_entry(entry)
                            if item:
                                items.append(item)
                except Exception:
                    pass

        except Exception as e:
            log.debug("Unified Agenda search failed: %s — trying RSS fallback", e)

        # RSS fallback — the agenda publishes an RSS with recent additions
        if not items:
            try:
                rss = http_get_text(
                    "https://www.reginfo.gov/public/do/eAgendaXml?operation=MAIN",
                    timeout=20
                )
                items = self._parse_agenda_rss(rss or "")
            except Exception as e:
                log.debug("Unified Agenda RSS fallback failed: %s", e)

        # Deduplicate by external_id
        seen = set()
        unique = []
        for item in items:
            if item["external_id"] not in seen:
                seen.add(item["external_id"])
                unique.append(item)

        return unique

    def _parse_agenda_entry(self, entry: Dict) -> Optional[Dict]:
        title = (entry.get("title") or entry.get("rule_title") or "").strip()
        if not title:
            return None
        combined = title + " " + (entry.get("abstract") or "")
        score = keyword_score(combined)
        if score < MIN_SCORE and not is_ai_relevant(combined) and not is_privacy_relevant(combined):
            return None

        eid = entry.get("rin") or entry.get("id") or _make_id("agenda", title)

        # Parse anticipated date
        date_str = (entry.get("anticipated_nprmdate") or
                    entry.get("anticipated_finaldate") or
                    entry.get("next_action_date") or "")
        anticipated = _parse_date(date_str)

        stage_raw = (entry.get("stage") or entry.get("priority") or "").lower()
        stage = "proposed" if "proposed" in stage_raw or "nprm" in stage_raw else \
                "pre-rule"  if "pre" in stage_raw else \
                "final"     if "final" in stage_raw else \
                "planned"

        return {
            "source":         "unified_agenda",
            "external_id":    str(eid),
            "jurisdiction":   "Federal",
            "title":          title,
            "description":    entry.get("abstract") or "",
            "agency":         entry.get("agency_name") or entry.get("agency") or "",
            "stage":          stage,
            "anticipated_date": anticipated,
            "url":            entry.get("url") or "",
            "ai_score":       round(score, 3),
        }

    def _parse_agenda_rss(self, rss_text: str) -> List[Dict]:
        """Parse the Unified Regulatory Agenda RSS feed."""
        items = []
        if not rss_text:
            return items

        # Extract <item> blocks
        item_blocks = re.findall(r"<item>(.*?)</item>", rss_text, re.DOTALL)
        for block in item_blocks:
            title = _xml_text(block, "title")
            desc  = _xml_text(block, "description")
            link  = _xml_text(block, "link")
            if not title:
                continue
            combined = title + " " + desc
            score = keyword_score(combined)
            if score < MIN_SCORE and not is_ai_relevant(combined) and not is_privacy_relevant(combined):
                continue

            # Try to extract a date from description
            date_match = re.search(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b", desc)
            anticipated = _parse_date(date_match.group(1)) if date_match else None

            items.append({
                "source":         "unified_agenda",
                "external_id":    _make_id("agenda-rss", title),
                "jurisdiction":   "Federal",
                "title":          title,
                "description":    desc,
                "agency":         "",
                "stage":          "planned",
                "anticipated_date": anticipated,
                "url":            link,
                "ai_score":       round(score, 3),
            })

        return items

    # ── Source 2: Congress.gov Hearing Schedules ──────────────────────────────

    def _fetch_congress_hearings(self, days_ahead: int = 90) -> List[Dict]:
        """
        Fetch upcoming committee hearings from Congress.gov API.
        Focus on hearings in the next days_ahead days that involve AI bills.
        """
        if not CONGRESS_GOV_KEY:
            log.debug("Congress.gov key not set — skipping hearing schedules")
            return []

        items  = []
        cutoff = datetime.utcnow() + timedelta(days=days_ahead)
        today  = datetime.utcnow().strftime("%Y-%m-%d")
        future = cutoff.strftime("%Y-%m-%d")

        # Fetch recent committee hearings
        try:
            url    = f"{CONGRESS_BASE}/committee-meeting"
            params = {
                "api_key":   CONGRESS_GOV_KEY,
                "format":    "json",
                "fromDateTime": f"{today}T00:00:00Z",
                "toDateTime":   f"{future}T23:59:59Z",
                "limit":     50,
            }
            data     = http_get(url, params=params, timeout=15)
            meetings = (data or {}).get("committeeMeetings") or []

            for m in meetings:
                title = m.get("title") or ""
                desc  = " ".join([
                    title,
                    m.get("chamber") or "",
                    " ".join(str(b.get("title", "")) for b in (m.get("bills") or [])),
                ])
                score = keyword_score(desc)
                if score < MIN_SCORE:
                    continue

                date_str = m.get("date") or m.get("meetingDateTime") or ""
                anticipated = _parse_date(date_str)
                committee   = (m.get("committee") or {}).get("name") or ""
                chamber     = m.get("chamber") or ""

                # Build bill list for title
                bills = m.get("bills") or []
                bill_titles = [b.get("number", "") for b in bills[:3] if b.get("number")]
                full_title  = title or (
                    f"Committee Hearing: {', '.join(bill_titles)}" if bill_titles
                    else "AI-related Committee Hearing"
                )

                items.append({
                    "source":         "congress_hearings",
                    "external_id":    _make_id("hearing", str(m.get("eventId") or full_title)),
                    "jurisdiction":   "Federal",
                    "title":          full_title,
                    "description":    f"{chamber} — {committee}",
                    "agency":         committee,
                    "stage":          "hearing",
                    "anticipated_date": anticipated,
                    "url":            m.get("url") or "",
                    "ai_score":       round(score, 3),
                })

        except Exception as e:
            log.debug("Congress hearings fetch failed: %s", e)

        return items

    # ── Source 3: EU Commission Work Programme ────────────────────────────────

    def _fetch_eu_work_programme(self, days_ahead: int = 365) -> List[Dict]:
        """
        Fetch the EU Commission Work Programme — annual list of planned
        legislative initiatives. Parsed for AI-relevant entries.
        """
        items = []

        # The Commission publishes the Work Programme as a structured page
        # Try the EUR-Lex 'in preparation' feed for AI-related items
        try:
            url    = "https://eur-lex.europa.eu/eurlex-content/EN/search/searchResult.do"
            params = {
                "type":    "quick",
                "qid":     "1",
                "query":   "artificial intelligence",
                "SUBDOM_INIT": "LEGISLATION_IN_FORCE",
                "DTS_DOM":     "LEGISLATION",
                "DTS_SUBDOM":  "LEGISLATION_IN_PREPARATION",
                "format":      "json",
            }
            # Use the EUR-Lex SPARQL endpoint for 'in preparation' documents
            sparql_url = "https://publications.europa.eu/webapi/rdf/sparql"
            sparql = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?work ?title ?date WHERE {
  ?work cdm:work_is_about_concept_eurovoc <http://eurovoc.europa.eu/2068> .
  ?expr cdm:expression_belongs_to_work ?work .
  ?expr cdm:expression_title ?title .
  OPTIONAL { ?work cdm:work_date_document ?date }
  FILTER(LANG(?title) = 'en')
  FILTER(?date >= "2024-01-01"^^xsd:date)
}
LIMIT 30
"""
            data = http_get(sparql_url, params={
                "query":  sparql,
                "format": "application/json",
            }, timeout=20)

            bindings = ((data or {}).get("results") or {}).get("bindings") or []
            for b in bindings:
                title = (b.get("title") or {}).get("value") or ""
                date  = (b.get("date")  or {}).get("value") or ""
                score = keyword_score(title)
                if score < MIN_SCORE:
                    continue
                items.append({
                    "source":         "eu_work_programme",
                    "external_id":    _make_id("eu-prep", title),
                    "jurisdiction":   "EU",
                    "title":          title,
                    "description":    "EU legislative initiative in preparation",
                    "agency":         "European Commission",
                    "stage":          "planned",
                    "anticipated_date": _parse_date(date),
                    "url":            (b.get("work") or {}).get("value") or "",
                    "ai_score":       round(score, 3),
                })

        except Exception as e:
            log.debug("EU Work Programme SPARQL failed: %s", e)

        # Fallback: EU AI Office news RSS
        if not items:
            try:
                rss = http_get_text(
                    "https://digital-strategy.ec.europa.eu/en/rss.xml",
                    timeout=15
                )
                items = self._parse_eu_rss(rss or "")
            except Exception as e:
                log.debug("EU RSS fallback failed: %s", e)

        return items

    def _parse_eu_rss(self, rss_text: str) -> List[Dict]:
        items = []
        if not rss_text:
            return items
        for block in re.findall(r"<item>(.*?)</item>", rss_text, re.DOTALL):
            title = _xml_text(block, "title")
            desc  = _xml_text(block, "description")
            link  = _xml_text(block, "link")
            pubdate = _xml_text(block, "pubDate")
            if not title:
                continue
            combined = title + " " + desc
            score = keyword_score(combined)
            if score < MIN_SCORE and not is_ai_relevant(combined) and not is_privacy_relevant(combined):
                continue
            items.append({
                "source":         "eu_work_programme",
                "external_id":    _make_id("eu-rss", title),
                "jurisdiction":   "EU",
                "title":          title,
                "description":    desc[:400],
                "agency":         "European Commission",
                "stage":          "planned",
                "anticipated_date": _parse_date(pubdate),
                "url":            link,
                "ai_score":       round(score, 3),
            })
        return items

    # ── Source 4: UK Parliament Upcoming Business ─────────────────────────────

    def _fetch_uk_upcoming(self, days_ahead: int = 90) -> List[Dict]:
        """
        Fetch upcoming UK Parliament bill stage dates.
        Uses the whatson.parliament.uk API — no key required.
        """
        items   = []
        today   = datetime.utcnow().strftime("%Y-%m-%d")
        future  = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        # Try whatson API for upcoming bill events
        try:
            url    = "https://whatson.parliament.uk/api/v1/Events.json"
            params = {
                "StartDate":  today,
                "EndDate":    future,
                "EventType":  "Bill",
                "take":       50,
            }
            data   = http_get(url, params=params, timeout=15)
            events = (data or []) if isinstance(data, list) else (data or {}).get("Results") or []

            for ev in events:
                title = ev.get("Description") or ev.get("Title") or ""
                date  = ev.get("StartDateTime") or ev.get("Date") or ""
                desc  = " ".join(filter(None, [
                    ev.get("SubCategory") or "",
                    ev.get("House") or "",
                    ev.get("Note") or "",
                ]))
                combined_uk = title + " " + desc
                score = keyword_score(combined_uk)
                if score < MIN_SCORE and not is_ai_relevant(combined_uk) and not is_privacy_relevant(combined_uk):
                    continue

                items.append({
                    "source":         "uk_upcoming",
                    "external_id":    _make_id("uk-event", str(ev.get("Id") or title)),
                    "jurisdiction":   "GB",
                    "title":          title,
                    "description":    desc,
                    "agency":         ev.get("House") or "UK Parliament",
                    "stage":          "hearing",
                    "anticipated_date": _parse_date(date),
                    "url":            ev.get("Url") or "",
                    "ai_score":       round(score, 3),
                })

        except Exception as e:
            log.debug("UK whatson API failed: %s", e)

        # Fallback: UK Parliament Bills RSS
        if not items:
            try:
                rss = http_get_text(
                    "https://bills.parliament.uk/rss/allbills.rss",
                    timeout=15
                )
                for block in re.findall(r"<item>(.*?)</item>", rss or "", re.DOTALL):
                    title   = _xml_text(block, "title")
                    desc    = _xml_text(block, "description")
                    link    = _xml_text(block, "link")
                    pubdate = _xml_text(block, "pubDate")
                    if not title:
                        continue
                    combined_ukb = title + " " + desc
                    score = keyword_score(combined_ukb)
                    if score < MIN_SCORE and not is_ai_relevant(combined_ukb) and not is_privacy_relevant(combined_ukb):
                        continue
                    items.append({
                        "source":         "uk_upcoming",
                        "external_id":    _make_id("uk-bills-rss", title),
                        "jurisdiction":   "GB",
                        "title":          title,
                        "description":    desc[:400],
                        "agency":         "UK Parliament",
                        "stage":          "planned",
                        "anticipated_date": _parse_date(pubdate),
                        "url":            link,
                        "ai_score":       round(score, 3),
                    })
            except Exception as e:
                log.debug("UK Parliament RSS fallback failed: %s", e)

        return items

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_items(self, items: List[Dict]) -> int:
        """Save horizon items, skipping duplicates. Returns count of new items."""
        if not items:
            return 0
        try:
            new_count = 0
            for item in items:
                if upsert_horizon_item(item):
                    new_count += 1
            return new_count
        except Exception as e:
            log.error("Error saving horizon items: %s", e)
            return 0

    # ── Public query helpers ──────────────────────────────────────────────────

    def get_upcoming(self,
                     days_ahead: int = 365,
                     jurisdiction: Optional[str] = None,
                     stage: Optional[str] = None,
                     limit: int = 100) -> List[Dict]:
        """Return upcoming horizon items from the database."""
        try:
            return get_horizon_items(
                days_ahead   = days_ahead,
                jurisdiction = jurisdiction,
                stage        = stage,
                limit        = limit,
            )
        except Exception as e:
            log.error("Error fetching horizon items: %s", e)
            return []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _xml_text(block: str, tag: str) -> str:
    """Extract text content of first XML element with given tag."""
    m = re.search(rf"<{tag}(?:\s[^>]*)?>(<!\[CDATA\[)?(.*?)(\]\]>)?</{tag}>",
                  block, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(2).strip()
    return ""


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = str(s).strip()
    for fmt in (
        "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
        "%B %Y", "%b %Y",
        "%Y/%m",
    ):
        try:
            dt = datetime.strptime(s[:len(fmt) + 5].strip(), fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    # Try year-only
    m = re.search(r"\b(20\d{2})\b", s)
    if m:
        try:
            return datetime(int(m.group(1)), 6, 1)   # mid-year estimate
        except Exception:
            pass
    return None


def _make_id(prefix: str, text: str) -> str:
    """Generate a stable short ID from prefix + text."""
    h = hashlib.md5(text.lower().encode()).hexdigest()[:10]
    return f"{prefix}-{h}"
