"""
ARIS — Regulatory Brief Agent

Generates structured intelligence briefs on regulatory topics, leveraging
the same RAG infrastructure as the Q&A system but producing a different
output format: a structured document rather than a conversational answer.

A brief is a 5-minute read that covers:
  - Overview of the regulatory landscape on the topic
  - Key jurisdictions and their approaches (comparative)
  - What is settled vs still developing
  - Practical implications
  - Open questions and what to watch

Briefs are cached in the database (brief_cache table) and expire after 14 days.
They can be regenerated on demand.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.cache import get_logger
from utils.llm   import call_llm, LLMError, active_model

log = get_logger("aris.briefs")

# ── DB model (appended to db.py via migration) ────────────────────────────────
# brief_cache: id, topic_key, topic_label, content_json, model_used, built_at

# ── Prompts ───────────────────────────────────────────────────────────────────

BRIEF_SYSTEM = """You are ARIS, an Automated Regulatory Intelligence System producing structured
regulatory intelligence briefs for compliance professionals, policy analysts, and legal teams.

Your briefs are:
- Grounded entirely in the provided source material
- Precise about jurisdiction and scope
- Clear about what is settled law vs still developing
- Practical — focused on implications, not just description
- Properly cited: reference each source as [SOURCE: id]

Format your response as structured markdown with clear headings."""

BRIEF_PROMPT = """Generate a regulatory intelligence brief on: {topic}

SOURCE MATERIAL:
{context}

Write a brief with these sections:

## Overview
2-3 sentences on the current state of {topic} regulation globally.
Cite sources: [SOURCE: source_id]

## Key Jurisdictions

For each major jurisdiction covered in the sources, one paragraph covering:
- The regulatory approach
- Specific obligations (if any)
- Status (in force / proposed / guidance)

## Convergences
What do most jurisdictions agree on? (2-4 bullet points)

## Divergences  
Where do jurisdictions meaningfully differ? (2-4 bullet points)

## What Is Settled vs Still Developing
Two short lists.

## Practical Implications
3-5 concrete implications for organisations operating across multiple jurisdictions.

## Open Questions & What to Watch
2-3 developments worth monitoring.

Keep each section concise. Total brief should be readable in 5 minutes.
Cite every factual claim with [SOURCE: baseline_id or doc_id]."""


# ── Brief Agent ───────────────────────────────────────────────────────────────

class BriefAgent:

    def generate(self,
                 topic:        str,
                 jurisdiction: Optional[str] = None,
                 force:        bool          = False,
                 cache_days:   int           = 14) -> Dict[str, Any]:
        """
        Generate a regulatory brief on a topic.

        Uses RAG to retrieve relevant passages, then generates a structured
        brief via one LLM call. Results are cached for cache_days.

        Args:
            topic:        Natural-language topic (e.g. "foundation model governance")
            jurisdiction: Optionally limit to a specific jurisdiction
            force:        Rebuild even if cached
            cache_days:   Cache TTL in days

        Returns:
            {topic_key, topic_label, content, citations, model_used, built_at}
        """
        topic_key = self._make_key(topic, jurisdiction)

        # Return cached if available and fresh
        if not force:
            cached = self._load_cache(topic_key, max_age_days=cache_days)
            if cached:
                return cached

        # Retrieve relevant passages using the Q&A RAG infrastructure
        try:
            from utils.rag import get_retriever
            retriever = get_retriever()
            retriever.ensure_ready()
            passages = retriever.retrieve(topic, top_k=14, jurisdiction=jurisdiction)
        except Exception as e:
            log.error("Passage retrieval failed for brief '%s': %s", topic, e)
            passages = []

        if not passages:
            return {
                "topic_key":   topic_key,
                "topic_label": topic,
                "content":     f"Insufficient corpus content to generate a brief on '{topic}'. "
                               "Ensure the Q&A index is built (POST /api/qa/index/rebuild).",
                "citations":   [],
                "model_used":  None,
                "built_at":    datetime.utcnow().isoformat(),
                "error":       True,
            }

        # Build context block
        context = self._build_context(passages)

        prompt = BRIEF_PROMPT.format(topic=topic, context=context)

        try:
            raw   = call_llm(prompt=prompt, system=BRIEF_SYSTEM, max_tokens=3000)
            model = active_model()
        except LLMError as e:
            log.error("Brief LLM call failed: %s", e)
            return {"error": True, "topic_key": topic_key, "topic_label": topic,
                    "content": f"LLM error: {e}", "citations": [], "model_used": None,
                    "built_at": datetime.utcnow().isoformat()}

        # Extract citations from [SOURCE: id] markers
        cited_ids = set(re.findall(r'\[SOURCE:\s*([^\]]+)\]', raw))
        source_map = {p["source_id"]: p for p in passages}
        citations = [
            {
                "source_id":    sid.strip(),
                "source_title": source_map.get(sid.strip(), {}).get("source_title", ""),
                "jurisdiction": source_map.get(sid.strip(), {}).get("jurisdiction", ""),
                "source_type":  source_map.get(sid.strip(), {}).get("source_type", ""),
            }
            for sid in cited_ids
            if sid.strip() in source_map
        ]

        # Clean citation markers in the content
        content = re.sub(r'\[SOURCE:\s*([^\]]+)\]',
                         lambda m: f'[{m.group(1).strip()}]', raw).strip()

        result = {
            "topic_key":   topic_key,
            "topic_label": topic,
            "content":     content,
            "citations":   citations,
            "model_used":  model,
            "built_at":    datetime.utcnow().isoformat(),
            "passage_count": len(passages),
        }

        self._save_cache(topic_key, topic, result)
        return result

    # ── Cache helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _make_key(topic: str, jurisdiction: Optional[str] = None) -> str:
        import hashlib
        raw = (topic.lower().strip() + (jurisdiction or "").lower()).encode()
        return "brief_" + hashlib.md5(raw).hexdigest()[:12]

    @staticmethod
    def _save_cache(key: str, label: str, result: Dict) -> None:
        try:
            from utils.db import save_brief_cache
            save_brief_cache(key, label, result)
        except Exception as e:
            log.debug("Brief cache save failed: %s", e)

    @staticmethod
    def _load_cache(key: str, max_age_days: int) -> Optional[Dict]:
        try:
            from utils.db import get_brief_cache
            return get_brief_cache(key, max_age_days=max_age_days)
        except Exception:
            return None

    @staticmethod
    def _build_context(passages: List[Dict]) -> str:
        lines = []
        for i, p in enumerate(passages, 1):
            title   = p.get("source_title", "")
            jur     = p.get("jurisdiction", "")
            section = p.get("section_label", "")
            sid     = p.get("source_id", "")
            lines.append(f"[{i}] {title} ({jur}) — {section} | source_id: {sid}")
            lines.append(p.get("text", "").strip()[:600])
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def list_briefs() -> List[Dict]:
        try:
            from utils.db import list_brief_caches
            return list_brief_caches()
        except Exception:
            return []
