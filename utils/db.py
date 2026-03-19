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
    Float, Boolean, JSON, Index, text, Integer
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

    __table_args__ = (
        Index("ix_doc_jurisdiction", "jurisdiction"),
        Index("ix_doc_source",       "source"),
        Index("ix_doc_published",    "published_date"),
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
                      limit: int = 500) -> List[Dict[str, Any]]:
    with get_session() as session:
        q = session.query(Document)
        if jurisdiction:
            q = q.filter(Document.jurisdiction == jurisdiction)
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
    }


# ── Summaries CRUD ────────────────────────────────────────────────────────────

def upsert_summary(summary_dict: Dict[str, Any]) -> None:
    with get_session() as session:
        session.merge(Summary(**summary_dict))
        session.commit()


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


def get_unsummarized_documents(limit: int = 50) -> List[Document]:
    with get_session() as session:
        summarized_ids = session.execute(
            text("SELECT document_id FROM summaries")
        ).scalars().all()
        return (
            session.query(Document)
            .filter(Document.id.notin_(summarized_ids))
            .order_by(Document.published_date.desc())
            .limit(limit)
            .all()
        )


def get_recent_summaries(days: int = 30,
                          jurisdiction: Optional[str] = None) -> List[Dict]:
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
                # Handles: null published_date, historically-dated pinned docs,
                # and documents fetched today that have old publication dates
                (Document.fetched_at >= since) |
                (Document.published_date >= since)
            )
        )
        if jurisdiction:
            q = q.filter(Document.jurisdiction == jurisdiction)

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
        }
