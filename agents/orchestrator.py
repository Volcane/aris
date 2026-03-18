"""
ARIS — Orchestrator

Coordinates the full pipeline:
  1. Load enabled state agents dynamically
  2. Run all source agents (Federal + States)
  3. Persist raw documents to SQLite
  4. Run interpretation agent on un-summarised documents
  5. Persist summaries
"""

from __future__ import annotations

import importlib
from typing import List, Dict, Any, Optional

from config.settings import LOOKBACK_DAYS
from config.states import ENABLED_STATES, STATE_MODULE_MAP
from sources.federal_agent import FederalAgent
from sources.state_agent_base import StateAgentBase
from agents.interpreter import InterpreterAgent
from utils.db import upsert_document, upsert_summary, get_unsummarized_documents, get_stats
from utils.cache import get_logger

log = get_logger("aris.orchestrator")


def _load_state_agents() -> List[StateAgentBase]:
    """Dynamically load enabled state agent classes."""
    agents = []
    for code in ENABLED_STATES:
        module_path = STATE_MODULE_MAP.get(code)
        if not module_path:
            log.warning("No module mapping for state %s — skipping", code)
            continue
        try:
            module = importlib.import_module(module_path)
            # Find a subclass of StateAgentBase in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type)
                        and issubclass(attr, StateAgentBase)
                        and attr is not StateAgentBase):
                    agents.append(attr())
                    log.info("Loaded state agent: %s", attr.__name__)
                    break
        except ImportError as e:
            log.error("Could not load state agent for %s (%s): %s", code, module_path, e)
    return agents


class Orchestrator:
    """Main pipeline controller."""

    def __init__(self):
        self.federal_agent  = FederalAgent()
        self.state_agents   = _load_state_agents()
        self._interpreter   = None  # lazy-load so we don't fail if key missing

    @property
    def interpreter(self) -> InterpreterAgent:
        if self._interpreter is None:
            self._interpreter = InterpreterAgent()
        return self._interpreter

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def fetch(self, sources: Optional[List[str]] = None,
              lookback_days: int = LOOKBACK_DAYS) -> int:
        """
        Fetch documents from all enabled sources.
        `sources` can be "federal", "state", or a specific state code.
        Returns count of new/updated documents saved.
        """
        docs_to_process: List[Dict[str, Any]] = []

        run_federal = not sources or "federal" in sources
        run_state   = not sources or "state" in sources or any(
            s.upper() in [a.state_code for a in self.state_agents] for s in (sources or [])
        )

        if run_federal:
            log.info("═══ Fetching Federal sources ═══")
            fed_docs = self.federal_agent.fetch_all(lookback_days)
            docs_to_process.extend(fed_docs)

        if run_state:
            for agent in self.state_agents:
                if sources and agent.state_code not in [s.upper() for s in sources]:
                    continue
                log.info("═══ Fetching %s ═══", agent.state_name)
                state_docs = agent.fetch_all(lookback_days)
                docs_to_process.extend(state_docs)

        # Persist to DB
        new_count = 0
        for doc in docs_to_process:
            if upsert_document(doc):
                new_count += 1

        log.info("Fetch complete — %d new/updated documents saved", new_count)
        return new_count

    # ── Summarize ─────────────────────────────────────────────────────────────

    def summarize(self, limit: int = 50, progress_callback=None) -> int:
        """
        Run the interpreter on all un-summarised documents in the DB.
        Returns count of summaries saved.
        """
        pending = get_unsummarized_documents(limit=limit)
        if not pending:
            log.info("No pending documents to summarize")
            return 0

        log.info("Summarizing %d documents…", len(pending))

        # Convert ORM objects to plain dicts
        doc_dicts = []
        for doc in pending:
            doc_dicts.append({
                "id":            doc.id,
                "source":        doc.source,
                "jurisdiction":  doc.jurisdiction,
                "doc_type":      doc.doc_type,
                "title":         doc.title,
                "url":           doc.url,
                "published_date": str(doc.published_date) if doc.published_date else "",
                "agency":        doc.agency or "",
                "status":        doc.status or "",
                "full_text":     doc.full_text or "",
            })

        summaries = self.interpreter.analyse_batch(doc_dicts, progress_callback)

        saved = 0
        for summary in summaries:
            upsert_summary(summary)
            saved += 1

        log.info("Summarization complete — %d summaries saved", saved)
        return saved

    # ── Full run ──────────────────────────────────────────────────────────────

    def run_full(self, lookback_days: int = LOOKBACK_DAYS,
                 summarize_limit: int = 50,
                 progress_callback=None) -> Dict[str, int]:
        """Fetch + summarize in one call. Returns counts."""
        fetched    = self.fetch(lookback_days=lookback_days)
        summarized = self.summarize(limit=summarize_limit,
                                    progress_callback=progress_callback)
        stats      = get_stats()
        return {
            "fetched":    fetched,
            "summarized": summarized,
            **stats,
        }
