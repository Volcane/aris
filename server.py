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
def list_baselines():
    """Return summary metadata for all loaded baseline regulations."""
    from agents.baseline_agent import BaselineAgent
    return BaselineAgent().get_all()


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
            if not ANTHROPIC_API_KEY:
                raise HTTPException(status_code=503,
                                    detail="ANTHROPIC_API_KEY not set for full mode")
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
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
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
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
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
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
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
