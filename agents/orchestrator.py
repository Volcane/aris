"""
ARIS — Orchestrator (updated with diff pipeline)

Three fetch tracks + automatic change detection:

  1. US Federal     — FederalAgent
  2. US States      — StateAgentBase subclasses
  3. International  — InternationalAgentBase subclasses

Change detection (runs after every fetch):
  - Version diffs: when a known document's content changes, the old and new
    versions are automatically compared by DiffAgent
  - Addendum scanning: new documents are scanned for signals that they
    amend or clarify an existing document in the database
"""

from __future__ import annotations

import importlib
from typing import List, Dict, Any, Optional

from config.settings import LOOKBACK_DAYS
from config.jurisdictions import (
    ENABLED_US_STATES, ENABLED_INTERNATIONAL,
    US_STATE_MODULE_MAP, INTERNATIONAL_MODULE_MAP, INTERNATIONAL_CLASS_MAP,
)
from sources.federal_agent import FederalAgent
from sources.state_agent_base import StateAgentBase
from sources.international.base import InternationalAgentBase
from agents.interpreter import InterpreterAgent
from agents.diff_agent import DiffAgent
from utils.db import (
    upsert_document, upsert_summary, get_unsummarized_documents,
    get_stats, get_document, get_all_documents,
    save_diff, save_link, diff_exists,
    log_fetch_event,
)
from utils.cache import get_logger

log = get_logger("aris.orchestrator")


def _get_learner():
    """Lazy-load the learning agent — gracefully absent if not yet configured."""
    try:
        from agents.learning_agent import LearningAgent
        return LearningAgent()
    except Exception:
        return None


# ── Agent loaders ─────────────────────────────────────────────────────────────

def _load_state_agents() -> List[StateAgentBase]:
    agents = []
    for code in ENABLED_US_STATES:
        module_path = US_STATE_MODULE_MAP.get(code)
        if not module_path:
            log.warning("No module mapping for US state %s — skipping", code)
            continue
        try:
            module = importlib.import_module(module_path)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type)
                        and issubclass(attr, StateAgentBase)
                        and attr is not StateAgentBase):
                    agents.append(attr())
                    log.info("Loaded US state agent: %s (%s)", attr.__name__, code)
                    break
        except ImportError as e:
            log.error("Could not load state agent for %s: %s", code, e)
    return agents


def _load_international_agents() -> List[InternationalAgentBase]:
    agents = []
    for code in ENABLED_INTERNATIONAL:
        module_path = INTERNATIONAL_MODULE_MAP.get(code)
        if not module_path:
            log.warning("No module mapping for %s — skipping", code)
            continue
        try:
            module            = importlib.import_module(module_path)
            target_class_name = INTERNATIONAL_CLASS_MAP.get(code)
            found             = False
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if not (isinstance(attr, type)
                        and issubclass(attr, InternationalAgentBase)
                        and attr is not InternationalAgentBase):
                    continue
                if target_class_name and attr.__name__ != target_class_name:
                    continue
                if not target_class_name and getattr(attr, "jurisdiction_code", "") != code:
                    continue
                agents.append(attr())
                log.info("Loaded international agent: %s (%s)", attr.__name__, code)
                found = True
                break
            if not found:
                log.warning("No matching class in %s for %s", module_path, code)
        except ImportError as e:
            log.error("Could not load international agent for %s: %s", code, e)
    return agents


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Main pipeline controller — fetch, summarize, and detect changes.

    fetch(sources=["federal"])         → US Federal only
    fetch(sources=["states"])          → All enabled US states
    fetch(sources=["international"])   → All international
    fetch(sources=["EU", "PA"])        → Specific jurisdictions
    fetch()                            → Everything
    """

    def __init__(self):
        self.federal_agent         = FederalAgent()
        self.state_agents          = _load_state_agents()
        self.international_agents  = _load_international_agents()
        self._interpreter          = None
        self._diff_agent           = None

    @property
    def interpreter(self) -> InterpreterAgent:
        if self._interpreter is None:
            self._interpreter = InterpreterAgent()
        return self._interpreter

    @property
    def diff_agent(self) -> DiffAgent:
        if self._diff_agent is None:
            self._diff_agent = DiffAgent()
        return self._diff_agent

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def fetch(self, sources: Optional[List[str]] = None,
              lookback_days: int = LOOKBACK_DAYS,
              run_diff: bool = True,
              domain: str = "both") -> Dict[str, int]:
        """
        Fetch documents from selected sources and persist to DB.
        If run_diff=True, automatically runs change detection after fetching.
        domain: "ai" | "privacy" | "both" — which regulatory domain to fetch.

        Returns a dict with counts: fetched, version_diffs, addenda_found.
        """
        all_docs: List[Dict[str, Any]] = []
        sources_lower = [s.lower() for s in sources] if sources else []
        run_all     = not sources
        run_federal = run_all or "federal" in sources_lower
        run_states  = run_all or "states"  in sources_lower
        run_intl    = run_all or "international" in sources_lower
        specific    = {s.upper() for s in (sources or [])} - {
            "FEDERAL", "STATES", "INTERNATIONAL"
        }

        # ── Track 1: US Federal ───────────────────────────────────────────────
        if run_federal:
            log.info("═══ Track 1: US Federal (domain=%s) ═══", domain)
            all_docs.extend(self.federal_agent.fetch_all(lookback_days, domain=domain))

        # ── Track 2: US States ────────────────────────────────────────────────
        for agent in self.state_agents:
            if run_states or agent.state_code in specific:
                log.info("═══ Track 2 (State): %s ═══", agent.state_name)
                all_docs.extend(agent.fetch_all(lookback_days, domain=domain))

        # ── Track 3: International ────────────────────────────────────────────
        for agent in self.international_agents:
            if run_intl or agent.jurisdiction_code in specific:
                log.info("═══ Track 3 (International): %s (%s) ═══",
                         agent.jurisdiction_name, agent.jurisdiction_code)
                all_docs.extend(agent.fetch_all(lookback_days))

        # ── Track 4: Horizon Scanning ─────────────────────────────────────────
        run_horizon = run_all or "horizon" in sources_lower
        if run_horizon:
            log.info("═══ Track 4: Horizon Scanning ═══")
            try:
                from sources.horizon_agent import HorizonAgent
                h_counts = HorizonAgent().run(days_ahead=365)
                log.info("Horizon fetch complete: %s", h_counts)
            except Exception as e:
                log.warning("Horizon fetch failed: %s", e)

        run_enforcement = run_all or "enforcement" in sources_lower
        if run_enforcement:
            log.info("═══ Track 5: Enforcement & Litigation ═══")
            try:
                from sources.enforcement_agent import EnforcementAgent
                e_counts = EnforcementAgent().fetch_all(lookback_days=lookback_days)
                log.info("Enforcement fetch complete: %s", e_counts)
            except Exception as e:
                log.warning("Enforcement fetch failed: %s", e)

        # ── Persist & detect version changes ─────────────────────────────────
        new_count      = 0
        changed_ids    = []
        learner        = _get_learner()

        # Update source statistics for adaptive scheduling
        if learner and all_docs:
            learner.update_source_statistics(all_docs)

        # Flag anomalies before persisting
        anomalies_flagged = 0
        for doc in all_docs:
            if learner:
                anomaly = learner.detect_anomalies(doc)
                if anomaly:
                    doc["anomaly_flag"] = anomaly
                    anomalies_flagged  += 1
                    log.info("Anomaly detected in %s: %s", doc.get("id", ""), anomaly)

        for doc in all_docs:
            old_doc = get_document(doc["id"])
            changed = upsert_document(doc)
            if changed:
                new_count += 1
                if old_doc and old_doc.get("full_text"):
                    changed_ids.append((old_doc, doc))

        # Log fetch events for adaptive scheduling
        by_source = {}
        for doc in all_docs:
            s = doc.get("source", "unknown")
            by_source[s] = by_source.get(s, 0) + 1
        for source, total in by_source.items():
            new_for_source = sum(1 for d in all_docs if d.get("source") == source and upsert_document(d) is False)
            log_fetch_event(source, new_count=0, total_count=total)

        log.info("Fetch complete — %d new/updated documents%s",
                 new_count,
                 f", {anomalies_flagged} anomalies flagged" if anomalies_flagged else "")

        version_diffs = 0
        addenda_found = 0

        if run_diff:
            version_diffs, addenda_found = self._run_change_detection(
                changed_ids, all_docs
            )

        return {
            "fetched":        new_count,
            "version_diffs":  version_diffs,
            "addenda_found":  addenda_found,
        }

    # ── Change detection ──────────────────────────────────────────────────────

    def _run_change_detection(self,
                               changed_docs: List[tuple],
                               new_docs: List[Dict]) -> tuple:
        """
        Run both version-diff and addendum detection.
        Returns (version_diffs_count, addenda_count).
        """
        version_diffs = 0
        addenda_found = 0

        # 1. Version diffs — documents we already had that changed content
        for old_doc, new_doc in changed_docs:
            if diff_exists(old_doc["id"], new_doc["id"]):
                continue
            log.info("Running version diff for: %s", new_doc.get("title", "")[:60])
            try:
                result = self.diff_agent.compare_versions(old_doc, new_doc)
                if result:
                    diff_id = save_diff(result)
                    save_link(old_doc["id"], new_doc["id"],
                              link_type="version_of",
                              notes=f"Auto-detected version update. Diff ID: {diff_id}")
                    version_diffs += 1
                    log.info("Version diff saved (ID %d, severity: %s)",
                             diff_id, result.get("severity"))
            except Exception as e:
                log.error("Version diff failed for %s: %s", new_doc.get("id"), e)

        # 2. Addendum scan — look for new documents that amend existing ones
        if new_docs:
            existing_docs = get_all_documents(limit=300)
            try:
                links = self.diff_agent.scan_for_addenda(new_docs, existing_docs)
                for addendum_id, base_id in links:
                    if diff_exists(base_id, addendum_id):
                        continue
                    addendum_doc = next(
                        (d for d in new_docs if d["id"] == addendum_id), None
                    )
                    base_doc = get_document(base_id)
                    if not addendum_doc or not base_doc:
                        continue

                    base_summary = None
                    try:
                        from utils.db import get_summary
                        base_summary = get_summary(base_id)
                    except Exception:
                        pass

                    log.info("Analysing addendum: '%s' → '%s'",
                             addendum_doc.get("title", "")[:50],
                             base_doc.get("title", "")[:50])
                    try:
                        result = self.diff_agent.analyse_addendum(
                            base_doc, addendum_doc, base_summary
                        )
                        if result:
                            diff_id = save_diff(result)
                            save_link(base_id, addendum_id,
                                      link_type="amends",
                                      notes=f"Auto-detected addendum. Diff ID: {diff_id}")
                            addenda_found += 1
                            log.info("Addendum analysis saved (ID %d, severity: %s)",
                                     diff_id, result.get("severity"))
                    except Exception as e:
                        log.error("Addendum analysis failed for %s: %s", addendum_id, e)
            except Exception as e:
                log.error("Addendum scan failed: %s", e)

        return version_diffs, addenda_found

    # ── Manual diff ───────────────────────────────────────────────────────────

    def compare_two_documents(self, doc_id_a: str, doc_id_b: str) -> Optional[Dict]:
        """
        Manually compare two specific documents by their database IDs.
        Useful for CLI-initiated comparisons.
        """
        doc_a = get_document(doc_id_a)
        doc_b = get_document(doc_id_b)
        if not doc_a:
            log.error("Document not found: %s", doc_id_a)
            return None
        if not doc_b:
            log.error("Document not found: %s", doc_id_b)
            return None

        result = self.diff_agent.compare_versions(doc_a, doc_b)
        if result:
            diff_id = save_diff(result)
            save_link(doc_id_a, doc_id_b, link_type="version_of",
                      notes="Manually triggered comparison", created_by="user")
            log.info("Manual diff saved as ID %d", diff_id)
        return result

    def link_addendum_manually(self, base_id: str, addendum_id: str) -> Optional[Dict]:
        """
        Manually declare that addendum_id amends/clarifies base_id
        and run the full addendum analysis.
        """
        base_doc    = get_document(base_id)
        addendum_doc = get_document(addendum_id)
        if not base_doc or not addendum_doc:
            log.error("One or both documents not found: %s, %s", base_id, addendum_id)
            return None

        from utils.db import get_summary
        base_summary = get_summary(base_id)

        result = self.diff_agent.analyse_addendum(base_doc, addendum_doc, base_summary)
        if result:
            diff_id = save_diff(result)
            save_link(base_id, addendum_id, link_type="amends",
                      notes="Manually declared addendum relationship", created_by="user")
            log.info("Addendum analysis saved as diff ID %d", diff_id)
        return result

    # ── Summarize ─────────────────────────────────────────────────────────────

    def summarize(self, limit: int = 50, progress_callback=None,
                  force: bool = False) -> int:
        """
        Summarise pending (unsummarised) documents.

        force=True bypasses the learning pre-filter entirely — useful when
        the quality filter has incorrectly learned to skip documents from
        valid sources, or when the user explicitly wants every pending doc
        processed regardless of source quality scores.
        """
        pending = get_unsummarized_documents(limit=limit * 2)  # fetch more, then priority-sort
        if not pending:
            log.info("No pending documents to summarize")
            return 0

        # Convert to dicts for priority scoring
        doc_dicts = [
            {
                "id":            doc.id,
                "source":        doc.source,
                "jurisdiction":  doc.jurisdiction,
                "doc_type":      doc.doc_type,
                "title":         doc.title,
                "url":           doc.url,
                "published_date": str(doc.published_date) if doc.published_date else "",
                "fetched_at":    str(doc.fetched_at) if doc.fetched_at else "",
                "agency":        doc.agency or "",
                "status":        doc.status or "",
                "full_text":     doc.full_text or "",
            }
            for doc in pending
        ]

        # Sort by priority and honour the limit
        learner = _get_learner()
        if learner:
            doc_dicts = learner.sort_by_priority(doc_dicts)
        doc_dicts = doc_dicts[:limit]

        log.info("Summarizing %d documents with Claude (priority-sorted)…", len(doc_dicts))
        summaries = self.interpreter.analyse_batch(doc_dicts, progress_callback,
                                                    force=force)
        saved = 0
        for summary in summaries:
            upsert_summary(summary)
            saved += 1
            # Re-index this document's passages so it's immediately Q&A searchable
            try:
                from utils.rag import index_document_passages
                from utils.db import get_summary, get_document
                doc_id  = summary.get("document_id", "")
                full_doc = get_document(doc_id) or {}
                summ     = get_summary(doc_id) or {}
                combined = {**full_doc, **summ, "id": doc_id}
                index_document_passages(combined)
            except Exception:
                pass   # never block summarisation
        log.info("Summarization complete — %d summaries saved", saved)
        return saved

    # ── Full run ──────────────────────────────────────────────────────────────

    def run_full(self, lookback_days: int = LOOKBACK_DAYS,
                 sources: Optional[List[str]] = None,
                 summarize_limit: int = 50,
                 run_diff: bool = True,
                 domain: str = "both",
                 progress_callback=None) -> Dict[str, Any]:
        fetch_result = self.fetch(sources=sources, lookback_days=lookback_days,
                                   run_diff=run_diff, domain=domain)
        summarized   = self.summarize(limit=summarize_limit,
                                       progress_callback=progress_callback)

        # Refresh trend snapshots after every full run (no API calls)
        try:
            from agents.trend_agent import TrendAgent
            trend_counts = TrendAgent().run_snapshot()
            log.info("Trend snapshots refreshed: %s", trend_counts)
        except Exception as e:
            log.debug("Trend snapshot refresh skipped: %s", e)

        # Rebuild TF-IDF search index (no API calls, ~1s for typical corpus)
        try:
            from config.settings import SEARCH_AUTO_REBUILD
            if SEARCH_AUTO_REBUILD:
                from utils.search import rebuild_index
                n = rebuild_index()
                log.info("Search index rebuilt: %d documents", n)
        except Exception as e:
            log.debug("Search index rebuild skipped: %s", e)

        # Rebuild Q&A passage index (incorporates newly summarised docs)
        try:
            from utils.rag import build_passage_index
            qa_counts = build_passage_index()
            log.info("Q&A index rebuilt: %s", qa_counts)
        except Exception as e:
            log.debug("Q&A index rebuild skipped: %s", e)

        return {**fetch_result, "summarized": summarized, **get_stats()}

    # ── Introspection ─────────────────────────────────────────────────────────

    def list_active_agents(self) -> Dict[str, List[str]]:
        return {
            "federal":       ["FederalAgent (Federal Register, Regulations.gov, Congress.gov)"],
            "us_states":     [f"{a.state_code} — {a.state_name}" for a in self.state_agents],
            "international": [
                f"{a.jurisdiction_code} — {a.jurisdiction_name} ({a.region})"
                for a in self.international_agents
            ],
        }
