# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) [YEAR] [YOUR NAME]
# ARIS — Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
"""
ARIS — FastAPI Server

Runs the REST API that powers the browser UI.
All endpoints wrap the existing Python agents and database layer.

Start with:  python server.py
Then open:   http://localhost:8000

The React frontend is served as static files from ui/dist/
API endpoints are all prefixed with /api/
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── FastAPI imports ───────────────────────────────────────────────────────────
try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, UploadFile, File, Form
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError:
    print("FastAPI not installed. Run: pip install fastapi uvicorn")
    sys.exit(1)

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import ANTHROPIC_API_KEY, LEGISCAN_KEY, REGULATIONS_GOV_KEY, CONGRESS_GOV_KEY
from config.jurisdictions import ENABLED_US_STATES, ENABLED_INTERNATIONAL
from utils.db import (
    get_stats, get_recent_summaries, get_document, get_all_documents,
    get_diffs_for_document, get_recent_diffs, get_unreviewed_diffs,
    mark_diff_reviewed, get_links_for_document, save_link,
    get_summary, get_unsummarized_documents,
)
from utils.cache import get_logger

log = get_logger("aris.server")

# ── App setup ─────────────────────────────────────────────────────────────────

# ── Startup: index baselines into RAG if not already done ─────────────────────

from contextlib import asynccontextmanager
import threading

def _startup_index_baselines():
    """
    Index baseline passages into the Q&A RAG store on server startup.
    Runs in a background thread so it never blocks the server from starting.
    Only indexes if baselines are not already present (idempotent).
    """
    try:
        from utils.db import get_session
        import sqlite3 as _sq
        from config.settings import DB_PATH
        conn = _sq.connect(DB_PATH)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM qa_passages WHERE source_type = 'baseline'"
            ).fetchone()[0]
        except Exception:
            count = 0
        finally:
            conn.close()

        if count > 0:
            log.debug("Q&A baseline passages already indexed (%d passages) — skipping", count)
            return

        log.info("Q&A index: indexing baseline passages on startup…")
        from utils.rag import build_passage_index
        result = build_passage_index(force=False)
        log.info("Q&A index: startup indexing complete — %s", result)
    except Exception as e:
        log.warning("Q&A startup indexing skipped: %s", e)


@asynccontextmanager
async def lifespan(application):
    # Index baselines in background — non-blocking
    t = threading.Thread(target=_startup_index_baselines, daemon=True)
    t.start()
    # Start scheduled monitoring thread
    _start_schedule_thread()
    yield
    # (shutdown cleanup could go here if needed)


app = FastAPI(
    title="ARIS — Automated Regulatory Intelligence System",
    description="REST API for the ARIS dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Scheduled monitoring ─────────────────────────────────────────────────────

import time as _time

_schedule_thread = None
_schedule_stop   = threading.Event()


def _schedule_loop():
    """Background thread: checks schedule config and fires runs at the right time."""
    import math
    log.info("Schedule monitor started")
    while not _schedule_stop.is_set():
        try:
            from utils.db import get_schedule_config, update_schedule_last_run
            cfg = get_schedule_config()
            if cfg["enabled"] and cfg["next_run"] and not _job_state["running"]:
                from datetime import datetime as _dt
                next_run = _dt.fromisoformat(cfg["next_run"])
                if _dt.utcnow() >= next_run:
                    log.info("Scheduled run triggered")
                    update_schedule_last_run()
                    try:
                        from agents.orchestrator import Orchestrator
                        orch = Orchestrator()
                        _job_state["running"] = True
                        _job_state["log"]     = []
                        _log("Scheduled run started")
                        fetch_result = orch.fetch(
                            lookback_days=cfg["lookback_days"],
                            domain=cfg["domain"],
                        )
                        _log(f"Fetched {fetch_result['fetched']} documents")
                        sum_result = orch.summarize(limit=100)
                        _log(f"Summarized {sum_result.get('saved', sum_result) if isinstance(sum_result, dict) else sum_result} documents")
                        _job_state["last_result"] = {**fetch_result, "summarized": sum_result.get("saved", 0) if isinstance(sum_result, dict) else sum_result, **get_stats()}
                        _log("Scheduled run complete ✓")
                        # Trigger notifications if configured
                        try:
                            from utils.notifier import send_digest_if_warranted
                            send_digest_if_warranted(_job_state["last_result"])
                        except Exception as ne:
                            log.debug("Notification skipped: %s", ne)
                    except Exception as e:
                        _log(f"ERROR in scheduled run: {e}")
                        log.error("Scheduled run error: %s", e)
                    finally:
                        _job_state["running"]  = False
                        _job_state["last_run"] = __import__("datetime").datetime.utcnow().isoformat()
        except Exception as e:
            log.debug("Schedule loop error: %s", e)
        _schedule_stop.wait(60)   # check every 60 seconds


def _start_schedule_thread():
    global _schedule_thread
    if _schedule_thread and _schedule_thread.is_alive():
        return
    _schedule_stop.clear()
    _schedule_thread = threading.Thread(target=_schedule_loop, daemon=True, name="aris-scheduler")
    _schedule_thread.start()


# ── Background job state ──────────────────────────────────────────────────────

_job_state: Dict[str, Any] = {
    "running":   False,
    "log":       [],
    "last_run":  None,
    "last_result": None,
}


def _log(msg: str):
    ts  = datetime.utcnow().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    _job_state["log"].append(line)
    log.info(msg)
    if len(_job_state["log"]) > 500:
        _job_state["log"] = _job_state["log"][-500:]


# ── Pydantic request models ───────────────────────────────────────────────────

class RunAgentsRequest(BaseModel):
    sources:         List[str] = []          # empty = all
    lookback_days:   int       = 30
    summarize:       bool      = True
    run_diff:        bool      = True
    limit:           int       = 50
    force_summarize: bool      = False       # bypass learning pre-filter
    domain:          str       = "both"      # ai | privacy | both

class DiffRequest(BaseModel):
    doc_id_a: str
    doc_id_b: str

class LinkRequest(BaseModel):
    base_id:     str
    addendum_id: str
    link_type:   str = "amends"
    notes:       Optional[str] = None

class WatchlistItem(BaseModel):
    name:       str
    keywords:   List[str]
    jurisdictions: List[str] = []
    notify_on:  List[str] = ["new_doc", "change"]  # "new_doc" | "change" | "checklist"

class ChecklistRequest(BaseModel):
    document_id: str
    company_context: Optional[str] = None   # e.g. "healthcare AI startup"


# ── Watchlist (stored as JSON file alongside DB) ──────────────────────────────

WATCHLIST_PATH = Path("output/watchlist.json")


def _load_watchlist() -> List[Dict]:
    if not WATCHLIST_PATH.exists():
        return []
    return json.loads(WATCHLIST_PATH.read_text())


def _save_watchlist(items: List[Dict]):
    WATCHLIST_PATH.parent.mkdir(exist_ok=True)
    WATCHLIST_PATH.write_text(json.dumps(items, indent=2))


def _match_watchlist(doc: Dict, watch_items: List[Dict]) -> List[str]:
    """Return names of watchlist items that match this document."""
    matched = []
    title   = (doc.get("title") or "").lower()
    text    = (doc.get("full_text") or "").lower()
    jur     = doc.get("jurisdiction", "")
    for item in watch_items:
        if item.get("jurisdictions") and jur not in item["jurisdictions"]:
            continue
        for kw in item.get("keywords", []):
            if kw.lower() in title or kw.lower() in text:
                matched.append(item["name"])
                break
    return matched


# ── API Routes ────────────────────────────────────────────────────────────────

# ·· System status ·············································

@app.get("/api/notifications/config")
def get_notification_config():
    """Return current notification configuration (keys masked)."""
    try:
        from utils.notifier import get_config
        return get_config()
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/notifications/test")
def test_notifications():
    """Send a test notification to all configured channels."""
    try:
        from utils.notifier import send_test_notification
        results = send_test_notification()
        return {"results": results, "any_sent": any(results.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/schedule")
def get_schedule():
    """Return the current schedule configuration."""
    from utils.db import get_schedule_config
    return get_schedule_config()


@app.post("/api/schedule")
def save_schedule(req: dict):
    """Save schedule configuration. Restarts the scheduler thread."""
    from utils.db import save_schedule_config
    result = save_schedule_config(
        enabled       = bool(req.get("enabled", False)),
        interval_hours= int(req.get("interval_hours", 24)),
        domain        = str(req.get("domain", "both")),
        lookback_days = int(req.get("lookback_days", 7)),
    )
    _start_schedule_thread()
    return result


@app.post("/api/schedule/trigger")
def trigger_schedule_now(background_tasks: BackgroundTasks):
    """Manually trigger a scheduled run now."""
    if _job_state["running"]:
        raise HTTPException(status_code=409, detail="A job is already running")
    from utils.db import get_schedule_config
    cfg = get_schedule_config()

    def _run():
        _job_state["running"] = True
        _job_state["log"]     = []
        _log("Manual scheduled run started")
        try:
            from agents.orchestrator import Orchestrator
            orch = Orchestrator()
            fetch_result = orch.fetch(lookback_days=cfg.get("lookback_days", 7), domain=cfg.get("domain", "both"))
            _log(f"Fetched {fetch_result['fetched']} documents")
            sum_result = orch.summarize(limit=100)
            saved = sum_result.get("saved", sum_result) if isinstance(sum_result, dict) else sum_result
            _log(f"Summarized {saved} documents")
            _job_state["last_result"] = {**fetch_result, "summarized": saved, **get_stats()}
            _log("Scheduled run complete ✓")
        except Exception as e:
            _log(f"ERROR: {e}")
        finally:
            _job_state["running"]  = False
            _job_state["last_run"] = __import__("datetime").datetime.utcnow().isoformat()

    background_tasks.add_task(_run)
    return {"status": "started"}


@app.get("/api/status")
def get_status():
    """System health, API key status, and DB statistics."""
    from utils.llm import provider_info, is_configured
    stats = get_stats()
    llm   = provider_info()
    return {
        "stats": stats,
        "api_key_set": is_configured(),   # kept for Dashboard compat
        "llm": llm,
        "api_keys": {
            "anthropic":        bool(ANTHROPIC_API_KEY),
            "regulations_gov":  bool(REGULATIONS_GOV_KEY),
            "congress_gov":     bool(CONGRESS_GOV_KEY),
            "legiscan":         bool(LEGISCAN_KEY),
        },
        "enabled_states":        ENABLED_US_STATES,
        "enabled_international": ENABLED_INTERNATIONAL,
        "job": {
            "running":     _job_state["running"],
            "last_run":    _job_state["last_run"],
            "last_result": _job_state["last_result"],
        },
    }


# ·· Documents ·················································

@app.get("/api/documents")
def list_documents(
    jurisdiction: Optional[str] = None,
    urgency:      Optional[str] = None,
    doc_type:     Optional[str] = None,
    domain:       Optional[str] = None,
    days:         int           = 365,
    search:       Optional[str] = None,
    page:         int           = 1,
    page_size:    int           = 50,
):
    """Paginated document list with filters. Excludes not_relevant (archived) documents."""
    from utils.db import get_document_review_statuses
    summaries = get_recent_summaries(days=days, jurisdiction=jurisdiction, domain=domain)

    if urgency:
        summaries = [s for s in summaries if s.get("urgency") == urgency]
    if doc_type:
        summaries = [s for s in summaries if s.get("doc_type") == doc_type]
    if search:
        q = search.lower()
        summaries = [
            s for s in summaries
            if q in (s.get("title") or "").lower()
            or q in (s.get("plain_english") or "").lower()
            or q in (s.get("agency") or "").lower()
        ]

    # Look up review status for all docs in this page
    doc_ids = [s["id"] for s in summaries]
    statuses = get_document_review_statuses(doc_ids)

    # Exclude not_relevant (archived) from the main list
    summaries = [s for s in summaries if statuses.get(s["id"]) != "not_relevant"]

    # Attach review_status to each item
    for s in summaries:
        s["review_status"] = statuses.get(s["id"])  # relevant | partially_relevant | None

    total  = len(summaries)
    start  = (page - 1) * page_size
    end    = start + page_size
    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "items":     summaries[start:end],
    }


@app.get("/api/documents/archived")
def list_archived_documents(
    jurisdiction: Optional[str] = None,
    days:         int           = 3650,
    search:       Optional[str] = None,
    page:         int           = 1,
    page_size:    int           = 30,
):
    """Documents marked Not Relevant — removed from main list, browsable here."""
    from utils.db import get_archived_documents
    return get_archived_documents(
        days         = days,
        jurisdiction = jurisdiction,
        search       = search,
        page         = page,
        page_size    = page_size,
    )


@app.get("/api/documents/{doc_id}")
def get_doc(doc_id: str):
    """Full document record with summary, diffs, and links."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    summary  = get_summary(doc_id)
    diffs    = get_diffs_for_document(doc_id)
    links    = get_links_for_document(doc_id)
    watchlist = _load_watchlist()
    matched  = _match_watchlist(doc, watchlist)
    return {
        **doc,
        "summary":         summary,
        "diffs":           diffs,
        "links":           links,
        "watchlist_match": matched,
    }


@app.get("/api/documents/{doc_id}/history")
def get_doc_history(doc_id: str):
    """Change history for a specific document."""
    diffs = get_diffs_for_document(doc_id)
    links = get_links_for_document(doc_id)
    return {"diffs": diffs, "links": links}


# ·· Diffs / Changes ···········································

@app.get("/api/changes")
def list_changes(
    days:       int           = 30,
    severity:   Optional[str] = None,
    diff_type:  Optional[str] = None,
    domain:     Optional[str] = None,
    unreviewed: bool          = False,
):
    """All detected regulatory changes. domain filter: ai | privacy"""
    if unreviewed:
        diffs = get_unreviewed_diffs(limit=200)
    else:
        diffs = get_recent_diffs(days=days, severity=severity, diff_type=diff_type)
    # Domain filter: join against document domain if requested
    if domain:
        from utils.db import get_document
        filtered = []
        for d in diffs:
            doc_id = d.get("doc_id_new") or d.get("doc_id_base") or ""
            if doc_id:
                doc = get_document(doc_id)
                if doc and doc.get("domain", "ai") == domain:
                    filtered.append(d)
            else:
                filtered.append(d)
        return filtered
    return diffs


@app.post("/api/changes/{diff_id}/review")
def review_change(diff_id: int):
    """Mark a diff as reviewed."""
    mark_diff_reviewed(diff_id)
    return {"ok": True, "diff_id": diff_id}


@app.post("/api/diff")
def run_manual_diff(req: DiffRequest, background_tasks: BackgroundTasks):
    """Manually trigger a diff between two documents."""
    if _job_state["running"]:
        raise HTTPException(status_code=409, detail="Another job is already running")

    def _run():
        _job_state["running"] = True
        _log(f"Starting manual diff: {req.doc_id_a} → {req.doc_id_b}")
        try:
            from agents.orchestrator import Orchestrator
            orch   = Orchestrator()
            result = orch.compare_two_documents(req.doc_id_a, req.doc_id_b)
            _job_state["last_result"] = result
            _log("Diff complete" if result else "No substantive difference found")
        except Exception as e:
            _log(f"ERROR: {e}")
        finally:
            _job_state["running"]  = False
            _job_state["last_run"] = datetime.utcnow().isoformat()

    background_tasks.add_task(_run)
    return {"status": "started"}


@app.post("/api/link")
def create_link(req: LinkRequest, background_tasks: BackgroundTasks):
    """Manually declare an addendum/amendment relationship and run analysis."""
    if _job_state["running"]:
        raise HTTPException(status_code=409, detail="Another job is already running")

    def _run():
        _job_state["running"] = True
        _log(f"Linking: {req.addendum_id} → base {req.base_id}")
        try:
            from agents.orchestrator import Orchestrator
            orch   = Orchestrator()
            result = orch.link_addendum_manually(req.base_id, req.addendum_id)
            save_link(req.base_id, req.addendum_id, req.link_type, req.notes, "user")
            _job_state["last_result"] = result
            _log("Addendum analysis complete")
        except Exception as e:
            _log(f"ERROR: {e}")
        finally:
            _job_state["running"]  = False
            _job_state["last_run"] = datetime.utcnow().isoformat()

    background_tasks.add_task(_run)
    return {"status": "started"}


# ·· Agent execution ···········································

@app.post("/api/run")
def run_agents(req: RunAgentsRequest, background_tasks: BackgroundTasks):
    """
    Trigger a full or partial pipeline run in the background.
    Poll /api/run/status and /api/run/log to monitor progress.
    """
    if _job_state["running"]:
        raise HTTPException(status_code=409, detail="A job is already running")

    def _run():
        _job_state["running"] = True
        _job_state["log"]     = []
        _log("Pipeline started")
        try:
            from agents.orchestrator import Orchestrator
            orch    = Orchestrator()
            sources = req.sources if req.sources else None

            _log(f"Fetching: {sources or 'all sources'} (lookback {req.lookback_days}d)")
            fetch_result = orch.fetch(
                sources=sources,
                lookback_days=req.lookback_days,
                run_diff=req.run_diff,
                domain=req.domain,
            )
            _log(f"Fetched {fetch_result['fetched']} new/updated documents")
            if req.run_diff:
                _log(f"Version diffs: {fetch_result.get('version_diffs', 0)}")
                _log(f"Addenda found: {fetch_result.get('addenda_found', 0)}")

            sum_result = {"saved": 0, "skipped": 0, "first_run": False}
            if req.summarize:
                _log(f"Summarizing up to {req.limit} documents with Claude…")
                if req.force_summarize:
                    _log("  (force mode: learning pre-filter bypassed)")

                def _cb(current, total):
                    _log(f"  Summarizing {current}/{total}…")

                sum_result = orch.summarize(limit=req.limit, progress_callback=_cb,
                                            force=req.force_summarize)
                saved   = sum_result["saved"]
                skipped = sum_result["skipped"]
                if sum_result.get("first_run"):
                    _log(f"  First run — Force Summarize was auto-enabled")
                _log(f"Summarized {saved} documents" +
                     (f", {skipped} skipped by pre-filter" if skipped else ""))

            # Urgency breakdown for the result card
            stats_now = get_stats()
            from utils.db import get_session
            from utils.db import Summary as _Summary, Document as _Document
            try:
                with get_session() as _sess:
                    from sqlalchemy import func as _func
                    urgency_rows = _sess.query(
                        _Summary.urgency, _func.count(_Summary.document_id)
                    ).group_by(_Summary.urgency).all()
                    urgency_dist = {u: n for u, n in urgency_rows if u and u != "Skipped"}
                    # Domain split for docs fetched this run
                    ai_fetched  = fetch_result.get("fetched_ai", 0)
                    priv_fetched = fetch_result.get("fetched_privacy", 0)
            except Exception:
                urgency_dist = {}
                ai_fetched = priv_fetched = 0

            _job_state["last_result"] = {
                **fetch_result,
                "summarized":      sum_result["saved"],
                "skipped":         sum_result["skipped"],
                "auto_archived":   sum_result.get("auto_archived", 0),
                "first_run":       sum_result.get("first_run", False),
                "urgency_dist":    urgency_dist,
                **stats_now,
            }
            _log("Pipeline complete ✓")
        except Exception as e:
            _log(f"ERROR: {e}")
            raise
        finally:
            _job_state["running"]  = False
            _job_state["last_run"] = datetime.utcnow().isoformat()

    background_tasks.add_task(_run)
    return {"status": "started"}


@app.get("/api/run/status")
def run_status():
    return {
        "running":     _job_state["running"],
        "last_run":    _job_state["last_run"],
        "last_result": _job_state["last_result"],
    }


@app.get("/api/run/log")
def run_log(since: int = 0):
    """Returns log lines since index `since`. Poll this while job is running."""
    lines = _job_state["log"]
    return {
        "lines": lines[since:],
        "total": len(lines),
        "running": _job_state["running"],
    }


# ·· Checklist generator ·······································

@app.post("/api/checklist")
def generate_checklist(req: ChecklistRequest):
    """
    Use Claude to generate a structured compliance checklist for a document.
    Returns markdown checklist text.
    """
    doc     = get_document(req.document_id)
    summary = get_summary(req.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from utils.llm import call_llm, is_configured, LLMError
    if not is_configured():
        from utils.llm import _provider
        raise HTTPException(status_code=503,
                            detail=f"LLM provider '{_provider()}' is not configured")

    context = req.company_context or "a company that develops or deploys AI systems"
    reqs    = (summary or {}).get("requirements") or []
    actions = (summary or {}).get("action_items") or []
    plain   = (summary or {}).get("plain_english") or ""
    text    = (doc.get("full_text") or "")[:3000]

    prompt = f"""Generate a detailed, actionable compliance checklist for {context}
based on the following regulation.

REGULATION: {doc.get('title')}
JURISDICTION: {doc.get('jurisdiction')}
STATUS: {doc.get('status')}
SUMMARY: {plain}

MANDATORY REQUIREMENTS:
{chr(10).join(f'- {r}' for r in reqs)}

KNOWN ACTION ITEMS:
{chr(10).join(f'- {a}' for a in actions)}

DOCUMENT TEXT EXCERPT:
{text}

---

Produce a compliance checklist in Markdown format organised into these sections:
1. **Immediate Actions** (within 30 days)
2. **Near-Term Actions** (31–90 days)
3. **Ongoing Obligations** (recurring compliance tasks)
4. **Documentation Required** (what to document and keep on file)
5. **Team Responsibilities** (who owns each obligation — Legal, Engineering, Product, HR, etc.)

Each item should be a checkbox: `- [ ] Action description`
Be specific and actionable. Include deadlines where known.
Do not include generic advice — every item should be specific to this regulation."""

    try:
        checklist_md = call_llm(prompt=prompt, max_tokens=2048)
    except LLMError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {
        "document_id": req.document_id,
        "title":       doc.get("title"),
        "checklist":   checklist_md,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ·· Search ····················································

@app.get("/api/search")
def search_docs(
    q:            str,
    limit:        int           = 30,
    jurisdiction: Optional[str] = None,
    urgency:      Optional[str] = None,
    days:         int           = 3650,
):
    """
    Ranked full-text search over documents using FTS5 + TF-IDF + optional embeddings.
    Returns documents sorted by relevance score.
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="q (query) is required")
    try:
        from utils.search import search_documents, get_engine
        import sqlite3 as _sqlite3

        # Connect to SQLite for FTS5 layer
        conn  = _sqlite3.connect(DB_PATH)
        hits  = search_documents(q.strip(), top_k=limit * 2, conn=conn)
        conn.close()

        # Join search hits with document metadata from the main DB
        hit_ids = {h["doc_id"]: h for h in hits}
        if not hit_ids:
            return {"query": q, "total": 0, "items": [], "expanded_query": q}

        from utils.search import expand_query
        summaries = get_recent_summaries(days=days, jurisdiction=jurisdiction)

        # Build result: ranked by search score, enriched with document metadata
        results = []
        for doc in summaries:
            did = doc.get("id")
            if did not in hit_ids:
                continue
            if urgency and doc.get("urgency") != urgency:
                continue
            results.append({
                **doc,
                "search_score": round(hit_ids[did]["score"], 3),
                "search_layers": hit_ids[did].get("sources", []),
            })

        # Sort by search score (already ranked), then fall through to docs
        # that matched via FTS but weren't in summaries
        results.sort(key=lambda x: -x["search_score"])

        return {
            "query":          q,
            "expanded_query": expand_query(q),
            "total":          len(results),
            "items":          results[:limit],
            "embedding_active": get_engine()._embedding.available,
        }
    except Exception as e:
        log.error("Search error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search/rebuild")
def rebuild_search_index(background_tasks: BackgroundTasks):
    """Rebuild the TF-IDF and FTS5 search indices (runs in background)."""
    def _run():
        import sqlite3 as _sqlite3
        from utils.search import rebuild_index, rebuild_fts_index, get_engine
        try:
            docs = get_recent_summaries(days=3650)
            n    = rebuild_index(docs)
            # Also rebuild FTS5
            conn = _sqlite3.connect(DB_PATH)
            rebuild_fts_index(conn, docs)
            conn.close()
            log.info("Search index rebuild complete: %d documents", n)
        except Exception as e:
            log.error("Search index rebuild error: %s", e)
    background_tasks.add_task(_run)
    return {"status": "rebuilding"}


@app.get("/api/search/status")
def search_status():
    """Return search engine status: which layers are active."""
    try:
        from utils.search import get_engine, AI_TERMS_EXPANDED
        engine = get_engine()
        return {
            "keyword_terms":      len(AI_TERMS_EXPANDED),
            "tfidf_built":        engine._tfidf.matrix is not None,
            "tfidf_doc_count":    len(engine._tfidf.doc_ids),
            "tfidf_vocab_size":   len(engine._tfidf.vocab),
            "fts5_available":     True,
            "embedding_available":engine._embedding.available,
            "embedding_model":    engine._embedding.MODEL_NAME if engine._embedding.available else None,
        }
    except Exception as e:
        return {"error": str(e)}


# ·· Regulatory Horizon ·············································

@app.get("/api/horizon")
def get_horizon(
    days_ahead:   int            = 365,
    jurisdiction: Optional[str] = None,
    stage:        Optional[str] = None,
    domain:       Optional[str] = None,
    limit:        int            = 200,
):
    from utils.db import get_horizon_items
    return get_horizon_items(
        days_ahead   = days_ahead,
        jurisdiction = jurisdiction,
        stage        = stage,
        domain       = domain,
        limit        = limit,
    )


@app.get("/api/horizon/stats")
def horizon_stats():
    from utils.db import get_horizon_stats
    return get_horizon_stats()


@app.post("/api/horizon/fetch")
def fetch_horizon(background_tasks: BackgroundTasks):
    """Trigger a horizon fetch (background)."""
    if _job_state["running"]:
        raise HTTPException(status_code=409, detail="Another job is already running")

    def _run():
        _job_state["running"] = True
        _log("Horizon fetch started")
        try:
            from sources.horizon_agent import HorizonAgent
            counts = HorizonAgent().run(days_ahead=365)
            total  = sum(counts.values())
            _log(f"Horizon fetch complete: {total} new items ({counts})")
            _job_state["last_result"] = {"horizon_new": total, "by_source": counts}
        except Exception as e:
            _log(f"ERROR: {e}")
        finally:
            _job_state["running"]  = False
            _job_state["last_run"] = datetime.utcnow().isoformat()

    background_tasks.add_task(_run)
    return {"status": "started"}


@app.post("/api/horizon/{item_id}/dismiss")
def dismiss_horizon(item_id: int):
    from utils.db import dismiss_horizon_item
    dismiss_horizon_item(item_id)
    return {"ok": True}


# ·· Regulatory Trends ·············································

@app.get("/api/trends")
def get_trends():
    """Return all trend data: velocity, heatmap, and alerts."""
    try:
        from agents.trend_agent import TrendAgent
        return TrendAgent().get_summary()
    except Exception as e:
        log.error("Trends error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trends/velocity")
def get_velocity():
    from agents.trend_agent import TrendAgent
    return TrendAgent().get_velocity()


@app.get("/api/trends/heatmap")
def get_heatmap():
    from agents.trend_agent import TrendAgent
    return TrendAgent().get_heatmap()


@app.get("/api/trends/alerts")
def get_alerts():
    from agents.trend_agent import TrendAgent
    return TrendAgent().get_alerts()


@app.post("/api/trends/refresh")
def refresh_trends(background_tasks: BackgroundTasks):
    """Trigger a trend snapshot recompute (runs in background)."""
    def _run():
        from agents.trend_agent import TrendAgent
        TrendAgent().run_snapshot()
    background_tasks.add_task(_run)
    return {"status": "refreshing"}


# ·· Regulatory Baselines ·····································

@app.get("/api/baselines/status")
def baseline_status():
    """Diagnostic endpoint — shows where the server is looking for baseline files."""
    from pathlib import Path
    try:
        from agents.baseline_agent import BaselineAgent, _BASELINES_DIR
        exists    = _BASELINES_DIR.exists()
        json_files= list(_BASELINES_DIR.glob("*.json")) if exists else []
        index_ok  = (_BASELINES_DIR / "index.json").exists()
        loaded    = 0
        if exists and index_ok:
            try:
                BaselineAgent._cache = None
                loaded = len(BaselineAgent().get_all())
            except Exception:
                pass
        return {
            "baselines_dir":   str(_BASELINES_DIR),
            "dir_exists":      exists,
            "index_exists":    index_ok,
            "json_file_count": len(json_files),
            "baselines_loaded":loaded,
            "json_files":      sorted(f.name for f in json_files),
        }
    except Exception as e:
        return {"error": str(e), "baselines_dir": None, "baselines_loaded": 0}


@app.get("/api/baselines")
def list_baselines(domain: Optional[str] = None):
    """Return summary metadata for all loaded baselines. Optional domain filter: ai | privacy"""
    from agents.baseline_agent import BaselineAgent
    return BaselineAgent().get_all(domain=domain)


@app.get("/api/baselines/coverage")
def baseline_coverage():
    """Return coverage summary — jurisdictions, count, last reviewed date."""
    from agents.baseline_agent import BaselineAgent
    return BaselineAgent().get_coverage_summary()


@app.get("/api/baselines/jurisdiction/{jurisdiction}")
def baselines_for_jurisdiction(jurisdiction: str):
    """Return all baselines for a specific jurisdiction."""
    from agents.baseline_agent import BaselineAgent
    return BaselineAgent().get_for_jurisdiction(jurisdiction)


@app.get("/api/baselines/{baseline_id}")
def get_baseline(baseline_id: str):
    """Return the full baseline for a given ID."""
    from agents.baseline_agent import BaselineAgent
    b = BaselineAgent().get_by_id(baseline_id)
    if not b:
        raise HTTPException(status_code=404, detail=f"Baseline '{baseline_id}' not found")
    return b


# ·· Obligation Register ·······································

class RegisterRequest(BaseModel):
    jurisdictions: List[str]
    mode:          str  = "fast"   # fast | full
    days:          int  = 365
    force:         bool = False


@app.get("/api/register")
def get_register(
    jurisdictions: str = Query(..., description="Comma-separated jurisdiction codes"),
    mode:          str = "fast",
    days:          int = 365,
    force:         bool = False,
):
    """
    Get the consolidated obligation register for a set of jurisdictions.
    mode=fast returns structural consolidation from baselines (no API call).
    mode=full uses Claude for semantic deduplication (one API call, cached 24h).
    """
    jurs = [j.strip() for j in jurisdictions.split(",") if j.strip()]
    if not jurs:
        raise HTTPException(status_code=400, detail="jurisdictions required")

    try:
        from agents.consolidation_agent import ConsolidationAgent
        agent = ConsolidationAgent()
        if mode == "full":
            from utils.llm import is_configured as _is_cfg
            if not _is_cfg():
                raise HTTPException(status_code=503,
                                    detail="LLM provider not configured for full mode")
            register = agent.consolidate_full(jurs, days=days, force=force)
        else:
            register = agent.consolidate_fast(jurs, force=force)
        return {
            "jurisdictions": jurs,
            "mode":          mode,
            "count":         len(register),
            "items":         register,
        }
    except Exception as e:
        log.error("Register error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/register/refresh")
def refresh_register(req: RegisterRequest):
    """Force-refresh the register for given jurisdictions."""
    try:
        from agents.consolidation_agent import ConsolidationAgent
        agent = ConsolidationAgent()
        if req.mode == "full":
            register = agent.consolidate_full(req.jurisdictions, req.days,
                                               force=True)
        else:
            register = agent.consolidate_fast(req.jurisdictions, force=True)
        return {"count": len(register), "items": register}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/register/categories")
def register_categories():
    """Return the list of obligation categories."""
    from agents.consolidation_agent import CATEGORIES
    return CATEGORIES


# ·· Company Profiles & Gap Analysis ···························

class AISystemModel(BaseModel):
    name:               str
    description:        Optional[str] = None
    purpose:            Optional[str] = None
    data_inputs:        List[str]     = []
    affected_population:Optional[str] = None
    deployment_status:  str           = "production"
    autonomy_level:     str           = "human-in-loop"


class CurrentPracticesModel(BaseModel):
    has_ai_governance_policy:     Optional[bool] = None
    has_risk_assessments:         Optional[bool] = None
    has_human_oversight:          Optional[bool] = None
    has_incident_response:        Optional[bool] = None
    has_documentation:            Optional[bool] = None
    has_bias_testing:             Optional[bool] = None
    has_transparency_disclosures: Optional[bool] = None
    notes:                        Optional[str]  = None


class ProfileRequest(BaseModel):
    id:                      Optional[int]       = None
    name:                    str
    industry_sector:         Optional[str]       = None
    company_size:            Optional[str]       = None
    operating_jurisdictions: List[str]           = []
    ai_systems:              List[AISystemModel] = []
    current_practices:       Optional[CurrentPracticesModel] = None
    existing_certifications: List[str]           = []
    primary_concerns:        Optional[str]       = None
    recent_changes:          Optional[str]       = None


class GapAnalysisRequest(BaseModel):
    profile_id:    int
    jurisdictions: Optional[List[str]] = None
    days:          int                 = 365
    system_filter: Optional[List[str]] = None


class GapAnnotateRequest(BaseModel):
    notes: str


@app.get("/api/profiles")
def list_profiles_endpoint():
    from utils.db import list_profiles
    return list_profiles()


@app.get("/api/profiles/{profile_id}")
def get_profile_endpoint(profile_id: int):
    from utils.db import get_profile
    p = get_profile(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")
    return p


@app.post("/api/profiles")
def save_profile_endpoint(req: ProfileRequest):
    from utils.db import save_profile
    data = req.model_dump()
    if data.get("current_practices"):
        data["current_practices"] = data["current_practices"]
    pid = save_profile(data)
    from utils.db import get_profile
    return get_profile(pid)


@app.delete("/api/profiles/{profile_id}")
def delete_profile_endpoint(profile_id: int):
    from utils.db import delete_profile
    delete_profile(profile_id)
    return {"ok": True}


@app.get("/api/gap-analyses")
def list_analyses_endpoint(profile_id: Optional[int] = None, limit: int = 20):
    from utils.db import list_gap_analyses
    return list_gap_analyses(profile_id=profile_id, limit=limit)


@app.get("/api/gap-analyses/{analysis_id}")
def get_analysis_endpoint(analysis_id: int):
    from utils.db import get_gap_analysis
    result = get_gap_analysis(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result


@app.post("/api/gap-analyses")
def run_gap_analysis_endpoint(req: GapAnalysisRequest,
                               background_tasks: BackgroundTasks):
    """Trigger a gap analysis run (background job)."""
    from utils.llm import is_configured as _is_cfg
    if not _is_cfg():
        raise HTTPException(status_code=503, detail="LLM provider not configured")
    if _job_state["running"]:
        raise HTTPException(status_code=409, detail="Another job is already running")

    def _run():
        _job_state["running"] = True
        _job_state["log"]     = []
        _log(f"Gap analysis started for profile ID {req.profile_id}")
        try:
            from agents.gap_analysis_agent import GapAnalysisAgent
            agent  = GapAnalysisAgent()
            result = agent.run(
                profile_id    = req.profile_id,
                jurisdictions = req.jurisdictions or None,
                days          = req.days,
                system_filter = req.system_filter or None,
            )
            if result.get("error"):
                _log(f"Gap analysis error: {result['error']}")
            else:
                _log(f"Gap analysis complete: {result.get('gap_count', 0)} gaps found, "
                     f"posture score {result.get('posture_score')}/100")
            _job_state["last_result"] = {
                "analysis_id":   result.get("id"),
                "gap_count":     result.get("gap_count", 0),
                "critical_count":result.get("critical_count", 0),
                "posture_score": result.get("posture_score", 0),
            }
        except Exception as e:
            _log(f"ERROR: {e}")
            raise
        finally:
            _job_state["running"]  = False
            _job_state["last_run"] = datetime.utcnow().isoformat()

    background_tasks.add_task(_run)
    return {"status": "started", "profile_id": req.profile_id}


@app.post("/api/gap-analyses/{analysis_id}/star")
def star_analysis_endpoint(analysis_id: int, starred: bool = True):
    from utils.db import star_gap_analysis
    star_gap_analysis(analysis_id, starred)
    return {"ok": True}


@app.post("/api/gap-analyses/{analysis_id}/annotate")
def annotate_analysis_endpoint(analysis_id: int, req: GapAnnotateRequest):
    from utils.db import annotate_gap_analysis
    annotate_gap_analysis(analysis_id, req.notes)
    return {"ok": True}


# ── DOCX Export ──────────────────────────────────────────────────────────────

def _run_docx_generator(payload: dict) -> bytes:
    """Call the Node.js docx generator, return the file bytes."""
    import json
    import subprocess
    import tempfile

    script = Path(__file__).parent / "scripts" / "generate_docx.js"
    if not script.exists():
        raise RuntimeError(f"DOCX generator script not found: {script}")

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_path = tmp.name

    payload["outpath"] = tmp_path
    result = subprocess.run(
        ["node", str(script)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"DOCX generation failed: {result.stderr}")

    data = Path(tmp_path).read_bytes()
    Path(tmp_path).unlink(missing_ok=True)
    return data


@app.get("/api/gap-analyses/{analysis_id}/export")
def export_gap_analysis(analysis_id: int):
    """Export a gap analysis as a formatted .docx file."""
    try:
        from utils.db import get_session, GapAnalysis as _GA
        with get_session() as sess:
            row = sess.query(_GA).filter(_GA.id == analysis_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Analysis not found")
            data = {
                "profile_name":    row.profile_name,
                "jurisdictions":   row.jurisdictions or [],
                "docs_examined":   row.docs_examined,
                "applicable_count":row.applicable_count,
                "gap_count":       row.gap_count,
                "critical_count":  row.critical_count,
                "posture_score":   row.posture_score,
                "model_used":      row.model_used,
                "generated_at":    row.generated_at.isoformat() if row.generated_at else None,
                "gaps_result":     row.gaps_json or {},
                "notes":           row.notes,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        docx_bytes = _run_docx_generator({"type": "gap_analysis", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

    safe_name = (data["profile_name"] or "gap_analysis").replace(" ", "_")[:40]
    date_str  = (data["generated_at"] or "")[:10]
    filename  = f"ARIS_GapAnalysis_{safe_name}_{date_str}.docx"

    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/synthesis/{synthesis_id}/export")
def export_synthesis(synthesis_id: int):
    """Export a synthesis as a formatted .docx file."""
    try:
        from utils.db import get_session, ThematicSynthesis as _TS
        with get_session() as sess:
            row = sess.query(_TS).filter(_TS.id == synthesis_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Synthesis not found")
            data = {
                "topic":          row.topic,
                "jurisdictions":  row.jurisdictions or [],
                "docs_used":      row.docs_used,
                "model_used":     row.model_used,
                "generated_at":   row.generated_at.isoformat() if row.generated_at else None,
                "synthesis_json": row.synthesis_json or {},
                "conflicts_json": row.conflicts_json or {},
                "notes":          row.notes,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        docx_bytes = _run_docx_generator({"type": "synthesis", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

    safe_topic = (data["topic"] or "synthesis").replace(" ", "_")[:40]
    date_str   = (data["generated_at"] or "")[:10]
    filename   = f"ARIS_Synthesis_{safe_topic}_{date_str}.docx"

    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ·· PDF Ingestion ·············································

class PDFIngestRequest(BaseModel):
    filename:       str
    title:          Optional[str]  = None
    jurisdiction:   str            = "Unknown"
    agency:         Optional[str]  = None
    doc_type:       str            = "PDF Document"
    status:         str            = "Unknown"
    url:            Optional[str]  = None
    published_date: Optional[str]  = None
    notes:          Optional[str]  = None


class PDFDownloadRequest(BaseModel):
    document_ids:   List[str]
    limit:          int = 20


@app.get("/api/pdf/stats")
def pdf_stats():
    """PDF ingestion statistics."""
    from sources.pdf_agent import get_pdf_stats
    return get_pdf_stats()


@app.get("/api/pdf/inbox")
def pdf_inbox():
    """List PDF files currently in the drop folder."""
    from sources.pdf_agent import PDFManualIngestor
    return PDFManualIngestor().list_inbox()


@app.get("/api/pdf/candidates")
def pdf_candidates(jurisdiction: Optional[str] = None):
    """List documents that have PDF URLs available for auto-download."""
    from sources.pdf_agent import PDFAutoDownloader
    return PDFAutoDownloader().candidates(jurisdiction=jurisdiction)


@app.post("/api/pdf/upload")
async def pdf_upload(
    file:           UploadFile = File(...),
    title:          str        = Form(""),
    jurisdiction:   str        = Form("Unknown"),
    agency:         str        = Form(""),
    doc_type:       str        = Form("PDF Document"),
    status:         str        = Form("Unknown"),
    url:            str        = Form(""),
    published_date: str        = Form(""),
    notes:          str        = Form(""),
):
    """Upload a PDF file with manual metadata tagging."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    data = await file.read()
    if len(data) < 100:
        raise HTTPException(status_code=400, detail="File appears empty")

    metadata = {
        "title":          title or Path(file.filename).stem,
        "jurisdiction":   jurisdiction,
        "agency":         agency or None,
        "doc_type":       doc_type,
        "status":         status,
        "url":            url or None,
        "published_date": published_date or None,
        "notes":          notes or None,
    }

    try:
        from sources.pdf_agent import PDFManualIngestor
        doc = PDFManualIngestor().ingest_bytes(file.filename, data, metadata)
        return {
            "ok":          True,
            "document_id": doc["id"],
            "title":       doc["title"],
            "word_count":  len((doc.get("full_text") or "").split()),
        }
    except Exception as e:
        log.error("PDF upload failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pdf/ingest")
def pdf_ingest_inbox(req: PDFIngestRequest):
    """Ingest a PDF file from the drop folder with metadata."""
    metadata = {
        "title":          req.title or Path(req.filename).stem,
        "jurisdiction":   req.jurisdiction,
        "agency":         req.agency,
        "doc_type":       req.doc_type,
        "status":         req.status,
        "url":            req.url,
        "published_date": req.published_date,
        "notes":          req.notes,
    }
    try:
        from sources.pdf_agent import PDFManualIngestor
        doc = PDFManualIngestor().ingest(req.filename, metadata)
        return {
            "ok":          True,
            "document_id": doc["id"],
            "title":       doc["title"],
            "word_count":  len((doc.get("full_text") or "").split()),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error("PDF ingest failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pdf/download")
def pdf_download(req: PDFDownloadRequest, background_tasks: BackgroundTasks):
    """Trigger background auto-download of PDFs for given document IDs."""
    if _job_state["running"]:
        raise HTTPException(status_code=409, detail="Another job is already running")

    def _run():
        _job_state["running"] = True
        _job_state["log"]     = []
        _log(f"PDF auto-download started for {len(req.document_ids)} documents")
        try:
            from sources.pdf_agent import PDFAutoDownloader
            downloader = PDFAutoDownloader()
            succeeded  = 0
            failed     = 0
            for doc_id in req.document_ids[:req.limit]:
                from utils.db import get_document
                doc = get_document(doc_id)
                if not doc:
                    _log(f"  ✗ Not found: {doc_id}")
                    failed += 1
                    continue
                _log(f"  ↓ Downloading: {doc.get('title', doc_id)[:60]}")
                result = downloader.run(limit=1,
                                        progress_cb=_log)
                if result["succeeded"]:
                    succeeded += 1
                else:
                    failed += 1
            _log(f"PDF download complete — {succeeded} succeeded, {failed} failed")
            _job_state["last_result"] = {"pdf_succeeded": succeeded, "pdf_failed": failed}
        except Exception as e:
            _log(f"ERROR: {e}")
            raise
        finally:
            _job_state["running"]  = False
            _job_state["last_run"] = datetime.utcnow().isoformat()

    background_tasks.add_task(_run)
    return {"status": "started", "count": len(req.document_ids)}


@app.post("/api/pdf/download-all")
def pdf_download_all(
    jurisdiction: Optional[str] = None,
    limit: int = 50,
    background_tasks: BackgroundTasks = None,
):
    """Auto-download PDFs for all eligible documents (background job)."""
    if _job_state["running"]:
        raise HTTPException(status_code=409, detail="Another job is already running")

    def _run():
        _job_state["running"] = True
        _job_state["log"]     = []
        _log(f"PDF bulk download started (jurisdiction={jurisdiction}, limit={limit})")
        try:
            from sources.pdf_agent import PDFAutoDownloader
            result = PDFAutoDownloader().run(
                jurisdiction=jurisdiction,
                limit=limit,
                progress_cb=_log,
            )
            _log(f"Done — {result['succeeded']} succeeded, "
                 f"{result['failed']} failed, {result['skipped']} skipped")
            _job_state["last_result"] = result
        except Exception as e:
            _log(f"ERROR: {e}")
            raise
        finally:
            _job_state["running"]  = False
            _job_state["last_run"] = datetime.utcnow().isoformat()

    background_tasks.add_task(_run)
    return {"status": "started"}


# ·· Thematic Synthesis & Conflict Detection ····················

class SynthesisRequest(BaseModel):
    topic:            str
    jurisdictions:    Optional[List[str]] = None
    days:             int  = 365
    detect_conflicts: bool = True
    force_refresh:    bool = False


class AnnotateRequest(BaseModel):
    notes: str


@app.get("/api/synthesis")
def list_syntheses(limit: int = 20):
    """List recent thematic synthesis records."""
    from utils.db import get_recent_syntheses
    return get_recent_syntheses(limit=limit)


@app.get("/api/synthesis/topics")
def suggested_topics():
    """Return topic suggestions based on what document clusters exist in the DB."""
    from utils.llm import is_configured as _is_cfg
    if not _is_cfg():
        raise HTTPException(status_code=503, detail="LLM provider not configured")
    from agents.synthesis_agent import SynthesisAgent
    return SynthesisAgent().list_suggested_topics()


@app.get("/api/synthesis/{synthesis_id}")
def get_synthesis(synthesis_id: int):
    """Return a full synthesis record by ID."""
    from utils.db import get_synthesis_by_id
    result = get_synthesis_by_id(synthesis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Synthesis not found")
    return result


@app.post("/api/synthesis")
def run_synthesis(req: SynthesisRequest, background_tasks: BackgroundTasks):
    """
    Trigger a thematic synthesis + optional conflict detection run.
    Runs in the background — poll /api/run/status and /api/run/log.
    """
    from utils.llm import is_configured as _is_cfg
    if not _is_cfg():
        raise HTTPException(status_code=503, detail="LLM provider not configured")
    if _job_state["running"]:
        raise HTTPException(status_code=409, detail="Another job is already running")

    def _run():
        _job_state["running"] = True
        _job_state["log"]     = []
        _log(f"Synthesis started: topic='{req.topic}'")
        try:
            from agents.synthesis_agent import SynthesisAgent
            agent  = SynthesisAgent()
            _log(f"Gathering documents for: {req.topic}")
            result = agent.run(
                topic            = req.topic,
                jurisdictions    = req.jurisdictions or None,
                days             = req.days,
                detect_conflicts = req.detect_conflicts,
                force_refresh    = req.force_refresh,
            )
            n_conflicts = 0
            if result.get("conflicts"):
                n_conflicts = len(result["conflicts"].get("conflicts", []))
            _log(f"Synthesis complete: {result.get('docs_used', 0)} docs, "
                 f"{n_conflicts} conflicts detected")
            _job_state["last_result"] = {
                "synthesis_id":  result.get("id"),
                "topic":         req.topic,
                "docs_used":     result.get("docs_used", 0),
                "conflicts":     n_conflicts,
                "jurisdictions": result.get("jurisdictions", []),
            }
        except Exception as e:
            _log(f"ERROR: {e}")
            raise
        finally:
            _job_state["running"]  = False
            _job_state["last_run"] = datetime.utcnow().isoformat()

    background_tasks.add_task(_run)
    return {"status": "started", "topic": req.topic}


@app.post("/api/synthesis/{synthesis_id}/star")
def star_synthesis_endpoint(synthesis_id: int, starred: bool = True):
    from utils.db import star_synthesis
    star_synthesis(synthesis_id, starred)
    return {"ok": True}


@app.post("/api/synthesis/{synthesis_id}/annotate")
def annotate_synthesis_endpoint(synthesis_id: int, req: AnnotateRequest):
    from utils.db import annotate_synthesis
    annotate_synthesis(synthesis_id, req.notes)
    return {"ok": True}


@app.delete("/api/synthesis/{synthesis_id}")
def delete_synthesis_endpoint(synthesis_id: int):
    from utils.db import delete_synthesis
    delete_synthesis(synthesis_id)
    return {"ok": True}


# ·· Learning / Feedback ········································

class FeedbackRequest(BaseModel):
    document_id: str
    feedback:    str                    # relevant | not_relevant | partially_relevant
    reason:      Optional[str] = None   # free-text explanation
    user:        str = "user"


@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest):
    """Record human relevance feedback on a document."""
    doc = get_document(req.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    summary = get_summary(req.document_id)
    doc_with_summary = {**doc, **({"relevance_score": summary.get("relevance_score")} if summary else {})}

    try:
        from agents.learning_agent import LearningAgent
        learner = LearningAgent()
        profile = learner.record_feedback(
            doc      = doc_with_summary,
            feedback = req.feedback,
            reason   = req.reason,
            user     = req.user,
        )
        return {"ok": True, "source_quality": profile.get("quality_score")}
    except Exception as e:
        log.error("Feedback recording failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning")
def get_learning_report():
    """Full learning report: source quality, keyword weights, prompt adaptations."""
    try:
        from agents.learning_agent import LearningAgent
        learner = LearningAgent()
        return learner.get_learning_report()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/feedback")
def get_feedback_history(days: int = 30):
    from utils.db import get_recent_feedback
    return get_recent_feedback(days=days)


@app.get("/api/learning/schedule")
def get_schedule():
    """Adaptive scheduling recommendations per source."""
    try:
        from agents.learning_agent import LearningAgent
        return LearningAgent().get_optimal_fetch_schedule()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/learning/adaptation/{adapt_id}/toggle")
def toggle_adaptation(adapt_id: int, active: bool = True):
    from utils.db import toggle_prompt_adaptation
    toggle_prompt_adaptation(adapt_id, active)
    return {"ok": True}


# ·· Watchlist ··················································

@app.get("/api/watchlist")
def get_watchlist():
    items     = _load_watchlist()
    all_docs  = get_all_documents(limit=200)
    result    = []
    for item in items:
        matches = [d for d in all_docs if item["name"] in _match_watchlist(d, [item])]
        result.append({**item, "match_count": len(matches), "recent_matches": matches[:5]})
    return result


@app.post("/api/watchlist")
def add_watchlist_item(item: WatchlistItem):
    items = _load_watchlist()
    if any(i["name"] == item.name for i in items):
        raise HTTPException(status_code=409, detail=f"Watch item '{item.name}' already exists")
    items.append(item.model_dump())
    _save_watchlist(items)
    return {"ok": True}


@app.delete("/api/watchlist/{name}")
def delete_watchlist_item(name: str):
    items = [i for i in _load_watchlist() if i["name"] != name]
    _save_watchlist(items)
    return {"ok": True}


@app.get("/api/watchlist/{name}/matches")
def get_watchlist_matches(name: str, days: int = 30,
                          domain: Optional[str] = None):
    items = _load_watchlist()
    item  = next((i for i in items if i["name"] == name), None)
    if not item:
        raise HTTPException(status_code=404, detail="Watch item not found")
    all_docs = get_all_documents(limit=500)
    matches  = [d for d in all_docs if _match_watchlist(d, [item])]
    if domain and domain != "both":
        matches = [d for d in matches if d.get("domain") == domain]
    return {"name": name, "matches": matches, "total": len(matches)}


# ·· Relationship graph ··········································

@app.get("/api/graph")
def get_knowledge_graph(
    jurisdiction: Optional[str] = None,
    node_types:   Optional[str] = None,   # comma-separated: baseline,document
    edge_types:   Optional[str] = None,   # comma-separated: cross_ref,genealogical,semantic,document,conflict
    max_nodes:    int           = 200,
):
    """
    Return the full regulatory knowledge graph: baseline nodes, document nodes,
    and typed edges (cross_ref, genealogical, semantic, document, conflict).
    """
    from agents.graph_agent import GraphAgent
    agent = GraphAgent()

    nt = [x.strip() for x in node_types.split(",")] if node_types else None
    et = [x.strip() for x in edge_types.split(",")] if edge_types else None

    return agent.get_graph_data(
        jurisdiction     = jurisdiction,
        node_types       = nt,
        edge_types       = et,
        max_nodes        = max_nodes,
    )


@app.post("/api/graph/build")
def build_knowledge_graph(background_tasks: BackgroundTasks,
                           force: bool = False):
    """
    (Re)build the knowledge graph edge table from all baselines and documents.
    Runs in the background — lightweight, no LLM calls.
    """
    def _run():
        from agents.graph_agent import GraphAgent
        counts = GraphAgent().build(force=force)
        log.info("Knowledge graph built: %s", counts)
    background_tasks.add_task(_run)
    return {"status": "building"}


@app.post("/api/graph/conflicts")
def detect_graph_conflicts(background_tasks: BackgroundTasks):
    """
    Detect regulatory conflicts using the LLM across curated baseline pairs.
    Each pair costs one LLM call. Runs in background.
    """
    from utils.llm import is_configured, _provider
    if not is_configured():
        raise HTTPException(status_code=503,
                            detail=f"LLM provider '{_provider()}' is not configured.")
    def _run():
        from agents.graph_agent import GraphAgent
        n = GraphAgent().build_conflicts()
        log.info("Conflict detection complete: %d conflicts", n)
    background_tasks.add_task(_run)
    return {"status": "detecting_conflicts"}


@app.get("/api/graph/status")
def graph_status():
    """Return knowledge graph statistics."""
    try:
        from utils.db import count_graph_edges, get_graph_edges
        edges = get_graph_edges()
        counts: Dict[str, int] = {}
        for e in edges:
            t = e.get("edge_type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return {
            "total_edges":       len(edges),
            "edge_type_counts":  counts,
            "built":             len(edges) > 0,
        }
    except Exception as e:
        return {"built": False, "error": str(e)}


# ·· Export ·····················································

@app.get("/api/export/json")
def export_json(days: int = 30, jurisdiction: Optional[str] = None):
    summaries = get_recent_summaries(days=days, jurisdiction=jurisdiction)
    return JSONResponse(content=summaries)


@app.get("/api/export/markdown")
def export_markdown(days: int = 30, jurisdiction: Optional[str] = None):
    from utils.reporter import export_markdown as _export
    path = _export(days=days)
    return FileResponse(path, media_type="text/markdown",
                        filename=Path(path).name)


# ·· Q&A ·····················································

class QARequest(BaseModel):
    question:    str
    jurisdiction: Optional[str] = None
    session_id:   Optional[int] = None   # for follow-up context (last N turns)


@app.post("/api/qa")
def ask_question(req: QARequest):
    """
    Answer a natural-language question about AI regulation, grounded in
    the full ARIS corpus (baselines + summarised documents).

    Returns: answer text with inline citations, structured citation objects
    for the UI, and suggested follow-up questions.
    """
    from utils.llm import is_configured, _provider
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail=f"LLM provider '{_provider()}' is not configured. "
                   "Set the appropriate API key in config/keys.env."
        )

    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    # Load recent history as conversation context
    conversation_history = None
    try:
        from utils.db import get_qa_history
        history = get_qa_history(limit=6)
        if history:
            conversation_history = list(reversed(history))   # oldest first
    except Exception:
        pass

    try:
        from agents.qa_agent import QAAgent
        agent  = QAAgent()
        result = agent.ask(
            question             = req.question.strip(),
            jurisdiction         = req.jurisdiction,
            conversation_history = conversation_history,
            save_to_history      = True,
        )
        return result
    except Exception as e:
        log.error("Q&A error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/qa/history")
def get_qa_history_endpoint(limit: int = 50):
    """Return recent Q&A session history, newest first."""
    try:
        from utils.db import get_qa_history
        return {"items": get_qa_history(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/qa/index/rebuild")
def rebuild_qa_index(background_tasks: BackgroundTasks):
    """
    Rebuild the Q&A passage index from all baselines and summarised documents.
    Runs in the background — takes 5-30 seconds depending on corpus size.
    Poll /api/qa/index/status to check progress.
    """
    def _run():
        try:
            from utils.rag import build_passage_index
            counts = build_passage_index(force=True)
            log.info("Q&A index rebuild complete: %s", counts)
        except Exception as e:
            log.error("Q&A index rebuild error: %s", e)
    background_tasks.add_task(_run)
    return {"status": "rebuilding"}


@app.get("/api/qa/index/status")
def qa_index_status():
    """Return Q&A index statistics: passage count, sources indexed, readiness."""
    try:
        from utils.db import get_all_qa_passage_ids
        from utils.rag import get_retriever
        sources = get_all_qa_passage_ids()
        baseline_count  = sum(1 for s in sources if s["source_type"] == "baseline")
        document_count  = sum(1 for s in sources if s["source_type"] == "document")

        retriever = get_retriever()
        return {
            "ready":            retriever._ready,
            "passage_count":    len(retriever._tfidf._ids),
            "baselines_indexed":baseline_count,
            "documents_indexed":document_count,
            "tfidf_built":      retriever._tfidf._built,
        }
    except Exception as e:
        return {"ready": False, "error": str(e)}


# ·· Enforcement & Litigation ··································

@app.get("/api/enforcement")
def get_enforcement(
    jurisdiction: Optional[str] = None,
    source:       Optional[str] = None,
    action_type:  Optional[str] = None,
    domain:       Optional[str] = None,
    days:         int            = 365,
    limit:        int            = 100,
):
    """
    Return enforcement actions and litigation.
    domain filter: ai | privacy | both
    """
    from utils.db import get_enforcement_actions
    return {
        "items": get_enforcement_actions(
            jurisdiction=jurisdiction,
            source=source,
            action_type=action_type,
            domain=domain,
            days=days,
            limit=limit,
        )
    }


@app.get("/api/enforcement/stats")
def enforcement_stats():
    """Return enforcement action counts by source and type."""
    from utils.db import count_enforcement_actions
    return count_enforcement_actions()


@app.post("/api/enforcement/fetch")
def fetch_enforcement(background_tasks: BackgroundTasks, days: int = 90):
    """Trigger background enforcement fetch from all sources."""
    def _run():
        from sources.enforcement_agent import EnforcementAgent
        counts = EnforcementAgent().fetch_all(lookback_days=days)
        log.info("Enforcement fetch complete: %s", counts)
    background_tasks.add_task(_run)
    return {"status": "fetching", "lookback_days": days}


# ·· Timeline ··················································

@app.get("/api/timeline")
def get_timeline(
    jurisdiction:     Optional[str] = None,
    include_docs:     bool          = True,
    include_horizon:  bool          = True,
    years_back:       int           = 10,
    years_ahead:      int           = 3,
):
    """
    Return the unified regulatory timeline: baseline milestones,
    live document events, and anticipated horizon items.
    """
    from agents.timeline_agent import TimelineAgent
    return TimelineAgent().get_timeline(
        jurisdiction    = jurisdiction,
        include_docs    = include_docs,
        include_horizon = include_horizon,
        years_back      = years_back,
        years_ahead     = years_ahead,
    )


# ·· Regulatory Briefs ·········································

class BriefRequest(BaseModel):
    topic:        str
    jurisdiction: Optional[str] = None
    force:        bool          = False


@app.post("/api/briefs/generate")
def generate_brief(req: BriefRequest):
    """
    Generate a structured regulatory brief on a topic using RAG + LLM.
    One LLM call; result cached for 14 days.
    """
    from utils.llm import is_configured, _provider
    if not is_configured():
        raise HTTPException(status_code=503,
                            detail=f"LLM provider '{_provider()}' is not configured.")
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic is required")
    try:
        from agents.brief_agent import BriefAgent
        return BriefAgent().generate(
            topic        = req.topic.strip(),
            jurisdiction = req.jurisdiction,
            force        = req.force,
        )
    except Exception as e:
        log.error("Brief generation error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/briefs")
def list_briefs():
    """List all cached regulatory briefs."""
    from agents.brief_agent import BriefAgent
    return {"briefs": BriefAgent.list_briefs()}


@app.get("/api/briefs/{topic_key}")
def get_brief(topic_key: str):
    """Return a cached brief by its topic key."""
    from utils.db import get_brief_cache
    cached = get_brief_cache(topic_key, max_age_days=9999)  # never expire on direct fetch
    if not cached:
        raise HTTPException(status_code=404, detail="Brief not found")
    return cached


# ·· Deep Document Comparison ··································

class CompareRequest(BaseModel):
    source_id_a:  str
    source_type_a: str = "auto"   # auto | baseline | document
    source_id_b:  str
    source_type_b: str = "auto"
    focus:        Optional[str] = None   # specific concept to focus on


@app.post("/api/compare")
def deep_compare(req: CompareRequest):
    """
    Deep conceptual comparison between any two baselines or documents.
    Unlike the diff endpoint (version comparison), this produces a
    structured analysis of how two regulations approach regulation differently.
    One LLM call.
    """
    from utils.llm import is_configured, _provider
    if not is_configured():
        raise HTTPException(status_code=503,
                            detail=f"LLM provider '{_provider()}' is not configured.")
    try:
        from agents.compare_agent import CompareAgent
        return CompareAgent().compare(
            id_a        = req.source_id_a,
            type_a      = req.source_type_a,
            id_b        = req.source_id_b,
            type_b      = req.source_type_b,
            focus       = req.focus,
        )
    except Exception as e:
        log.error("Compare error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/concepts")
def list_concepts():
    """List all available concepts with cache status."""
    from agents.concept_agent import ConceptAgent
    return {"concepts": ConceptAgent.list_concepts()}


@app.get("/api/concepts/{concept_key}")
def get_concept(concept_key: str, force: bool = False):
    """
    Return the cross-jurisdiction concept map for a given concept.
    Served from cache if available (< 7 days old); builds fresh otherwise.
    """
    from agents.concept_agent import ConceptAgent, CONCEPT_CATALOGUE
    if concept_key not in CONCEPT_CATALOGUE:
        raise HTTPException(status_code=404,
                            detail=f"Unknown concept '{concept_key}'. "
                                   f"Valid: {list(CONCEPT_CATALOGUE.keys())}")

    # Serve from cache without LLM if available
    if not force:
        from utils.db import get_concept_map
        cached = get_concept_map(concept_key)
        if cached:
            spec = CONCEPT_CATALOGUE[concept_key]
            cached["description"] = spec["description"]
            return cached

    # Needs LLM
    from utils.llm import is_configured, _provider
    if not is_configured():
        raise HTTPException(status_code=503,
                            detail=f"LLM provider '{_provider()}' is not configured.")
    try:
        agent  = ConceptAgent()
        result = agent.get_concept_map(concept_key, force=force)
        if not result:
            raise HTTPException(status_code=500, detail="Concept map build failed")
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error("Concept map error for %s: %s", concept_key, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/concepts/{concept_key}/build")
def build_concept(concept_key: str, background_tasks: BackgroundTasks):
    """
    Trigger a background rebuild of the concept map (uses one LLM call).
    """
    from agents.concept_agent import CONCEPT_CATALOGUE
    if concept_key not in CONCEPT_CATALOGUE:
        raise HTTPException(status_code=404, detail=f"Unknown concept: {concept_key}")
    from utils.llm import is_configured, _provider
    if not is_configured():
        raise HTTPException(status_code=503,
                            detail=f"LLM provider '{_provider()}' is not configured.")

    def _run():
        from agents.concept_agent import ConceptAgent
        result = ConceptAgent().get_concept_map(concept_key, force=True)
        if result:
            log.info("Concept map built: %s (%d entries)", concept_key, result.get("entry_count", 0))
    background_tasks.add_task(_run)
    return {"status": "building", "concept_key": concept_key}


UI_DIST = Path(__file__).parent / "ui" / "dist"

if UI_DIST.exists():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        index = UI_DIST / "index.html"
        return FileResponse(index)
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"message": "ARIS API running. Build the frontend with: cd ui && npm run build"}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn")
        sys.exit(1)

    print("\n  ARIS Server starting...")
    print("  API docs:  http://localhost:8000/docs")
    print("  Dashboard: http://localhost:8000\n")

    # Bind to localhost only by default — no authentication layer exists.
    # Set ARIS_HOST=0.0.0.0 in keys.env only if you need LAN access and
    # understand the implications (no auth, full API access to anyone on the network).
    import os as _os
    host = _os.getenv("ARIS_HOST", "127.0.0.1")

    uvicorn.run(
        "server:app",
        host=host,
        port=8000,
        reload=True,
        log_level="info",
    )
