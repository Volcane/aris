# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 Mitch Kwiatkowski
# ARIS — Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
"""
ARIS — Enforcement & Litigation Agent

Monitors AI-related enforcement actions, court cases, and regulatory
sanctions from ten free public sources:

US FEDERAL AGENCIES (all RSS/JSON, no key required)
  FTC    — Algorithmic bias, dark patterns, AI fraud, ROSCA violations
             https://www.ftc.gov/feeds/press-release.xml
  SEC    — AI fraud, algorithmic manipulation, AI-generated disclosures
             https://efts.sec.gov/LATEST/search-index (EDGAR full-text)
  CFPB   — Automated underwriting, credit scoring, BNPL algorithm enforcement
             https://www.consumerfinance.gov/about-us/newsroom/feed/
  EEOC   — Employment AI discrimination (hiring, promotion, performance)
             https://www.eeoc.gov/rss/newsroom
  DOJ    — Civil rights AI discrimination in housing, lending, criminal justice
             https://www.justice.gov/news/rss

INTERNATIONAL (RSS, no key required)
  ICO    — UK GDPR / data protection enforcement actions
  (UK)     https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/rss/

US COURTS (free REST API, optional free token for higher rate limits)
  CourtListener — Federal court opinions and dockets from PACER/RECAP
  (Free Open Law  https://www.courtlistener.com/api/rest/v4/
   Project)       Optional: COURTLISTENER_KEY env var (free registration)
                  5,000 req/day without token, more with free token

NEWS & LEGAL INTELLIGENCE (RSS, no key required)
  IAPP            — IAPP Daily Dashboard: curated global privacy & AI
                    governance news, editorially filtered. Covers enforcement
                    actions, court decisions, and regulatory settlements.
                    https://iapp.org/rss/daily-dashboard/
                    https://iapp.org/rss/united-states-dashboard-digest/

  Regulatory      — Troutman Pepper "Regulatory Oversight" blog: dedicated
  Oversight         to tracking enforcement actions across consumer protection,
                    privacy, and AI. Strong state AG coverage.
                    https://www.regulatoryoversight.com/feed/

  Courthouse      — Courthouse News Service: federal and state court filings
  News              (complaints, settlements, verdicts) the day they are filed.
                    https://www.courthousenews.com/feed/

News sources use a stricter two-signal relevance filter
(_is_news_enforcement_relevant) that requires both a domain keyword
(AI/privacy) AND an enforcement action term (settlement, fine, lawsuit,
violation, etc.) to pass. This prevents general policy commentary,
opinion, and legislative news from appearing in the enforcement view.

Architecture
------------
Each source is a class with a fetch() method returning normalised
EnforcementAction dicts. The EnforcementAgent.fetch_all() aggregates
all sources, deduplicates, scores AI relevance, and persists to DB.

Relevance scoring uses the existing is_ai_relevant() keyword matcher
plus a set of enforcement-specific terms.

Related-regulation linking: after ingestion, a lightweight matcher
checks whether the action text references any known baseline IDs or
regulation titles and records them in related_regs.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from utils.cache import http_get, http_get_text, is_ai_relevant, keyword_score, get_logger
try:
    from config.settings import COURTLISTENER_KEY
except ImportError:
    COURTLISTENER_KEY = ""

log = get_logger("aris.enforcement")

# ── Enforcement-specific keyword patterns ─────────────────────────────────────

ENFORCEMENT_AI_TERMS = [
    "artificial intelligence", "machine learning", "algorithm",
    "automated decision", "automated system", "predictive model",
    "facial recognition", "biometric", "deepfake", "generative ai",
    "large language model", "chatbot", "ai-generated", "ai model",
    "automated scoring", "credit scoring", "automated hiring",
    "surveillance", "content moderation", "recommendation system",
    "autonomous", "discriminatory algorithm", "algorithmic bias",
]

ENFORCEMENT_PRIVACY_TERMS = [
    "personal data", "personal information", "data protection",
    "gdpr", "ccpa", "pipeda", "lgpd", "pdpa", "appi",
    "data breach", "breach notification", "data subject",
    "right to erasure", "right to be forgotten", "right of access",
    "consent", "data controller", "data processor",
    "privacy notice", "privacy policy", "cookie consent",
    "data retention", "data transfer", "supervisory authority",
    "information commissioner", "ico", "cnil", "anpd",
    "privacy violation", "data leak", "unauthorized disclosure",
    "sensitive data", "special category", "children's privacy",
    "coppa", "hipaa", "ferpa", "glba", "fcra",
]

_ALL_ENFORCEMENT_TERMS = ENFORCEMENT_AI_TERMS + ENFORCEMENT_PRIVACY_TERMS

# Map known regulation titles/short-names to baseline IDs for linking
REGULATION_LINK_MAP = {
    # AI baselines
    "ftc act":                  "us_ftc_ai",
    "section 5":                "us_ftc_ai",
    "eu ai act":                "eu_ai_act",
    "ai act":                   "eu_ai_act",
    "fcra":                     "us_sector_ai",
    "fair credit reporting":    "us_sector_ai",
    "ecoa":                     "us_sector_ai",
    "equal credit opportunity": "us_sector_ai",
    "title vii":                "us_sector_ai",
    "nist rmf":                 "us_nist_ai_rmf",
    "eo 14110":                 "us_eo_14110",
    "executive order 14110":    "us_eo_14110",
    "colorado ai":              "colorado_ai",
    "illinois aipa":            "illinois_aipa",
    "nyc ll144":                "nyc_ll144",
    "local law 144":            "nyc_ll144",
    # Privacy baselines
    "gdpr":                     "eu_gdpr_full",
    "article 22":               "eu_gdpr_full",
    "article 83":               "eu_gdpr_full",
    "general data protection":  "eu_gdpr_full",
    "uk gdpr":                  "uk_gdpr_dpa",
    "data protection act":      "uk_gdpr_dpa",
    "dpa 2018":                 "uk_gdpr_dpa",
    "information commissioner": "uk_gdpr_dpa",
    "ico":                      "uk_gdpr_dpa",
    "ccpa":                     "ccpa_cpra",
    "cpra":                     "ccpa_cpra",
    "california consumer privacy": "ccpa_cpra",
    "consumer privacy":         "us_state_privacy",
    "vcdpa":                    "us_state_privacy",
    "colorado privacy":         "us_state_privacy",
    "pipeda":                   "canada_pipeda_c27",
    "cppa":                     "canada_pipeda_c27",
    "lgpd":                     "brazil_lgpd",
    "pdpa":                     "singapore_pdpa",
    "appi":                     "japan_appi",
    "hipaa":                    "us_privacy_federal",
    "coppa":                    "us_privacy_federal",
    "glba":                     "us_privacy_federal",
    "ferpa":                    "us_privacy_federal",
    "eu data act":              "eu_data_act",
    "eprivacy":                 "eu_eprivacy",
    "cookie":                   "eu_eprivacy",
}


def _is_enforcement_relevant(text: str) -> bool:
    """Check if text is relevant to AI or privacy enforcement/litigation."""
    lower = text.lower()
    return any(term in lower for term in _ALL_ENFORCEMENT_TERMS)


# Terms that signal an actual enforcement/litigation action rather than
# general news, opinion, or policy coverage. Used to filter news RSS feeds
# (IAPP, Regulatory Oversight, Courthouse News) where _is_enforcement_relevant
# alone is too broad.
_ENFORCEMENT_ACTION_SIGNALS = [
    "settlement", "settled", "settles",
    "fine", "fined", "fines",
    "penalty", "penalties",
    "consent order", "consent decree",
    "lawsuit", "suit filed", "sues", "sued",
    "complaint filed", "files complaint",
    "enforcement action", "enforcement notice",
    "civil penalty", "monetary penalty",
    "injunction", "enjoined",
    "investigation", "investigates",
    "class action", "class-action",
    "violation", "violations",
    "charges", "charged",
    "verdict", "ruled", "ruling",
    "judgment", "judgement",
    "sanctions", "sanctioned",
    "subpoena", "order to",
    "liable", "liability",
    "breach", "data breach",
    "regulatory action",
]


def _is_news_enforcement_relevant(text: str) -> bool:
    """
    Stricter relevance check for news/blog RSS feeds.
    Requires BOTH a domain signal (AI/privacy) AND an enforcement action signal.
    This prevents general policy commentary, opinion, and legislative news from
    passing through sources like IAPP and Regulatory Oversight.
    """
    lower = text.lower()
    has_domain    = any(term in lower for term in _ALL_ENFORCEMENT_TERMS)
    has_action    = any(term in lower for term in _ENFORCEMENT_ACTION_SIGNALS)
    return has_domain and has_action


def _detect_jurisdiction(text: str) -> str:
    """Infer jurisdiction from news/blog text for non-agency sources."""
    lower = text.lower()
    if any(t in lower for t in ["european union", " eu ", "gdpr", "eu ai act", "eur-lex", "european commission"]):
        return "EU"
    if any(t in lower for t in ["united kingdom", " uk ", "ico", "information commissioner", "uk gdpr"]):
        return "GB"
    if any(t in lower for t in ["california", " ca ", "ccpa", "cppa", "cpra"]):
        return "CA_STATE"
    if any(t in lower for t in ["new york", " ny ", "nyc"]):
        return "NY"
    if any(t in lower for t in ["texas", " tx "]):
        return "TX"
    if any(t in lower for t in ["illinois", " il ", "bipa"]):
        return "IL"
    if any(t in lower for t in ["federal trade commission", " ftc ", "sec ", "cfpb", "eeoc", "doj", "federal court",
                                  "u.s. district", "federal", "congress", "senate", "house of representatives"]):
        return "Federal"
    if any(t in lower for t in ["canada", "pipeda", "cppa"]):
        return "CA"
    if any(t in lower for t in ["brazil", "lgpd", "anpd"]):
        return "BR"
    if any(t in lower for t in ["india", "dpdp", "meity"]):
        return "IN"
    return "Federal"   # default for US-centric news sources


def _detect_enforcement_domain(text: str) -> str:
    """Detect whether an enforcement action is AI, privacy, or both domain."""
    lower     = text.lower()
    ai_hits   = sum(1 for t in ENFORCEMENT_AI_TERMS    if t in lower)
    priv_hits = sum(1 for t in ENFORCEMENT_PRIVACY_TERMS if t in lower)
    if ai_hits >= 2 and priv_hits >= 2:
        return "both"
    if priv_hits > ai_hits:
        return "privacy"
    return "ai"


def _score_relevance(text: str) -> float:
    """Score enforcement relevance 0-1 (AI + privacy combined)."""
    lower = text.lower()
    hits  = sum(1 for t in _ALL_ENFORCEMENT_TERMS if t in lower)
    return min(1.0, hits / 3.0)


def _find_related_regs(text: str) -> List[str]:
    """Find baseline IDs mentioned or implied by enforcement text."""
    lower   = text.lower()
    related = set()
    for pattern, baseline_id in REGULATION_LINK_MAP.items():
        if pattern in lower:
            related.add(baseline_id)
    return sorted(related)

def _extract_penalty(text: str) -> Optional[str]:
    """Extract monetary penalty from text if present."""
    patterns = [
        r'\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|thousand)?',
        r'€\s*([\d,]+(?:\.\d+)?)\s*(million|billion|thousand)?',
        r'([\d,]+(?:\.\d+)?)\s*(million|billion)?\s*(?:dollar|euro|pound)',
        r'civil penalty of \$?([\d,]+)',
        r'fine of \$?([\d,]+)',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()[:50]
    return None


def _action_id(source: str, text: str) -> str:
    return f"{source.upper()}-{hashlib.md5(text.encode()).hexdigest()[:10]}"


def _parse_rss_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]
    s = s.strip()
    for fmt in formats:
        try:
            return datetime.strptime(s[:len(fmt) + 5], fmt).replace(tzinfo=None)
        except ValueError:
            continue
    # Try stripping timezone string at end
    m = re.match(r'(\w{3}, \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2})', s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%a, %d %b %Y %H:%M:%S")
        except ValueError:
            pass
    return None


def _parse_rss_feed(xml_text: str) -> List[Dict]:
    """Generic RSS/Atom parser returning list of {title, link, description, date}."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("RSS parse error: %s", e)
        return []

    # Handle both RSS and Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # RSS items
    for item in root.findall(".//item"):
        t = item.findtext("title") or ""
        l = item.findtext("link") or ""
        d = item.findtext("description") or item.findtext("summary") or ""
        p = item.findtext("pubDate") or item.findtext("dc:date") or ""
        items.append({"title": t.strip(), "link": l.strip(),
                      "description": d.strip(), "date": p.strip()})

    # Atom entries
    for entry in root.findall("atom:entry", ns):
        t = entry.findtext("atom:title", namespaces=ns) or ""
        l_el = entry.find("atom:link", ns)
        l = l_el.get("href", "") if l_el is not None else ""
        d = entry.findtext("atom:summary", namespaces=ns) or \
            entry.findtext("atom:content", namespaces=ns) or ""
        p = entry.findtext("atom:published", namespaces=ns) or \
            entry.findtext("atom:updated", namespaces=ns) or ""
        if t:
            items.append({"title": t.strip(), "link": l.strip(),
                          "description": _strip_html(d).strip(), "date": p.strip()})

    return items


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class FTCEnforcementSource:
    """
    FTC press releases — enforcement actions, consent orders, AI-related cases.

    The FTC JSON API (/api/v1/news-events.json and /api/v1/search.json) started
    returning HTTPError after the FTC site restructure in 2024/2025.
    Primary source is now the confirmed-working RSS feed (verified March 2026).
    """
    NAME    = "ftc"
    RSS_URL = "https://www.ftc.gov/feeds/press-release.xml"  # confirmed working Mar 2026

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)

        # Primary: FTC RSS feed (confirmed working 2026)
        try:
            rss = http_get_text(self.RSS_URL, use_cache=True)
            if rss:
                for item in _parse_rss_feed(rss):
                    blob = f"{item['title']} {item['description']}"
                    if not _is_enforcement_relevant(blob):
                        continue
                    pub = _parse_rss_date(item.get("date", ""))
                    if pub and pub < cutoff:
                        continue
                    results.append(self._normalise(item, pub))
        except Exception as e:
            log.debug("FTC RSS failed: %s", e)

        return self._dedup(results)

    def _normalise(self, item: Dict, pub: Optional[datetime]) -> Dict:
        blob = f"{item['title']} {item['description']}"
        return {
            "id":             _action_id("FTC", item["link"] or item["title"]),
            "source":         self.NAME,
            "action_type":    "enforcement",
            "title":          item["title"],
            "url":            item["link"],
            "published_date": pub,
            "agency":         "Federal Trade Commission",
            "jurisdiction":   "Federal",
            "respondent":     self._extract_respondent(item["title"]),
            "summary":        item["description"][:500],
            "related_regs":   _find_related_regs(blob),
            "outcome":        self._infer_outcome(blob),
            "penalty_amount": _extract_penalty(blob),
            "ai_concepts":    self._infer_concepts(blob),
            "relevance_score":_score_relevance(blob),
            "domain":         _detect_enforcement_domain(blob),
            "raw_json":       item,
        }

    @staticmethod
    def _extract_respondent(title: str) -> str:
        m = re.search(r'(?:vs?\.?\s+|against\s+|in the matter of\s+)(.+?)(?:\s*,|\s*\(|$)',
                      title, re.IGNORECASE)
        return m.group(1).strip()[:100] if m else ""

    @staticmethod
    def _infer_outcome(text: str) -> str:
        lower = text.lower()
        if any(w in lower for w in ("consent order", "settlement", "agreed to")):
            return "settlement"
        if any(w in lower for w in ("penalty", "fine", "civil money")):
            return "fine"
        if "injunction" in lower:
            return "injunction"
        if "complaint" in lower:
            return "pending"
        return "enforcement"

    @staticmethod
    def _infer_concepts(text: str) -> List[str]:
        lower = text.lower()
        concepts = []
        if any(w in lower for w in ("bias", "discrimination", "disparate")):
            concepts.append("bias_fairness")
        if any(w in lower for w in ("transparent", "explainab", "disclos", "disclose",
                                     "right to explain")):
            concepts.append("transparency")
        if any(w in lower for w in ("automated decision", "algorithmic decision")):
            concepts.append("automated_decisions")
        if any(w in lower for w in ("facial recognition", "biometric")):
            concepts.append("biometric")
        if any(w in lower for w in ("data", "privacy", "personal information")):
            concepts.append("data_governance")
        return concepts

    @staticmethod
    def _dedup(items: List[Dict]) -> List[Dict]:
        seen, out = set(), []
        for item in items:
            if item["id"] not in seen:
                seen.add(item["id"])
                out.append(item)
        return out


class SECEnforcementSource:
    """
    SEC enforcement — AI fraud, algorithmic manipulation, AI-generated disclosures.

    SEC.gov RSS is behind Cloudflare and returns 403.
    We use the EDGAR full-text search (EFTS) which is on different infrastructure
    and accepts API requests without Cloudflare challenge.
    No API key required.
    """
    NAME         = "sec"
    EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
    # EDGAR full-text search (different endpoint, more reliable)
    EDGAR_FTS    = "https://efts.sec.gov/LATEST/search-index"

    SEARCH_TERMS = [
        '"artificial intelligence"',
        '"machine learning" discrimination',
        '"algorithmic" fraud',
        '"AI-generated"',
    ]

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
        start_dt = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        for term in self.SEARCH_TERMS[:3]:
            try:
                params = {
                    "q":        term,
                    "dateRange":"custom",
                    "startdt":  start_dt,
                    "forms":    "LITIG,EA",
                    "hits.hits._source.period_of_report": "*",
                }
                data = http_get(self.EDGAR_SEARCH, params=params, use_cache=True)
                hits = (data.get("hits") or {}).get("hits") or []
                for hit in hits[:15]:
                    src   = hit.get("_source", {})
                    title = (
                        src.get("entity_name") or
                        src.get("display_names", [{}])[0].get("name", "") or
                        src.get("period_of_report") or
                        "SEC Enforcement Filing"
                    )
                    blob = f"{title} {term}"
                    if not _is_enforcement_relevant(blob):
                        continue
                    doc_id  = hit.get("_id", "")
                    results.append({
                        "id":             _action_id("SEC", doc_id or title),
                        "source":         self.NAME,
                        "action_type":    "enforcement",
                        "title":          title,
                        "url":            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={src.get('entity_id','')}&type=LITIG&dateb=&owner=include&count=40",
                        "published_date": _parse_rss_date(src.get("file_date")),
                        "agency":         "Securities and Exchange Commission",
                        "jurisdiction":   "Federal",
                        "respondent":     src.get("entity_name", ""),
                        "summary":        f"SEC enforcement filing related to {term.strip('\"')}",
                        "related_regs":   [],
                        "outcome":        "pending",
                        "penalty_amount": None,
                        "ai_concepts":    FTCEnforcementSource._infer_concepts(blob),
                        "relevance_score":_score_relevance(blob),
                        "domain":         _detect_enforcement_domain(blob),
                        "raw_json":       src,
                    })
            except Exception as e:
                log.debug("SEC EDGAR search failed for '%s': %s", term, e)

        return FTCEnforcementSource._dedup(results)


class CFPBEnforcementSource:
    """
    CFPB enforcement actions — automated underwriting, credit scoring,
    discriminatory lending algorithms.

    The /activity-log/rss/ path was deprecated. Current RSS is at /about-us/newsroom/rss/
    No API key required.
    """
    NAME  = "cfpb"
    FEEDS = [
        "https://www.consumerfinance.gov/about-us/newsroom/feed/",    # confirmed working Mar 2026
    ]

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
        for feed_url in self.FEEDS:
            try:
                raw = http_get_text(feed_url, use_cache=True)
                # Guard: ICO sometimes returns HTML (cookie wall or "unavailable"
                # page) instead of XML. Detect and skip gracefully.
                if not raw or raw.strip().startswith('<!DOCTYPE') or '<html' in raw[:200].lower():
                    log.debug("ICO feed %s returned HTML, not XML — skipping", feed_url)
                    continue
                items = _parse_rss_feed(raw)
                for item in items:
                    blob = f"{item['title']} {item['description']}"
                    if not _is_enforcement_relevant(blob):
                        continue
                    pub = _parse_rss_date(item["date"])
                    if pub and pub < cutoff:
                        continue
                    results.append({
                        "id":             _action_id("CFPB", item["link"] or item["title"]),
                        "source":         self.NAME,
                        "action_type":    "enforcement",
                        "title":          item["title"],
                        "url":            item["link"],
                        "published_date": pub,
                        "agency":         "Consumer Financial Protection Bureau",
                        "jurisdiction":   "Federal",
                        "respondent":     FTCEnforcementSource._extract_respondent(item["title"]),
                        "summary":        item["description"][:500],
                        "related_regs":   _find_related_regs(blob),
                        "outcome":        FTCEnforcementSource._infer_outcome(blob),
                        "penalty_amount": _extract_penalty(blob),
                        "ai_concepts":    FTCEnforcementSource._infer_concepts(blob),
                        "relevance_score":_score_relevance(blob),
                        "domain":         _detect_enforcement_domain(blob),
                        "raw_json":       item,
                    })
            except Exception as e:
                log.debug("CFPB feed %s failed: %s", feed_url, e)
        return FTCEnforcementSource._dedup(results)


class EEOCEnforcementSource:
    """
    EEOC press releases — AI employment discrimination enforcement.
    Notable cases: iTutorGroup (2023), Workday (ongoing), DHI (2023).

    Uses the EEOC newsroom JSON endpoint which returns paginated press
    release data in a structured format.
    No API key required.
    """
    NAME     = "eeoc"
    # EEOC newsroom search page — scrape for AI-related press releases
    NEWSROOM = "https://www.eeoc.gov/newsroom/search"
    # EEOC JSON API — try multiple known endpoints
    JSON_API = "https://www.eeoc.gov/newsroom/search?keys=artificial+intelligence&format=json"
    RSS_URL  = "https://www.eeoc.gov/rss/newsroom"   # confirmed working Mar 2026

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)

        # Try RSS feed first (most reliable)
        try:
            rss = http_get_text(self.RSS_URL, use_cache=True)
            if rss:
                for item in _parse_rss_feed(rss):
                    blob = f"{item['title']} {item['description']}"
                    if not _is_enforcement_relevant(blob):
                        continue
                    pub = _parse_rss_date(item.get("date", ""))
                    if pub and pub < cutoff:
                        continue
                    results.append({
                        "id":             _action_id("EEOC", item.get("link", "") or item["title"]),
                        "source":         self.NAME,
                        "action_type":    "press_release",
                        "title":          item["title"],
                        "url":            item.get("link", ""),
                        "published_date": pub,
                        "agency":         "EEOC",
                        "jurisdiction":   "Federal",
                        "respondent":     "",
                        "summary":        item["description"][:500],
                        "related_regs":   _find_related_regs(blob),
                        "outcome":        FTCEnforcementSource._infer_outcome(blob),
                        "penalty_amount": _extract_penalty(blob),
                        "ai_concepts":    FTCEnforcementSource._infer_concepts(blob) + ["bias_fairness"],
                        "relevance_score":_score_relevance(blob),
                        "domain":         _detect_enforcement_domain(blob),
                        "raw_json":       item,
                    })
        except Exception as e:
            log.debug("EEOC RSS failed: %s", e)

        if results:
            return FTCEnforcementSource._dedup(results)

        # Fallback: EEOC JSON API (if RSS fails)
        for term in ["artificial intelligence", "algorithm", "automated hiring"]:
            try:
                params = {"keys": term, "limit": 20, "offset": 0}
                data  = http_get(self.JSON_API, params=params, use_cache=True)
                if isinstance(data, str):
                    log.debug("EEOC JSON API returned plain text, skipping")
                    continue
                items = data if isinstance(data, list) else (
                    data.get("data") or data.get("items") or data.get("results") or []
                )
                for item in items:
                    attrs = item.get("attributes") or item
                    title = attrs.get("title") or attrs.get("name") or ""
                    body  = attrs.get("body") or attrs.get("summary") or ""
                    if isinstance(body, dict):
                        body = body.get("value") or body.get("processed") or ""
                    path  = (attrs.get("path") or {}).get("alias") or attrs.get("url") or ""
                    link  = ("https://www.eeoc.gov" + path) if path and not path.startswith("http") else path
                    date_s = attrs.get("field_date") or attrs.get("created") or ""
                    blob  = f"{title} {_strip_html(str(body))}"
                    if not _is_enforcement_relevant(blob):
                        continue
                    pub = _parse_rss_date(str(date_s)) if date_s else None
                    if pub and pub < cutoff:
                        continue
                    results.append({
                        "id":             _action_id("EEOC", link or title),
                        "source":         self.NAME,
                        "action_type":    "enforcement",
                        "title":          title,
                        "url":            link,
                        "published_date": pub,
                        "agency":         "Equal Employment Opportunity Commission",
                        "jurisdiction":   "Federal",
                        "respondent":     FTCEnforcementSource._extract_respondent(title),
                        "summary":        _strip_html(str(body))[:500],
                        "related_regs":   _find_related_regs(blob),
                        "outcome":        FTCEnforcementSource._infer_outcome(blob),
                        "penalty_amount": _extract_penalty(blob),
                        "ai_concepts":    FTCEnforcementSource._infer_concepts(blob) + ["bias_fairness"],
                        "relevance_score":_score_relevance(blob),
                        "domain":         _detect_enforcement_domain(blob),
                        "raw_json":       attrs,
                    })
            except Exception as e:
                log.debug("EEOC API failed for '%s': %s", term, e)

        return FTCEnforcementSource._dedup(results)


class DOJEnforcementSource:
    """
    DOJ Civil Rights Division — AI discrimination in housing, lending,
    criminal justice, public accommodation.
    """
    NAME  = "doj"
    FEEDS = [
        "https://www.justice.gov/news/rss",                    # confirmed working Mar 2026
        "https://www.justice.gov/crt/press-releases/rss",              # CRT press releases
    ]

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
        for feed in self.FEEDS:
            try:
                raw   = http_get_text(feed, use_cache=True)
                items = _parse_rss_feed(raw)
                for item in items:
                    blob = f"{item['title']} {item['description']}"
                    if not _is_enforcement_relevant(blob):
                        continue
                    pub = _parse_rss_date(item["date"])
                    if pub and pub < cutoff:
                        continue
                    results.append({
                        "id":             _action_id("DOJ", item["link"] or item["title"]),
                        "source":         self.NAME,
                        "action_type":    "enforcement",
                        "title":          item["title"],
                        "url":            item["link"],
                        "published_date": pub,
                        "agency":         "Department of Justice",
                        "jurisdiction":   "Federal",
                        "respondent":     FTCEnforcementSource._extract_respondent(item["title"]),
                        "summary":        item["description"][:500],
                        "related_regs":   _find_related_regs(blob),
                        "outcome":        FTCEnforcementSource._infer_outcome(blob),
                        "penalty_amount": _extract_penalty(blob),
                        "ai_concepts":    FTCEnforcementSource._infer_concepts(blob),
                        "relevance_score":_score_relevance(blob),
                        "domain":         _detect_enforcement_domain(blob),
                        "raw_json":       item,
                    })
            except Exception as e:
                log.debug("DOJ feed %s failed: %s", feed, e)
        return FTCEnforcementSource._dedup(results)


class ICOEnforcementSource:
    """
    UK Information Commissioner's Office — GDPR Article 22 automated
    decisions, AI data processing enforcement notices.

    ICO discontinued their enforcement-specific RSS feed after a site redesign
    (confirmed Mar 2026 — /global/rss-feeds/enforcement/ now returns an HTML
    page saying "Enforcement RSS is currently unavailable").

    Current strategy: use the ICO media centre news RSS, which carries
    enforcement announcements alongside other news, filtered by
    _is_enforcement_relevant(). The Welsh-language mirror of the enforcement
    RSS was still serving XML as of Mar 2026 and is included as a fallback.

    TODO: the POST /api/search endpoint (nodeId filter) could give
    enforcement-specific JSON — wire up once the correct filter param
    is confirmed from DevTools inspection.

    No API key required.
    """
    NAME  = "ico"
    FEEDS = [
        "https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/rss/",  # media centre with enforcement announcements
        "https://cy.ico.org.uk/global/rss-feeds/enforcement/",                 # Welsh mirror — enforcement RSS
    ]

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
        for feed_url in self.FEEDS:
            try:
                raw = http_get_text(feed_url, use_cache=True)
                # Guard: ICO sometimes returns HTML (cookie wall or "unavailable"
                # page) instead of XML. Detect and skip gracefully.
                if not raw or raw.strip().startswith('<!DOCTYPE') or '<html' in raw[:200].lower():
                    log.debug("ICO feed %s returned HTML, not XML — skipping", feed_url)
                    continue
                items = _parse_rss_feed(raw)
                for item in items:
                    blob = f"{item['title']} {item['description']}"
                    if not _is_enforcement_relevant(blob):
                        continue
                    pub = _parse_rss_date(item["date"])
                    if pub and pub < cutoff:
                        continue
                    results.append({
                        "id":             _action_id("ICO", item["link"] or item["title"]),
                        "source":         self.NAME,
                        "action_type":    "enforcement",
                        "title":          item["title"],
                        "url":            item["link"],
                        "published_date": pub,
                        "agency":         "Information Commissioner's Office",
                        "jurisdiction":   "GB",
                        "respondent":     FTCEnforcementSource._extract_respondent(item["title"]),
                        "summary":        item["description"][:500],
                        "related_regs":   _find_related_regs(blob) or ["eu_gdpr_ai"],
                        "outcome":        FTCEnforcementSource._infer_outcome(blob),
                        "penalty_amount": _extract_penalty(blob),
                        "ai_concepts":    FTCEnforcementSource._infer_concepts(blob),
                        "relevance_score":_score_relevance(blob),
                        "domain":         _detect_enforcement_domain(blob),
                        "raw_json":       item,
                    })
            except Exception as e:
                log.debug("ICO feed %s failed: %s", feed_url, e)
        return FTCEnforcementSource._dedup(results)


class CourtListenerSource:
    """
    CourtListener (Free Law Project) — federal court opinions and dockets
    related to AI systems. Covers RECAP-uploaded PACER documents.

    API: https://www.courtlistener.com/api/rest/v4/
    Optional free token at courtlistener.com for higher rate limits.
    Without token: 5000 req/day. With free token: 50000 req/day.
    """
    NAME    = "courtlistener"
    API_BASE = "https://www.courtlistener.com/api/rest/v4"

    SEARCH_TERMS = [
        "artificial intelligence discrimination",
        "algorithmic bias employment",
        "facial recognition",
        "automated hiring",
        "predictive policing",
        "AI deepfake",
    ]

    def __init__(self):
        self._headers = {}
        if COURTLISTENER_KEY:
            self._headers["Authorization"] = f"Token {COURTLISTENER_KEY}"

    def fetch(self, lookback_days: int = 180) -> List[Dict]:
        results = []
        cutoff  = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        for term in self.SEARCH_TERMS[:4]:  # limit requests
            try:
                params = {
                    "q":           term,
                    "type":        "o",           # opinions
                    "filed_after": cutoff,
                    "order_by":    "score desc",
                    "page_size":   10,
                    "format":      "json",
                }
                data = http_get(
                    f"{self.API_BASE}/search/",
                    params=params,
                    headers=self._headers,
                    use_cache=True,
                )
                for result in data.get("results", []):
                    blob = f"{result.get('caseName', '')} {result.get('snippet', '')}"
                    if not _is_enforcement_relevant(blob):
                        continue
                    results.append(self._normalise(result))
            except Exception as e:
                log.debug("CourtListener search '%s' failed: %s", term, e)

        return FTCEnforcementSource._dedup(results)

    def _normalise(self, result: Dict) -> Dict:
        case_name = result.get("caseName") or result.get("case_name") or "Unknown Case"
        blob = f"{case_name} {result.get('snippet', '')}"
        # Determine court
        court = result.get("court", "") or result.get("court_id", "")
        return {
            "id":             _action_id("CL", result.get("id", case_name)),
            "source":         self.NAME,
            "action_type":    "opinion",
            "title":          case_name,
            "url":            f"https://www.courtlistener.com{result.get('absolute_url', '')}",
            "published_date": _parse_rss_date(
                result.get("dateFiled") or result.get("date_filed")
            ),
            "agency":         court or "Federal Court",
            "jurisdiction":   "Federal",
            "respondent":     case_name.split(" v. ")[-1][:100] if " v. " in case_name else "",
            "summary":        result.get("snippet", "")[:500],
            "related_regs":   _find_related_regs(blob),
            "outcome":        "opinion",
            "penalty_amount": _extract_penalty(blob),
            "ai_concepts":    FTCEnforcementSource._infer_concepts(blob),
            "relevance_score":_score_relevance(blob),
            "domain":         _detect_enforcement_domain(blob),
            "raw_json":       {k: result.get(k) for k in
                               ("caseName", "court", "dateFiled", "docketNumber", "snippet")},
        }


# ═══════════════════════════════════════════════════════════════════════════════
# ENFORCEMENT AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class IAPPNewsSource:
    """
    IAPP Daily Dashboard RSS — curated privacy & AI governance news.

    The IAPP (International Association of Privacy Professionals) editorial
    team publishes a daily digest of the most significant privacy and AI
    governance stories globally. Because it is editorially curated it carries
    a high density of enforcement actions, court decisions, regulatory
    settlements, and agency announcements alongside some policy/legislative
    news.

    Uses the stricter _is_news_enforcement_relevant() filter (requires both
    a domain signal and an enforcement action signal) to pass through
    enforcement items while blocking general commentary.

    No API key required.
    """
    NAME  = "iapp"
    FEEDS = [
        "https://iapp.org/rss/daily-dashboard/",         # global daily digest
        "https://iapp.org/rss/united-states-dashboard-digest/",  # US-focused
    ]

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
        seen: set = set()
        for feed_url in self.FEEDS:
            try:
                raw = http_get_text(feed_url, use_cache=True)
                if not raw or raw.strip().startswith('<!DOCTYPE') or '<html' in raw[:200].lower():
                    log.debug("IAPP feed %s returned HTML — skipping", feed_url)
                    continue
                for item in _parse_rss_feed(raw):
                    if item["link"] in seen:
                        continue
                    seen.add(item["link"])
                    blob = f"{item['title']} {item['description']}"
                    if not _is_news_enforcement_relevant(blob):
                        continue
                    pub = _parse_rss_date(item["date"])
                    if pub and pub < cutoff:
                        continue
                    results.append({
                        "id":             _action_id("IAPP", item["link"] or item["title"]),
                        "source":         self.NAME,
                        "action_type":    "news",
                        "title":          item["title"],
                        "url":            item["link"],
                        "published_date": pub,
                        "agency":         "IAPP / Various",
                        "jurisdiction":   _detect_jurisdiction(blob),
                        "respondent":     FTCEnforcementSource._extract_respondent(item["title"]),
                        "summary":        item["description"][:500],
                        "related_regs":   _find_related_regs(blob),
                        "outcome":        FTCEnforcementSource._infer_outcome(blob),
                        "penalty_amount": _extract_penalty(blob),
                        "ai_concepts":    FTCEnforcementSource._infer_concepts(blob),
                        "relevance_score":_score_relevance(blob),
                        "domain":         _detect_enforcement_domain(blob),
                        "raw_json":       item,
                    })
            except Exception as e:
                log.debug("IAPP feed %s failed: %s", feed_url, e)
        return FTCEnforcementSource._dedup(results)


class RegulatoryOversightSource:
    """
    Troutman Pepper "Regulatory Oversight" blog RSS.

    A law firm blog dedicated to tracking regulatory enforcement actions
    across consumer protection, privacy, and AI. Nearly every post covers
    an enforcement action, investigation, settlement, or litigation
    development — very low noise-to-signal ratio. Strong coverage of
    state AG actions that no government RSS feed captures.

    Uses the stricter _is_news_enforcement_relevant() filter as a secondary
    check, though most posts will pass regardless given the blog's tight focus.

    No API key required.
    """
    NAME  = "regulatory_oversight"
    FEEDS = [
        "https://www.regulatoryoversight.com/feed/",
    ]

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
        for feed_url in self.FEEDS:
            try:
                raw = http_get_text(feed_url, use_cache=True)
                if not raw or raw.strip().startswith('<!DOCTYPE') or '<html' in raw[:200].lower():
                    log.debug("RegulatoryOversight feed returned HTML — skipping")
                    continue
                for item in _parse_rss_feed(raw):
                    blob = f"{item['title']} {item['description']}"
                    if not _is_news_enforcement_relevant(blob):
                        continue
                    pub = _parse_rss_date(item["date"])
                    if pub and pub < cutoff:
                        continue
                    results.append({
                        "id":             _action_id("REGOV", item["link"] or item["title"]),
                        "source":         self.NAME,
                        "action_type":    "enforcement",
                        "title":          item["title"],
                        "url":            item["link"],
                        "published_date": pub,
                        "agency":         "Various / State AG",
                        "jurisdiction":   _detect_jurisdiction(blob),
                        "respondent":     FTCEnforcementSource._extract_respondent(item["title"]),
                        "summary":        item["description"][:500],
                        "related_regs":   _find_related_regs(blob),
                        "outcome":        FTCEnforcementSource._infer_outcome(blob),
                        "penalty_amount": _extract_penalty(blob),
                        "ai_concepts":    FTCEnforcementSource._infer_concepts(blob),
                        "relevance_score":_score_relevance(blob),
                        "domain":         _detect_enforcement_domain(blob),
                        "raw_json":       item,
                    })
            except Exception as e:
                log.debug("RegulatoryOversight feed failed: %s", e)
        return FTCEnforcementSource._dedup(results)


class CourthouseNewsSource:
    """
    Courthouse News Service RSS — federal and state court filings.

    Courthouse News is a legal newswire covering court filings (complaints,
    motions, settlements, verdicts) the day they are filed. It provides
    litigation coverage that CourtListener misses — state courts, newly-filed
    complaints before they appear in PACER/RECAP, and fast-breaking cases.

    High volume source: the general feed covers all litigation, so the
    _is_news_enforcement_relevant() filter is essential here. Only items
    that contain both a domain signal (AI/privacy) AND an enforcement action
    term (lawsuit, complaint, settlement, etc.) will pass through.

    No API key required.
    """
    NAME  = "courthouse_news"
    FEEDS = [
        "https://www.courthousenews.com/feed/",
    ]

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
        for feed_url in self.FEEDS:
            try:
                raw = http_get_text(feed_url, use_cache=True)
                if not raw or raw.strip().startswith('<!DOCTYPE') or '<html' in raw[:200].lower():
                    log.debug("CourthouseNews feed returned HTML — skipping")
                    continue
                for item in _parse_rss_feed(raw):
                    blob = f"{item['title']} {item['description']}"
                    if not _is_news_enforcement_relevant(blob):
                        continue
                    pub = _parse_rss_date(item["date"])
                    if pub and pub < cutoff:
                        continue
                    results.append({
                        "id":             _action_id("CNS", item["link"] or item["title"]),
                        "source":         self.NAME,
                        "action_type":    "litigation",
                        "title":          item["title"],
                        "url":            item["link"],
                        "published_date": pub,
                        "agency":         "Federal/State Court",
                        "jurisdiction":   _detect_jurisdiction(blob),
                        "respondent":     FTCEnforcementSource._extract_respondent(item["title"]),
                        "summary":        item["description"][:500],
                        "related_regs":   _find_related_regs(blob),
                        "outcome":        FTCEnforcementSource._infer_outcome(blob),
                        "penalty_amount": _extract_penalty(blob),
                        "ai_concepts":    FTCEnforcementSource._infer_concepts(blob),
                        "relevance_score":_score_relevance(blob),
                        "domain":         _detect_enforcement_domain(blob),
                        "raw_json":       item,
                    })
            except Exception as e:
                log.debug("CourthouseNews feed failed: %s", e)
        return FTCEnforcementSource._dedup(results)


class EnforcementAgent:
    """
    Aggregates all enforcement and litigation sources into a single interface.
    Called by the orchestrator during full runs.
    """

    def __init__(self):
        self.sources = [
            FTCEnforcementSource(),
            SECEnforcementSource(),
            CFPBEnforcementSource(),
            EEOCEnforcementSource(),
            DOJEnforcementSource(),
            ICOEnforcementSource(),
            CourtListenerSource(),
            IAPPNewsSource(),
            RegulatoryOversightSource(),
            CourthouseNewsSource(),
        ]

    def fetch_all(self, lookback_days: int = 90) -> Dict[str, Any]:
        """
        Fetch AI-related enforcement actions from all sources.
        Persists to the enforcement_actions table.
        Returns summary counts.
        """
        from utils.db import upsert_enforcement_action

        log.info("Starting enforcement fetch (lookback=%d days)…", lookback_days)
        counts = {"new": 0, "updated": 0, "failed": 0, "by_source": {}}

        for source in self.sources:
            src_name = source.NAME
            try:
                actions  = source.fetch(lookback_days=lookback_days)
                new_cnt  = 0
                for action in actions:
                    # Filter out very low relevance scores
                    if action.get("relevance_score", 0) < 0.1:
                        continue
                    is_new = upsert_enforcement_action(action)
                    if is_new:
                        new_cnt += 1
                        counts["new"] += 1
                    else:
                        counts["updated"] += 1
                counts["by_source"][src_name] = new_cnt
                log.info("%s: %d actions (%d new)", src_name.upper(), len(actions), new_cnt)
            except Exception as e:
                log.error("Enforcement source %s failed: %s", src_name, e)
                counts["failed"] += 1

        log.info("Enforcement fetch complete: %d new, %d updated", counts["new"], counts["updated"])
        return counts

    def get_recent(self,
                   jurisdiction: Optional[str] = None,
                   source:       Optional[str] = None,
                   action_type:  Optional[str] = None,
                   days:         int            = 365,
                   limit:        int            = 100) -> List[Dict]:
        """Retrieve recent enforcement actions from the database."""
        from utils.db import get_enforcement_actions
        return get_enforcement_actions(
            jurisdiction=jurisdiction,
            source=source,
            action_type=action_type,
            days=days,
            limit=limit,
        )

    def stats(self) -> Dict:
        """Return enforcement action statistics."""
        from utils.db import count_enforcement_actions
        return count_enforcement_actions()
