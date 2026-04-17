# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 Mitch Kwiatkowski
# ARIS — Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
"""
ARIS — Retrieval-Augmented Generation (RAG) Engine

Converts the full document corpus (database documents + all 19 baselines)
into retrievable passages that can be assembled into grounded Q&A responses.

Architecture
------------
CHUNKING
  Documents and baselines are split into passages of ~800 tokens (≈3000 chars).
  Each passage carries enough metadata to cite its source precisely:
    - Source title, jurisdiction, doc type
    - Section label (e.g. "Key Definitions", "Prohibited Practices", "Article 5")
    - Position within the source (chunk 3 of 7)

INDEXING
  Passages are stored in the `qa_passages` SQLite table and indexed two ways:
    1. FTS5 full-text search for keyword matching
    2. TF-IDF matrix (from utils/search) for semantic proximity scoring

RETRIEVAL
  Given a question, the retriever:
    1. Expands the query with regulatory synonyms (utils/search.expand_query)
    2. Runs FTS5 to get keyword-matched passages
    3. Scores all passages via TF-IDF cosine similarity
    4. Combines scores, deduplicates by source, returns top-k with metadata

CONTEXT ASSEMBLY
  Selected passages are formatted into a structured prompt context block
  with clear source labels so the LLM can cite them precisely.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.cache import get_logger

log = get_logger("aris.rag")

# ── Constants ──────────────────────────────────────────────────────────────────

CHUNK_SIZE = 3000  # characters (~750 tokens) — fits ~10 chunks in context
CHUNK_OVERLAP = 300  # overlap between consecutive chunks
MAX_PASSAGES = 12  # maximum passages to assemble into context
MIN_SCORE = 0.05  # minimum relevance score to include a passage

BASELINES_DIR = Path(__file__).parent.parent / "data" / "baselines"


# ═══════════════════════════════════════════════════════════════════════════════
# CHUNKING
# ═══════════════════════════════════════════════════════════════════════════════


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def chunk_text(
    text: str,
    source_id: str,
    source_title: str,
    source_type: str,
    jurisdiction: str,
    section_label: str = "",
) -> List[Dict]:
    """
    Split a text blob into overlapping passages.
    Returns a list of passage dicts ready for upsert_qa_passage().
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        # Try to break at a sentence boundary
        if end < len(text):
            boundary = text.rfind(". ", start, end)
            if boundary > start + CHUNK_SIZE // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(start + CHUNK_SIZE - CHUNK_OVERLAP, end)
        if start >= len(text):
            break

    total = len(chunks)
    return [
        {
            "source_type": source_type,
            "source_id": source_id,
            "source_title": source_title,
            "jurisdiction": jurisdiction,
            "chunk_index": i,
            "chunk_total": total,
            "section_label": section_label,
            "text": chunk,
            "text_hash": _hash(chunk),
        }
        for i, chunk in enumerate(chunks)
    ]


def chunk_document(doc: Dict) -> List[Dict]:
    """
    Chunk a document dict (from get_document / get_recent_summaries).
    Produces passages from: title + plain_english summary, then full_text.
    """
    passages = []
    doc_id = doc.get("id", "")
    title = doc.get("title", "")
    jur = doc.get("jurisdiction", "")
    source_type = "document"

    # Passage 1: the summary (highly dense, always include)
    plain = doc.get("plain_english", "") or ""
    reqs = doc.get("requirements") or []
    acts = doc.get("action_items") or []

    summary_parts = [title]
    if plain:
        summary_parts.append(plain)
    if reqs:
        summary_parts.append(
            "Key requirements: "
            + "; ".join(
                r if isinstance(r, str) else r.get("description", str(r))
                for r in reqs[:8]
            )
        )
    if acts:
        summary_parts.append(
            "Action items: "
            + "; ".join(
                a if isinstance(a, str) else a.get("description", str(a))
                for a in acts[:5]
            )
        )

    summary_text = "\n\n".join(summary_parts)
    if summary_text.strip():
        passages += chunk_text(
            summary_text, doc_id, title, source_type, jur, section_label="Summary"
        )

    # Passage 2+: full document text (if available)
    full = doc.get("full_text", "") or ""
    if full and len(full) > 200:
        passages += chunk_text(
            full[:50000], doc_id, title, source_type, jur, section_label="Full Text"
        )

    return passages


def chunk_baseline(baseline: Dict) -> List[Dict]:
    """
    Chunk a baseline JSON dict into structured passages.
    Each major section becomes its own passage with a section label,
    ensuring the richly structured baseline content is retrievable precisely.
    """
    passages = []
    baseline_id = baseline.get("id", "")
    title = baseline.get("title", "") or baseline.get("short_name", "")
    jur = baseline.get("jurisdiction", "")

    def _add(text: str, section: str) -> None:
        if text and text.strip():
            passages.extend(
                chunk_text(
                    text, baseline_id, title, "baseline", jur, section_label=section
                )
            )

    def _stringify(obj: Any, depth: int = 0) -> str:
        """Recursively convert nested dicts/lists to readable text."""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            parts = []
            for k, v in obj.items():
                label = k.replace("_", " ").title()
                content = _stringify(v, depth + 1)
                if content:
                    parts.append(f"{label}: {content}")
            return "\n".join(parts)
        if isinstance(obj, list):
            parts = []
            for item in obj:
                s = _stringify(item, depth + 1)
                if s:
                    parts.append(f"• {s}" if depth == 0 else s)
            return "\n".join(parts)
        return str(obj) if obj is not None else ""

    # Overview — always a top-level passage
    _add(f"{title}\n\n{baseline.get('overview', '')}", "Overview")

    # Iterate all non-metadata top-level keys
    skip_keys = {
        "id",
        "jurisdiction",
        "title",
        "official_title",
        "short_name",
        "celex",
        "oj_reference",
        "status",
        "last_reviewed",
        "overview",
        "cross_references",
    }

    for key, value in baseline.items():
        if key in skip_keys or not value:
            continue
        section_name = key.replace("_", " ").title()
        content = _stringify(value)
        if content and len(content) > 50:
            _add(content, section_name)

    return passages


def chunk_all_baselines() -> List[Dict]:
    """Load and chunk all 19 baseline JSON files."""
    passages = []
    if not BASELINES_DIR.exists():
        return passages
    for path in BASELINES_DIR.glob("*.json"):
        if path.name == "index.json":
            continue
        try:
            data = json.loads(path.read_text())
            passages += chunk_baseline(data)
        except Exception as e:
            log.warning("Could not chunk baseline %s: %s", path.name, e)
    return passages


# ═══════════════════════════════════════════════════════════════════════════════
# FTS5 PASSAGE INDEX
# ═══════════════════════════════════════════════════════════════════════════════

_PASSAGE_FTS = "qa_passage_fts"
_PASSAGE_META = "qa_passage_fts_meta"


def _ensure_passage_fts(conn: sqlite3.Connection) -> None:
    conn.executescript(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {_PASSAGE_FTS} USING fts5(text);
        CREATE TABLE IF NOT EXISTS {_PASSAGE_META} (
            rowid     INTEGER PRIMARY KEY,
            passage_id INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_qpfm ON {_PASSAGE_META}(passage_id);
    """)
    conn.commit()


def index_passage_fts(conn: sqlite3.Connection, passage_id: int, text: str) -> None:
    """Add a passage to the FTS5 index."""
    try:
        _ensure_passage_fts(conn)
        # Remove old entry if any
        rows = conn.execute(
            f"SELECT rowid FROM {_PASSAGE_META} WHERE passage_id = ?", (passage_id,)
        ).fetchall()
        for (rowid,) in rows:
            conn.execute(f"DELETE FROM {_PASSAGE_FTS}   WHERE rowid = ?", (rowid,))
            conn.execute(f"DELETE FROM {_PASSAGE_META} WHERE rowid = ?", (rowid,))

        cursor = conn.execute(f"INSERT INTO {_PASSAGE_FTS}(text) VALUES (?)", (text,))
        conn.execute(
            f"INSERT INTO {_PASSAGE_META}(rowid, passage_id) VALUES (?, ?)",
            (cursor.lastrowid, passage_id),
        )
        conn.commit()
    except Exception as e:
        log.debug("Passage FTS index error: %s", e)


def search_passage_fts(
    conn: sqlite3.Connection, query: str, limit: int = 50
) -> List[Tuple[int, float]]:
    """
    Search passage FTS5 index.
    Returns list of (passage_id, fts_score) tuples.
    """
    try:
        _ensure_passage_fts(conn)
        # Build FTS query
        clean = re.sub(r"[^\w\s\-]", " ", query).strip()
        words = [w for w in clean.split() if len(w) > 2]
        if not words:
            return []
        if len(words) > 1:
            phrase = '"' + " ".join(words) + '"'
            singles = " OR ".join(f"{w}*" for w in words[:6])
            fts_q = f"{phrase} OR {singles}"
        else:
            fts_q = words[0] + "*"

        rows = conn.execute(
            f"SELECT m.passage_id, f.rank "
            f"FROM {_PASSAGE_FTS} f "
            f"JOIN {_PASSAGE_META} m ON m.rowid = f.rowid "
            f"WHERE {_PASSAGE_FTS} MATCH ? "
            f"ORDER BY f.rank LIMIT ?",
            (fts_q, limit),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except Exception as e:
        log.debug("Passage FTS search error: %s", e)
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# PASSAGE TFIDF INDEX
# ═══════════════════════════════════════════════════════════════════════════════


class PassageTFIDF:
    """
    Lightweight TF-IDF index over passage texts.
    Backed by utils/search.TFIDFIndex but stored separately from
    the document-level index so they don't interfere.
    """

    def __init__(self):
        from utils.search import TFIDFIndex

        self._idx = TFIDFIndex()
        self._ids: List[int] = []  # passage DB ids, parallel to idx.doc_ids
        self._built = False
        self._cache = _models_dir() / "qa_tfidf_index.json"
        self._id_cache = _models_dir() / "qa_tfidf_ids.json"

    def build(self, passages: List[Dict]) -> None:
        """Build from a list of passage dicts (with 'id' and 'text' keys)."""
        pairs = [(str(p["id"]), p["text"]) for p in passages if p.get("text")]
        self._ids = [p["id"] for p in passages if p.get("text")]
        self._idx.build(pairs)
        self._built = True
        self._save()

    def _save(self) -> None:
        self._idx.save(self._cache)
        self._id_cache.write_text(json.dumps(self._ids))

    def load(self) -> bool:
        ok = self._idx.load(self._cache)
        if ok and self._id_cache.exists():
            self._ids = json.loads(self._id_cache.read_text())
            self._built = True
            return True
        return False

    def query(self, text: str, top_k: int = 30) -> List[Tuple[int, float]]:
        """Return (passage_id, score) pairs."""
        if not self._built:
            return []
        str_results = self._idx.query(text, top_k=top_k)
        # idx.doc_ids are strings like "123" — convert back to ints
        id_map = {str(pid): pid for pid in self._ids}
        return [
            (id_map[doc_id], score) for doc_id, score in str_results if doc_id in id_map
        ]


def _models_dir() -> Path:
    from config.settings import OUTPUT_DIR

    d = OUTPUT_DIR / "models"
    d.mkdir(exist_ok=True)
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# RETRIEVER
# ═══════════════════════════════════════════════════════════════════════════════


class PassageRetriever:
    """
    Retrieves and ranks passages relevant to a question.
    Combines FTS5 keyword matching with TF-IDF semantic proximity.
    Singleton — loaded once at server startup.
    """

    def __init__(self):
        self._tfidf = PassageTFIDF()
        self._ready = False

    def ensure_ready(self) -> None:
        """Load cached index or trigger rebuild if missing."""
        if self._ready:
            return
        if self._tfidf.load():
            self._ready = True
            log.info("Q&A passage index loaded (%d passages)", len(self._tfidf._ids))
        else:
            log.info("Q&A passage index not found — building on first query")

    def retrieve(
        self,
        question: str,
        top_k: int = MAX_PASSAGES,
        jurisdiction: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve the top-k most relevant passages for a question.

        Returns a list of passage dicts enriched with a combined relevance
        score. Each passage is ready to be assembled into the LLM prompt.
        """
        from utils.search import expand_query
        from utils.db import DB_PATH

        self.ensure_ready()

        expanded = expand_query(question)
        conn = sqlite3.connect(DB_PATH)
        scores: Dict[int, float] = {}

        # Layer 1: FTS5 keyword matching
        fts_results = search_passage_fts(conn, expanded, limit=top_k * 3)
        for passage_id, fts_rank in fts_results:
            fts_score = max(0.0, min(1.0, 1.0 + fts_rank / 10.0))
            scores[passage_id] = scores.get(passage_id, 0.0) + fts_score * 0.40

        # Layer 2: TF-IDF semantic scoring
        if self._tfidf._built:
            tfidf_results = self._tfidf.query(expanded, top_k=top_k * 3)
            for passage_id, score in tfidf_results:
                scores[passage_id] = scores.get(passage_id, 0.0) + score * 0.60

        conn.close()

        if not scores:
            return []

        # Sort by combined score, filter by minimum
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        ranked = [(pid, s) for pid, s in ranked if s >= MIN_SCORE]

        # Fetch passage details from DB
        top_ids = [pid for pid, _ in ranked[: top_k * 2]]
        if not top_ids:
            return []

        from utils.db import get_session, QAPassage as _QAPassage

        with get_session() as session:
            rows = session.query(_QAPassage).filter(_QAPassage.id.in_(top_ids)).all()
            passage_map = {
                r.id: {
                    "id": r.id,
                    "source_type": r.source_type,
                    "source_id": r.source_id,
                    "source_title": r.source_title,
                    "jurisdiction": r.jurisdiction,
                    "chunk_index": r.chunk_index,
                    "chunk_total": r.chunk_total,
                    "section_label": r.section_label,
                    "text": r.text,
                }
                for r in rows
            }

        # Filter by jurisdiction if specified
        results = []
        seen_sources: Dict[str, int] = {}  # source_id → passages included

        for passage_id, score in ranked:
            if passage_id not in passage_map:
                continue
            p = {**passage_map[passage_id], "score": round(score, 3)}

            # Apply jurisdiction filter
            if (
                jurisdiction
                and p.get("jurisdiction")
                and p["jurisdiction"].upper() != jurisdiction.upper()
            ):
                continue

            # Limit passages per source to avoid one document dominating
            src = p["source_id"]
            if seen_sources.get(src, 0) >= 3:
                continue
            seen_sources[src] = seen_sources.get(src, 0) + 1

            results.append(p)
            if len(results) >= top_k:
                break

        return results


# ── Module singleton ───────────────────────────────────────────────────────────

_retriever: Optional[PassageRetriever] = None


def get_retriever() -> PassageRetriever:
    global _retriever
    if _retriever is None:
        _retriever = PassageRetriever()
    return _retriever


# ═══════════════════════════════════════════════════════════════════════════════
# INDEX BUILDER
# ═══════════════════════════════════════════════════════════════════════════════


def build_passage_index(force: bool = False) -> Dict[str, int]:
    """
    Build the full passage index from:
      1. All 19 baseline JSON files
      2. All summarised documents in the database

    Called:
      - After python migrate.py (first run)
      - After python main.py run (new documents summarised)
      - Via POST /api/qa/index/rebuild
      - Via CLI: python main.py build-qa-index

    Returns counts: {baselines, documents, passages_total}
    """
    from utils.db import (
        upsert_qa_passage,
        get_all_qa_passage_ids,
        delete_qa_passages_for_source,
        get_recent_summaries,
        DB_PATH,
    )

    log.info("Building Q&A passage index…")

    # Track what source IDs we (re)index
    indexed_sources: set = set()
    all_passages: List[Dict] = []
    baseline_count = 0
    document_count = 0

    # ── 1. Baselines ──────────────────────────────────────────────────────────
    if not BASELINES_DIR.exists():
        log.warning("Baselines dir not found: %s", BASELINES_DIR)
    else:
        for path in sorted(BASELINES_DIR.glob("*.json")):
            if path.name == "index.json":
                continue
            try:
                data = json.loads(path.read_text())
                bid = data.get("id", path.stem)
                if force:
                    delete_qa_passages_for_source(bid)
                passages = chunk_baseline(data)
                if passages:
                    all_passages.extend(passages)
                    indexed_sources.add(bid)
                    baseline_count += 1
            except Exception as e:
                log.warning("Baseline chunking failed for %s: %s", path.name, e)

    # ── 2. Database documents (summaries + full text) ─────────────────────────
    try:
        docs = get_recent_summaries(days=3650)
        for doc in docs:
            did = doc.get("id", "")
            if not did:
                continue
            if force:
                delete_qa_passages_for_source(did)
            passages = chunk_document(doc)
            if passages:
                all_passages.extend(passages)
                indexed_sources.add(did)
                document_count += 1
    except Exception as e:
        log.warning("Document chunking failed: %s", e)

    # ── 3. Persist passages ───────────────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    passage_ids_inserted = []

    for p in all_passages:
        try:
            pid = upsert_qa_passage(p)
            passage_ids_inserted.append(pid)
            index_passage_fts(conn, pid, p["text"])
        except Exception as e:
            log.debug("Passage insert error: %s", e)

    conn.close()

    # ── 4. Build TF-IDF index ─────────────────────────────────────────────────
    from utils.db import get_session, QAPassage as _QAPassage

    with get_session() as session:
        all_p = session.query(_QAPassage).all()
        passage_dicts = [{"id": p.id, "text": p.text} for p in all_p]

    retriever = get_retriever()
    retriever._tfidf.build(passage_dicts)
    retriever._ready = True

    total = len(passage_dicts)
    log.info(
        "Q&A index complete: %d baselines, %d documents, %d passages",
        baseline_count,
        document_count,
        total,
    )
    return {
        "baselines": baseline_count,
        "documents": document_count,
        "passages_total": total,
    }


def index_document_passages(doc: Dict) -> int:
    """
    Index a single document's passages. Called from orchestrator after
    a document is summarised so new content becomes immediately searchable.
    Returns number of new passages added.
    """
    from utils.db import upsert_qa_passage, delete_qa_passages_for_source, DB_PATH

    did = doc.get("id", "")
    if not did:
        return 0

    delete_qa_passages_for_source(did)
    passages = chunk_document(doc)
    if not passages:
        return 0

    conn = sqlite3.connect(DB_PATH)
    inserted = 0
    for p in passages:
        try:
            pid = upsert_qa_passage(p)
            index_passage_fts(conn, pid, p["text"])
            inserted += 1
        except Exception:
            pass
    conn.close()

    # Mark TF-IDF as dirty (full rebuild deferred to next scheduled rebuild)
    retriever = get_retriever()
    retriever._ready = False

    return inserted
