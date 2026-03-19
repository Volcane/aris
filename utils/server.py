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
    from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
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

app = FastAPI(
    title="ARIS — AI Regulation Intelligence System",
    description="REST API for the ARIS dashboard",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    sources:       List[str] = []          # empty = all
    lookback_days: int       = 30
    summarize:     bool      = True
    run_diff:      bool      = True
    limit:         int       = 50

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

@app.get("/api/status")
def get_status():
    """System health, API key status, and DB statistics."""
    stats = get_stats()
    return {
        "stats": stats,
        "api_keys": {
            "anthropic":        bool(ANTHROPIC_API_KEY),
            "regulations_gov":  bool(REGULATIONS_GOV_KEY),
            "congress_gov":     bool(CONGRESS_GOV_KEY),
            "legiscan":         bool(LEGISCAN_KEY),
        },
        "enabled_states":        ENABLED_US_STATES,
        "enabled_international": ENABLED_INTERNATIONAL,
        "job": {
            "running":    _job_state["running"],
            "last_run":   _job_state["last_run"],
            "last_result": _job_state["last_result"],
        },
    }


# ·· Documents ·················································

@app.get("/api/documents")
def list_documents(
    jurisdiction: Optional[str] = None,
    urgency:      Optional[str] = None,
    doc_type:     Optional[str] = None,
    days:         int           = 365,
    search:       Optional[str] = None,
    page:         int           = 1,
    page_size:    int           = 50,
):
    """Paginated document list with filters."""
    summaries = get_recent_summaries(days=days, jurisdiction=jurisdiction)

    if urgency:
        # Only filter by urgency when explicitly set — unsummarized docs
        # (urgency=None) are preserved when no urgency filter is active
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
    days:      int           = 30,
    severity:  Optional[str] = None,
    diff_type: Optional[str] = None,
    unreviewed: bool         = False,
):
    """All detected regulatory changes."""
    if unreviewed:
        return get_unreviewed_diffs(limit=200)
    return get_recent_diffs(days=days, severity=severity, diff_type=diff_type)


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
            )
            _log(f"Fetched {fetch_result['fetched']} new/updated documents")
            if req.run_diff:
                _log(f"Version diffs: {fetch_result.get('version_diffs', 0)}")
                _log(f"Addenda found: {fetch_result.get('addenda_found', 0)}")

            summarized = 0
            if req.summarize:
                _log(f"Summarizing up to {req.limit} documents with Claude…")

                def _cb(current, total):
                    _log(f"  Summarizing {current}/{total}…")

                summarized = orch.summarize(limit=req.limit, progress_callback=_cb)
                _log(f"Summarized {summarized} documents")

            _job_state["last_result"] = {
                **fetch_result,
                "summarized": summarized,
                **get_stats(),
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

    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    import anthropic as _anthropic
    client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    checklist_md = message.content[0].text
    return {
        "document_id": req.document_id,
        "title":       doc.get("title"),
        "checklist":   checklist_md,
        "generated_at": datetime.utcnow().isoformat(),
    }


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
def get_watchlist_matches(name: str, days: int = 30):
    items = _load_watchlist()
    item  = next((i for i in items if i["name"] == name), None)
    if not item:
        raise HTTPException(status_code=404, detail="Watch item not found")
    all_docs = get_all_documents(limit=500)
    matches  = [d for d in all_docs if _match_watchlist(d, [item])]
    return {"name": name, "matches": matches, "total": len(matches)}


# ·· Relationship graph ··········································

@app.get("/api/graph")
def get_relationship_graph(jurisdiction: Optional[str] = None, days: int = 90):
    """
    Return a nodes + edges graph of document relationships for visualisation.
    Nodes = documents, Edges = DocumentLink relationships.
    """
    from utils.db import get_session, DocumentLink, Document, Summary

    with get_session() as session:
        # Get all links
        links = session.query(DocumentLink).all()
        doc_ids = set()
        for lnk in links:
            doc_ids.add(lnk.base_doc_id)
            doc_ids.add(lnk.related_doc_id)

        # Get nodes
        nodes = []
        for doc_id in doc_ids:
            doc  = session.get(Document, doc_id)
            summ = session.get(Summary,  doc_id)
            if not doc:
                continue
            if jurisdiction and doc.jurisdiction != jurisdiction:
                continue
            nodes.append({
                "id":           doc.id,
                "label":        (doc.title or "")[:60],
                "jurisdiction": doc.jurisdiction,
                "doc_type":     doc.doc_type,
                "status":       doc.status,
                "urgency":      summ.urgency if summ else "Low",
                "url":          doc.url,
            })

        node_ids = {n["id"] for n in nodes}
        edges = [
            {
                "source":    lnk.base_doc_id,
                "target":    lnk.related_doc_id,
                "type":      lnk.link_type,
                "label":     lnk.link_type,
                "created_at": lnk.created_at.isoformat() if lnk.created_at else None,
            }
            for lnk in links
            if lnk.base_doc_id in node_ids and lnk.related_doc_id in node_ids
        ]

    return {"nodes": nodes, "edges": edges}


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


# ·· Serve React frontend ·······································

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

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
