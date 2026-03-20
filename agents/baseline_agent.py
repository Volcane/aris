"""
ARIS — Baseline Agent

Loads and provides access to the curated static baseline regulations shipped
with the application in data/baselines/. These baselines represent the settled,
in-force body of AI law for each supported jurisdiction and require NO API calls.

The baselines serve three roles:

1. COMPARISON ANCHOR FOR THE DIFF AGENT
   When a new document arrives, the diff agent can compare it against the
   baseline for its regulation family — identifying whether the change adds,
   removes, clarifies, or contradicts the baseline obligations.

2. FOUNDATION FOR GAP ANALYSIS
   The gap analysis agent incorporates baseline obligations as the starting
   point for its scope mapping. This means the gap analysis covers obligations
   that may not yet have any associated document in the database.

3. STANDALONE REFERENCE VIEW
   The Baseline view in the UI lets users browse the settled regulatory
   landscape for their jurisdictions without running any analysis.

The baselines are static JSON files committed to the repository. They require
no network access and are always available. When a regulation reaches a new
milestone (e.g. EU AI Act full application in 2027), a developer updates the
relevant JSON file — a five-minute edit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.cache import get_logger

log = get_logger("aris.baseline")

# Path to baseline data relative to project root
_BASELINES_DIR = Path(__file__).parent.parent / "data" / "baselines"


# ── Baseline Agent ────────────────────────────────────────────────────────────

class BaselineAgent:
    """
    Loads and queries the static baseline regulation files.
    Thread-safe singleton-style loading with in-process cache.
    """

    _cache: Optional[Dict[str, Any]] = None   # class-level cache

    def __init__(self):
        if BaselineAgent._cache is None:
            BaselineAgent._cache = self._load_all()

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load_all(self) -> Dict[str, Any]:
        """Load all baseline files from disk. Called once at first instantiation."""
        index_path = _BASELINES_DIR / "index.json"
        if not index_path.exists():
            log.warning("Baseline index not found at %s", index_path)
            return {"index": {}, "baselines": {}}

        with index_path.open() as f:
            index = json.load(f)

        baselines = {}
        for entry in index.get("baselines", []):
            file_path = _BASELINES_DIR / entry["file"]
            if not file_path.exists():
                log.warning("Baseline file not found: %s", file_path)
                continue
            try:
                with file_path.open() as f:
                    data = json.load(f)
                baselines[entry["id"]] = {
                    **entry,    # index metadata
                    **data,     # full baseline content
                }
                log.debug("Loaded baseline: %s (%s)", entry["id"], entry["jurisdiction"])
            except Exception as e:
                log.error("Failed to load baseline %s: %s", entry["file"], e)

        log.info("Baseline agent loaded %d baselines", len(baselines))
        return {"index": index, "baselines": baselines}

    @classmethod
    def reload(cls) -> None:
        """Force-reload baselines from disk. Useful in tests or after file updates."""
        cls._cache = None
        cls()

    # ── Public queries ────────────────────────────────────────────────────────

    def get_all(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Return summary metadata for all loaded baselines.
        domain: "ai" | "privacy" | None (all)
        """
        return [
            {
                "id":           b["id"],
                "jurisdiction": b["jurisdiction"],
                "title":        b["title"],
                "short_name":   b.get("short_name", b["title"]),
                "status":       b.get("status", "Unknown"),
                "priority":     b.get("priority", "medium"),
                "overview":     b.get("overview", ""),
                "domain":       b.get("domain", "ai"),
            }
            for b in self._cache["baselines"].values()
            if domain is None or b.get("domain", "ai") == domain
        ]

    def get_by_id(self, baseline_id: str) -> Optional[Dict[str, Any]]:
        """Return the full baseline for a given ID."""
        return self._cache["baselines"].get(baseline_id)

    def get_for_jurisdiction(self, jurisdiction: str,
                              domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all baselines for a given jurisdiction code, optionally filtered by domain."""
        jur = jurisdiction.upper()
        return [
            b for b in self._cache["baselines"].values()
            if b.get("jurisdiction", "").upper() == jur
            and (domain is None or b.get("domain", "ai") == domain)
        ]

    def get_for_jurisdictions(self, jurisdictions: List[str],
                               domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all baselines for a list of jurisdiction codes, optionally filtered by domain."""
        jurs = {j.upper() for j in jurisdictions}
        return [
            b for b in self._cache["baselines"].values()
            if b.get("jurisdiction", "").upper() in jurs
            and (domain is None or b.get("domain", "ai") == domain)
        ]

    def match_document(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find the baseline that corresponds to a document, if any.
        Uses the doc_id_patterns from the index to match.

        Returns the matched baseline or None.
        """
        doc_id = (doc.get("id") or "").lower()
        title  = (doc.get("title") or "").lower()
        jur    = (doc.get("jurisdiction") or "").upper()

        for baseline in self._cache["baselines"].values():
            if baseline.get("jurisdiction", "").upper() != jur:
                continue
            patterns = baseline.get("doc_id_patterns") or []
            for pat in patterns:
                try:
                    if re.search(pat.lower(), doc_id) or re.search(pat.lower(), title):
                        return baseline
                except re.error:
                    if pat.lower() in doc_id or pat.lower() in title:
                        return baseline
        return None

    def get_obligations_for_jurisdiction(self,
                                          jurisdiction: str,
                                          severity_filter: Optional[str] = None
                                          ) -> List[Dict[str, Any]]:
        """
        Return a flat list of all obligations from all baselines for a
        jurisdiction, optionally filtered by severity.

        Each obligation dict includes baseline_id, jurisdiction, and regulation title.
        """
        obligations = []
        for baseline in self.get_for_jurisdiction(jurisdiction):
            obls_by_actor = baseline.get("obligations_by_actor") or {}
            # Structured obligations (EU AI Act style)
            for actor_key, actor_obls in obls_by_actor.items():
                for obl in actor_obls:
                    obligations.append({
                        **obl,
                        "baseline_id":       baseline["id"],
                        "regulation_title":  baseline.get("short_name", baseline["title"]),
                        "jurisdiction":      baseline["jurisdiction"],
                        "actor":             actor_key,
                        "source":            "baseline",
                    })
            # Flat obligations (AIDA / state law style)
            for obl_key in ("proposed_obligations", "key_obligations", "deployer_obligations",
                             "developer_obligations"):
                for obl in (baseline.get(obl_key) or []):
                    if not any(o.get("id") == obl.get("id") for o in obligations):
                        obligations.append({
                            **obl,
                            "baseline_id":      baseline["id"],
                            "regulation_title": baseline.get("short_name", baseline["title"]),
                            "jurisdiction":     baseline["jurisdiction"],
                            "source":           "baseline",
                        })
        return obligations

    def format_for_gap_analysis(self,
                                 jurisdictions: List[str]) -> str:
        """
        Format baseline obligations for the jurisdictions into a structured
        prompt block for the gap analysis agent.

        This supplements (does not replace) the document-based scope mapping.
        """
        baselines = self.get_for_jurisdictions(jurisdictions)
        if not baselines:
            return ""

        lines = ["=== BASELINE REGULATORY OBLIGATIONS (settled, in-force law) ===\n"]

        for b in baselines:
            lines.append(f"--- {b.get('short_name', b['title'])} [{b['jurisdiction']}] ---")
            lines.append(f"Status: {b.get('status', 'Unknown')}")
            if b.get("overview"):
                lines.append(f"Overview: {b['overview'][:300]}…" if len(b.get('overview','')) > 300 else f"Overview: {b['overview']}")

            # Prohibited practices (highest priority)
            prohibited = b.get("prohibited_practices") or []
            if prohibited:
                lines.append("PROHIBITED (in force):")
                for p in prohibited:
                    since = f" [since {p['in_force_from']}]" if p.get("in_force_from") else ""
                    lines.append(f"  • {p['title']}: {p['description']}{since}")

            # Obligations
            obls_by_actor = b.get("obligations_by_actor") or {}
            for actor, obls in obls_by_actor.items():
                lines.append(f"OBLIGATIONS ({actor.replace('_', ' ')}):")
                for obl in obls:
                    dl = f" [deadline: {obl['deadline']}]" if obl.get("deadline") else ""
                    lines.append(f"  [{obl.get('id', '')}] {obl['title']}: {obl['description']}{dl}")

            # Flat obligation lists
            for key, label in [("proposed_obligations", "PROPOSED OBLIGATIONS"),
                                ("key_obligations",      "KEY OBLIGATIONS"),
                                ("deployer_obligations", "DEPLOYER OBLIGATIONS"),
                                ("developer_obligations","DEVELOPER OBLIGATIONS")]:
                items = b.get(key) or []
                if items:
                    lines.append(f"{label}:")
                    for item in items:
                        dl = f" [deadline: {item['deadline']}]" if item.get("deadline") else ""
                        lines.append(f"  [{item.get('id', '')}] {item['title']}: {item['description']}{dl}")

            # ICO / sector-specific obligations (UK)
            ico_obls = b.get("ico_ai_obligations") or []
            if ico_obls:
                lines.append("ICO / DATA PROTECTION OBLIGATIONS:")
                for obl in ico_obls:
                    lines.append(f"  • {obl['obligation']}: {obl['description']}")

            lines.append("")

        return "\n".join(lines)

    def format_for_diff_context(self, doc: Dict[str, Any]) -> str:
        """
        Return a formatted baseline context block for use by the diff agent
        when comparing a document against its baseline.

        Returns empty string if no matching baseline found.
        """
        baseline = self.match_document(doc)
        if not baseline:
            return ""

        lines = [
            f"=== BASELINE: {baseline.get('short_name', baseline['title'])} ===",
            f"Status: {baseline.get('status', 'Unknown')}",
            "",
        ]

        if baseline.get("overview"):
            lines.append(f"Baseline overview: {baseline['overview']}")
            lines.append("")

        # Key definitions
        defs = baseline.get("key_definitions") or []
        if defs:
            lines.append("KEY DEFINITIONS IN BASELINE:")
            for d in defs[:5]:
                lines.append(f"  {d['term']}: {d['definition']}")
            lines.append("")

        # All obligations
        obls_by_actor = baseline.get("obligations_by_actor") or {}
        if obls_by_actor:
            lines.append("BASELINE OBLIGATIONS:")
            for actor, obls in obls_by_actor.items():
                for obl in obls:
                    dl = f" [deadline: {obl.get('deadline', '')}]" if obl.get("deadline") else ""
                    lines.append(f"  [{obl.get('id', '')}] {obl['title']}{dl}")
            lines.append("")

        # Prohibited practices
        prohibited = baseline.get("prohibited_practices") or []
        if prohibited:
            lines.append("BASELINE PROHIBITIONS:")
            for p in prohibited:
                since = f" [since {p.get('in_force_from', '')}]" if p.get("in_force_from") else ""
                lines.append(f"  {p['title']}: {p['description']}{since}")
            lines.append("")

        # Timeline
        timeline = baseline.get("timeline") or []
        if timeline:
            lines.append("COMPLIANCE TIMELINE:")
            for t in timeline:
                lines.append(f"  {t['date']}: {t['milestone']}")

        return "\n".join(lines)

    def get_coverage_summary(self) -> Dict[str, Any]:
        """Return a coverage summary for display in the UI."""
        all_b = list(self._cache["baselines"].values())
        by_jur: Dict[str, List] = {}
        for b in all_b:
            jur = b.get("jurisdiction", "Unknown")
            by_jur.setdefault(jur, []).append(b.get("short_name", b["title"]))
        return {
            "total":        len(all_b),
            "by_jurisdiction": by_jur,
            "jurisdictions":   sorted(by_jur.keys()),
            "last_reviewed": self._cache["index"].get("last_reviewed", "Unknown"),
        }
