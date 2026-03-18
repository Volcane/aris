"""
ARIS — Pennsylvania State Agent

Extends StateAgentBase with:
  1. LegiScan API (inherited)
  2. PA General Assembly native XML feed (hourly updates, no key needed)
     https://www.legis.state.pa.us/data/
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional

from sources.state_agent_base import StateAgentBase, _parse_date
from config.settings import AI_KEYWORDS
from utils.cache import is_ai_relevant, get_logger

log = get_logger("aris.state.pa")

# PA General Assembly XML feed URLs (updated hourly, no key required)
PA_HOUSE_BILLS_XML = "https://www.legis.state.pa.us/cfdocs/legis/home/xml/hbHistXML.cfm"
PA_SENATE_BILLS_XML = "https://www.legis.state.pa.us/cfdocs/legis/home/xml/sbHistXML.cfm"


class PennsylvaniaAgent(StateAgentBase):
    """
    Pennsylvania AI legislation monitor.

    Data sources:
      - LegiScan API  (keyword search, full text)
      - PA Legis XML  (house + senate bill history, updated hourly)
    """

    state_code     = "PA"
    state_name     = "Pennsylvania"
    legiscan_state = "PA"

    # ── Native feed: PA General Assembly XML ─────────────────────────────────

    def get_native_feed_url(self) -> Optional[str]:
        # We override fetch_native() directly to pull two feeds
        return None   # handled below

    def fetch_native(self) -> List[Dict[str, Any]]:
        """
        Pull the PA House + Senate bill history XML feeds and filter for
        AI-relevant legislation.
        """
        from utils.cache import http_get_text
        results = []

        for chamber, url in [("House", PA_HOUSE_BILLS_XML), ("Senate", PA_SENATE_BILLS_XML)]:
            try:
                xml_text = http_get_text(url, use_cache=True)
                parsed   = self._parse_pa_xml(xml_text, chamber)
                results.extend(parsed)
                log.info("PA %s XML: %d AI-relevant bills", chamber, len(parsed))
            except Exception as e:
                log.error("PA %s XML feed failed: %s", chamber, e)

        return results

    def _parse_pa_xml(self, xml_text: str, chamber: str) -> List[Dict[str, Any]]:
        """
        Parse the PA General Assembly bill history XML.

        The feed uses <BillHistory> → <Bill> elements with attributes:
          BillNumber, PrintersNumber, ShortTitle, PrimeSponsor, LastAction, LastActionDate
        """
        results = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            log.error("PA XML parse error: %s", e)
            return []

        # Support both namespaced and non-namespaced XML
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        for bill_el in root.iter(f"{ns}Bill"):
            title = (
                bill_el.get("ShortTitle")
                or bill_el.findtext(f"{ns}ShortTitle")
                or ""
            )
            actions_text = " ".join(
                a.get("Description", "") or a.text or ""
                for a in bill_el.iter(f"{ns}Action")
            )
            combined = f"{title} {actions_text}"

            if not is_ai_relevant(combined):
                continue

            bill_num      = bill_el.get("BillNumber") or bill_el.findtext(f"{ns}BillNumber") or ""
            printer_num   = bill_el.get("PrintersNumber") or ""
            sponsor       = bill_el.get("PrimeSponsor") or bill_el.findtext(f"{ns}PrimeSponsor") or ""
            last_action   = bill_el.get("LastAction") or bill_el.findtext(f"{ns}LastAction") or ""
            last_action_dt = bill_el.get("LastActionDate") or bill_el.findtext(f"{ns}LastActionDate") or ""

            prefix = "HB" if chamber == "House" else "SB"
            doc_id = f"PA-LEGIS-{prefix}{bill_num}"

            results.append({
                "id":            doc_id,
                "source":        "pa_general_assembly",
                "jurisdiction":  "PA",
                "doc_type":      "Bill",
                "title":         title or f"PA {chamber} Bill {bill_num}",
                "url":           self._build_pa_url(chamber, bill_num, printer_num),
                "published_date": _parse_date(last_action_dt),
                "agency":        f"PA General Assembly — {chamber}",
                "status":        last_action or "Introduced",
                "full_text":     f"{title}. Last action: {last_action}",
                "raw_json":      {
                    "bill_number":   bill_num,
                    "printer_number": printer_num,
                    "sponsor":       sponsor,
                    "last_action":   last_action,
                    "chamber":       chamber,
                },
            })

        return results

    @staticmethod
    def _build_pa_url(chamber: str, bill_num: str, printer_num: str) -> str:
        """Construct a URL to the bill on the PA General Assembly site."""
        if not bill_num:
            return "https://www.palegis.us/bills/"
        b_type = "H" if chamber == "House" else "S"
        return (
            f"https://www.palegis.us/legislation/bills/"
            f"?q=bill_number&chamber={b_type}&billnbr={bill_num}"
        )

    # ── Enrichment ────────────────────────────────────────────────────────────

    def enrich_with_full_text(self, docs: List[Dict]) -> List[Dict]:
        """
        For LegiScan documents that lack full text, attempt to fetch it.
        PA General Assembly docs already contain sufficient text for summarisation.
        """
        for doc in docs:
            if doc["source"] == f"legiscan_pa" and len(doc.get("full_text", "")) < 200:
                bill_id = doc["id"].replace("PA-LS-", "")
                text    = self.fetch_bill_text(bill_id)
                if text:
                    doc["full_text"] = text
        return docs

    def fetch_all(self, lookback_days: int = 30) -> List[Dict[str, Any]]:
        """Override to add enrichment pass."""
        docs = super().fetch_all(lookback_days)
        docs = self.enrich_with_full_text(docs)
        return docs
