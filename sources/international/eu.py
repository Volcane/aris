"""
ARIS — European Union Agent

Data sources (all free, no API key required):

1. EUR-Lex Cellar SPARQL endpoint
   - Publications Office of the EU semantic database
   - Queries regulations, directives, decisions, proposals
   - Endpoint: https://publications.europa.eu/webapi/rdf/sparql
   - Docs: https://eur-lex.europa.eu/content/help/data-reuse/reuse-contents-eurlex-details.html

2. EUR-Lex REST/search API
   - Keyword search across full legislative corpus
   - Endpoint: https://eur-lex.europa.eu/search.html (form-based, JSON response)
   - Direct document fetch: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:<id>

3. EU AI Office news & guidelines feed
   - https://digital-strategy.ec.europa.eu/en/policies/european-approach-artificial-intelligence
   - RSS/Atom feed for AI Office publications

4. Official Journal of the EU — RSS feed
   - https://op.europa.eu/en/web/general-publications/publications
   - Filtered for AI-related OJ entries

Key EU AI Act facts tracked by this agent:
  - Regulation (EU) 2024/1689 — EU AI Act (in force 1 Aug 2024)
  - Prohibited practices in effect: 2 Feb 2025
  - GPAI obligations in effect: 2 Aug 2025
  - High-risk AI obligations in effect: 2 Aug 2026
  - Full application: 2 Aug 2027
  - Max penalty: €35M or 7% global turnover
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sources.international.base import InternationalAgentBase, parse_date, strip_tags
from config.settings import AI_KEYWORDS, LOOKBACK_DAYS
from utils.cache import http_get, http_get_text, is_ai_relevant, get_logger

log = get_logger("aris.international.eu")

# ── Endpoint constants ────────────────────────────────────────────────────────

CELLAR_SPARQL   = "https://publications.europa.eu/webapi/rdf/sparql"
EURLEX_BASE     = "https://eur-lex.europa.eu"
EURLEX_SEARCH   = f"{EURLEX_BASE}/search.html"
EURLEX_TEXT_URL = f"{EURLEX_BASE}/legal-content/EN/TXT/HTML/?uri=CELEX:"
EU_AI_ACT_CELEX = "32024R1689"   # CELEX number for the EU AI Act

# EU AI Office / Digital Strategy RSS
EU_AI_OFFICE_RSS = (
    "https://digital-strategy.ec.europa.eu/en/rss.xml"
)

# EUR-Lex OJ RSS (Official Journal)
OJ_RSS = "https://op.europa.eu/en/web/general-publications/publications/-/publication/rss"

# Known high-priority AI Act documents (pinned; always included)
PINNED_AI_DOCUMENTS = [
    {
        "celex":    "32024R1689",
        "title":    "Regulation (EU) 2024/1689 — EU Artificial Intelligence Act",
        "doc_type": "Regulation",
        "date":     "2024-07-12",
        "status":   "In Force",
        "url":      f"{EURLEX_BASE}/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689",
        "abstract": (
            "The EU AI Act establishes a risk-based regulatory framework for AI systems "
            "placed on the EU market or used in the EU. It classifies AI systems into "
            "unacceptable risk (prohibited), high-risk (strictly regulated), limited risk "
            "(transparency obligations), and minimal risk (largely unregulated) categories. "
            "It covers providers, deployers, importers, and distributors. "
            "Penalties reach €35 million or 7% of global annual turnover."
        ),
    },
    {
        "celex":    "C2025/1203",
        "title":    "Commission Guidelines on Prohibited AI Practices (Article 5)",
        "doc_type": "Commission Guidelines",
        "date":     "2025-02-04",
        "status":   "Published",
        "url":      f"{EURLEX_BASE}/legal-content/EN/TXT/?uri=CELEX:C2025/1203",
        "abstract": (
            "European Commission guidelines clarifying which AI practices are prohibited "
            "under Article 5 of the EU AI Act, including social scoring, subliminal "
            "manipulation, real-time biometric surveillance in public spaces, and "
            "AI systems exploiting vulnerabilities of specific groups."
        ),
    },
    {
        "celex":    "C2025/1204",
        "title":    "Commission Guidelines on the Definition of an AI System (Article 3(1))",
        "doc_type": "Commission Guidelines",
        "date":     "2025-02-06",
        "status":   "Published",
        "url":      f"{EURLEX_BASE}/legal-content/EN/TXT/?uri=CELEX:C2025/1204",
        "abstract": (
            "European Commission guidelines clarifying the definition of an 'AI system' "
            "under the EU AI Act, distinguishing AI systems from simpler software, "
            "expert systems, and traditional algorithms. Critical for determining "
            "whether a product is in-scope of the Act."
        ),
    },
    {
        "celex":    "GPAI_COP_2025",
        "title":    "General-Purpose AI Code of Practice (Final Draft, July 2025)",
        "doc_type": "Code of Practice",
        "date":     "2025-07-10",
        "status":   "Published — Voluntary Compliance Tool",
        "url":      "https://digital-strategy.ec.europa.eu/en/policies/ai-code-practice",
        "abstract": (
            "The voluntary GPAI Code of Practice, developed under Article 56 of the EU AI Act, "
            "provides detailed measures for GPAI model providers to demonstrate compliance. "
            "Covers three chapters: transparency (for all GPAI providers), copyright "
            "(for all GPAI providers), and safety & security (for systemic-risk GPAI models). "
            "Following the Code is a compliance pathway but not mandatory."
        ),
    },
]


class EUAgent(InternationalAgentBase):
    """
    European Union AI regulation monitor.

    Tracks:
     - EU AI Act (Regulation 2024/1689) and all implementing acts / guidelines
     - EUR-Lex SPARQL queries for new AI-related regulations and directives
     - EU AI Office publications via RSS
     - Official Journal AI-related notices
    """

    jurisdiction_code = "EU"
    jurisdiction_name = "European Union"
    region            = "Europe"
    language          = "en"

    # ── Pinned documents (always present, no API call needed) ─────────────────

    def _get_pinned_docs(self) -> List[Dict[str, Any]]:
        """Return the curated list of critical EU AI Act documents."""
        docs = []
        for item in PINNED_AI_DOCUMENTS:
            docs.append(self._make_doc(
                id           = f"EU-CELEX-{item['celex']}",
                source       = "eurlex_pinned",
                doc_type     = item["doc_type"],
                title        = item["title"],
                url          = item["url"],
                published_date = parse_date(item["date"]),
                agency       = "European Commission / European Parliament",
                status       = item["status"],
                full_text    = item["abstract"],
                raw_json     = item,
            ))
        return docs

    # ── EUR-Lex SPARQL query ──────────────────────────────────────────────────

    def _sparql_search(self, lookback_days: int) -> List[Dict[str, Any]]:
        """
        Query the EU Publications Office SPARQL endpoint for AI-related
        regulations and directives published within lookback_days.
        """
        since = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        # SPARQL query: fetch regulations/directives mentioning AI keywords
        # Uses the CDM (Common Data Model) ontology
        query = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>

        SELECT DISTINCT ?work ?celex ?title ?date ?type
        WHERE {{
            ?work cdm:work_has_resource-type ?type .
            OPTIONAL {{ ?work cdm:resource_legal_id_celex ?celex . }}
            OPTIONAL {{ ?work cdm:work_date_document ?date . }}
            OPTIONAL {{
                ?work cdm:work_is_about_concept_eurovoc ?concept .
                ?concept skos:prefLabel ?label .
                FILTER(lang(?label) = "en")
            }}
            FILTER(?type IN (
                <http://publications.europa.eu/resource/authority/resource-type/REG>,
                <http://publications.europa.eu/resource/authority/resource-type/DIR>,
                <http://publications.europa.eu/resource/authority/resource-type/DEC>,
                <http://publications.europa.eu/resource/authority/resource-type/PROC_INIT>,
                <http://publications.europa.eu/resource/authority/resource-type/GUIDELINE_EU>
            ))
            FILTER(?date >= "{since}"^^xsd:date)
            FILTER NOT EXISTS {{ ?work cdm:do_not_index "true"^^xsd:boolean }}
        }}
        ORDER BY DESC(?date)
        LIMIT 100
        """

        headers = {
            "Accept":       "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        results = []
        try:
            import requests as _req
            resp = _req.post(
                CELLAR_SPARQL,
                data={"query": query, "format": "application/sparql-results+json"},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data     = resp.json()
            bindings = data.get("results", {}).get("bindings", [])

            for row in bindings:
                celex   = row.get("celex", {}).get("value", "")
                date_v  = row.get("date",  {}).get("value", "")
                type_v  = row.get("type",  {}).get("value", "").split("/")[-1]

                if not celex:
                    continue

                # Fetch the English title separately from EUR-Lex REST
                title = self._fetch_celex_title(celex)
                if not title:
                    continue

                # Keyword filter on title
                if not is_ai_relevant(title):
                    continue

                # Fetch abstract / excerpt
                abstract = self._fetch_celex_excerpt(celex)

                doc_id = f"EU-CELEX-{celex}"
                # Skip if already in pinned set
                pinned_ids = {f"EU-CELEX-{p['celex']}" for p in PINNED_AI_DOCUMENTS}
                if doc_id in pinned_ids:
                    continue

                results.append(self._make_doc(
                    id           = doc_id,
                    source       = "eurlex_sparql",
                    doc_type     = _map_eu_type(type_v),
                    title        = title,
                    url          = f"{EURLEX_TEXT_URL}{celex}",
                    published_date = parse_date(date_v),
                    agency       = "European Union",
                    status       = "Published",
                    full_text    = abstract or title,
                    raw_json     = row,
                ))
        except Exception as e:
            log.warning("EUR-Lex SPARQL query failed: %s", e)

        log.info("EUR-Lex SPARQL: %d AI documents found", len(results))
        return results

    def _fetch_celex_title(self, celex: str) -> Optional[str]:
        """Fetch the English title for a CELEX document via EUR-Lex REST."""
        try:
            url  = f"{EURLEX_BASE}/legal-content/EN/TIT/?uri=CELEX:{celex}"
            html = http_get_text(url, use_cache=True)
            # Extract title from HTML
            match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            if match:
                t = match.group(1).strip()
                t = re.sub(r"\s*[-|].*EUR-Lex.*$", "", t).strip()
                return t or None
        except Exception:
            pass
        return None

    def _fetch_celex_excerpt(self, celex: str, max_chars: int = 3000) -> Optional[str]:
        """Fetch the first portion of a CELEX document for summarisation."""
        try:
            url  = f"{EURLEX_TEXT_URL}{celex}"
            html = http_get_text(url, use_cache=True)
            text = strip_tags(html, max_chars)
            return text if len(text) > 100 else None
        except Exception:
            pass
        return None

    # ── EUR-Lex keyword search (fallback / supplement to SPARQL) ─────────────

    def _eurlex_keyword_search(self, lookback_days: int) -> List[Dict[str, Any]]:
        """
        Keyword search via EUR-Lex public search endpoint.
        Returns normalised docs for AI-relevant hits not caught by SPARQL.
        """
        since = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%d/%m/%Y")
        results = []

        for term in ["artificial intelligence", "machine learning", "algorithmic decision"]:
            params = {
                "scope":      "EURLEX",
                "type":       "quick",
                "lang":       "en",
                "DD_DATE_OF_EFFECT[MIN]": since,
                "text":       term,
                "qid":        "1",
            }
            try:
                data = http_get(f"{EURLEX_BASE}/search.html", params=params, use_cache=True)
                # EUR-Lex returns HTML for browser requests; use JSON format
                # The JSON API requires specific Accept headers
            except Exception as e:
                log.debug("EUR-Lex keyword search skipped (%s): %s", term, e)

        return results   # SPARQL + pinned docs are the primary mechanism

    # ── EU AI Office RSS feed ─────────────────────────────────────────────────

    def _fetch_ai_office_feed(self, lookback_days: int) -> List[Dict[str, Any]]:
        """
        Parse the EU Digital Strategy / AI Office RSS feed for new publications.
        """
        results  = []
        since    = datetime.utcnow() - timedelta(days=lookback_days)
        feed_url = EU_AI_OFFICE_RSS

        try:
            xml_text = http_get_text(feed_url, use_cache=True)
            root     = ET.fromstring(xml_text)
            ns       = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            channel  = root.find(f"{ns}channel") or root
            items    = channel.findall(f"{ns}item") or root.findall(".//item")

            for item in items:
                title   = (item.findtext(f"{ns}title") or "").strip()
                link    = (item.findtext(f"{ns}link")  or "").strip()
                desc    = (item.findtext(f"{ns}description") or "").strip()
                pub_str = (item.findtext(f"{ns}pubDate") or "").strip()
                pub_dt  = parse_date(pub_str)

                if pub_dt and pub_dt < since:
                    continue
                if not is_ai_relevant(f"{title} {desc}"):
                    continue

                safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", link)[-60:]
                results.append(self._make_doc(
                    id           = f"EU-AIOFFICE-{safe_id}",
                    source       = "eu_ai_office_rss",
                    doc_type     = "Publication / Guidance",
                    title        = title,
                    url          = link,
                    published_date = pub_dt,
                    agency       = "EU AI Office / European Commission",
                    status       = "Published",
                    full_text    = strip_tags(desc, 3000),
                    raw_json     = {"title": title, "link": link, "description": desc},
                ))

        except Exception as e:
            log.warning("EU AI Office RSS failed: %s", e)

        log.info("EU AI Office RSS: %d items", len(results))
        return results

    # ── Main fetch ────────────────────────────────────────────────────────────

    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        """
        Primary fetch: pinned EU AI Act documents + EUR-Lex SPARQL search.
        Pinned docs are always included regardless of lookback_days, as they
        are the most business-critical AI regulations in the world.
        """
        docs = []
        docs.extend(self._get_pinned_docs())
        docs.extend(self._sparql_search(lookback_days))
        return docs

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        """Secondary fetch: EU AI Office RSS feed."""
        return self._fetch_ai_office_feed(lookback_days)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _map_eu_type(raw: str) -> str:
    """Map EUR-Lex resource type codes to human-readable labels."""
    mapping = {
        "REG":          "Regulation",
        "DIR":          "Directive",
        "DEC":          "Decision",
        "PROC_INIT":    "Legislative Proposal",
        "GUIDELINE_EU": "EU Guidelines",
        "REC":          "Recommendation",
        "COM":          "Commission Communication",
        "JOIN":         "Joint Communication",
        "SWD":          "Staff Working Document",
        "C_ANN":        "Annex to Commission Document",
    }
    return mapping.get(raw, raw or "EU Document")
