"""
ARIS — Canada Agent

Data sources (all free, no API key required):

1. OpenParliament.ca API
   - https://api.openparliament.ca/bills/
   - Tracks federal bills with keyword search
   - Covers House of Commons and Senate

2. Canada Gazette RSS feeds
   - https://gazette.gc.ca/rss/p2-eng.html  (Part II — regulations in force)
   - https://gazette.gc.ca/rss/p1-eng.html  (Part I — proposed regulations)
   - Official government publication; no key required

3. ISED (Innovation, Science and Economic Development) news feed
   - https://www.canada.ca/en/innovation-science-economic-development.atom.xml
   - Covers AI policy announcements, AIDA updates, and consultations

Key Canada AI policy landscape (as of 2026):
  - No federal AI law currently in force
  - Bill C-27 (AIDA) died on order paper — Jan 2025 prorogation
  - New government (Conservative) — AI policy direction uncertain
  - Quebec Law 25 — strongest provincial AI/privacy rules
  - Canadian AI Safety Institute (CAISI) — launched Nov 2024
  - AI Strategy Task Force — renewed national AI strategy expected
  - Office of the Privacy Commissioner — active AI enforcement under PIPEDA
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sources.international.base import InternationalAgentBase, parse_date, strip_tags
from config.settings import AI_KEYWORDS, LOOKBACK_DAYS
from utils.cache import http_get, http_get_text, is_ai_relevant, get_logger

log = get_logger("aris.international.ca")

# ── Endpoint constants ────────────────────────────────────────────────────────

OPENPARLIAMENT_BILLS  = "https://api.openparliament.ca/bills/"
CANADA_GAZETTE_P1_RSS = "https://gazette.gc.ca/rss/p1-eng.html"
CANADA_GAZETTE_P2_RSS = "https://gazette.gc.ca/rss/p2-eng.html"
ISED_ATOM_FEED        = "https://www.canada.ca/en/innovation-science-economic-development.atom.xml"
OPC_NEWS_FEED         = "https://www.priv.gc.ca/en/opc-news/rss/"

# Pinned high-priority Canadian AI policy documents
PINNED_CA_DOCUMENTS = [
    {
        "id":       "CA-AIDA-BILL-C27-DIED",
        "title":    "Artificial Intelligence and Data Act (AIDA) — Bill C-27 (Lapsed)",
        "doc_type": "Federal Bill (Lapsed)",
        "date":     "2025-01-06",
        "status":   "Lapsed — Parliament Prorogued January 2025",
        "url":      "https://ised-isde.canada.ca/site/innovation-better-canada/en/artificial-intelligence-and-data-act",
        "agency":   "Innovation, Science and Economic Development Canada (ISED)",
        "abstract": (
            "Canada's proposed federal AI regulation framework died on the order paper "
            "when Parliament was prorogued in January 2025. AIDA would have regulated "
            "high-impact AI systems, required risk assessments, bias mitigation, and "
            "disclosure obligations. A Conservative government was elected in April 2025; "
            "reintroduction in modified form is possible but timing is uncertain. "
            "Companies should monitor for new AI bill introduction while aligning with "
            "Quebec Law 25 and GDPR as de facto standards."
        ),
    },
    {
        "id":       "CA-CAISI-LAUNCH-2024",
        "title":    "Canadian AI Safety Institute (CAISI) — Launch",
        "doc_type": "Government Initiative",
        "date":     "2024-11-12",
        "status":   "Active",
        "url":      "https://ised-isde.canada.ca/site/innovation-better-canada/en/canadian-ai-safety-institute",
        "agency":   "ISED / Government of Canada",
        "abstract": (
            "Canada launched the Canadian AI Safety Institute (CAISI) in November 2024 "
            "as part of a CAD $2.4 billion AI investment. CAISI focuses on evaluating "
            "risks of frontier AI models. While not yet a regulatory body, CAISI's "
            "evaluations may inform future mandatory requirements. AI companies should "
            "engage with CAISI's voluntary evaluation processes."
        ),
    },
    {
        "id":       "CA-QUEBEC-LAW25-FULL-FORCE",
        "title":    "Quebec Law 25 — Full Force (September 2024)",
        "doc_type": "Provincial Law",
        "date":     "2024-09-22",
        "status":   "In Force",
        "url":      "https://www.cai.gouv.qc.ca/en/law-25/",
        "agency":   "Commission d'accès à l'information (CAI) — Quebec",
        "abstract": (
            "Quebec's privacy modernisation law (Bill 64 / Law 25) reached full force in "
            "September 2024. Requires opt-in consent for sensitive data, mandatory privacy "
            "impact assessments (PIAs) before deploying AI-driven profiling or automated "
            "decision-making that affects individuals' rights, and notices when automated "
            "decisions are made. Applies to any company handling personal information of "
            "Quebec residents. Fines up to CAD $25M or 4% of worldwide revenue."
        ),
    },
    {
        "id":       "CA-OPC-PIPEDA-AI-GUIDANCE",
        "title":    "Office of the Privacy Commissioner — AI and PIPEDA Guidance",
        "doc_type": "Regulatory Guidance",
        "date":     "2024-06-01",
        "status":   "Active",
        "url":      "https://www.priv.gc.ca/en/privacy-topics/technology/artificial-intelligence/",
        "agency":   "Office of the Privacy Commissioner of Canada (OPC)",
        "abstract": (
            "The OPC has issued guidance applying PIPEDA to AI systems, particularly "
            "around consent for training data, transparency about automated decisions, "
            "and accountability for AI vendors. Although PIPEDA is not AI-specific, "
            "the OPC actively investigates AI-related complaints. Companies using personal "
            "data to train or deploy AI must have documented PIPEDA compliance."
        ),
    },
]


class CanadaAgent(InternationalAgentBase):
    """
    Canada federal AI regulation monitor.

    Tracks:
     - Federal Parliament AI bills via OpenParliament
     - Canada Gazette proposed and final regulations
     - ISED news feed for AI policy developments
     - OPC (privacy commissioner) AI guidance
     - Pinned critical documents (AIDA status, Quebec Law 25, CAISI)
    """

    jurisdiction_code = "CA"
    jurisdiction_name = "Canada"
    region            = "North America"
    language          = "en"

    # ── Pinned documents ──────────────────────────────────────────────────────

    def _get_pinned_docs(self) -> List[Dict[str, Any]]:
        docs = []
        for item in PINNED_CA_DOCUMENTS:
            docs.append(self._make_doc(
                id           = item["id"],
                source       = "ca_pinned",
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

    # ── OpenParliament bills ──────────────────────────────────────────────────

    def _fetch_openparliament_bills(self) -> List[Dict[str, Any]]:
        """
        Search OpenParliament.ca for AI-related federal bills.
        API docs: https://openparliament.ca/api/
        """
        results = []
        pinned  = {d["id"] for d in PINNED_CA_DOCUMENTS}

        for term in ["artificial intelligence", "algorithmic", "automated decision"]:
            try:
                params = {
                    "q":      term,
                    "format": "json",
                    "limit":  20,
                }
                data  = http_get(OPENPARLIAMENT_BILLS, params=params)
                bills = data.get("objects", [])

                for bill in bills:
                    title  = bill.get("name", {}).get("en", "") or ""
                    number = bill.get("number", "")
                    url    = "https://openparliament.ca" + bill.get("url", "")

                    if not is_ai_relevant(f"{title} {term}"):
                        continue

                    doc_id = f"CA-BILL-{re.sub(r'[^A-Z0-9]', '', number.upper())}"
                    if doc_id in pinned:
                        continue

                    session    = bill.get("session", "")
                    status_str = bill.get("status", {}).get("en", "") if isinstance(bill.get("status"), dict) else str(bill.get("status", ""))

                    results.append(self._make_doc(
                        id           = doc_id,
                        source       = "ca_openparliament",
                        doc_type     = "Federal Bill",
                        title        = title or f"Canada Bill {number}",
                        url          = url,
                        published_date = parse_date(bill.get("introduced")),
                        agency       = f"Parliament of Canada — {session}",
                        status       = status_str or "Active",
                        full_text    = title,
                        raw_json     = bill,
                    ))

            except Exception as e:
                log.warning("OpenParliament bills failed (%s): %s", term, e)

        seen, unique = set(), []
        for r in results:
            if r["id"] not in seen:
                seen.add(r["id"])
                unique.append(r)

        log.info("OpenParliament: %d AI bills found", len(unique))
        return unique

    # ── Canada Gazette RSS ────────────────────────────────────────────────────

    def _fetch_gazette_feed(self, feed_url: str, gazette_part: str,
                            lookback_days: int) -> List[Dict[str, Any]]:
        """Parse a Canada Gazette RSS feed (Part I or Part II)."""
        results = []
        since   = datetime.utcnow() - timedelta(days=lookback_days)

        try:
            xml_text = http_get_text(feed_url, use_cache=True)
            root     = ET.fromstring(xml_text)
            ns       = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            channel = root.find(f"{ns}channel") or root

            for item in (channel.findall(f"{ns}item") or root.findall(".//item")):
                title   = (item.findtext(f"{ns}title")       or "").strip()
                link    = (item.findtext(f"{ns}link")         or "").strip()
                desc    = strip_tags(item.findtext(f"{ns}description") or "", 2000)
                pub_str = (item.findtext(f"{ns}pubDate")      or "").strip()
                pub_dt  = parse_date(pub_str)

                if pub_dt and pub_dt < since:
                    continue
                if not is_ai_relevant(f"{title} {desc}"):
                    continue

                safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", link)[-60:]
                status  = "Proposed Regulation" if "Part I" in gazette_part else "Regulation in Force"

                results.append(self._make_doc(
                    id           = f"CA-GAZETTE-{gazette_part.replace(' ', '')}-{safe_id}",
                    source       = f"ca_gazette_{gazette_part.replace(' ', '_').lower()}",
                    doc_type     = "Regulation" if "Part II" in gazette_part else "Proposed Regulation",
                    title        = title,
                    url          = link,
                    published_date = pub_dt,
                    agency       = f"Government of Canada — Canada Gazette {gazette_part}",
                    status       = status,
                    full_text    = desc or title,
                    raw_json     = {"title": title, "link": link, "description": desc},
                ))

        except Exception as e:
            log.warning("Canada Gazette %s RSS failed: %s", gazette_part, e)

        log.info("Canada Gazette %s: %d AI entries found", gazette_part, len(results))
        return results

    # ── ISED Atom feed ────────────────────────────────────────────────────────

    def _fetch_ised_feed(self, lookback_days: int) -> List[Dict[str, Any]]:
        """Parse the ISED / Canada.ca Atom news feed for AI policy items."""
        results = []
        since   = datetime.utcnow() - timedelta(days=lookback_days)

        try:
            xml_text = http_get_text(ISED_ATOM_FEED, use_cache=True)
            root     = ET.fromstring(xml_text)
            ns       = "{http://www.w3.org/2005/Atom}"

            for entry in root.findall(f"{ns}entry"):
                title   = (entry.findtext(f"{ns}title")   or "").strip()
                link_el = entry.find(f"{ns}link")
                link    = link_el.get("href", "") if link_el is not None else ""
                updated = (entry.findtext(f"{ns}updated") or "").strip()
                summary = strip_tags(entry.findtext(f"{ns}summary") or "", 2000)

                pub_dt = parse_date(updated)
                if pub_dt and pub_dt < since:
                    continue
                if not is_ai_relevant(f"{title} {summary}"):
                    continue

                safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", link)[-60:]
                results.append(self._make_doc(
                    id           = f"CA-ISED-{safe_id}",
                    source       = "ca_ised_feed",
                    doc_type     = "Government Announcement / Policy",
                    title        = title,
                    url          = link,
                    published_date = pub_dt,
                    agency       = "Innovation, Science and Economic Development Canada (ISED)",
                    status       = "Published",
                    full_text    = summary or title,
                    raw_json     = {"title": title, "link": link},
                ))

        except Exception as e:
            log.warning("ISED Atom feed failed: %s", e)

        log.info("ISED feed: %d AI entries found", len(results))
        return results

    # ── Main fetch ────────────────────────────────────────────────────────────

    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        """Primary: pinned docs + OpenParliament bills."""
        docs = []
        docs.extend(self._get_pinned_docs())
        docs.extend(self._fetch_openparliament_bills())
        return docs

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        """Secondary: Canada Gazette feeds + ISED policy feed."""
        docs = []
        docs.extend(self._fetch_gazette_feed(CANADA_GAZETTE_P1_RSS, "Part I",  lookback_days))
        docs.extend(self._fetch_gazette_feed(CANADA_GAZETTE_P2_RSS, "Part II", lookback_days))
        docs.extend(self._fetch_ised_feed(lookback_days))
        return docs
