"""
ARIS — Orchestrator (updated)

Coordinates the full pipeline across three independent tracks:
  1. US Federal     — FederalAgent (Federal Register, Regulations.gov, Congress.gov)
  2. US States      — StateAgentBase subclasses (PA, etc.)
  3. International  — InternationalAgentBase subclasses (EU, GB, CA, JP, etc.)

Each track can be run independently or together.
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
from utils.db import upsert_document, upsert_summary, get_unsummarized_documents, get_stats
from utils.cache import get_logger

log = get_logger("aris.orchestrator")


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
            log.warning("No module mapping for international jurisdiction %s — skipping", code)
            continue
        try:
            module = importlib.import_module(module_path)
            target_class_name = INTERNATIONAL_CLASS_MAP.get(code)
            found = False
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
                log.warning("No matching agent class found in %s for %s", module_path, code)
        except ImportError as e:
            log.error("Could not load international agent for %s: %s", code, e)
    return agents


class Orchestrator:
    """
    Main pipeline controller — three independent fetch tracks.

    fetch(sources=["federal"])         → US Federal only
    fetch(sources=["states"])          → All enabled US states
    fetch(sources=["international"])   → All enabled international
    fetch(sources=["EU", "GB"])        → Specific jurisdictions
    fetch()                            → Everything
    """

    def __init__(self):
        self.federal_agent        = FederalAgent()
        self.state_agents         = _load_state_agents()
        self.international_agents = _load_international_agents()
        self._interpreter         = None

    @property
    def interpreter(self) -> InterpreterAgent:
        if self._interpreter is None:
            self._interpreter = InterpreterAgent()
        return self._interpreter

    def fetch(self, sources: Optional[List[str]] = None,
              lookback_days: int = LOOKBACK_DAYS) -> int:
        docs: List[Dict[str, Any]] = []
        sources_lower = [s.lower() for s in sources] if sources else []
        run_all     = not sources
        run_federal = run_all or "federal" in sources_lower
        run_states  = run_all or "states"  in sources_lower
        run_intl    = run_all or "international" in sources_lower
        specific    = {s.upper() for s in (sources or [])} - {
            "FEDERAL", "STATES", "INTERNATIONAL"
        }

        if run_federal:
            log.info("═══ Track 1: US Federal ═══")
            docs.extend(self.federal_agent.fetch_all(lookback_days))

        for agent in self.state_agents:
            if run_states or agent.state_code in specific:
                log.info("═══ Track 2 (State): %s ═══", agent.state_name)
                docs.extend(agent.fetch_all(lookback_days))

        for agent in self.international_agents:
            if run_intl or agent.jurisdiction_code in specific:
                log.info("═══ Track 3 (International): %s (%s) ═══",
                         agent.jurisdiction_name, agent.jurisdiction_code)
                docs.extend(agent.fetch_all(lookback_days))

        new_count = sum(1 for doc in docs if upsert_document(doc))
        log.info("Fetch complete — %d new/updated documents", new_count)
        return new_count

    def summarize(self, limit: int = 50, progress_callback=None) -> int:
        pending = get_unsummarized_documents(limit=limit)
        if not pending:
            log.info("No pending documents to summarize")
            return 0
        log.info("Summarizing %d documents with Claude…", len(pending))
        doc_dicts = [
            {
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
            }
            for doc in pending
        ]
        summaries = self.interpreter.analyse_batch(doc_dicts, progress_callback)
        saved = 0
        for summary in summaries:
            upsert_summary(summary)
            saved += 1
        log.info("Summarization complete — %d summaries saved", saved)
        return saved

    def run_full(self, lookback_days: int = LOOKBACK_DAYS,
                 sources: Optional[List[str]] = None,
                 summarize_limit: int = 50,
                 progress_callback=None) -> Dict[str, int]:
        fetched    = self.fetch(sources=sources, lookback_days=lookback_days)
        summarized = self.summarize(limit=summarize_limit,
                                    progress_callback=progress_callback)
        return {"fetched": fetched, "summarized": summarized, **get_stats()}

    def list_active_agents(self) -> Dict[str, List[str]]:
        return {
            "federal":       ["FederalAgent (Federal Register, Regulations.gov, Congress.gov)"],
            "us_states":     [f"{a.state_code} — {a.state_name}" for a in self.state_agents],
            "international": [
                f"{a.jurisdiction_code} — {a.jurisdiction_name} ({a.region})"
                for a in self.international_agents
            ],
        }
