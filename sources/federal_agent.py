"""
ARIS — Federal Source Agent

Fetches AI-related documents from:
  1. Federal Register API  (no key required)
  2. Regulations.gov API   (free key required)
  3. Congress.gov API      (free key required)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from config.settings import (
    FEDERAL_REGISTER_BASE, REGS_GOV_BASE, CONGRESS_BASE,
    REGULATIONS_GOV_KEY, CONGRESS_GOV_KEY,
    FR_DOC_TYPES, AI_KEYWORDS, LOOKBACK_DAYS
)
from utils.cache import http_get, is_ai_relevant, keyword_score, get_logger

log = get_logger("aris.federal")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _date_str(days_ago: int = 0) -> str:
    d = datetime.utcnow() - timedelta(days=days_ago)
    return d.strftime("%Y-%m-%d")


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


# ── 1. Federal Register ───────────────────────────────────────────────────────

class FederalRegisterSource:
    """
    Queries the Federal Register v1 API for AI-related documents.
    API docs: https://www.federalregister.gov/developers/documentation/api/v1
    No API key required.
    """

    BASE = FEDERAL_REGISTER_BASE

    def search(self, lookback_days: int = LOOKBACK_DAYS,
               per_page: int = 40) -> List[Dict[str, Any]]:
        """
        Search for AI-related Federal Register documents published in the
        last `lookback_days` days.
        Returns a list of normalised document dicts.
        """
        results = []
        query   = " OR ".join(f'"{kw}"' for kw in AI_KEYWORDS[:12])  # top 12 terms
        params  = {
            "conditions[term]":           query,
            "conditions[publication_date][gte]": _date_str(lookback_days),
            "fields[]": [
                "document_number", "title", "publication_date", "type",
                "agency_names", "abstract", "html_url", "pdf_url",
                "action", "docket_ids", "effective_on", "comment_date",
            ],
            "per_page": per_page,
            "order":    "newest",
        }

        try:
            data = http_get(f"{self.BASE}/documents.json", params=params)
        except Exception as e:
            log.error("Federal Register search failed: %s", e)
            return []

        for item in data.get("results", []):
            text_blob = f"{item.get('title','')} {item.get('abstract','')}"
            if not is_ai_relevant(text_blob):
                continue

            results.append(self._normalise(item))

        log.info("Federal Register: %d AI-relevant documents found", len(results))
        return results

    def fetch_full_text(self, document_number: str) -> Optional[str]:
        """Fetch the full text body of a specific document."""
        try:
            data = http_get(
                f"{self.BASE}/documents/{document_number}.json",
                params={"fields[]": ["full_text_xml_url", "body_html_url"]},
            )
            body_url = data.get("body_html_url") or data.get("full_text_xml_url")
            if body_url:
                from utils.cache import http_get_text
                raw = http_get_text(body_url)
                # Strip HTML/XML tags
                return re.sub(r"<[^>]+>", " ", raw)[:8000]  # limit to 8k chars
        except Exception as e:
            log.warning("Could not fetch full text for %s: %s", document_number, e)
        return None

    @staticmethod
    def _normalise(item: Dict) -> Dict[str, Any]:
        agencies = item.get("agency_names") or []
        return {
            "id":            f"FR-{item.get('document_number', '')}",
            "source":        "federal_register",
            "jurisdiction":  "Federal",
            "doc_type":      item.get("type", ""),
            "title":         item.get("title", ""),
            "url":           item.get("html_url", ""),
            "published_date": _parse_date(item.get("publication_date")),
            "agency":        ", ".join(agencies) if agencies else None,
            "status":        _map_fr_status(item.get("type", "")),
            "full_text":     item.get("abstract", ""),
            "raw_json":      item,
        }


def _map_fr_status(doc_type: str) -> str:
    mapping = {
        "RULE":      "Final Rule",
        "PRORULE":   "Proposed Rule",
        "NOTICE":    "Notice",
        "PRESDOCU":  "Presidential Document",
    }
    return mapping.get(doc_type, doc_type)


# ── 2. Regulations.gov ────────────────────────────────────────────────────────

class RegulationsGovSource:
    """
    Queries Regulations.gov v4 API for AI-related dockets and documents.
    API docs: https://open.gsa.gov/api/regulationsgov/
    Free API key required: register at https://open.gsa.gov/api/regulationsgov/
    """

    BASE = REGS_GOV_BASE

    def __init__(self):
        if not REGULATIONS_GOV_KEY:
            log.warning(
                "REGULATIONS_GOV_KEY not set — Regulations.gov source disabled. "
                "Get a free key at https://open.gsa.gov/api/regulationsgov/"
            )
        self._headers = {"X-Api-Key": REGULATIONS_GOV_KEY} if REGULATIONS_GOV_KEY else {}

    def search(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        if not REGULATIONS_GOV_KEY:
            return []

        results      = []
        search_terms = ["artificial intelligence", "machine learning", "algorithmic"]

        for term in search_terms:
            params = {
                "filter[searchTerm]":           term,
                "filter[postedDate][ge]":        _date_str(lookback_days),
                "filter[documentType]":          "Rule,Proposed Rule,Notice",
                "sort":                          "-postedDate",
                "page[size]":                    25,
            }
            try:
                data = http_get(f"{self.BASE}/documents", params=params,
                                headers=self._headers)
            except Exception as e:
                log.error("Regulations.gov search '%s' failed: %s", term, e)
                continue

            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                title = attrs.get("title", "")
                if not is_ai_relevant(title):
                    continue
                results.append(self._normalise(item))

        # de-duplicate by ID
        seen   = set()
        unique = []
        for r in results:
            if r["id"] not in seen:
                seen.add(r["id"])
                unique.append(r)

        log.info("Regulations.gov: %d AI-relevant documents found", len(unique))
        return unique

    @staticmethod
    def _normalise(item: Dict) -> Dict[str, Any]:
        attrs   = item.get("attributes", {})
        doc_id  = item.get("id", "")
        return {
            "id":            f"RGOV-{doc_id}",
            "source":        "regulations_gov",
            "jurisdiction":  "Federal",
            "doc_type":      attrs.get("documentType", ""),
            "title":         attrs.get("title", ""),
            "url":           f"https://www.regulations.gov/document/{doc_id}",
            "published_date": _parse_date(attrs.get("postedDate")),
            "agency":        attrs.get("agencyId", ""),
            "status":        attrs.get("documentType", ""),
            "full_text":     attrs.get("comment", "") or attrs.get("title", ""),
            "raw_json":      item,
        }


# ── 3. Congress.gov ───────────────────────────────────────────────────────────

class CongressGovSource:
    """
    Queries Congress.gov API v3 for AI-related bills and resolutions.
    API docs: https://api.congress.gov/
    Free API key required: https://api.congress.gov/sign-up/
    """

    BASE = CONGRESS_BASE

    def __init__(self):
        if not CONGRESS_GOV_KEY:
            log.warning(
                "CONGRESS_GOV_KEY not set — Congress.gov source disabled. "
                "Get a free key at https://api.congress.gov/sign-up/"
            )
        self._params_base = {"api_key": CONGRESS_GOV_KEY} if CONGRESS_GOV_KEY else {}

    def search(self, lookback_days: int = LOOKBACK_DAYS,
               congress: int = 119) -> List[Dict[str, Any]]:
        """Fetch AI-related bills from the current Congress."""
        if not CONGRESS_GOV_KEY:
            return []

        results = []
        for term in ["artificial intelligence", "machine learning", "algorithmic decision"]:
            params = {
                **self._params_base,
                "query":  term,
                "limit":  20,
                "sort":   "updateDate+desc",
                "format": "json",
            }
            try:
                data = http_get(
                    f"{self.BASE}/bill/{congress}",
                    params=params,
                )
            except Exception as e:
                log.error("Congress.gov search '%s' failed: %s", term, e)
                continue

            for bill in data.get("bills", []):
                title = bill.get("title", "")
                if not is_ai_relevant(title):
                    continue
                results.append(self._normalise(bill, congress))

        seen, unique = set(), []
        for r in results:
            if r["id"] not in seen:
                seen.add(r["id"])
                unique.append(r)

        log.info("Congress.gov: %d AI-relevant bills found", len(unique))
        return unique

    def fetch_bill_text(self, congress: int, bill_type: str, bill_num: str) -> Optional[str]:
        """Attempt to fetch the plain-text summary of a bill."""
        try:
            params = {**self._params_base, "format": "json"}
            data   = http_get(
                f"{self.BASE}/bill/{congress}/{bill_type.lower()}/{bill_num}/summaries",
                params=params,
            )
            summaries = data.get("summaries", [])
            if summaries:
                return summaries[-1].get("text", "")
        except Exception as e:
            log.warning("Bill text fetch failed: %s", e)
        return None

    @staticmethod
    def _normalise(bill: Dict, congress: int) -> Dict[str, Any]:
        bill_type   = bill.get("type", "").upper()
        bill_num    = bill.get("number", "")
        latest      = bill.get("latestAction", {})
        sponsors    = bill.get("sponsors", [])
        sponsor_str = sponsors[0].get("fullName", "") if sponsors else ""

        return {
            "id":            f"CONG-{congress}-{bill_type}{bill_num}",
            "source":        "congress_gov",
            "jurisdiction":  "Federal",
            "doc_type":      f"Bill ({bill_type})",
            "title":         bill.get("title", ""),
            "url":           bill.get("url", ""),
            "published_date": _parse_date(bill.get("introducedDate")),
            "agency":        sponsor_str,
            "status":        latest.get("text", ""),
            "full_text":     bill.get("title", ""),
            "raw_json":      bill,
        }


# ── Unified Federal Agent ─────────────────────────────────────────────────────

class FederalAgent:
    """
    Aggregates all three federal sources into a single interface.
    Called by the Orchestrator.
    """

    def __init__(self):
        self.fr  = FederalRegisterSource()
        self.rg  = RegulationsGovSource()
        self.cg  = CongressGovSource()

    def fetch_all(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        """
        Fetch AI-related documents from all federal sources.
        Returns combined, de-duplicated list.
        """
        log.info("Starting Federal fetch (lookback=%d days)…", lookback_days)
        docs = []
        docs.extend(self.fr.search(lookback_days))
        docs.extend(self.rg.search(lookback_days))
        docs.extend(self.cg.search(lookback_days))

        # Enrich Federal Register docs with snippet of full text when missing
        for doc in docs:
            if doc["source"] == "federal_register" and not doc.get("full_text"):
                doc_num = doc["id"].replace("FR-", "")
                doc["full_text"] = self.fr.fetch_full_text(doc_num) or ""

        log.info("Federal fetch complete: %d total documents", len(docs))
        return docs
