"""
ARIS — Database Layer (updated)

Tables:
  documents         — Raw legislative/regulatory documents
  summaries         — AI-generated business intelligence summaries
  document_diffs    — Version comparison and addendum analysis results
  document_links    — Explicit relationships between documents
"""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    create_engine, Column, String, Text, DateTime,
    Float, Boolean, JSON, Index, text, Integer, func
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import DB_PATH


class Base(DeclarativeBase):
    pass


# ── Core tables ───────────────────────────────────────────────────────────────

class Document(Base):
    """Raw legislative / regulatory document fetched from a source."""
    __tablename__ = "documents"

    id             = Column(String, primary_key=True)
    source         = Column(String, nullable=False)
    jurisdiction   = Column(String, nullable=False)
    doc_type       = Column(String)
    title          = Column(Text, nullable=False)
    url            = Column(Text)
    published_date = Column(DateTime)
    agency         = Column(String)
    status         = Column(String)
    full_text      = Column(Text)
    raw_json       = Column(JSON)
    fetched_at     = Column(DateTime, default=datetime.utcnow)
    content_hash   = Column(String)
    origin         = Column(String, default="api")   # api | pdf_auto | pdf_manual
    domain         = Column(String, default="ai")    # ai | privacy | both

    __table_args__ = (
        Index("ix_doc_jurisdiction", "jurisdiction"),
        Index("ix_doc_source",       "source"),
        Index("ix_doc_published",    "published_date"),
        Index("ix_doc_domain",       "domain"),
    )


class PdfMetadata(Base):
    """
    Stores metadata about PDFs that have been downloaded or manually ingested.
    One record per document that has associated PDF extraction data.
    """
    __tablename__ = "pdf_metadata"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    document_id        = Column(String, nullable=False, unique=True)
    pdf_path           = Column(Text)           # local file path
    pdf_url            = Column(Text)           # source URL (if downloaded)
    page_count         = Column(Integer)
    word_count         = Column(Integer)
    extraction_method  = Column(String)         # pdfplumber | pypdf
    extracted_at       = Column(DateTime, default=datetime.utcnow)
    origin             = Column(String)         # pdf_auto | pdf_manual

    __table_args__ = (
        Index("ix_pdf_document_id", "document_id"),
        Index("ix_pdf_origin",      "origin"),
    )


class Summary(Base):
    """AI-generated business-intelligence summary for a Document."""
    __tablename__ = "summaries"

    document_id     = Column(String, primary_key=True)
    plain_english   = Column(Text)
    requirements    = Column(JSON)
    recommendations = Column(JSON)
    action_items    = Column(JSON)
    deadline        = Column(String)
    impact_areas    = Column(JSON)
    urgency         = Column(String)
    relevance_score = Column(Float)
    model_used      = Column(String)
    summarized_at   = Column(DateTime, default=datetime.utcnow)
    domain          = Column(String, default="ai")   # ai | privacy | both


class DocumentDiff(Base):
    """
    Stores the result of a version comparison or addendum analysis
    produced by the DiffAgent.

    diff_type:
      "version_update" — same regulation, newer version published
      "addendum"       — a separate document modifies/reinterprets the base

    For version_update:
      base_document_id = older version's document ID
      new_document_id  = newer version's document ID

    For addendum:
      base_document_id = the regulation being amended or clarified
      new_document_id  = the addendum / amendment / guidance document
    """
    __tablename__ = "document_diffs"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    base_document_id      = Column(String, nullable=False)
    new_document_id       = Column(String, nullable=False)
    diff_type             = Column(String, nullable=False)
    relationship_type     = Column(String)
    change_summary        = Column(Text)
    severity              = Column(String)
    added_requirements    = Column(JSON)
    removed_requirements  = Column(JSON)
    modified_requirements = Column(JSON)
    definition_changes    = Column(JSON)
    deadline_changes      = Column(JSON)
    penalty_changes       = Column(JSON)
    scope_changes         = Column(Text)
    new_action_items      = Column(JSON)
    obsolete_action_items = Column(JSON)
    overall_assessment    = Column(Text)
    model_used            = Column(String)
    detected_at           = Column(DateTime, default=datetime.utcnow)
    reviewed              = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_diff_base",     "base_document_id"),
        Index("ix_diff_new",      "new_document_id"),
        Index("ix_diff_severity", "severity"),
        Index("ix_diff_type",     "diff_type"),
        Index("ix_diff_detected", "detected_at"),
    )


class DocumentLink(Base):
    """
    Explicit relationship between two documents.
    link_type values: "amends" | "clarifies" | "implements" | "supersedes" | "version_of"
    """
    __tablename__ = "document_links"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    base_doc_id    = Column(String, nullable=False)
    related_doc_id = Column(String, nullable=False)
    link_type      = Column(String, nullable=False)
    notes          = Column(Text)
    created_at     = Column(DateTime, default=datetime.utcnow)
    created_by     = Column(String, default="system")

    __table_args__ = (
        Index("ix_link_base",    "base_doc_id"),
        Index("ix_link_related", "related_doc_id"),
    )


# ── Engine & session factory ──────────────────────────────────────────────────

_engine  = None
_Session = None


def get_engine():
    global _engine
    if _engine is None:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
        Base.metadata.create_all(_engine)
    return _engine


def get_session() -> Session:
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=get_engine())
    return _Session()


# ── Documents CRUD ────────────────────────────────────────────────────────────

def upsert_document(doc_dict: Dict[str, Any]) -> bool:
    """
    Insert or update a document.
    Returns True if content changed (triggers diff pipeline in orchestrator).
    Also updates the FTS5 search index.
    """
    content_hash = hashlib.md5(
        (doc_dict.get("full_text") or doc_dict.get("title") or "").encode()
    ).hexdigest()

    with get_session() as session:
        existing = session.get(Document, doc_dict["id"])
        if existing and existing.content_hash == content_hash:
            return False

        doc = existing or Document()
        for k, v in doc_dict.items():
            if hasattr(doc, k):
                setattr(doc, k, v)
        doc.content_hash = content_hash
        doc.fetched_at   = datetime.utcnow()
        session.merge(doc)
        session.commit()

    # Update FTS index (non-blocking — failure never blocks document storage)
    try:
        from utils.search import index_document as _fts_index
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(DB_PATH)
        _fts_index(
            conn,
            doc_id       = doc_dict["id"],
            title        = doc_dict.get("title", ""),
            summary      = doc_dict.get("plain_english", "") or doc_dict.get("full_text", "")[:500],
            agency       = doc_dict.get("agency", ""),
            jurisdiction = doc_dict.get("jurisdiction", ""),
        )
        conn.close()
    except Exception:
        pass   # FTS failure never blocks document storage

    return True


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    with get_session() as session:
        doc = session.get(Document, doc_id)
        return _doc_to_dict(doc) if doc else None


def get_documents_by_title_pattern(pattern: str,
                                    jurisdiction: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_session() as session:
        q = session.query(Document).filter(Document.title.ilike(f"%{pattern}%"))
        if jurisdiction:
            q = q.filter(Document.jurisdiction == jurisdiction)
        return [_doc_to_dict(d) for d in q.all()]


def get_all_documents(jurisdiction: Optional[str] = None,
                      domain: Optional[str] = None,
                      limit: int = 500) -> List[Dict[str, Any]]:
    with get_session() as session:
        q = session.query(Document)
        if jurisdiction:
            q = q.filter(Document.jurisdiction == jurisdiction)
        if domain:
            q = q.filter(Document.domain == domain)
        return [_doc_to_dict(d) for d in
                q.order_by(Document.published_date.desc()).limit(limit).all()]


def _doc_to_dict(doc: Document) -> Dict[str, Any]:
    return {
        "id":            doc.id,
        "source":        doc.source,
        "jurisdiction":  doc.jurisdiction,
        "doc_type":      doc.doc_type,
        "title":         doc.title,
        "url":           doc.url,
        "published_date": doc.published_date.isoformat() if doc.published_date else None,
        "agency":        doc.agency,
        "status":        doc.status,
        "full_text":     doc.full_text,
        "domain":        doc.domain or "ai",
    }


# ── Summaries CRUD ────────────────────────────────────────────────────────────

def upsert_summary(summary_dict: Dict[str, Any]) -> None:
    with get_session() as session:
        session.merge(Summary(**summary_dict))
        session.commit()

    # Update FTS index with the richer plain-English summary text
    doc_id = summary_dict.get("document_id", "")
    plain  = summary_dict.get("plain_english", "") or ""
    if doc_id and plain:
        try:
            from utils.search import index_document as _fts_index
            import sqlite3 as _sqlite3
            conn = _sqlite3.connect(DB_PATH)
            # Re-fetch document metadata to keep the index complete
            doc = get_document(doc_id) or {}
            _fts_index(
                conn,
                doc_id       = doc_id,
                title        = doc.get("title", ""),
                summary      = plain,
                agency       = doc.get("agency", ""),
                jurisdiction = doc.get("jurisdiction", ""),
            )
            conn.close()
        except Exception:
            pass


def get_summary(doc_id: str) -> Optional[Dict[str, Any]]:
    with get_session() as session:
        s = session.get(Summary, doc_id)
        if not s:
            return None
        return {
            "document_id":     s.document_id,
            "plain_english":   s.plain_english,
            "requirements":    s.requirements,
            "recommendations": s.recommendations,
            "action_items":    s.action_items,
            "deadline":        s.deadline,
            "impact_areas":    s.impact_areas,
            "urgency":         s.urgency,
            "relevance_score": s.relevance_score,
        }


def get_unsummarized_documents(limit: int = 50,
                               domain: Optional[str] = None) -> List[Document]:
    with get_session() as session:
        summarized_ids = session.execute(
            text("SELECT document_id FROM summaries")
        ).scalars().all()
        q = (
            session.query(Document)
            .filter(Document.id.notin_(summarized_ids))
        )
        if domain:
            q = q.filter(Document.domain == domain)
        return (
            q.order_by(Document.published_date.desc())
            .limit(limit)
            .all()
        )


def get_recent_summaries(days: int = 30,
                          jurisdiction: Optional[str] = None,
                          domain: Optional[str] = None) -> List[Dict]:
    """
    Return documents joined with their summaries (if available).

    Uses a LEFT OUTER JOIN so documents without a summary still appear —
    they show with null summary fields until summarization runs.

    The date filter applies to whichever is more recent: published_date or
    fetched_at. This ensures documents with old or null published_date are
    still visible as long as they were fetched recently.
    """
    with get_session() as session:
        since = datetime.utcnow() - timedelta(days=days)

        # LEFT OUTER JOIN — documents without summaries still returned
        q = (
            session.query(Document, Summary)
            .outerjoin(Summary, Document.id == Summary.document_id)
            .filter(
                # Include if published recently OR fetched recently
                (Document.fetched_at >= since) |
                (Document.published_date >= since)
            )
        )
        if jurisdiction:
            q = q.filter(Document.jurisdiction == jurisdiction)
        if domain:
            q = q.filter(Document.domain == domain)

        results = []
        for doc, summ in q.order_by(Document.fetched_at.desc()).all():
            summary_fields = {
                "plain_english":   None,
                "requirements":    [],
                "recommendations": [],
                "action_items":    [],
                "deadline":        None,
                "impact_areas":    [],
                "urgency":         None,
                "relevance_score": None,
            }
            if summ:
                for k in summary_fields:
                    summary_fields[k] = getattr(summ, k)

            results.append({
                "id":             doc.id,
                "title":          doc.title,
                "source":         doc.source,
                "jurisdiction":   doc.jurisdiction,
                "doc_type":       doc.doc_type,
                "agency":         doc.agency,
                "status":         doc.status,
                "url":            doc.url,
                "published_date": doc.published_date.isoformat() if doc.published_date else None,
                "fetched_at":     doc.fetched_at.isoformat() if doc.fetched_at else None,
                "summarized":     summ is not None,
                "domain":         doc.domain or "ai",
                **summary_fields,
            })
        return results


# ── DocumentDiff CRUD ─────────────────────────────────────────────────────────

def save_diff(diff_dict: Dict[str, Any]) -> int:
    """Save a diff record. Each comparison is a new record — history is preserved."""
    with get_session() as session:
        d = DocumentDiff(**{
            k: v for k, v in diff_dict.items()
            if k != "id" and hasattr(DocumentDiff, k)
        })
        session.add(d)
        session.commit()
        session.refresh(d)
        return d.id


def diff_exists(base_id: str, new_id: str) -> bool:
    with get_session() as session:
        result = session.execute(
            text("SELECT COUNT(*) FROM document_diffs "
                 "WHERE base_document_id = :b AND new_document_id = :n"),
            {"b": base_id, "n": new_id},
        ).scalar()
        return (result or 0) > 0


def get_diffs_for_document(doc_id: str) -> List[Dict[str, Any]]:
    """All diffs where this document appears as either base or new version."""
    with get_session() as session:
        rows = session.query(DocumentDiff).filter(
            (DocumentDiff.base_document_id == doc_id) |
            (DocumentDiff.new_document_id  == doc_id)
        ).order_by(DocumentDiff.detected_at.desc()).all()
        return [_diff_to_dict(r) for r in rows]


def get_recent_diffs(days: int = 30,
                      severity: Optional[str] = None,
                      diff_type: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_session() as session:
        since = datetime.utcnow() - timedelta(days=days)
        q     = session.query(DocumentDiff).filter(DocumentDiff.detected_at >= since)
        if severity:
            q = q.filter(DocumentDiff.severity == severity)
        if diff_type:
            q = q.filter(DocumentDiff.diff_type == diff_type)
        return [_diff_to_dict(r) for r in q.order_by(DocumentDiff.detected_at.desc()).all()]


def get_unreviewed_diffs(limit: int = 50) -> List[Dict[str, Any]]:
    with get_session() as session:
        rows = (
            session.query(DocumentDiff)
            .filter(DocumentDiff.reviewed == False)          # noqa: E712
            .order_by(DocumentDiff.detected_at.desc())
            .limit(limit)
            .all()
        )
        return [_diff_to_dict(r) for r in rows]


def mark_diff_reviewed(diff_id: int) -> None:
    with get_session() as session:
        d = session.get(DocumentDiff, diff_id)
        if d:
            d.reviewed = True
            session.commit()


def _diff_to_dict(d: DocumentDiff) -> Dict[str, Any]:
    return {
        "id":                    d.id,
        "base_document_id":      d.base_document_id,
        "new_document_id":       d.new_document_id,
        "diff_type":             d.diff_type,
        "relationship_type":     d.relationship_type,
        "change_summary":        d.change_summary,
        "severity":              d.severity,
        "added_requirements":    d.added_requirements    or [],
        "removed_requirements":  d.removed_requirements  or [],
        "modified_requirements": d.modified_requirements or [],
        "definition_changes":    d.definition_changes    or [],
        "deadline_changes":      d.deadline_changes      or [],
        "penalty_changes":       d.penalty_changes       or [],
        "scope_changes":         d.scope_changes,
        "new_action_items":      d.new_action_items      or [],
        "obsolete_action_items": d.obsolete_action_items or [],
        "overall_assessment":    d.overall_assessment,
        "detected_at":           d.detected_at.isoformat() if d.detected_at else None,
        "reviewed":              d.reviewed,
    }


# ── DocumentLink CRUD ─────────────────────────────────────────────────────────

def save_link(base_doc_id: str, related_doc_id: str,
              link_type: str, notes: Optional[str] = None,
              created_by: str = "system") -> None:
    with get_session() as session:
        exists = session.execute(
            text("SELECT COUNT(*) FROM document_links "
                 "WHERE base_doc_id = :b AND related_doc_id = :r AND link_type = :t"),
            {"b": base_doc_id, "r": related_doc_id, "t": link_type},
        ).scalar()
        if exists:
            return
        session.add(DocumentLink(
            base_doc_id=base_doc_id, related_doc_id=related_doc_id,
            link_type=link_type, notes=notes, created_by=created_by,
        ))
        session.commit()


def get_links_for_document(doc_id: str) -> List[Dict[str, Any]]:
    with get_session() as session:
        rows = session.query(DocumentLink).filter(
            (DocumentLink.base_doc_id    == doc_id) |
            (DocumentLink.related_doc_id == doc_id)
        ).all()
        return [
            {
                "base_doc_id":    r.base_doc_id,
                "related_doc_id": r.related_doc_id,
                "link_type":      r.link_type,
                "notes":          r.notes,
                "created_at":     r.created_at.isoformat() if r.created_at else None,
                "created_by":     r.created_by,
            }
            for r in rows
        ]


# ── Learning tables ──────────────────────────────────────────────────────────

class FeedbackEvent(Base):
    """
    Human feedback on a document's relevance.
    Drives source quality scoring and keyword weight adjustment.
    """
    __tablename__ = "feedback_events"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    document_id      = Column(String, nullable=False)
    feedback         = Column(String, nullable=False)  # relevant|not_relevant|partially_relevant
    reason           = Column(Text)
    source           = Column(String)
    agency           = Column(String)
    jurisdiction     = Column(String)
    doc_type         = Column(String)
    matched_keywords = Column(JSON)    # list[str] — keywords that triggered the fetch
    claude_score     = Column(Float)   # Claude's original relevance score
    user             = Column(String, default="user")
    recorded_at      = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_fb_document",    "document_id"),
        Index("ix_fb_source",      "source"),
        Index("ix_fb_feedback",    "feedback"),
        Index("ix_fb_recorded_at", "recorded_at"),
    )


class SourceProfile(Base):
    """
    Rolling quality profile for each data source and agency.
    Tracks positive/negative feedback counts and computed quality score.
    """
    __tablename__ = "source_profiles"

    source_key     = Column(String, primary_key=True)  # source name or "agency::<name>"
    profile_json   = Column(JSON, nullable=False)
    last_updated   = Column(DateTime, default=datetime.utcnow)


class KeywordWeights(Base):
    """
    Learned per-keyword weights for the pre-filter relevance score.
    Weights start at 1.0 and drift based on feedback.
    """
    __tablename__ = "keyword_weights"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    weights_json = Column(JSON, nullable=False)   # {keyword: float}
    updated_at   = Column(DateTime, default=datetime.utcnow)


class PromptAdaptation(Base):
    """
    Domain-specific additions to the Claude interpretation prompt,
    generated when false-positive patterns are detected.
    """
    __tablename__ = "prompt_adaptations"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    match_keys   = Column(JSON)     # {source, agency, jurisdiction} to match
    instruction  = Column(Text)     # the NOTE: instruction to prepend
    basis        = Column(Text)     # how many examples drove this
    active       = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)


class RegulatoryHorizon(Base):
    """
    Forward-looking regulatory items — things planned or advancing but not
    yet published. Populated by HorizonAgent from regulatory calendars.
    """
    __tablename__ = "regulatory_horizon"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    source           = Column(String, nullable=False)
    external_id      = Column(String, nullable=False)
    jurisdiction     = Column(String, nullable=False)
    title            = Column(Text,   nullable=False)
    description      = Column(Text)
    agency           = Column(String)
    stage            = Column(String)
    anticipated_date = Column(DateTime)
    url              = Column(Text)
    ai_score         = Column(Float, default=0.0)
    fetched_at       = Column(DateTime, default=datetime.utcnow)
    dismissed        = Column(Boolean,  default=False)
    domain           = Column(String, default="ai")   # ai | privacy | both

    __table_args__ = (
        Index("ix_horizon_source_eid",   "source", "external_id", unique=True),
        Index("ix_horizon_jurisdiction", "jurisdiction"),
        Index("ix_horizon_anticipated",  "anticipated_date"),
        Index("ix_horizon_domain",       "domain"),
    )


class TrendSnapshot(Base):
    """
    Cached output from TrendAgent — one row per snapshot_type.
    Recomputed once per day; loaded instantly for the Trends view.
    """
    __tablename__ = "trend_snapshots"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_type = Column(String, nullable=False, unique=True)  # velocity | heatmap | alerts
    data_json     = Column(JSON)
    computed_at   = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_trend_type", "snapshot_type"),)


class ObligationRegisterCache(Base):
    """
    Cached results from the ConsolidationAgent.
    Keyed by a hash of (jurisdictions, mode).
    """
    __tablename__ = "obligation_register_cache"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    cache_key    = Column(String, nullable=False, unique=True)
    jurisdictions= Column(JSON)      # list[str]
    mode         = Column(String)    # fast | full
    register_json= Column(JSON)      # list of consolidated obligation dicts
    item_count   = Column(Integer, default=0)
    computed_at  = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_orc_cache_key", "cache_key"),)


class CompanyProfile(Base):
    """
    Stores a company's profile for gap analysis.
    Multiple profiles are supported (e.g. per business unit or product line).
    """
    __tablename__ = "company_profiles"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    name                    = Column(String, nullable=False)   # e.g. "ACME Corp — Healthcare Division"
    industry_sector         = Column(String)
    company_size            = Column(String)
    operating_jurisdictions = Column(JSON)    # list[str]
    ai_systems              = Column(JSON)    # list[AISytem dicts]
    current_practices       = Column(JSON)    # governance practices dict
    existing_certifications = Column(JSON)    # list[str]
    primary_concerns        = Column(Text)
    recent_changes          = Column(Text)
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_profile_name", "name"),
    )


class GapAnalysis(Base):
    """
    Stores the result of a gap analysis run against a company profile.
    History is preserved — each run produces a new record.
    """
    __tablename__ = "gap_analyses"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    profile_id       = Column(Integer, nullable=False)
    profile_name     = Column(String)
    jurisdictions    = Column(JSON)           # list[str] — scope of this run
    docs_examined    = Column(Integer, default=0)
    applicable_count = Column(Integer, default=0)
    gap_count        = Column(Integer, default=0)
    critical_count   = Column(Integer, default=0)
    posture_score    = Column(Integer, default=0)   # 0-100
    scope_json       = Column(JSON)           # Pass 1 output
    gaps_json        = Column(JSON)           # Pass 2 output
    model_used       = Column(String)
    generated_at     = Column(DateTime, default=datetime.utcnow)
    starred          = Column(Boolean, default=False)
    notes            = Column(Text)

    __table_args__ = (
        Index("ix_gap_profile_id",   "profile_id"),
        Index("ix_gap_generated_at", "generated_at"),
    )


class ThematicSynthesis(Base):
    """
    Stores the result of a cross-document thematic synthesis run.
    One record per (topic_key, generated_at) pair — history is preserved.
    """
    __tablename__ = "thematic_syntheses"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    topic_key        = Column(String, nullable=False)   # stable hash of topic + jurisdictions
    topic            = Column(Text, nullable=False)
    jurisdictions    = Column(JSON)                     # list[str]
    docs_used        = Column(Integer, default=0)
    doc_ids          = Column(JSON)                     # list[str]
    synthesis_json   = Column(JSON)                     # full synthesis output from Claude
    conflicts_json   = Column(JSON)                     # conflict detection output from Claude
    model_used       = Column(String)
    generated_at     = Column(DateTime, default=datetime.utcnow)
    starred          = Column(Boolean, default=False)   # user can star important syntheses
    notes            = Column(Text)                     # user annotations

    __table_args__ = (
        Index("ix_synth_topic_key",    "topic_key"),
        Index("ix_synth_generated_at", "generated_at"),
    )


class FetchHistory(Base):
    """
    Log of every fetch operation, used for adaptive scheduling.
    """
    __tablename__ = "fetch_history"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    source      = Column(String, nullable=False)
    new_count   = Column(Integer, default=0)
    total_count = Column(Integer, default=0)
    fetched_at  = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_fh_source",     "source"),
        Index("ix_fh_fetched_at", "fetched_at"),
    )


class QAPassage(Base):
    """
    A retrievable passage from the document corpus or a baseline file.

    The Q&A system chunks all documents and baselines into passages of
    ~800 tokens. Each passage stores enough metadata to cite its source
    precisely in a Q&A response.
    """
    __tablename__ = "qa_passages"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    source_type    = Column(String, nullable=False)  # document | baseline
    source_id      = Column(String, nullable=False)  # document id or baseline id
    source_title   = Column(Text)
    jurisdiction   = Column(String)
    chunk_index    = Column(Integer, default=0)      # passage number within source
    chunk_total    = Column(Integer, default=1)      # total passages for this source
    section_label  = Column(String)                  # e.g. "Key Definitions", "Article 5"
    text           = Column(Text, nullable=False)    # the passage text
    text_hash      = Column(String)                  # md5 for dedup
    indexed_at     = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_qap_source_id",   "source_id"),
        Index("ix_qap_source_type", "source_type"),
        Index("ix_qap_jurisdiction","jurisdiction"),
    )


class QASession(Base):
    """
    Stores Q&A conversation turns for history and re-use.
    """
    __tablename__ = "qa_sessions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    question        = Column(Text, nullable=False)
    answer          = Column(Text)
    citations       = Column(JSON)    # list of {source_id, source_title, section, excerpt}
    passage_ids     = Column(JSON)    # list of QAPassage.id used
    follow_ups      = Column(JSON)    # list of suggested follow-up questions
    model_used      = Column(String)
    retrieval_count = Column(Integer, default=0)
    asked_at        = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_qas_asked_at", "asked_at"),
    )


# ── Learning CRUD ─────────────────────────────────────────────────────────────

def save_feedback(fb_dict: Dict[str, Any]) -> int:
    with get_session() as session:
        ev = FeedbackEvent(**{k: v for k, v in fb_dict.items() if hasattr(FeedbackEvent, k)})
        session.add(ev)
        session.commit()
        session.refresh(ev)
        return ev.id


def get_recent_feedback(days: int = 30, document_id: Optional[str] = None) -> List[Dict]:
    with get_session() as session:
        since = datetime.utcnow() - timedelta(days=days)
        q     = session.query(FeedbackEvent).filter(FeedbackEvent.recorded_at >= since)
        if document_id:
            q = q.filter(FeedbackEvent.document_id == document_id)
        rows  = q.order_by(FeedbackEvent.recorded_at.desc()).all()
        return [
            {
                "id":               r.id,
                "document_id":      r.document_id,
                "feedback":         r.feedback,
                "reason":           r.reason,
                "source":           r.source,
                "agency":           r.agency,
                "jurisdiction":     r.jurisdiction,
                "doc_type":         r.doc_type,
                "matched_keywords": r.matched_keywords or [],
                "claude_score":     r.claude_score,
                "recorded_at":      r.recorded_at.isoformat() if r.recorded_at else None,
            }
            for r in rows
        ]


def count_feedback_by_type() -> Dict[str, int]:
    with get_session() as session:
        from sqlalchemy import func
        rows = session.query(
            FeedbackEvent.feedback, func.count(FeedbackEvent.id)
        ).group_by(FeedbackEvent.feedback).all()
        return {fb: count for fb, count in rows}


def get_recent_false_positives(source: str, limit: int = 20) -> List[Dict]:
    with get_session() as session:
        since = datetime.utcnow() - timedelta(days=60)
        rows  = (
            session.query(FeedbackEvent)
            .filter(
                FeedbackEvent.feedback == "not_relevant",
                FeedbackEvent.source   == source,
                FeedbackEvent.recorded_at >= since,
            )
            .order_by(FeedbackEvent.recorded_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "document_id": r.document_id,
                "reason":      r.reason,
                "agency":      r.agency,
                "title":       None,   # caller can join if needed
            }
            for r in rows
        ]


def count_recent_false_positives(source: str, days: int = 30) -> int:
    with get_session() as session:
        since = datetime.utcnow() - timedelta(days=days)
        return (
            session.query(FeedbackEvent)
            .filter(
                FeedbackEvent.feedback == "not_relevant",
                FeedbackEvent.source   == source,
                FeedbackEvent.recorded_at >= since,
            )
            .count()
        )


def get_false_positive_patterns() -> List[Dict]:
    """Return source+agency combinations with high false-positive rates."""
    with get_session() as session:
        from sqlalchemy import func
        rows = (
            session.query(
                FeedbackEvent.source,
                FeedbackEvent.agency,
                func.count(FeedbackEvent.id).label("fp_count"),
            )
            .filter(FeedbackEvent.feedback == "not_relevant")
            .group_by(FeedbackEvent.source, FeedbackEvent.agency)
            .having(func.count(FeedbackEvent.id) >= 3)
            .order_by(func.count(FeedbackEvent.id).desc())
            .all()
        )
        return [{"source": r.source, "agency": r.agency, "fp_count": r.fp_count} for r in rows]


def is_known_false_positive_pattern(doc: Dict) -> bool:
    """Quick check: is this source+agency combination a known bad pattern?"""
    with get_session() as session:
        count = (
            session.query(FeedbackEvent)
            .filter(
                FeedbackEvent.feedback == "not_relevant",
                FeedbackEvent.source   == doc.get("source", ""),
                FeedbackEvent.agency   == (doc.get("agency") or ""),
            )
            .count()
        )
        return count >= 8   # 8 confirmed false positives = auto-block pattern


# ── Source profiles ───────────────────────────────────────────────────────────

def get_source_profile(source_key: str) -> Optional[Dict]:
    with get_session() as session:
        row = session.get(SourceProfile, source_key)
        return row.profile_json if row else None


def upsert_source_profile(source_key: str, profile: Dict) -> None:
    with get_session() as session:
        row = session.get(SourceProfile, source_key)
        if row:
            row.profile_json = profile
            row.last_updated = datetime.utcnow()
        else:
            session.add(SourceProfile(
                source_key   = source_key,
                profile_json = profile,
                last_updated = datetime.utcnow(),
            ))
        session.commit()


def get_all_source_profiles() -> Dict[str, Dict]:
    with get_session() as session:
        rows = session.query(SourceProfile).all()
        return {r.source_key: r.profile_json for r in rows}


# ── Keyword weights ───────────────────────────────────────────────────────────

def get_keyword_weights() -> Dict[str, float]:
    with get_session() as session:
        row = session.query(KeywordWeights).order_by(
            KeywordWeights.updated_at.desc()
        ).first()
        return row.weights_json if row else {}


def save_keyword_weights(weights: Dict[str, float]) -> None:
    with get_session() as session:
        # Single row — always replace
        session.query(KeywordWeights).delete()
        session.add(KeywordWeights(weights_json=weights, updated_at=datetime.utcnow()))
        session.commit()


# ── Prompt adaptations ────────────────────────────────────────────────────────

def get_prompt_adaptations(active_only: bool = True) -> List[Dict]:
    with get_session() as session:
        q = session.query(PromptAdaptation)
        if active_only:
            q = q.filter(PromptAdaptation.active == True)   # noqa: E712
        rows = q.order_by(PromptAdaptation.created_at.desc()).all()
        return [
            {
                "id":          r.id,
                "match_keys":  r.match_keys,
                "instruction": r.instruction,
                "basis":       r.basis,
                "active":      r.active,
                "created_at":  r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def save_prompt_adaptation(adapt_dict: Dict) -> int:
    with get_session() as session:
        pa = PromptAdaptation(**{k: v for k, v in adapt_dict.items() if hasattr(PromptAdaptation, k)})
        session.add(pa)
        session.commit()
        session.refresh(pa)
        return pa.id


def toggle_prompt_adaptation(adapt_id: int, active: bool) -> None:
    with get_session() as session:
        row = session.get(PromptAdaptation, adapt_id)
        if row:
            row.active = active
            session.commit()


# ── Fetch history ─────────────────────────────────────────────────────────────

def log_fetch_event(source: str, new_count: int, total_count: int) -> None:
    with get_session() as session:
        session.add(FetchHistory(
            source=source, new_count=new_count,
            total_count=total_count, fetched_at=datetime.utcnow(),
        ))
        session.commit()


def get_fetch_history(days: int = 60) -> List[Dict]:
    with get_session() as session:
        since = datetime.utcnow() - timedelta(days=days)
        rows  = (
            session.query(FetchHistory)
            .filter(FetchHistory.fetched_at >= since)
            .order_by(FetchHistory.fetched_at.desc())
            .all()
        )
        return [
            {
                "source":      r.source,
                "new_count":   r.new_count,
                "total_count": r.total_count,
                "fetched_at":  r.fetched_at.isoformat() if r.fetched_at else None,
            }
            for r in rows
        ]


# ── Document review status helpers ───────────────────────────────────────────

def get_document_review_statuses(doc_ids: List[str]) -> Dict[str, str]:
    """
    Return a dict of {document_id: feedback} for the given doc IDs.
    Only the most recent feedback per document is returned.
    Documents with no feedback are absent from the dict.
    """
    if not doc_ids:
        return {}
    with get_session() as session:
        # Most recent feedback per document
        from sqlalchemy import func
        latest = (
            session.query(
                FeedbackEvent.document_id,
                FeedbackEvent.feedback,
                FeedbackEvent.recorded_at,
            )
            .filter(FeedbackEvent.document_id.in_(doc_ids))
            .order_by(
                FeedbackEvent.document_id,
                FeedbackEvent.recorded_at.desc(),
            )
            .all()
        )
        seen: Dict[str, str] = {}
        for doc_id, feedback, _ in latest:
            if doc_id not in seen:
                seen[doc_id] = feedback
        return seen


def get_archived_documents(days: int = 3650,
                            jurisdiction: Optional[str] = None,
                            search: Optional[str] = None,
                            page: int = 1,
                            page_size: int = 30) -> Dict[str, Any]:
    """
    Return paginated list of documents marked not_relevant.
    """
    # Get all not_relevant document IDs
    with get_session() as session:
        q = session.query(FeedbackEvent.document_id).filter(
            FeedbackEvent.feedback == "not_relevant"
        ).distinct()
        archived_ids = {row[0] for row in q.all()}

    if not archived_ids:
        return {"total": 0, "page": page, "page_size": page_size, "pages": 0, "items": []}

    since     = datetime.utcnow() - timedelta(days=days)
    all_items = []

    with get_session() as session:
        q = (
            session.query(Document, Summary)
            .outerjoin(Summary, Document.id == Summary.document_id)
            .filter(Document.id.in_(archived_ids))
            .filter(
                (Document.fetched_at    >= since) |
                (Document.published_date >= since)
            )
        )
        if jurisdiction:
            q = q.filter(Document.jurisdiction == jurisdiction)

        for doc, summ in q.order_by(Document.fetched_at.desc()).all():
            d = _doc_to_dict(doc)
            if summ:
                d.update({
                    "plain_english":   summ.plain_english,
                    "urgency":         summ.urgency,
                    "relevance_score": summ.relevance_score,
                    "requirements":    summ.requirements,
                    "impact_areas":    summ.impact_areas,
                    "deadline":        summ.deadline,
                })
            d["review_status"] = "not_relevant"
            if search:
                q_lower = search.lower()
                if not (q_lower in (d.get("title") or "").lower()
                        or q_lower in (d.get("plain_english") or "").lower()):
                    continue
            all_items.append(d)

    total = len(all_items)
    start = (page - 1) * page_size
    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     max(1, (total + page_size - 1) // page_size),
        "items":     all_items[start:start + page_size],
    }


# ── Regulatory horizon CRUD ──────────────────────────────────────────────────

def upsert_horizon_item(item: Dict[str, Any]) -> bool:
    """
    Insert or update a horizon item. Returns True if it was new.
    Deduplicates by (source, external_id).
    """
    with get_session() as session:
        existing = session.query(RegulatoryHorizon).filter_by(
            source      = item["source"],
            external_id = item["external_id"],
        ).first()

        if existing:
            # Update anticipated date and score if changed
            existing.anticipated_date = item.get("anticipated_date")
            existing.ai_score         = item.get("ai_score", 0)
            existing.fetched_at       = datetime.utcnow()
            session.commit()
            return False

        row = RegulatoryHorizon(
            source           = item["source"],
            external_id      = item["external_id"],
            jurisdiction     = item["jurisdiction"],
            title            = item["title"],
            description      = item.get("description") or "",
            agency           = item.get("agency") or "",
            stage            = item.get("stage") or "planned",
            anticipated_date = item.get("anticipated_date"),
            url              = item.get("url") or "",
            ai_score         = item.get("ai_score", 0),
            fetched_at       = datetime.utcnow(),
            dismissed        = False,
        )
        session.add(row)
        session.commit()
        return True


def get_horizon_items(days_ahead: int = 365,
                       jurisdiction: Optional[str] = None,
                       stage: Optional[str] = None,
                       domain: Optional[str] = None,
                       include_past: bool = False,
                       limit: int = 200) -> List[Dict[str, Any]]:
    """Return upcoming horizon items ordered by anticipated date."""
    with get_session() as session:
        q = session.query(RegulatoryHorizon).filter_by(dismissed=False)

        if not include_past:
            cutoff_past = datetime.utcnow() - timedelta(days=30)
            q = q.filter(
                (RegulatoryHorizon.anticipated_date == None) |
                (RegulatoryHorizon.anticipated_date >= cutoff_past)
            )

        if days_ahead:
            cutoff_future = datetime.utcnow() + timedelta(days=days_ahead)
            q = q.filter(
                (RegulatoryHorizon.anticipated_date == None) |
                (RegulatoryHorizon.anticipated_date <= cutoff_future)
            )

        if jurisdiction:
            q = q.filter(RegulatoryHorizon.jurisdiction == jurisdiction)

        if stage:
            q = q.filter(RegulatoryHorizon.stage == stage)

        if domain:
            q = q.filter(RegulatoryHorizon.domain == domain)

        rows = q.order_by(
            RegulatoryHorizon.anticipated_date.asc().nullslast(),
            RegulatoryHorizon.ai_score.desc(),
        ).limit(limit).all()

        return [_horizon_to_dict(r) for r in rows]


def dismiss_horizon_item(item_id: int) -> None:
    with get_session() as session:
        row = session.get(RegulatoryHorizon, item_id)
        if row:
            row.dismissed = True
            session.commit()


def get_horizon_stats() -> Dict[str, Any]:
    with get_session() as session:
        total    = session.query(RegulatoryHorizon).filter_by(dismissed=False).count()
        upcoming = session.query(RegulatoryHorizon).filter(
            RegulatoryHorizon.dismissed        == False,
            RegulatoryHorizon.anticipated_date != None,
            RegulatoryHorizon.anticipated_date >= datetime.utcnow(),
            RegulatoryHorizon.anticipated_date <= datetime.utcnow() + timedelta(days=90),
        ).count()
        by_jur: Dict[str, int] = {}
        for row in session.query(RegulatoryHorizon).filter_by(dismissed=False).all():
            jur = row.jurisdiction or "Unknown"
            by_jur[jur] = by_jur.get(jur, 0) + 1
        return {
            "total":            total,
            "upcoming_90_days": upcoming,
            "by_jurisdiction":  by_jur,
        }


def _horizon_to_dict(row: RegulatoryHorizon) -> Dict[str, Any]:
    return {
        "id":               row.id,
        "source":           row.source,
        "external_id":      row.external_id,
        "jurisdiction":     row.jurisdiction,
        "title":            row.title,
        "description":      row.description,
        "agency":           row.agency,
        "stage":            row.stage,
        "anticipated_date": row.anticipated_date.isoformat() if row.anticipated_date else None,
        "url":              row.url,
        "ai_score":         row.ai_score,
        "fetched_at":       row.fetched_at.isoformat() if row.fetched_at else None,
        "dismissed":        row.dismissed,
    }


# ── Obligation register cache CRUD ───────────────────────────────────────────

def save_register_cache(cache_key: str, register: List[Dict[str, Any]]) -> None:
    with get_session() as session:
        row = session.query(ObligationRegisterCache).filter_by(
            cache_key=cache_key
        ).first()
        if row:
            row.register_json = register
            row.item_count    = len(register)
            row.computed_at   = datetime.utcnow()
        else:
            session.add(ObligationRegisterCache(
                cache_key     = cache_key,
                register_json = register,
                item_count    = len(register),
                computed_at   = datetime.utcnow(),
            ))
        session.commit()


def get_register_cache(cache_key: str,
                        max_age_hours: int = 24) -> Optional[List[Dict]]:
    with get_session() as session:
        since = datetime.utcnow() - timedelta(hours=max_age_hours)
        row   = session.query(ObligationRegisterCache).filter(
            ObligationRegisterCache.cache_key   == cache_key,
            ObligationRegisterCache.computed_at >= since,
        ).first()
        return row.register_json if row else None


def delete_register_cache(jurisdictions: Optional[List[str]] = None) -> int:
    """Delete cached register entries. Pass None to clear all."""
    with get_session() as session:
        q = session.query(ObligationRegisterCache)
        deleted = q.delete()
        session.commit()
        return deleted


# ── Company profile CRUD ─────────────────────────────────────────────────────

def save_profile(profile_dict: Dict[str, Any]) -> int:
    """Create or update a company profile. Returns the profile ID."""
    with get_session() as session:
        profile_id = profile_dict.get("id")
        if profile_id:
            row = session.get(CompanyProfile, profile_id)
            if row:
                for k, v in profile_dict.items():
                    if hasattr(row, k) and k != "id":
                        setattr(row, k, v)
                row.updated_at = datetime.utcnow()
                session.commit()
                return row.id
        # New profile
        row = CompanyProfile(**{
            k: v for k, v in profile_dict.items()
            if hasattr(CompanyProfile, k) and k != "id"
        })
        row.created_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def get_profile(profile_id: int) -> Optional[Dict[str, Any]]:
    with get_session() as session:
        row = session.get(CompanyProfile, profile_id)
        return _profile_to_dict(row) if row else None


def list_profiles() -> List[Dict[str, Any]]:
    with get_session() as session:
        rows = session.query(CompanyProfile).order_by(
            CompanyProfile.updated_at.desc()
        ).all()
        return [_profile_to_dict(r) for r in rows]


def delete_profile(profile_id: int) -> None:
    with get_session() as session:
        row = session.get(CompanyProfile, profile_id)
        if row:
            session.delete(row)
            session.commit()


def _profile_to_dict(row: CompanyProfile) -> Dict[str, Any]:
    return {
        "id":                      row.id,
        "name":                    row.name,
        "industry_sector":         row.industry_sector,
        "company_size":            row.company_size,
        "operating_jurisdictions": row.operating_jurisdictions or [],
        "ai_systems":              row.ai_systems or [],
        "current_practices":       row.current_practices or {},
        "existing_certifications": row.existing_certifications or [],
        "primary_concerns":        row.primary_concerns,
        "recent_changes":          row.recent_changes,
        "created_at":              row.created_at.isoformat() if row.created_at else None,
        "updated_at":              row.updated_at.isoformat() if row.updated_at else None,
    }


# ── Gap analysis CRUD ─────────────────────────────────────────────────────────

def save_gap_analysis(result: Dict[str, Any]) -> int:
    """Persist a gap analysis result. Returns the new row ID."""
    with get_session() as session:
        row = GapAnalysis(
            profile_id       = result.get("profile_id"),
            profile_name     = result.get("profile_name"),
            jurisdictions    = result.get("jurisdictions", []),
            docs_examined    = result.get("docs_examined", 0),
            applicable_count = result.get("applicable_count", 0),
            gap_count        = result.get("gap_count", 0),
            critical_count   = result.get("critical_count", 0),
            posture_score    = result.get("posture_score", 0),
            scope_json       = result.get("scope"),
            gaps_json        = result.get("gaps_result"),
            model_used       = result.get("model_used", ""),
            generated_at     = datetime.utcnow(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def get_gap_analysis(analysis_id: int) -> Optional[Dict[str, Any]]:
    with get_session() as session:
        row = session.get(GapAnalysis, analysis_id)
        return _gap_to_dict(row) if row else None


def list_gap_analyses(profile_id: Optional[int] = None,
                      limit: int = 20) -> List[Dict[str, Any]]:
    with get_session() as session:
        q = session.query(GapAnalysis)
        if profile_id:
            q = q.filter(GapAnalysis.profile_id == profile_id)
        rows = q.order_by(GapAnalysis.generated_at.desc()).limit(limit).all()
        return [_gap_to_dict(r, summary_only=True) for r in rows]


def star_gap_analysis(analysis_id: int, starred: bool = True) -> None:
    with get_session() as session:
        row = session.get(GapAnalysis, analysis_id)
        if row:
            row.starred = starred
            session.commit()


def annotate_gap_analysis(analysis_id: int, notes: str) -> None:
    with get_session() as session:
        row = session.get(GapAnalysis, analysis_id)
        if row:
            row.notes = notes
            session.commit()


def _gap_to_dict(row: GapAnalysis,
                  summary_only: bool = False) -> Dict[str, Any]:
    base = {
        "id":               row.id,
        "profile_id":       row.profile_id,
        "profile_name":     row.profile_name,
        "jurisdictions":    row.jurisdictions or [],
        "docs_examined":    row.docs_examined,
        "applicable_count": row.applicable_count,
        "gap_count":        row.gap_count,
        "critical_count":   row.critical_count,
        "posture_score":    row.posture_score,
        "model_used":       row.model_used,
        "generated_at":     row.generated_at.isoformat() if row.generated_at else None,
        "starred":          row.starred,
        "notes":            row.notes,
    }
    if not summary_only:
        base["scope"]       = row.scope_json
        base["gaps_result"] = row.gaps_json
    return base


# ── PDF metadata CRUD ────────────────────────────────────────────────────────

def save_pdf_metadata(meta: Dict[str, Any]) -> int:
    """Insert or replace a PDF metadata record."""
    with get_session() as session:
        # Upsert by document_id
        existing = (
            session.query(PdfMetadata)
            .filter_by(document_id=meta["document_id"])
            .first()
        )
        if existing:
            for k, v in meta.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            session.commit()
            return existing.id
        row = PdfMetadata(**{k: v for k, v in meta.items() if hasattr(PdfMetadata, k)})
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def get_pdf_metadata(document_id: str) -> Optional[Dict[str, Any]]:
    with get_session() as session:
        row = (
            session.query(PdfMetadata)
            .filter_by(document_id=document_id)
            .first()
        )
        return _pdf_meta_to_dict(row) if row else None


def get_all_pdf_metadata() -> List[Dict[str, Any]]:
    with get_session() as session:
        rows = session.query(PdfMetadata).order_by(PdfMetadata.extracted_at.desc()).all()
        return [_pdf_meta_to_dict(r) for r in rows]


def _pdf_meta_to_dict(row: PdfMetadata) -> Dict[str, Any]:
    return {
        "id":                row.id,
        "document_id":       row.document_id,
        "pdf_path":          row.pdf_path,
        "pdf_url":           row.pdf_url,
        "page_count":        row.page_count,
        "word_count":        row.word_count,
        "extraction_method": row.extraction_method,
        "extracted_at":      row.extracted_at.isoformat() if row.extracted_at else None,
        "origin":            row.origin,
    }


# ── Synthesis CRUD ────────────────────────────────────────────────────────────

def save_synthesis(result: Dict[str, Any]) -> int:
    """Persist a thematic synthesis result. Returns the new row ID."""
    with get_session() as session:
        row = ThematicSynthesis(
            topic_key      = result.get("topic_key", ""),
            topic          = result.get("topic", ""),
            jurisdictions  = result.get("jurisdictions", []),
            docs_used      = result.get("docs_used", 0),
            doc_ids        = result.get("doc_ids", []),
            synthesis_json = result.get("synthesis"),
            conflicts_json = result.get("conflicts"),
            model_used     = result.get("model_used", ""),
            generated_at   = datetime.utcnow(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def get_existing_synthesis(topic_key: str, max_age_days: int = 7) -> Optional[Dict[str, Any]]:
    """Return the most recent synthesis for a topic_key if it is fresh enough."""
    with get_session() as session:
        since = datetime.utcnow() - timedelta(days=max_age_days)
        row   = (
            session.query(ThematicSynthesis)
            .filter(
                ThematicSynthesis.topic_key    == topic_key,
                ThematicSynthesis.generated_at >= since,
            )
            .order_by(ThematicSynthesis.generated_at.desc())
            .first()
        )
        return _synthesis_to_dict(row) if row else None


def get_synthesis_by_id(synthesis_id: int) -> Optional[Dict[str, Any]]:
    with get_session() as session:
        row = session.get(ThematicSynthesis, synthesis_id)
        return _synthesis_to_dict(row) if row else None


def get_recent_syntheses(limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent synthesis records (summary only — no full JSON)."""
    with get_session() as session:
        rows = (
            session.query(ThematicSynthesis)
            .order_by(ThematicSynthesis.generated_at.desc())
            .limit(limit)
            .all()
        )
        return [_synthesis_to_dict(r, summary_only=True) for r in rows]


def star_synthesis(synthesis_id: int, starred: bool = True) -> None:
    with get_session() as session:
        row = session.get(ThematicSynthesis, synthesis_id)
        if row:
            row.starred = starred
            session.commit()


def annotate_synthesis(synthesis_id: int, notes: str) -> None:
    with get_session() as session:
        row = session.get(ThematicSynthesis, synthesis_id)
        if row:
            row.notes = notes
            session.commit()


def delete_synthesis(synthesis_id: int) -> None:
    with get_session() as session:
        row = session.get(ThematicSynthesis, synthesis_id)
        if row:
            session.delete(row)
            session.commit()


def _synthesis_to_dict(row: ThematicSynthesis,
                        summary_only: bool = False) -> Dict[str, Any]:
    base = {
        "id":           row.id,
        "topic_key":    row.topic_key,
        "topic":        row.topic,
        "jurisdictions": row.jurisdictions or [],
        "docs_used":    row.docs_used,
        "model_used":   row.model_used,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "starred":      row.starred,
        "notes":        row.notes,
        "has_conflicts": bool(row.conflicts_json),
        "conflict_count": (
            len(row.conflicts_json.get("conflicts", []))
            if row.conflicts_json else 0
        ),
    }
    if not summary_only:
        base["synthesis"]  = row.synthesis_json
        base["conflicts"]  = row.conflicts_json
        base["doc_ids"]    = row.doc_ids or []
    return base


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats() -> Dict[str, Any]:
    with get_session() as session:
        total_docs      = session.query(Document).count()
        total_summaries = session.query(Summary).count()
        federal_docs    = session.query(Document).filter_by(jurisdiction="Federal").count()
        total_diffs     = session.query(DocumentDiff).count()
        unreviewed      = session.query(DocumentDiff).filter_by(reviewed=False).count()
        critical_diffs  = session.query(DocumentDiff).filter_by(severity="Critical").count()
        high_diffs      = session.query(DocumentDiff).filter_by(severity="High").count()
        total_feedback  = session.query(FeedbackEvent).count()
        not_relevant    = session.query(FeedbackEvent).filter_by(feedback="not_relevant").count()
        adaptations     = session.query(PromptAdaptation).filter_by(active=True).count()
        total_syntheses = session.query(ThematicSynthesis).count()
        total_pdfs      = session.query(PdfMetadata).count()
        pdf_manual      = session.query(PdfMetadata).filter_by(origin="pdf_manual").count()
        pdf_auto        = session.query(PdfMetadata).filter_by(origin="pdf_auto").count()
        total_profiles  = session.query(CompanyProfile).count()
        total_analyses  = session.query(GapAnalysis).count()
        trend_snapshots = session.query(TrendSnapshot).count()
        horizon_items   = session.query(RegulatoryHorizon).filter_by(dismissed=False).count()
        # Per-domain document counts
        ai_docs      = session.query(Document).filter(
            Document.domain.in_(["ai", "both"])
        ).count()
        privacy_docs = session.query(Document).filter(
            Document.domain.in_(["privacy", "both"])
        ).count()
        return {
            "total_documents":     total_docs,
            "total_summaries":     total_summaries,
            "federal_documents":   federal_docs,
            "state_documents":     total_docs - federal_docs,
            "pending_summaries":   total_docs - total_summaries,
            "total_diffs":         total_diffs,
            "unreviewed_diffs":    unreviewed,
            "critical_diffs":      critical_diffs,
            "high_severity_diffs": high_diffs,
            "total_feedback":      total_feedback,
            "false_positives":     not_relevant,
            "prompt_adaptations":  adaptations,
            "total_syntheses":     total_syntheses,
            "total_pdfs":          total_pdfs,
            "pdf_manual":          pdf_manual,
            "pdf_auto":            pdf_auto,
            "company_profiles":    total_profiles,
            "gap_analyses":        total_analyses,
            "trend_snapshots":     trend_snapshots,
            "horizon_items":       horizon_items,
            "ai_documents":        ai_docs,
            "privacy_documents":   privacy_docs,
        }


class KnowledgeGraphEdge(Base):
    """
    A typed, evidenced edge in the regulatory knowledge graph.

    Source and target can be either baseline IDs or document IDs.
    node_type distinguishes them so the graph renderer can style appropriately.

    Edge types
    ----------
    genealogical  — one regulation was modelled on or inspired by another
    semantic      — two regulations share a concept (bias, transparency, etc.)
    implements    — a document implements/operationalises a baseline
    amends        — a document amends a prior document or baseline
    cross_ref     — explicit cross-reference declared in a baseline file
    conflict      — the two regulations impose conflicting requirements
    """
    __tablename__ = "knowledge_graph_edges"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    source_id      = Column(String, nullable=False)
    source_type    = Column(String, nullable=False)   # baseline | document
    target_id      = Column(String, nullable=False)
    target_type    = Column(String, nullable=False)   # baseline | document
    edge_type      = Column(String, nullable=False)   # see docstring
    concept        = Column(String)                   # for semantic edges
    evidence       = Column(Text)                     # why this edge exists
    strength       = Column(Float, default=1.0)       # 0–1 relevance/confidence
    detected_by    = Column(String, default="system") # system | user
    created_at     = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_kge_source",    "source_id"),
        Index("ix_kge_target",    "target_id"),
        Index("ix_kge_edge_type", "edge_type"),
    )


class EnforcementAction(Base):
    """
    A regulatory enforcement action, court case, or litigation notice
    related to AI systems.

    Covers: FTC consent orders, SEC litigation releases, CFPB enforcement,
    EEOC press releases, UK ICO enforcement, DOJ civil rights actions,
    CourtListener federal court opinions/dockets.

    action_type values:
      enforcement   — agency enforcement action / consent order / penalty
      litigation    — active court case (complaint filed, not yet resolved)
      opinion       — court opinion / judgment
      settlement    — case resolved by settlement
      guidance      — enforcement-related guidance (EEOC technical assistance, etc.)
    """
    __tablename__ = "enforcement_actions"

    id               = Column(String, primary_key=True)
    source           = Column(String, nullable=False)
    action_type      = Column(String, nullable=False)
    title            = Column(Text, nullable=False)
    url              = Column(Text)
    published_date   = Column(DateTime)
    agency           = Column(String)
    jurisdiction     = Column(String)
    respondent       = Column(Text)
    summary          = Column(Text)
    full_text        = Column(Text)
    related_regs     = Column(JSON)
    outcome          = Column(String)
    penalty_amount   = Column(String)
    ai_concepts      = Column(JSON)
    relevance_score  = Column(Float, default=0.0)
    fetched_at       = Column(DateTime, default=datetime.utcnow)
    raw_json         = Column(JSON)
    domain           = Column(String, default="ai")   # ai | privacy | both

    __table_args__ = (
        Index("ix_ea_source",     "source"),
        Index("ix_ea_type",       "action_type"),
        Index("ix_ea_jur",        "jurisdiction"),
        Index("ix_ea_published",  "published_date"),
        Index("ix_ea_domain",     "domain"),
    )


# ── Enforcement Action CRUD ───────────────────────────────────────────────────

def upsert_enforcement_action(action: dict) -> bool:
    """Insert or update an enforcement action. Returns True if new."""
    with get_session() as session:
        existing = session.get(EnforcementAction, action["id"])
        if existing:
            for k, v in action.items():
                if hasattr(existing, k) and k != "id":
                    setattr(existing, k, v)
            session.commit()
            return False
        session.add(EnforcementAction(**{
            k: v for k, v in action.items()
            if hasattr(EnforcementAction, k)
        }))
        session.commit()
        return True


def get_enforcement_actions(
    jurisdiction: Optional[str]  = None,
    source:       Optional[str]  = None,
    action_type:  Optional[str]  = None,
    domain:       Optional[str]  = None,
    days:         int             = 365,
    limit:        int             = 200,
) -> List[Dict]:
    with get_session() as session:
        q = session.query(EnforcementAction)
        if jurisdiction:
            q = q.filter(EnforcementAction.jurisdiction == jurisdiction)
        if source:
            q = q.filter(EnforcementAction.source == source)
        if action_type:
            q = q.filter(EnforcementAction.action_type == action_type)
        if domain:
            q = q.filter(EnforcementAction.domain == domain)
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            q = q.filter(EnforcementAction.published_date >= cutoff)
        q = q.order_by(EnforcementAction.published_date.desc()).limit(limit)
        return [
            {
                "id":             r.id,
                "source":         r.source,
                "action_type":    r.action_type,
                "title":          r.title,
                "url":            r.url,
                "published_date": r.published_date.isoformat() if r.published_date else None,
                "agency":         r.agency,
                "jurisdiction":   r.jurisdiction,
                "respondent":     r.respondent,
                "summary":        r.summary,
                "related_regs":   r.related_regs or [],
                "outcome":        r.outcome,
                "penalty_amount": r.penalty_amount,
                "ai_concepts":    r.ai_concepts or [],
                "relevance_score":r.relevance_score,
                "domain":         r.domain or "ai",
            }
            for r in q.all()
        ]


def count_enforcement_actions() -> Dict[str, int]:
    with get_session() as session:
        total = session.query(EnforcementAction).count()
        by_source: Dict[str, int] = {}
        for row in session.query(
            EnforcementAction.source,
            func.count(EnforcementAction.id)
        ).group_by(EnforcementAction.source).all():
            by_source[row[0]] = row[1]
        return {"total": total, "by_source": by_source}


# ── Knowledge Graph CRUD ──────────────────────────────────────────────────────

def upsert_graph_edge(edge: dict) -> int:
    """Insert a knowledge graph edge; skip if (source, target, edge_type, concept) exists."""
    with get_session() as session:
        existing = session.query(KnowledgeGraphEdge).filter_by(
            source_id = edge["source_id"],
            target_id = edge["target_id"],
            edge_type = edge["edge_type"],
            concept   = edge.get("concept"),
        ).first()
        if existing:
            return existing.id
        e = KnowledgeGraphEdge(**{k: v for k, v in edge.items()
                                   if hasattr(KnowledgeGraphEdge, k)})
        session.add(e)
        session.commit()
        return e.id


def get_graph_edges(source_id: Optional[str] = None,
                    edge_types: Optional[List[str]] = None) -> List[Dict]:
    with get_session() as session:
        q = session.query(KnowledgeGraphEdge)
        if source_id:
            q = q.filter(
                (KnowledgeGraphEdge.source_id == source_id) |
                (KnowledgeGraphEdge.target_id == source_id)
            )
        if edge_types:
            q = q.filter(KnowledgeGraphEdge.edge_type.in_(edge_types))
        return [
            {
                "id":          r.id,
                "source_id":   r.source_id,
                "source_type": r.source_type,
                "target_id":   r.target_id,
                "target_type": r.target_type,
                "edge_type":   r.edge_type,
                "concept":     r.concept,
                "evidence":    r.evidence,
                "strength":    r.strength,
            }
            for r in q.all()
        ]


def count_graph_edges() -> int:
    with get_session() as session:
        return session.query(KnowledgeGraphEdge).count()


class ConceptMapCache(Base):
    """
    Cached cross-jurisdiction concept map.
    Stores the full structured comparison for a concept so it can be
    served instantly without re-running LLM calls.
    """
    __tablename__ = "concept_map_cache"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    concept_key   = Column(String, nullable=False, unique=True)
    concept_label = Column(String)
    entries_json  = Column(Text)      # JSON: list of ConceptEntry dicts
    entry_count   = Column(Integer, default=0)
    model_used    = Column(String)
    built_at      = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_cmc_concept", "concept_key"),
    )


# ── Concept Map CRUD ──────────────────────────────────────────────────────────

def save_concept_map(concept_key: str, concept_label: str,
                     entries: list, model_used: str = "") -> None:
    with get_session() as session:
        existing = session.query(ConceptMapCache).filter_by(concept_key=concept_key).first()
        if existing:
            existing.entries_json  = json.dumps(entries)
            existing.entry_count   = len(entries)
            existing.model_used    = model_used
            existing.concept_label = concept_label
            existing.built_at      = datetime.utcnow()
        else:
            session.add(ConceptMapCache(
                concept_key   = concept_key,
                concept_label = concept_label,
                entries_json  = json.dumps(entries),
                entry_count   = len(entries),
                model_used    = model_used,
            ))
        session.commit()


def get_concept_map(concept_key: str, max_age_days: int = 7) -> Optional[Dict]:
    with get_session() as session:
        row = session.query(ConceptMapCache).filter_by(concept_key=concept_key).first()
        if not row:
            return None
        age = (datetime.utcnow() - row.built_at).days if row.built_at else 999
        if age > max_age_days:
            return None
        try:
            entries = json.loads(row.entries_json or "[]")
        except Exception:
            entries = []
        return {
            "concept_key":   row.concept_key,
            "concept_label": row.concept_label,
            "entries":       entries,
            "entry_count":   row.entry_count,
            "model_used":    row.model_used,
            "built_at":      row.built_at.isoformat() if row.built_at else None,
        }


def list_concept_maps() -> List[Dict]:
    with get_session() as session:
        rows = session.query(ConceptMapCache).order_by(
            ConceptMapCache.concept_label
        ).all()
        return [
            {
                "concept_key":   r.concept_key,
                "concept_label": r.concept_label,
                "entry_count":   r.entry_count,
                "built_at":      r.built_at.isoformat() if r.built_at else None,
            }
            for r in rows
        ]


class BriefCache(Base):
    """Cached regulatory intelligence brief."""
    __tablename__ = "brief_cache"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    topic_key   = Column(String, nullable=False, unique=True)
    topic_label = Column(String)
    content     = Column(Text)
    citations   = Column(JSON)
    model_used  = Column(String)
    built_at    = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_bc_topic", "topic_key"),)


# ── Brief Cache CRUD ──────────────────────────────────────────────────────────

def save_brief_cache(key: str, label: str, result: dict) -> None:
    with get_session() as session:
        existing = session.query(BriefCache).filter_by(topic_key=key).first()
        if existing:
            existing.topic_label = label
            existing.content     = result.get("content", "")
            existing.citations   = result.get("citations", [])
            existing.model_used  = result.get("model_used", "")
            existing.built_at    = datetime.utcnow()
        else:
            session.add(BriefCache(
                topic_key   = key,
                topic_label = label,
                content     = result.get("content", ""),
                citations   = result.get("citations", []),
                model_used  = result.get("model_used", ""),
            ))
        session.commit()


def get_brief_cache(key: str, max_age_days: int = 14) -> Optional[Dict]:
    with get_session() as session:
        row = session.query(BriefCache).filter_by(topic_key=key).first()
        if not row:
            return None
        age = (datetime.utcnow() - row.built_at).days if row.built_at else 999
        if age > max_age_days:
            return None
        return {
            "topic_key":   row.topic_key,
            "topic_label": row.topic_label,
            "content":     row.content or "",
            "citations":   row.citations or [],
            "model_used":  row.model_used,
            "built_at":    row.built_at.isoformat() if row.built_at else None,
        }


def list_brief_caches() -> List[Dict]:
    with get_session() as session:
        rows = session.query(BriefCache).order_by(BriefCache.built_at.desc()).all()
        return [
            {
                "topic_key":   r.topic_key,
                "topic_label": r.topic_label,
                "model_used":  r.model_used,
                "built_at":    r.built_at.isoformat() if r.built_at else None,
                "content_len": len(r.content or ""),
            }
            for r in rows
        ]


# ── Q&A CRUD ──────────────────────────────────────────────────────────────────

def upsert_qa_passage(passage: dict) -> int:
    """
    Insert a passage, skipping if text_hash already exists.
    Returns the passage id.
    """
    with get_session() as session:
        existing = session.query(QAPassage).filter_by(
            text_hash=passage["text_hash"]
        ).first()
        if existing:
            return existing.id
        p = QAPassage(**{k: v for k, v in passage.items()
                         if hasattr(QAPassage, k)})
        session.add(p)
        session.commit()
        return p.id


def get_qa_passages(source_id: str) -> List[Dict]:
    """Return all passages for a given source (document or baseline)."""
    with get_session() as session:
        rows = (session.query(QAPassage)
                .filter_by(source_id=source_id)
                .order_by(QAPassage.chunk_index)
                .all())
        return [
            {
                "id":           r.id,
                "source_type":  r.source_type,
                "source_id":    r.source_id,
                "source_title": r.source_title,
                "jurisdiction": r.jurisdiction,
                "chunk_index":  r.chunk_index,
                "chunk_total":  r.chunk_total,
                "section_label":r.section_label,
                "text":         r.text,
            }
            for r in rows
        ]


def delete_qa_passages_for_source(source_id: str) -> int:
    """Remove all passages for a source (called before re-indexing)."""
    with get_session() as session:
        count = session.query(QAPassage).filter_by(source_id=source_id).delete()
        session.commit()
        return count


def get_all_qa_passage_ids() -> List[Dict]:
    """Return lightweight {source_id, source_type} list for index status."""
    with get_session() as session:
        rows = session.query(
            QAPassage.source_id,
            QAPassage.source_type,
        ).distinct().all()
        return [{"source_id": r[0], "source_type": r[1]} for r in rows]


def save_qa_session(session_dict: dict) -> int:
    """Persist a Q&A turn. Returns the session id."""
    with get_session() as session:
        qa = QASession(**{k: v for k, v in session_dict.items()
                          if hasattr(QASession, k)})
        session.add(qa)
        session.commit()
        return qa.id


def get_qa_history(limit: int = 50) -> List[Dict]:
    """Return recent Q&A turns, newest first."""
    with get_session() as session:
        rows = (session.query(QASession)
                .order_by(QASession.asked_at.desc())
                .limit(limit)
                .all())
        return [
            {
                "id":               r.id,
                "question":         r.question,
                "answer":           r.answer,
                "citations":        r.citations or [],
                "follow_ups":       r.follow_ups or [],
                "retrieval_count":  r.retrieval_count,
                "model_used":       r.model_used,
                "asked_at":         r.asked_at.isoformat() if r.asked_at else None,
            }
            for r in rows
        ]
