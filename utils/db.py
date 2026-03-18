"""
ARIS — Database Layer
SQLite storage via SQLAlchemy. Stores raw documents and AI-generated summaries.
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    create_engine, Column, String, Text, DateTime,
    Float, Boolean, JSON, Index, text
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import DB_PATH


class Base(DeclarativeBase):
    pass


class Document(Base):
    """Raw legislative / regulatory document fetched from a source."""
    __tablename__ = "documents"

    id             = Column(String, primary_key=True)   # source-specific ID
    source         = Column(String, nullable=False)      # e.g. "federal_register"
    jurisdiction   = Column(String, nullable=False)      # "Federal" | state code
    doc_type       = Column(String)                      # RULE, PRORULE, BILL, etc.
    title          = Column(Text, nullable=False)
    url            = Column(Text)
    published_date = Column(DateTime)
    agency         = Column(String)
    status         = Column(String)
    full_text      = Column(Text)
    raw_json       = Column(JSON)
    fetched_at     = Column(DateTime, default=datetime.utcnow)
    content_hash   = Column(String)                      # detect changes

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
    requirements    = Column(JSON)     # list[str]
    recommendations = Column(JSON)     # list[str]
    action_items    = Column(JSON)     # list[str]
    deadline        = Column(String)
    impact_areas    = Column(JSON)     # list[str]
    urgency         = Column(String)   # Low | Medium | High | Critical
    relevance_score = Column(Float)
    model_used      = Column(String)
    summarized_at   = Column(DateTime, default=datetime.utcnow)


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


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def upsert_document(doc_dict: Dict[str, Any]) -> bool:
    """
    Insert or update a document. Returns True if content changed (new or updated).
    """
    content_hash = hashlib.md5(
        (doc_dict.get("full_text") or doc_dict.get("title") or "").encode()
    ).hexdigest()

    with get_session() as session:
        existing = session.get(Document, doc_dict["id"])
        if existing and existing.content_hash == content_hash:
            return False  # no change

        doc = existing or Document()
        for k, v in doc_dict.items():
            if hasattr(doc, k):
                setattr(doc, k, v)
        doc.content_hash = content_hash
        doc.fetched_at   = datetime.utcnow()

        session.merge(doc)
        session.commit()
        return True


def upsert_summary(summary_dict: Dict[str, Any]) -> None:
    with get_session() as session:
        s = Summary(**summary_dict)
        session.merge(s)
        session.commit()


def get_unsummarized_documents(limit: int = 50) -> List[Document]:
    with get_session() as session:
        summarized_ids = session.execute(
            text("SELECT document_id FROM summaries")
        ).scalars().all()
        query = session.query(Document).filter(
            Document.id.notin_(summarized_ids)
        ).order_by(Document.published_date.desc()).limit(limit)
        return query.all()


def get_recent_summaries(days: int = 30, jurisdiction: Optional[str] = None) -> List[Dict]:
    """Return joined document + summary rows as dicts for reporting."""
    with get_session() as session:
        since = datetime.utcnow().replace(hour=0, minute=0) 
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(days=days)
        
        q = (
            session.query(Document, Summary)
            .join(Summary, Document.id == Summary.document_id)
            .filter(Document.published_date >= since)
        )
        if jurisdiction:
            q = q.filter(Document.jurisdiction == jurisdiction)
        
        results = []
        for doc, summ in q.order_by(Document.published_date.desc()).all():
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
                **{k: getattr(summ, k) for k in [
                    "plain_english", "requirements", "recommendations",
                    "action_items", "deadline", "impact_areas",
                    "urgency", "relevance_score"
                ]},
            })
        return results


def get_stats() -> Dict[str, Any]:
    with get_session() as session:
        total_docs     = session.query(Document).count()
        total_summaries = session.query(Summary).count()
        federal_docs   = session.query(Document).filter_by(jurisdiction="Federal").count()
        return {
            "total_documents":  total_docs,
            "total_summaries":  total_summaries,
            "federal_documents": federal_docs,
            "state_documents":  total_docs - federal_docs,
            "pending_summaries": total_docs - total_summaries,
        }
