# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 Mitch Kwiatkowski
# ARIS — Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
"""
ARIS — State Agent Base Class

All state-specific agents inherit from StateAgentBase.
To add a new state, create sources/states/<state_code>.py
and subclass StateAgentBase with at minimum:
  - state_code
  - state_name
  - legiscan_state

Override get_native_feed_url() and parse_native_feed()
if the state has its own public XML/RSS feed.
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from config.settings import LEGISCAN_BASE, LEGISCAN_KEY, AI_KEYWORDS, LOOKBACK_DAYS
from utils.cache import http_get, is_ai_relevant, get_logger
from utils.search import is_privacy_relevant, detect_domain

log = get_logger("aris.state")


class LegiScanAPIError(Exception):
    """Raised when LegiScan returns an API-level error (quota, auth, etc.)."""

    pass


class StateAgentBase(ABC):
    """
    Abstract base for state-level legislation monitoring.

    Concrete subclasses must set:
        state_code      : str   — USPS two-letter code e.g. "PA"
        state_name      : str   — Full name e.g. "Pennsylvania"
        legiscan_state  : str   — LegiScan state identifier (usually same as state_code)

    Optional overrides:
        get_native_feed_url()  — return URL string if the state has its own XML/RSS feed
        parse_native_feed(xml) — parse that feed, return list of normalised dicts
    """

    state_code: str = ""
    state_name: str = ""
    legiscan_state: str = ""

    # ── LegiScan ──────────────────────────────────────────────────────────────

    def _legiscan_call(self, op: str, extra_params: Optional[Dict] = None) -> Any:
        """
        Make a single LegiScan API call.
        Raises LegiScanError on API-level errors (quota exceeded, bad key, etc.)
        so callers can distinguish "no data" from "API unavailable".
        """
        if not LEGISCAN_KEY:
            log.warning(
                "LEGISCAN_KEY not set — state source disabled. "
                "Register free at https://legiscan.com/legiscan"
            )
            return {}
        params = {"key": LEGISCAN_KEY, "op": op, **(extra_params or {})}
        # Never cache LegiScan calls — quota errors would be cached and
        # silently returned on every subsequent call within the TTL window.
        data = http_get(LEGISCAN_BASE, params=params, use_cache=False)
        # Detect API-level errors (quota, auth, invalid request)
        if isinstance(data, dict) and data.get("status") == "ERROR":
            msg = data.get("alert", {}).get("message", "Unknown LegiScan error")
            raise LegiScanAPIError(f"LegiScan API error ({op}): {msg}")
        return data

    def search_legiscan(
        self, lookback_days: int = LOOKBACK_DAYS
    ) -> List[Dict[str, Any]]:
        """
        Fetch AI/privacy-relevant bills from LegiScan for this state.

        Strategy: getMasterList (one call) returns all bills in the current
        session. We filter locally for AI/privacy relevance. This uses 1 API
        call per state instead of 11 keyword searches, preserving quota.

        Falls back to getSearch if getMasterList returns nothing.
        """
        if not LEGISCAN_KEY:
            return []

        domain = getattr(self, "_domain", "both")
        results: List[Dict[str, Any]] = []

        # ── Primary: getMasterList (1 call per state) ─────────────────────────
        try:
            data = self._legiscan_call("getMasterList", {"state": self.legiscan_state})
            bills = data.get("masterlist", {})

            # Count raw bills before filtering so we can distinguish
            # "API returned data but nothing relevant" from "API returned nothing"
            raw_count = sum(
                1
                for k, v in bills.items()
                if k not in ("session", "0") and isinstance(v, dict)
            )
            if raw_count == 0:
                log.warning(
                    "LegiScan getMasterList (%s): 0 bills returned — "
                    "may indicate quota exhaustion or invalid session",
                    self.state_code,
                )

            cutoff = (
                datetime.utcnow() - timedelta(days=lookback_days)
                if lookback_days
                else None
            )
            seen: set = set()
            for key, item in bills.items():
                if key in ("session", "0") or not isinstance(item, dict):
                    continue
                bill_id = str(item.get("bill_id", ""))
                if not bill_id or bill_id in seen:
                    continue
                title = item.get("title", "")
                if not title:
                    continue
                # Apply lookback filter using last_action_date
                if cutoff:
                    last_action = item.get("last_action_date", "")
                    if last_action:
                        try:
                            if datetime.strptime(last_action[:10], "%Y-%m-%d") < cutoff:
                                continue
                        except ValueError:
                            pass  # keep bill if date unparseable
                # Filter by domain relevance on title only
                if domain == "privacy" and not is_privacy_relevant(title):
                    continue
                elif domain == "ai" and not is_ai_relevant(title):
                    continue
                elif domain == "both" and not (
                    is_ai_relevant(title) or is_privacy_relevant(title)
                ):
                    continue
                seen.add(bill_id)
                doc = self._normalise_legiscan(item)
                doc["domain"] = detect_domain(title)
                results.append(doc)

            log.info(
                "LegiScan getMasterList (%s): %d AI/privacy bills "
                "(of %d total in session, lookback=%dd)",
                self.state_code,
                len(results),
                raw_count,
                lookback_days,
            )

        except LegiScanAPIError as e:
            # Quota or auth error — log prominently, skip fallback
            # (keyword searches would burn more quota on the same error)
            log.error("LEGISCAN API ERROR (%s): %s", self.state_code, e)
            return []
        except Exception as e:
            log.warning(
                "LegiScan getMasterList (%s) failed: %s — falling back to getSearch",
                self.state_code,
                e,
            )
            # ── Fallback: targeted getSearch queries ──────────────────────────
            results = self._search_legiscan_keywords(domain)

        return results

    def _search_legiscan_keywords(self, domain: str) -> List[Dict[str, Any]]:
        """Keyword search fallback — used when getMasterList fails."""
        _ai_kws = [
            "artificial intelligence",
            "machine learning",
            "algorithmic",
            "deepfake",
            "automated decision",
        ]
        _priv_kws = [
            "personal data",
            "consumer privacy",
            "data protection",
            "data privacy",
            "privacy act",
            "data broker",
        ]
        search_kws = (
            _priv_kws
            if domain == "privacy"
            else _ai_kws
            if domain == "ai"
            else _ai_kws + _priv_kws
        )
        results: List[Dict[str, Any]] = []
        seen: set = set()
        for kw in search_kws:
            try:
                data = self._legiscan_call(
                    "getSearch",
                    {
                        "state": self.legiscan_state,
                        "query": kw,
                    },
                )
                for key, item in data.get("searchresult", {}).items():
                    if key == "summary" or not isinstance(item, dict):
                        continue
                    bill_id = str(item.get("bill_id", ""))
                    if not bill_id or bill_id in seen:
                        continue
                    title = item.get("title", "")
                    if domain == "privacy" and not is_privacy_relevant(title):
                        continue
                    elif domain == "ai" and not is_ai_relevant(title):
                        continue
                    elif domain == "both" and not (
                        is_ai_relevant(title) or is_privacy_relevant(title)
                    ):
                        continue
                    seen.add(bill_id)
                    doc = self._normalise_legiscan(item)
                    doc["domain"] = detect_domain(title)
                    results.append(doc)
            except Exception as e:
                log.error(
                    "LegiScan getSearch '%s' (%s) failed: %s", kw, self.state_code, e
                )
        log.info(
            "LegiScan getSearch fallback (%s): %d bills found",
            self.state_code,
            len(results),
        )
        return results

    def fetch_bill_text(self, bill_id: str) -> Optional[str]:
        """Fetch the full text of a LegiScan bill (base64-decoded)."""
        try:
            data = self._legiscan_call("getBill", {"id": bill_id})
            bill = data.get("bill", {})
            texts = bill.get("texts", [])
            if texts:
                latest = texts[-1]
                text_id = latest.get("doc_id")
                txt_data = self._legiscan_call("getBillText", {"id": text_id})
                encoded = txt_data.get("text", {}).get("doc", "")
                if encoded:
                    return base64.b64decode(encoded).decode("utf-8", errors="replace")[
                        :8000
                    ]
        except Exception as e:
            log.warning("Bill text fetch failed (%s): %s", bill_id, e)
        return None

    def _get_current_session_id(self) -> Optional[int]:
        """Look up the active legislative session ID for this state."""
        try:
            data = self._legiscan_call("getSessionList", {"state": self.legiscan_state})
            sessions = data.get("sessions", [])
            # Sessions are returned newest-first; find the most recent active one
            for s in sessions:
                if s.get("year_end", 0) >= datetime.utcnow().year:
                    return s.get("session_id")
            return sessions[0].get("session_id") if sessions else None
        except Exception as e:
            log.error("getSessionList failed (%s): %s", self.state_code, e)
            return None

    def _normalise_legiscan(self, item: Dict) -> Dict[str, Any]:
        bill_id = str(item.get("bill_id", ""))
        bill_num = item.get("bill_number", "")
        title = item.get("title", "")
        url = item.get(
            "url", f"https://legiscan.com/{self.legiscan_state}/bill/{bill_num}"
        )

        # Map LegiScan status codes
        status_map = {
            1: "Introduced",
            2: "Engrossed",
            3: "Enrolled",
            4: "Passed",
            5: "Vetoed",
            6: "Failed",
        }
        status_code = item.get("status", 1)
        status = status_map.get(status_code, "Introduced")

        last_action_date = item.get("last_action_date")

        return {
            "id": f"{self.state_code}-LS-{bill_id}",
            "source": f"legiscan_{self.state_code.lower()}",
            "jurisdiction": self.state_code,
            "doc_type": "Bill",
            "title": title,
            "url": url,
            "published_date": _parse_date(last_action_date),
            "agency": f"{self.state_name} General Assembly",
            "status": status,
            "full_text": title,  # enriched later by fetch_bill_text
            "raw_json": item,
        }

    # ── Optional: native state XML/RSS feed ───────────────────────────────────

    def get_native_feed_url(self) -> Optional[str]:
        """
        Override in subclass to return the URL of a native XML/RSS feed.
        Return None (default) to skip native feed and use LegiScan only.
        """
        return None

    def parse_native_feed(self, raw_xml: str) -> List[Dict[str, Any]]:
        """
        Override in subclass to parse the native XML/RSS feed.
        Must return a list of normalised document dicts.
        """
        return []

    def fetch_native(self) -> List[Dict[str, Any]]:
        """Fetch and parse the native state feed, if available."""
        url = self.get_native_feed_url()
        if not url:
            return []
        try:
            from utils.cache import http_get_text

            raw = http_get_text(url)
            docs = self.parse_native_feed(raw)
            log.info("Native feed (%s): %d documents", self.state_code, len(docs))
            return docs
        except Exception as e:
            log.error("Native feed (%s) failed: %s", self.state_code, e)
            return []

    # ── Main entry point ──────────────────────────────────────────────────────

    def fetch_all(
        self, lookback_days: int = LOOKBACK_DAYS, domain: str = "both"
    ) -> List[Dict[str, Any]]:
        """
        Fetch relevant legislation for this state.
        domain: "ai" | "privacy" | "both" — controls which keywords are searched.
        Combines LegiScan + native feed (if available).
        """
        self._domain = domain  # used by search_legiscan
        log.info("Starting %s state fetch (domain=%s)…", self.state_name, domain)
        docs = self.search_legiscan(lookback_days)
        docs.extend(self.fetch_native())

        # De-duplicate
        seen, unique = set(), []
        for d in docs:
            if d["id"] not in seen:
                seen.add(d["id"])
                unique.append(d)

        log.info("%s fetch complete: %d documents", self.state_name, len(unique))
        return unique


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None
