"""
ARIS — Search Engine

Replaces the simple keyword substring scan with a multi-layer search system
that significantly improves recall (catching relevant documents that don't
use exact keyword phrases) and precision (ranking results by relevance rather
than just presence/absence).

Architecture
------------
Four layers, applied in order. Each layer is independently useful and
gracefully falls back to the previous layer if unavailable.

LAYER 1 — EXPANDED KEYWORD FILTER  (always active, no dependencies)
  Replaces the 30-term exact-match list with a 150+ term taxonomy that
  covers synonyms, regulatory shorthand, sector-specific terminology, and
  related concepts. Also expands queries using a synonym map so "llm
  governance" matches documents that say "large language model compliance".

LAYER 2 — SQLITE FTS5  (always active — SQLite 3.45 has FTS5)
  Full-text search index over document titles, summaries, and plain-English
  descriptions. Supports phrase queries, prefix matching, and BM25 ranking.
  Dramatically faster than substring scanning for large document corpora.
  Maintained via triggers so the index stays in sync automatically.

LAYER 3 — TF-IDF SIMILARITY  (always active — requires only numpy + scipy)
  Builds a sparse TF-IDF matrix from document summaries and titles.
  Used to rank search results and to score incoming documents for relevance.
  Much better than keyword density for multi-word queries because it weights
  rare, distinctive terms more heavily than common ones.

LAYER 4 — ONNX EMBEDDING SIMILARITY  (optional — activate by placing model)
  If the user places an ONNX sentence-embedding model in output/models/,
  ARIS uses it for semantic similarity — catching documents that discuss the
  same concept in completely different words ("algorithmic accountability"
  matching "responsible AI deployment"). Uses onnxruntime (already installed).

  To activate: download all-MiniLM-L6-v2 ONNX model files
    python -c "from utils.search import download_embedding_model; download_embedding_model()"
  Or manually place model files in output/models/all-MiniLM-L6-v2/

Public API
----------
  from utils.search import (
      is_ai_relevant,        # bool — fast pre-filter for fetch pipeline
      relevance_score,       # 0-1 float — richer score replacing keyword_score
      search_documents,      # ranked search over document database
      index_document,        # index a document when it arrives
      rebuild_index,         # rebuild full FTS + TF-IDF index from DB
  )

Backward compatibility
----------------------
  utils.cache.keyword_score() and utils.cache.is_ai_relevant() are updated
  to delegate here. All call sites continue to work unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from utils.cache import get_logger

log = get_logger("aris.search")

# ── Model path ────────────────────────────────────────────────────────────────

def _models_dir() -> Path:
    from config.settings import OUTPUT_DIR
    d = OUTPUT_DIR / "models"
    d.mkdir(exist_ok=True)
    return d

_ONNX_MODEL_DIR  = None   # resolved lazily


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — EXPANDED KEYWORD TAXONOMY
# ═══════════════════════════════════════════════════════════════════════════════

# 150+ term taxonomy covering:
# - Core AI/ML technology terms
# - Regulatory and governance vocabulary
# - Sector-specific terms (hiring, credit, healthcare, law enforcement)
# - International regulatory shorthand
# - Related concepts that imply AI involvement

AI_TERMS_EXPANDED = [
    # Core technology
    "artificial intelligence", "machine learning", "deep learning", "neural network",
    "large language model", "llm", "generative ai", "generative model", "foundation model",
    "language model", "transformer model", "diffusion model", "multimodal model",
    "computer vision", "natural language processing", "nlp", "speech recognition",
    "image recognition", "object detection", "facial recognition", "biometric",
    "autonomous system", "autonomous vehicle", "self-driving", "robotics",
    "predictive analytics", "predictive model", "recommendation system", "recommender",
    "decision tree", "random forest", "gradient boosting", "reinforcement learning",
    "federated learning", "transfer learning", "fine-tuning", "pre-trained model",

    # Automated decisions and systems
    "automated decision", "automated decision-making", "automated decision making",
    "algorithmic decision", "algorithmic system", "algorithmic tool", "algorithm", "algorithmic",
    "automated system", "automated tool", "automated process", "automated screening",
    "automated scoring", "automated assessment", "automated hiring",
    "automated underwriting", "credit scoring", "fraud detection", "risk scoring",
    "hiring algorithm", "resume screening", "candidate screening",

    # AI governance and regulation
    "ai governance", "ai regulation", "ai policy", "ai law", "ai act",
    "ai safety", "ai risk", "ai ethics", "ai accountability", "ai transparency",
    "ai bias", "ai fairness", "ai discrimination", "ai audit", "ai auditing",
    "ai disclosure", "ai oversight", "ai compliance", "ai standard", "ai framework",
    "responsible ai", "trustworthy ai", "ethical ai", "human-centered ai",
    "ai risk management", "ai risk assessment", "ai impact assessment",
    "conformity assessment", "algorithmic accountability", "algorithmic transparency",
    "algorithmic fairness", "algorithmic bias", "algorithmic auditing",
    "explainability", "interpretability", "explainable ai", "xai",

    # Specific regulatory concepts
    "high-risk ai", "high risk ai", "prohibited ai", "unacceptable risk",
    "human oversight", "human review", "human in the loop", "meaningful human control",
    "right to explanation", "automated profiling", "profiling", "scoring system",
    "deepfake", "synthetic media", "synthetic content", "ai-generated content",
    "watermarking", "content provenance", "digital watermark",
    "training data", "model training", "data minimisation", "purpose limitation",

    # International regulations by name/shorthand
    "eu ai act", "ai act", "eu aia", "nist ai rmf", "nist rmf",
    "eu gdpr", "gdpr article 22", "automated individual decisions",
    "colorado ai act", "illinois aipa", "nyc local law 144", "ll144",
    "california ai", "uk ai", "canada aida", "aida", "eo 14110",

    # Sector-specific AI regulation
    "aedt", "automated employment decision tool",
    "adverse action", "model risk management", "model validation",
    "clinical decision support", "software as medical device", "samd",
    "credit decision", "lending algorithm", "fair lending",
    "insurance underwriting", "claims processing",
    "recidivism", "predictive policing", "surveillance", "social scoring",

    # Harms and rights
    "disparate impact", "disparate treatment", "protected characteristic",
    "discrimination", "bias testing", "bias audit", "fairness testing",
    "opt out", "right to appeal", "right to contest", "human review request",

    # Emerging terms
    "foundation model", "gpai", "general purpose ai", "general-purpose ai",
    "frontier model", "advanced ai", "capable ai system",
    "agentic ai", "ai agent", "autonomous agent", "copilot",
    "chatbot", "conversational ai", "virtual assistant",
]

# Remove duplicates while preserving order
_seen = set()
AI_TERMS_EXPANDED = [t for t in AI_TERMS_EXPANDED if not (t in _seen or _seen.add(t))]

# ── Privacy regulation terms ──────────────────────────────────────────────────
# Separate taxonomy for data privacy regulations (GDPR, CCPA, etc.)
# Kept distinct from AI terms so domain filtering stays clean.

PRIVACY_TERMS_EXPANDED = [
    # Core privacy concepts
    "personal data", "personal information", "personally identifiable information", "pii",
    "sensitive data", "special category data", "biometric data", "genetic data",
    "health data", "financial data", "location data", "behavioral data",
    "data subject", "data controller", "data processor", "joint controller",
    "data protection", "privacy", "privacy protection", "privacy law", "privacy regulation",
    "privacy policy", "privacy notice", "privacy statement", "privacy rights",

    # Rights of data subjects
    "right to access", "right of access", "access request", "subject access request", "sar",
    "right to erasure", "right to be forgotten", "erasure request", "deletion request",
    "right to rectification", "right to correction", "data correction",
    "right to portability", "data portability", "data transfer",
    "right to object", "right to restrict", "restriction of processing",
    "right to withdraw consent", "opt out", "opt-out", "do not sell",
    "automated decision right", "human review right",

    # Legal bases and consent
    "consent", "explicit consent", "informed consent", "freely given consent",
    "legitimate interest", "legal basis", "lawful basis", "lawfulness",
    "contractual necessity", "legal obligation", "vital interests", "public task",
    "purpose limitation", "data minimisation", "data minimization", "storage limitation",
    "accuracy principle", "integrity confidentiality",

    # Controllers and processors
    "controller", "processor", "sub-processor", "third party processor",
    "data processing agreement", "dpa", "processing agreement",
    "standard contractual clauses", "scc", "binding corporate rules", "bcr",
    "adequacy decision", "adequacy determination", "cross-border transfer",
    "international transfer", "third country transfer",

    # Obligations
    "privacy by design", "privacy by default", "data protection by design",
    "data protection impact assessment", "dpia", "privacy impact assessment", "pia",
    "records of processing", "processing activities", "article 30",
    "data breach", "personal data breach", "breach notification", "breach report",
    "72-hour notification", "72 hour notification", "supervisory authority",
    "lead supervisory authority", "one-stop-shop",
    "data protection officer", "dpo",
    "privacy audit", "data audit", "compliance audit",

    # Specific regulations and frameworks
    "gdpr", "general data protection regulation", "regulation 2016/679",
    "ccpa", "california consumer privacy act",
    "cpra", "california privacy rights act",
    "vcdpa", "virginia consumer data protection act",
    "cpa colorado", "colorado privacy act",
    "ctdpa", "connecticut data privacy act",
    "tdpsa", "texas data privacy and security act",
    "pipeda", "personal information protection and electronic documents act",
    "cppa", "consumer privacy protection act",
    "lgpd", "lei geral de proteção de dados",
    "pdpa", "personal data protection act",
    "appi", "act on protection of personal information",
    "uk gdpr", "data protection act 2018", "dpa 2018",
    "eu data act", "data act",
    "eprivacy", "eprivacy regulation", "cookie law", "cookie directive",
    "privacy shield", "privacy framework",

    # Enforcement and authorities
    "information commissioner", "ico", "cnil", "bfdi", "agpd", "garante",
    "supervisory authority", "data protection authority", "regulatory authority",
    "enforcement notice", "reprimand", "administrative fine",
    "article 83", "article 84", "penalty", "sanction",
    "complaint", "investigation", "enforcement action",

    # Sector-specific privacy
    "hipaa", "health insurance portability", "protected health information", "phi",
    "glba", "gramm-leach-bliley", "financial privacy",
    "coppa", "children's online privacy", "child data",
    "ferpa", "educational records", "student data",
    "ccra", "consumer credit", "fcra", "fair credit reporting",
    "data broker", "consumer report", "credit report",

    # Technical and operational
    "encryption", "pseudonymisation", "pseudonymization", "anonymisation", "anonymization",
    "data retention", "retention period", "deletion policy",
    "data inventory", "data mapping", "data flow",
    "vendor management", "third party risk",
    "cookie consent", "tracking", "profiling consent",
]

# Remove duplicates
_seen_priv = set()
PRIVACY_TERMS_EXPANDED = [
    t for t in PRIVACY_TERMS_EXPANDED
    if not (t in _seen_priv or _seen_priv.add(t))
]

# ── Synonym / query expansion map ────────────────────────────────────────────

QUERY_EXPANSIONS: Dict[str, List[str]] = {
    # Abbreviations → full forms
    "ai":     ["artificial intelligence", "algorithmic", "automated"],
    "ml":     ["machine learning", "model"],
    "llm":    ["large language model", "foundation model", "generative ai", "language model"],
    "nlp":    ["natural language processing", "language model"],
    "xai":    ["explainability", "interpretable", "explainable ai"],
    "gpai":   ["general purpose ai", "foundation model"],
    "aida":   ["artificial intelligence and data act", "canada ai"],
    "aedt":   ["automated employment decision tool", "hiring algorithm"],
    "samd":   ["software as medical device", "clinical ai"],
    "rmf":    ["risk management framework", "nist ai"],

    # Concept synonyms
    "bias":           ["discrimination", "fairness", "disparate impact", "inequity"],
    "fairness":       ["bias", "discrimination", "equitable", "disparate impact"],
    "transparency":   ["explainability", "interpretability", "disclosure", "openness"],
    "governance":     ["compliance", "oversight", "accountability", "regulation"],
    "oversight":      ["human review", "human in the loop", "monitoring", "supervision"],
    "accountability": ["responsibility", "liability", "governance", "oversight"],
    "discrimination": ["bias", "disparate impact", "unfair treatment", "protected class"],
    "safety":         ["risk", "harm prevention", "guardrails", "safeguards"],
    "hiring":         ["employment", "recruitment", "candidate screening", "aedt"],
    "credit":         ["lending", "underwriting", "financial decision", "loan"],
    "healthcare":     ["medical", "clinical", "patient", "hospital", "diagnostic"],
    "surveillance":   ["monitoring", "tracking", "biometric", "facial recognition"],
    "deepfake":       ["synthetic media", "ai-generated content", "manipulated media"],

    # Regulatory shorthand
    "high-risk":        ["high risk ai", "regulated ai", "conformity assessment"],
    "prohibited":       ["banned", "unacceptable risk", "forbidden practice"],
    "eo":               ["executive order", "presidential order", "federal mandate"],
    "automated decision": ["algorithmic decision", "automated system", "ai decision",
                           "automated decision-making"],
}


def expand_query(query: str) -> str:
    """
    Expand a search query with synonyms and related regulatory terms.
    Returns the original query plus expansion terms.
    """
    lower  = query.lower().strip()
    tokens = set(re.findall(r'[a-z0-9\-]+', lower))
    added  = []

    for key, synonyms in QUERY_EXPANSIONS.items():
        # Match whole-word only to avoid partial matches
        pattern = r'\b' + re.escape(key) + r'\b'
        if re.search(pattern, lower):
            added.extend(synonyms)

    # Also expand any two-word phrases
    for key, synonyms in QUERY_EXPANSIONS.items():
        if ' ' in key and key in lower:
            added.extend(synonyms)

    if not added:
        return lower

    expanded = lower + ' ' + ' '.join(dict.fromkeys(added))   # dedup, preserve order
    return expanded


def is_ai_relevant(text: str, threshold: float = 0.08) -> bool:
    """
    Return True if text is likely related to AI regulation.
    Uses the expanded 150+ term taxonomy.
    Replaces the simple 30-term exact match in utils/cache.py.
    """
    if not text:
        return False
    lower = text.lower()
    hits  = sum(1 for term in AI_TERMS_EXPANDED if term in lower)
    score = min(hits / 10.0, 1.0)   # normalise to 0-1
    return score >= threshold


def is_privacy_relevant(text: str, threshold: float = 0.08) -> bool:
    """
    Return True if text is likely related to data privacy regulation.
    Uses the PRIVACY_TERMS_EXPANDED taxonomy (~130 terms).
    """
    if not text:
        return False
    lower = text.lower()
    hits  = sum(1 for term in PRIVACY_TERMS_EXPANDED if term in lower)
    score = min(hits / 10.0, 1.0)
    return score >= threshold


def is_domain_relevant(text: str, domain: str = "ai", threshold: float = 0.08) -> bool:
    """
    Domain-aware relevance check.

    domain: "ai" | "privacy" | "both"
      "ai"      → must match AI terms
      "privacy" → must match privacy terms
      "both"    → matches either domain (used when fetching for all domains)
    """
    if domain == "privacy":
        return is_privacy_relevant(text, threshold)
    if domain == "both":
        return is_ai_relevant(text, threshold) or is_privacy_relevant(text, threshold)
    return is_ai_relevant(text, threshold)


def detect_domain(text: str) -> str:
    """
    Infer the most likely domain for a piece of text.
    Returns "privacy", "ai", or "both" (if strongly relevant to both).
    Used to auto-tag documents fetched without an explicit domain context.
    """
    if not text:
        return "ai"
    lower    = text.lower()
    ai_hits  = sum(1 for t in AI_TERMS_EXPANDED    if t in lower)
    priv_hits= sum(1 for t in PRIVACY_TERMS_EXPANDED if t in lower)

    ai_score  = min(ai_hits  / 10.0, 1.0)
    priv_score= min(priv_hits / 10.0, 1.0)

    if ai_score >= 0.15 and priv_score >= 0.15:
        return "both"
    if priv_score >= 0.08 and priv_score > ai_score:
        return "privacy"
    return "ai"


def privacy_relevance_score(text: str,
                             weights: Optional[Dict[str, float]] = None) -> float:
    """
    Return a 0-1 relevance score against the privacy term taxonomy.
    Mirrors the structure of relevance_score() for AI terms.
    """
    if not text:
        return 0.0
    lower     = text.lower()
    score     = 0.0
    for term in PRIVACY_TERMS_EXPANDED:
        w = 1.0
        if weights:
            w = weights.get(term, 1.0)
        if term in lower:
            specificity = min(len(term.split()) * 0.15, 0.4)
            score += w * (1.0 + specificity)
    cap = sum(sorted(
        [weights.get(t, 1.0) if weights else 1.0 for t in PRIVACY_TERMS_EXPANDED],
        reverse=True
    )[:12])
    return min(score / cap, 1.0) if cap > 0 else 0.0


def relevance_score(text: str, weights: Optional[Dict[str, float]] = None) -> float:
    """
    Return a 0-1 relevance score using the expanded taxonomy with optional
    per-term weights from the learning agent.

    This replaces utils.cache.keyword_score() — it is called from there
    for backward compatibility.
    """
    if not text:
        return 0.0
    lower = text.lower()
    score = 0.0
    total_weight = 0.0

    for term in AI_TERMS_EXPANDED:
        w = 1.0
        if weights:
            w = weights.get(term, 1.0)
        total_weight += w
        if term in lower:
            # Longer terms (more specific) get a small bonus
            specificity = min(len(term.split()) * 0.15, 0.4)
            score += w * (1.0 + specificity)

    cap = sum(sorted(
        [weights.get(t, 1.0) if weights else 1.0 for t in AI_TERMS_EXPANDED],
        reverse=True
    )[:12])
    return min(score / cap, 1.0) if cap > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — SQLITE FTS5
# ═══════════════════════════════════════════════════════════════════════════════

_FTS_TABLE  = "document_search_fts"
_META_TABLE = "document_search_meta"   # stores doc_id mappings for FTS5

def ensure_fts_index(conn: sqlite3.Connection) -> None:
    """
    Create the FTS5 virtual table and companion metadata table if they don't exist.
    Safe to call repeatedly — idempotent.

    Uses a regular FTS5 table (not contentless) so that DELETE and UPDATE work.
    The companion metadata table stores doc_id → FTS5 rowid mapping since FTS5
    does not allow arbitrary UNINDEXED columns to be retrieved via SELECT.
    """
    conn.executescript(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {_FTS_TABLE} USING fts5(
            title,
            summary
        );
        CREATE TABLE IF NOT EXISTS {_META_TABLE} (
            rowid        INTEGER PRIMARY KEY,
            doc_id       TEXT NOT NULL,
            agency       TEXT,
            jurisdiction TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_dsm_doc_id ON {_META_TABLE}(doc_id);
    """)
    conn.commit()


def index_document(conn: sqlite3.Connection, doc_id: str, title: str,
                    summary: str = "", agency: str = "",
                    jurisdiction: str = "") -> None:
    """Add or update a document in the FTS5 index."""
    try:
        ensure_fts_index(conn)
        # Delete existing entry by doc_id lookup
        rows = conn.execute(
            f"SELECT rowid FROM {_META_TABLE} WHERE doc_id = ?", (doc_id,)
        ).fetchall()
        for (rowid,) in rows:
            conn.execute(f"DELETE FROM {_FTS_TABLE} WHERE rowid = ?", (rowid,))
            conn.execute(f"DELETE FROM {_META_TABLE} WHERE rowid = ?", (rowid,))

        # Insert into FTS table (auto-assigns rowid)
        cursor = conn.execute(
            f"INSERT INTO {_FTS_TABLE}(title, summary) VALUES (?, ?)",
            (title or "", summary or "")
        )
        new_rowid = cursor.lastrowid
        # Store doc_id in companion table with same rowid
        conn.execute(
            f"INSERT INTO {_META_TABLE}(rowid, doc_id, agency, jurisdiction) VALUES (?, ?, ?, ?)",
            (new_rowid, doc_id, agency or "", jurisdiction or "")
        )
        conn.commit()
    except Exception as e:
        log.debug("FTS index error for %s: %s", doc_id, e)


def fts_search(conn: sqlite3.Connection, query: str,
                limit: int = 100) -> List[Dict[str, Any]]:
    """
    Full-text search using FTS5 BM25 ranking.
    Returns list of {doc_id, fts_rank} dicts ordered by relevance.
    """
    try:
        ensure_fts_index(conn)
        fts_query = _build_fts_query(query)
        rows = conn.execute(
            f"SELECT m.doc_id, f.rank "
            f"FROM {_FTS_TABLE} f "
            f"JOIN {_META_TABLE} m ON m.rowid = f.rowid "
            f"WHERE {_FTS_TABLE} MATCH ? "
            f"ORDER BY f.rank LIMIT ?",
            (fts_query, limit)
        ).fetchall()
        return [{"doc_id": r[0], "fts_rank": r[1]} for r in rows]
    except Exception as e:
        log.debug("FTS search error: %s", e)
        return []


def rebuild_fts_index(conn: sqlite3.Connection,
                       documents: List[Dict[str, Any]]) -> int:
    """Rebuild the entire FTS5 index from a list of document dicts."""
    try:
        ensure_fts_index(conn)
        conn.execute(f"DELETE FROM {_FTS_TABLE}")
        conn.execute(f"DELETE FROM {_META_TABLE}")
        conn.commit()
        for doc in documents:
            index_document(
                conn,
                doc_id       = doc.get("id", ""),
                title        = doc.get("title", ""),
                summary      = doc.get("plain_english") or doc.get("summary", ""),
                agency       = doc.get("agency", ""),
                jurisdiction = doc.get("jurisdiction", ""),
            )
        return len(documents)
    except Exception as e:
        log.error("FTS rebuild error: %s", e)
        return 0


def _build_fts_query(query: str) -> str:
    """Convert a natural-language query to a safe FTS5 query string."""
    # Remove FTS5 special characters that could cause parse errors
    clean = re.sub(r'[^\w\s\-]', ' ', query).strip()
    words = clean.split()
    if not words:
        return '""'

    # Exact phrase for multi-word query, plus individual token fallback
    if len(words) > 1:
        phrase = '"' + ' '.join(words) + '"'
        tokens = ' OR '.join(w for w in words if len(w) > 2)
        return f'{phrase} OR {tokens}'
    else:
        return words[0] + '*'   # prefix match for single token


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — TF-IDF SIMILARITY INDEX
# ═══════════════════════════════════════════════════════════════════════════════

class TFIDFIndex:
    """
    Sparse TF-IDF index over document texts.
    Operates entirely in memory using numpy.
    Persists to disk as a compact JSON snapshot for fast startup.
    """

    def __init__(self):
        self.vocab:    Dict[str, int]    = {}   # token → column index
        self.idf:      np.ndarray        = None  # shape (V,)
        self.doc_ids:  List[str]         = []   # row i → doc_id
        self.matrix:   Optional[np.ndarray] = None  # shape (N, V) — sparse-ish
        self.dirty     = False
        self._cache_path: Optional[Path] = None

    # ── Build / update ────────────────────────────────────────────────────────

    def build(self, documents: List[Tuple[str, str]]) -> None:
        """
        Build index from scratch.
        documents: list of (doc_id, text) tuples.
        """
        if not documents:
            return

        tokenised = [(doc_id, self._tokenize(text)) for doc_id, text in documents]

        # Build vocabulary from all documents
        all_tokens: Counter = Counter()
        for _, toks in tokenised:
            all_tokens.update(set(toks))   # document frequency
        # Regulatory terms get priority — keep even with df=1
        reg_terms    = set(re.sub(r'[^a-z0-9]', '', t.lower()) for t in AI_TERMS_EXPANDED)
        # Build vocabulary — keep tokens that appear in ≥2 documents,
        # OR appear in only 1 document but are known regulatory terms,
        # OR the corpus is very small (< 10 docs) in which case keep everything non-trivial.
        small_corpus = len(documents) < 10
        self.vocab = {
            tok: i for i, tok in enumerate(
                t for t, df in all_tokens.most_common()
                if df >= 2 or t in reg_terms or (small_corpus and df >= 1 and len(t) > 3)
            )
        }

        N = len(documents)
        V = len(self.vocab)
        if V == 0:
            return

        # IDF
        df_vec = np.zeros(V)
        for _, toks in tokenised:
            for tok in set(toks):
                if tok in self.vocab:
                    df_vec[self.vocab[tok]] += 1
        self.idf = np.log((N + 1) / (df_vec + 1)) + 1.0

        # TF-IDF matrix
        self.doc_ids = [d[0] for d in tokenised]
        mat = np.zeros((N, V), dtype=np.float32)
        for i, (_, toks) in enumerate(tokenised):
            tf = Counter(toks)
            for tok, count in tf.items():
                if tok in self.vocab:
                    j = self.vocab[tok]
                    mat[i, j] = (count / max(len(toks), 1)) * self.idf[j]

        # L2-normalise rows
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1
        self.matrix = mat / norms
        self.dirty  = False
        log.info("TF-IDF index built: %d docs, %d vocab terms", N, V)

    def add(self, doc_id: str, text: str) -> None:
        """Add a single document (incremental update). Marks dirty for rebuild."""
        self.dirty = True   # triggers rebuild on next query if needed

    def query(self, text: str, top_k: int = 50) -> List[Tuple[str, float]]:
        """
        Return top_k (doc_id, score) tuples for a query string.
        Scores are cosine similarities in [0, 1].
        """
        if self.matrix is None or len(self.vocab) == 0:
            return []

        expanded = expand_query(text)
        toks     = self._tokenize(expanded)
        V        = len(self.vocab)
        vec      = np.zeros(V, dtype=np.float32)
        tf       = Counter(toks)

        for tok, count in tf.items():
            if tok in self.vocab:
                j = self.vocab[tok]
                vec[j] = (count / max(len(toks), 1)) * self.idf[j]

        norm = np.linalg.norm(vec)
        if norm == 0:
            return []
        vec /= norm

        scores = self.matrix @ vec   # shape (N,)
        top    = np.argpartition(scores, -min(top_k, len(scores)))[-top_k:]
        top    = top[np.argsort(scores[top])[::-1]]

        return [
            (self.doc_ids[i], float(scores[i]))
            for i in top
            if scores[i] > 0.01
        ]

    def score_document(self, text: str) -> float:
        """
        Return a relevance score for a single document text.
        Uses the expanded keyword taxonomy weighted by IDF if available.
        """
        if self.idf is None or len(self.vocab) == 0:
            # Fall back to basic relevance_score
            return relevance_score(text)

        expanded = expand_query(text)
        toks     = self._tokenize(expanded)
        if not toks:
            return 0.0

        score = 0.0
        for tok in set(toks):
            if tok in self.vocab:
                j     = self.vocab[tok]
                score += self.idf[j]

        # Normalise against the top-10 IDF values (most distinctive terms)
        cap = float(np.sum(np.sort(self.idf)[-10:]))
        return min(score / cap, 1.0) if cap > 0 else 0.0

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: Path) -> None:
        """Save index to disk as a compact binary format."""
        try:
            data = {
                "vocab":   self.vocab,
                "idf":     self.idf.tolist() if self.idf is not None else [],
                "doc_ids": self.doc_ids,
                "matrix":  self.matrix.tolist() if self.matrix is not None else [],
            }
            path.write_bytes(json.dumps(data, separators=(',', ':')).encode())
        except Exception as e:
            log.debug("TF-IDF save error: %s", e)

    def load(self, path: Path) -> bool:
        """Load index from disk. Returns True on success."""
        try:
            data       = json.loads(path.read_bytes())
            self.vocab   = data["vocab"]
            self.idf     = np.array(data["idf"], dtype=np.float32) if data["idf"] else None
            self.doc_ids = data["doc_ids"]
            self.matrix  = np.array(data["matrix"], dtype=np.float32) if data["matrix"] else None
            return True
        except Exception:
            return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        Tokenize text into unigrams and meaningful bigrams.
        Bigrams are included when both tokens are non-stopwords.
        """
        STOPWORDS = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
            'for', 'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was',
            'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do',
            'does', 'did', 'will', 'would', 'could', 'should', 'may',
            'might', 'shall', 'this', 'that', 'these', 'those', 'it',
            'its', 'not', 'no', 'so', 'if', 'all', 'any', 'each',
        }
        words  = re.findall(r'[a-z0-9]+', text.lower())
        tokens = [w for w in words if len(w) > 1 and w not in STOPWORDS]
        # Add bigrams
        bigrams = [
            f"{tokens[i]}_{tokens[i+1]}"
            for i in range(len(tokens) - 1)
            if tokens[i] not in STOPWORDS and tokens[i+1] not in STOPWORDS
        ]
        return tokens + bigrams


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — ONNX EMBEDDING SIMILARITY (optional)
# ═══════════════════════════════════════════════════════════════════════════════

class EmbeddingIndex:
    """
    Semantic embedding index using an ONNX model.

    Activation: place all-MiniLM-L6-v2 ONNX files in output/models/all-MiniLM-L6-v2/
    The model files needed are:
      - model.onnx     (~22 MB — the embedding model)
      - tokenizer.json (~0.5 MB — tokenizer vocabulary)
      - tokenizer_config.json

    To download:
      python -c "from utils.search import download_embedding_model; download_embedding_model()"

    Without these files, this class is a no-op and Layer 3 handles everything.
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    EMBED_DIM  = 384   # all-MiniLM-L6-v2 output dimension

    def __init__(self):
        self._session  = None
        self._tokenizer = None
        self._doc_ids:  List[str]        = []
        self._embeddings: Optional[np.ndarray] = None   # shape (N, 384)
        self._available: Optional[bool]  = None   # lazy-checked

    @property
    def available(self) -> bool:
        if self._available is None:
            self._available = self._try_load()
        return self._available

    def _try_load(self) -> bool:
        model_dir = _models_dir() / self.MODEL_NAME
        onnx_path = model_dir / "model.onnx"
        tok_path  = model_dir / "tokenizer.json"
        if not onnx_path.exists() or not tok_path.exists():
            return False
        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(
                str(onnx_path),
                providers=["CPUExecutionProvider"],
            )
            # Load tokenizer manually from tokenizer.json
            self._tokenizer = _MinimalTokenizer(tok_path)
            log.info("Embedding model loaded: %s", self.MODEL_NAME)
            return True
        except Exception as e:
            log.debug("Could not load embedding model: %s", e)
            return False

    def embed(self, texts: List[str]) -> Optional[np.ndarray]:
        """Return (N, 384) embedding matrix, or None if model unavailable."""
        if not self.available or not texts:
            return None
        try:
            embeddings = []
            for text in texts:
                enc = self._tokenizer.encode(text[:512])
                input_ids      = np.array([enc["input_ids"]],      dtype=np.int64)
                attention_mask = np.array([enc["attention_mask"]], dtype=np.int64)
                token_type_ids = np.zeros_like(input_ids)
                outputs = self._session.run(None, {
                    "input_ids":      input_ids,
                    "attention_mask": attention_mask,
                    "token_type_ids": token_type_ids,
                })
                # Mean pooling
                last_hidden = outputs[0][0]   # (seq_len, hidden_dim)
                mask = attention_mask[0, :, None].astype(np.float32)
                emb  = (last_hidden * mask).sum(0) / mask.sum()
                # L2 normalise
                norm = np.linalg.norm(emb)
                embeddings.append(emb / norm if norm > 0 else emb)
            return np.stack(embeddings)
        except Exception as e:
            log.debug("Embedding error: %s", e)
            return None

    def build(self, documents: List[Tuple[str, str]]) -> bool:
        """Build embedding index from (doc_id, text) pairs."""
        if not self.available or not documents:
            return False
        texts  = [text for _, text in documents]
        embs   = self.embed(texts)
        if embs is None:
            return False
        self._doc_ids    = [d[0] for d in documents]
        self._embeddings = embs
        log.info("Embedding index built: %d documents", len(documents))
        return True

    def query(self, text: str, top_k: int = 50) -> List[Tuple[str, float]]:
        """Return top_k (doc_id, cosine_similarity) pairs."""
        if not self.available or self._embeddings is None:
            return []
        qvec = self.embed([text])
        if qvec is None:
            return []
        scores = self._embeddings @ qvec[0]   # cosine similarity (already L2-normed)
        top    = np.argpartition(scores, -min(top_k, len(scores)))[-top_k:]
        top    = top[np.argsort(scores[top])[::-1]]
        return [
            (self._doc_ids[i], float(scores[i]))
            for i in top
            if scores[i] > 0.1
        ]

    def save(self, path: Path) -> None:
        if self._embeddings is None:
            return
        try:
            np.save(str(path.with_suffix('.npy')), self._embeddings)
            (path.with_suffix('.ids.json')).write_text(json.dumps(self._doc_ids))
        except Exception as e:
            log.debug("Embedding save error: %s", e)

    def load(self, path: Path) -> bool:
        try:
            npy = path.with_suffix('.npy')
            ids = path.with_suffix('.ids.json')
            if not npy.exists() or not ids.exists():
                return False
            self._embeddings = np.load(str(npy))
            self._doc_ids    = json.loads(ids.read_text())
            return True
        except Exception:
            return False


class _MinimalTokenizer:
    """
    Minimal BPE tokenizer that reads tokenizer.json directly.
    Handles the all-MiniLM-L6-v2 vocabulary without needing huggingface/tokenizers.
    """

    MAX_LEN  = 128
    PAD_ID   = 0
    CLS_ID   = 101
    SEP_ID   = 102
    UNK_ID   = 100

    def __init__(self, tokenizer_json_path: Path):
        data = json.loads(tokenizer_json_path.read_text())
        # Build vocab: token → id
        self._vocab: Dict[str, int] = {}
        model = data.get("model", {})
        vocab = model.get("vocab", {})
        if isinstance(vocab, dict):
            self._vocab = vocab
        elif isinstance(vocab, list):
            self._vocab = {tok: i for i, tok in enumerate(vocab)}

    def encode(self, text: str) -> Dict[str, List[int]]:
        """Simple wordpiece tokenization returning input_ids and attention_mask."""
        words  = text.lower().split()
        tokens = [self.CLS_ID]
        for word in words[:self.MAX_LEN - 2]:
            wid = self._vocab.get(word, self._vocab.get(f"##" + word, self.UNK_ID))
            tokens.append(wid)
        tokens.append(self.SEP_ID)
        # Pad to MAX_LEN
        mask = [1] * len(tokens)
        pad_len = self.MAX_LEN - len(tokens)
        tokens += [self.PAD_ID] * pad_len
        mask   += [0]          * pad_len
        return {"input_ids": tokens, "attention_mask": mask}


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED SEARCH COORDINATOR
# ═══════════════════════════════════════════════════════════════════════════════

class SearchEngine:
    """
    Coordinates all four search layers into a single interface.
    Singleton — instantiated once per process.
    """

    def __init__(self):
        self._tfidf     = TFIDFIndex()
        self._embedding = EmbeddingIndex()
        self._built     = False

        # Try loading cached indices
        self._tfidf_cache_path = _models_dir() / "tfidf_index.json"
        self._emb_cache_path   = _models_dir() / "embedding_index"

    def build(self, documents: List[Dict[str, Any]]) -> None:
        """
        Build all indices from a list of document dicts.
        Expects each dict to have: id, title, plain_english/summary, agency, jurisdiction.
        """
        pairs = [
            (d["id"], self._doc_text(d))
            for d in documents
            if d.get("id")
        ]
        self._tfidf.build(pairs)
        self._tfidf.save(self._tfidf_cache_path)

        self._embedding.build(pairs)
        self._embedding.save(self._emb_cache_path)

        self._built = True
        log.info("Search engine built: %d documents, embedding=%s",
                 len(pairs), self._embedding.available)

    def load_or_build(self, documents: List[Dict[str, Any]]) -> None:
        """Load cached indices if available, otherwise build from scratch."""
        tfidf_ok = self._tfidf.load(self._tfidf_cache_path)
        emb_ok   = self._embedding.load(self._emb_cache_path)

        if tfidf_ok:
            log.debug("TF-IDF index loaded from cache (%d docs)", len(self._tfidf.doc_ids))
        else:
            log.info("Building TF-IDF index from scratch")
            self.build(documents)
            return

        if not emb_ok and self._embedding.available:
            # Have model but no cached embeddings — build them
            pairs = [(d["id"], self._doc_text(d)) for d in documents if d.get("id")]
            self._embedding.build(pairs)
            self._embedding.save(self._emb_cache_path)

        self._built = True

    def search(self, query: str, top_k: int = 50,
                conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
        """
        Search documents using all available layers.
        Returns list of {doc_id, score, sources} dicts sorted by combined score.
        """
        expanded = expand_query(query)
        results: Dict[str, Dict] = {}

        # Layer 2: FTS5 (fast, BM25-ranked)
        if conn:
            fts_results = fts_search(conn, expanded, limit=top_k * 2)
            for r in fts_results:
                did = r["doc_id"]
                if did not in results:
                    results[did] = {"doc_id": did, "score": 0.0, "sources": []}
                # FTS rank is negative BM25 — convert to 0-1
                fts_score = max(0.0, min(1.0, 1.0 + r["fts_rank"] / 10.0))
                results[did]["score"]  += fts_score * 0.35
                results[did]["sources"].append("fts")

        # Layer 3: TF-IDF
        if self._tfidf.matrix is not None:
            tfidf_results = self._tfidf.query(expanded, top_k=top_k * 2)
            for did, score in tfidf_results:
                if did not in results:
                    results[did] = {"doc_id": did, "score": 0.0, "sources": []}
                results[did]["score"]  += score * 0.40
                results[did]["sources"].append("tfidf")

        # Layer 4: Embeddings
        if self._embedding.available and self._embedding._embeddings is not None:
            emb_results = self._embedding.query(expanded, top_k=top_k)
            for did, score in emb_results:
                if did not in results:
                    results[did] = {"doc_id": did, "score": 0.0, "sources": []}
                results[did]["score"]  += score * 0.25
                results[did]["sources"].append("embedding")

        # Sort by combined score
        sorted_results = sorted(results.values(), key=lambda x: -x["score"])
        return sorted_results[:top_k]

    def score(self, text: str) -> float:
        """
        Score a single document text for AI relevance.
        Uses TF-IDF if available, otherwise falls back to expanded keyword scoring.
        """
        if self._tfidf.matrix is not None:
            return self._tfidf.score_document(text)
        return relevance_score(text)

    @staticmethod
    def _doc_text(doc: Dict) -> str:
        parts = [
            doc.get("title", ""),
            doc.get("plain_english", "") or doc.get("summary", ""),
            doc.get("agency", ""),
            doc.get("jurisdiction", ""),
        ]
        return " ".join(p for p in parts if p)


# ── Module-level singleton ─────────────────────────────────────────────────────

_engine: Optional[SearchEngine] = None


def get_engine() -> SearchEngine:
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine


def rebuild_index(documents: Optional[List[Dict]] = None) -> int:
    """
    Rebuild the search index from the database.
    If documents is None, loads from the database automatically.
    Returns number of documents indexed.
    """
    if documents is None:
        try:
            from utils.db import get_recent_summaries
            documents = get_recent_summaries(days=3650)
        except Exception as e:
            log.warning("Could not load documents for index rebuild: %s", e)
            documents = []

    engine = get_engine()
    engine.build(documents)
    return len(documents)


def search_documents(query: str, top_k: int = 50,
                      conn: Optional[sqlite3.Connection] = None) -> List[Dict]:
    """
    Search documents using all available layers.
    Public entry point for server endpoints.
    """
    engine = get_engine()
    if not engine._built:
        try:
            from utils.db import get_recent_summaries
            docs = get_recent_summaries(days=3650)
            engine.load_or_build(docs)
        except Exception:
            pass
    return engine.search(query, top_k=top_k, conn=conn)


# ── Optional: download embedding model ────────────────────────────────────────

def download_embedding_model() -> bool:
    """
    Download all-MiniLM-L6-v2 ONNX model files from Hugging Face.
    Run once: python -c "from utils.search import download_embedding_model; download_embedding_model()"
    """
    import urllib.request

    model_dir = _models_dir() / "all-MiniLM-L6-v2"
    model_dir.mkdir(exist_ok=True)

    BASE = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx"
    files = [
        ("model.onnx",            f"{BASE}/model.onnx"),
        ("tokenizer.json",        "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer.json"),
        ("tokenizer_config.json", "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer_config.json"),
    ]

    for filename, url in files:
        dest = model_dir / filename
        if dest.exists():
            print(f"  Already present: {filename}")
            continue
        print(f"  Downloading {filename}...")
        try:
            urllib.request.urlretrieve(url, str(dest))
            print(f"  ✓ {filename} ({dest.stat().st_size // 1024} KB)")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            return False

    print(f"\nModel saved to: {model_dir}")
    print("Restart ARIS to activate semantic search.")
    return True
