"""
ARIS — Enforcement & Litigation Agent

Monitors AI-related enforcement actions, court cases, and regulatory
sanctions from seven free public sources:

US FEDERAL AGENCIES (all RSS/JSON, no key required)
  FTC    — Algorithmic bias, dark patterns, AI fraud, ROSCA violations
             https://www.ftc.gov/rss.xml
  SEC    — AI fraud, algorithmic manipulation, AI-generated disclosures
             https://www.sec.gov/rss/litigation/litreleases.xml
             https://efts.sec.gov/LATEST/search-index (EDGAR full-text)
  CFPB   — Automated underwriting, credit scoring, BNPL algorithm enforcement
             https://www.consumerfinance.gov/activity-log/rss/
  EEOC   — Employment AI discrimination (hiring, promotion, performance)
             https://www.eeoc.gov/newsroom/rss
  DOJ    — Civil rights AI discrimination in housing, lending, criminal justice
             https://www.justice.gov/crt/rss

INTERNATIONAL (RSS, no key required)
  ICO    — UK GDPR Article 22 automated decisions, AI data processing
  (UK)     https://ico.org.uk/action-weve-taken/enforcement/rss/

US COURTS (free REST API, optional free token for higher rate limits)
  CourtListener — Federal court opinions and dockets from PACER/RECAP
  (Free Open Law  https://www.courtlistener.com/api/rest/v4/
   Project)       Optional: COURTLISTENER_KEY env var (free registration)
                  5,000 req/day without token, more with free token

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

# Map known regulation titles/short-names to baseline IDs for linking
REGULATION_LINK_MAP = {
    "ftc act":                  "us_ftc_ai",
    "section 5":                "us_ftc_ai",
    "gdpr":                     "eu_gdpr_ai",
    "article 22":               "eu_gdpr_ai",
    "eu ai act":                "eu_ai_act",
    "ai act":                   "eu_ai_act",
    "fcra":                     "us_sector_ai",
    "fair credit reporting":    "us_sector_ai",
    "ecoa":                     "us_sector_ai",
    "equal credit opportunity": "us_sector_ai",
    "title vii":                "us_sector_ai",
    "ada":                      "us_sector_ai",
    "nist rmf":                 "us_nist_ai_rmf",
    "eo 14110":                 "us_eo_14110",
    "executive order 14110":    "us_eo_14110",
    "colorado ai":              "colorado_ai",
    "illinois aipa":            "illinois_aipa",
    "nyc ll144":                "nyc_ll144",
    "local law 144":            "nyc_ll144",
    "uk gdpr":                  "eu_gdpr_ai",
}


def _is_enforcement_relevant(text: str) -> bool:
    """Check if text is relevant to AI enforcement/litigation."""
    lower = text.lower()
    return any(term in lower for term in ENFORCEMENT_AI_TERMS)


def _score_relevance(text: str) -> float:
    """Score AI relevance 0–1."""
    lower = text.lower()
    hits  = sum(1 for t in ENFORCEMENT_AI_TERMS if t in lower)
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

    FTC removed their RSS feed in 2023. We now use their JSON API:
      https://www.ftc.gov/api/v1/news-events.json
    No API key required.
    """
    NAME     = "ftc"
    JSON_API = "https://www.ftc.gov/api/v1/news-events.json"
    # Fallback: search API endpoint
    SEARCH_API = "https://www.ftc.gov/api/v1/search.json"

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)

        # Primary: FTC news-events JSON API
        for category in ["press-release", "enforcement-action"]:
            try:
                params = {
                    "category": category,
                    "limit":    50,
                    "sort":     "-created",
                }
                data = http_get(self.JSON_API, params=params, use_cache=True)
                items = data if isinstance(data, list) else data.get("items") or data.get("results") or []
                for item in items:
                    title   = item.get("title") or item.get("name") or ""
                    summary = (item.get("summary") or item.get("description") or
                               item.get("body") or "")
                    link    = item.get("url") or item.get("link") or item.get("path") or ""
                    if link and not link.startswith("http"):
                        link = "https://www.ftc.gov" + link
                    date_s  = (item.get("created") or item.get("date") or
                               item.get("published") or "")
                    blob    = f"{title} {summary}"
                    if not _is_enforcement_relevant(blob):
                        continue
                    pub = _parse_rss_date(str(date_s)) if date_s else None
                    if pub and pub < cutoff:
                        continue
                    fake_item = {"title": title, "description": summary,
                                 "link": link, "date": str(date_s)}
                    results.append(self._normalise(fake_item, pub))
            except Exception as e:
                log.debug("FTC JSON API (%s) failed: %s", category, e)

        # Fallback: FTC search API filtered for AI terms
        if not results:
            for term in ["artificial intelligence", "algorithm", "automated decision"]:
                try:
                    params = {"q": term, "type": "press-release", "limit": 20}
                    data   = http_get(self.SEARCH_API, params=params, use_cache=True)
                    items  = data if isinstance(data, list) else data.get("results") or []
                    for item in items:
                        title = item.get("title") or ""
                        link  = item.get("url") or item.get("path") or ""
                        if link and not link.startswith("http"):
                            link = "https://www.ftc.gov" + link
                        summary = item.get("summary") or item.get("snippet") or ""
                        blob = f"{title} {summary}"
                        if not _is_enforcement_relevant(blob):
                            continue
                        pub = _parse_rss_date(item.get("date") or "")
                        if pub and pub < cutoff:
                            continue
                        fake_item = {"title": title, "description": summary,
                                     "link": link, "date": item.get("date", "")}
                        results.append(self._normalise(fake_item, pub))
                except Exception as e:
                    log.debug("FTC search API failed for '%s': %s", term, e)

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
        "https://www.consumerfinance.gov/about-us/newsroom/rss/",
        "https://www.consumerfinance.gov/enforcement/actions/feed/",
    ]

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
        for feed_url in self.FEEDS:
            try:
                raw   = http_get_text(feed_url, use_cache=True)
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
                        "raw_json":       item,
                    })
            except Exception as e:
                log.debug("CFPB feed %s failed: %s", feed_url, e)
        return FTCEnforcementSource._dedup(results)


class EEOCEnforcementSource:
    """
    EEOC press releases — AI employment discrimination enforcement.
    Notable cases: iTutorGroup (2023), Workday (ongoing), DHI (2023).

    EEOC removed their RSS feed in 2022. We use their JSON newsroom API
    and fall back to scraping the newsroom page for press release links.
    No API key required.
    """
    NAME     = "eeoc"
    JSON_API = "https://www.eeoc.gov/newsroom/search"
    # EEOC Drupal JSON API
    DRUPAL_API = "https://www.eeoc.gov/api/newsroom"

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)

        # Try Drupal JSON API
        for term in ["artificial intelligence", "algorithm", "automated hiring"]:
            try:
                params = {
                    "search_api_fulltext": term,
                    "sort_by":             "field_date",
                    "sort_order":          "DESC",
                    "page[limit]":         20,
                }
                data  = http_get(self.DRUPAL_API, params=params, use_cache=True)
                items = data if isinstance(data, list) else (
                    data.get("data") or data.get("items") or []
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
        "https://www.justice.gov/crt/rss",
        "https://www.justice.gov/opa/pr/rss",   # Office of Public Affairs
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
                        "raw_json":       item,
                    })
            except Exception as e:
                log.debug("DOJ feed %s failed: %s", feed, e)
        return FTCEnforcementSource._dedup(results)


class ICOEnforcementSource:
    """
    UK Information Commissioner's Office — GDPR Article 22 automated
    decisions, AI data processing enforcement notices.

    The /enforcement/rss/ path was removed. Current feeds:
      /about-the-ico/news-and-events/rss/  — news and enforcement announcements
    No API key required.
    """
    NAME  = "ico"
    FEEDS = [
        "https://ico.org.uk/about-the-ico/news-and-events/rss/",
        "https://ico.org.uk/feed/",
    ]

    def fetch(self, lookback_days: int = 90) -> List[Dict]:
        results = []
        cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
        for feed_url in self.FEEDS:
            try:
                raw   = http_get_text(feed_url, use_cache=True)
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
            "raw_json":       {k: result.get(k) for k in
                               ("caseName", "court", "dateFiled", "docketNumber", "snippet")},
        }


# ═══════════════════════════════════════════════════════════════════════════════
# ENFORCEMENT AGENT
# ═══════════════════════════════════════════════════════════════════════════════

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
