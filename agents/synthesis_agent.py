# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 Mitch Kwiatkowski
# ARIS   Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
"""
ARIS - Synthesis Agent

Two capabilities working together:

1. THEMATIC SYNTHESIS
   Reads across all documents in the database on a given theme or topic
   and produces a coherent regulatory landscape narrative - what is required,
   how the rules are evolving, and what the cumulative compliance picture
   looks like when you read all the documents together rather than one at a time.

2. JURISDICTION CONFLICT DETECTION
   After synthesising the landscape, identifies specific points where two or
   more jurisdictions disagree - conflicting requirements, opposite obligations,
   places where complying with one jurisdiction's rules may violate another's,
   and places where the same concept is defined differently.

Both outputs are stored in new database tables so they accumulate over time
and can be retrieved without re-running Claude.

Usage:
    from agents.synthesis_agent import SynthesisAgent

    agent = SynthesisAgent()

    # Synthesise everything about a topic
    result = agent.synthesise(topic="AI in healthcare")

    # Synthesise with explicit jurisdiction scope
    result = agent.synthesise(
        topic="automated hiring decisions",
        jurisdictions=["EU", "Federal", "PA"],
    )

    # Run conflict detection only (uses existing synthesis)
    conflicts = agent.detect_conflicts(
        synthesis_id=result["id"],
        jurisdiction_pairs=[("EU", "Federal"), ("EU", "GB")]
    )

    # Full pipeline: synthesise + detect conflicts
    result = agent.run(topic="generative AI content obligations")
"""

from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import anthropic  # kept for backward compat; actual calls go through utils.llm

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL
from utils.llm import call_llm, is_configured, LLMError
from utils.cache import get_logger

log = get_logger("aris.synthesis")


# Module-level re-exports so tests can patch them cleanly
def get_recent_summaries(days: int = 365, jurisdiction=None):
    from utils.db import get_recent_summaries as _fn

    return _fn(days=days, jurisdiction=jurisdiction)


def get_existing_synthesis(topic_key: str, max_age_days: int = 7):
    from utils.db import get_existing_synthesis as _fn

    return _fn(topic_key, max_age_days)


def save_synthesis(result: dict) -> int:
    from utils.db import save_synthesis as _fn

    return _fn(result)


# ── Token budget - synthesis reads many documents at once ─────────────────────
SYNTHESIS_MAX_TOKENS = 4096
CONFLICT_MAX_TOKENS = 4096
MAX_DOCS_PER_SYNTHESIS = 30  # cap at 30 documents per synthesis run
MAX_CHARS_PER_DOC = 1200  # truncate each doc contribution to keep within context


# ── System prompts ─────────────────────────────────────────────────────────────

SYNTHESIS_SYSTEM = """You are a senior regulatory intelligence analyst specialising in global AI law and policy.

You have access to summaries and key provisions from multiple AI regulations and legislative documents
across different jurisdictions. Your job is to synthesise these into a coherent regulatory landscape
narrative that a compliance team can use to understand the full picture - not just individual documents.

Focus on:
- What obligations exist in aggregate (not just per document)
- How the regulatory approach is evolving over time
- What gaps or grey areas remain unaddressed
- What a company must do to be compliant across all relevant documents

Always respond with valid JSON only - no markdown, no extra commentary."""


SYNTHESIS_PROMPT = """Analyse the following {doc_count} regulatory documents related to the topic: "{topic}"
Jurisdictions covered: {jurisdictions}
Date range: {date_range}

DOCUMENTS:
{documents}

---

Produce a comprehensive regulatory landscape synthesis in JSON with exactly these keys:

{{
  "topic": "{topic}",
  "landscape_summary": "<3-5 sentences describing the overall state of AI regulation on this topic across all jurisdictions covered>",
  "regulatory_maturity": "<one of: Emerging | Developing | Established | Fragmented - describes how coherent and settled the regulatory landscape is>",
  "evolution_narrative": "<2-3 sentences on how regulation of this topic has been changing - is it tightening, loosening, converging or diverging across jurisdictions?>",
  "cumulative_obligations": [
    {{
      "obligation": "<a specific thing companies must do that emerges from reading these documents together>",
      "source_jurisdictions": ["<list of jurisdictions that impose this>"],
      "applies_to": "<who this applies to - providers, deployers, importers, etc.>",
      "earliest_deadline": "<earliest compliance deadline across all jurisdictions, or null>",
      "universality": "<one of: Universal (all jurisdictions) | Majority | Minority | Single jurisdiction>"
    }}
  ],
  "cumulative_prohibitions": [
    {{
      "prohibition": "<something that is banned or restricted across one or more jurisdictions>",
      "source_jurisdictions": ["<list>"],
      "exceptions": "<any notable exceptions or carve-outs, or null>"
    }}
  ],
  "enforcement_landscape": {{
    "strictest_jurisdiction": "<which jurisdiction has the highest penalties or most aggressive enforcement posture>",
    "max_penalty_summary": "<brief description of the highest penalties across all jurisdictions>",
    "enforcement_gaps": "<jurisdictions or topics where enforcement mechanisms are weak or absent>"
  }},
  "regulatory_gaps": [
    "<specific aspect of AI on this topic that is not yet regulated anywhere, or regulated inconsistently>"
  ],
  "emerging_trends": [
    "<a direction or pattern visible across documents - e.g. increasing focus on human oversight, converging on risk tiers>"
  ],
  "key_definitions_compared": [
    {{
      "term": "<a defined term that appears in multiple jurisdictions>",
      "definitions": {{
        "<jurisdiction>": "<how this jurisdiction defines the term>"
      }},
      "practical_implication": "<why differences in definition matter for compliance>"
    }}
  ],
  "recommended_compliance_posture": "<2-3 sentences on what a company operating across these jurisdictions should do to be proactively compliant with the full landscape>"
}}"""


CONFLICT_SYSTEM = """You are a senior cross-jurisdictional regulatory compliance analyst specialising in AI law.

Your job is to identify specific, concrete conflicts between AI regulations from different jurisdictions -
places where complying with one jurisdiction's rules may create problems in another, or where the same
activity is treated fundamentally differently.

Be precise and practical. Only flag genuine conflicts that would require a company to make a real
compliance decision - not merely stylistic differences or differences in terminology.

Always respond with valid JSON only - no markdown, no extra commentary."""


CONFLICT_PROMPT = """Analyse the following regulatory summaries for jurisdiction conflicts on the topic: "{topic}"

{jurisdiction_summaries}

---

Identify all material conflicts, tensions, and overlapping obligations between these jurisdictions.
Return a JSON object with exactly these keys:

{{
  "conflict_summary": "<2-3 sentences describing the overall conflict landscape - are conflicts minor or fundamental?>",
  "conflicts": [
    {{
      "conflict_id": "<short slug e.g. eu-federal-consent-training-data>",
      "title": "<short title describing the conflict>",
      "type": "<one of: Direct Conflict | Double Obligation | Definitional Divergence | Scope Mismatch | Enforcement Gap | Permitted vs Prohibited>",
      "severity": "<one of: Critical | High | Medium | Low>",
      "jurisdiction_a": "<first jurisdiction>",
      "jurisdiction_b": "<second jurisdiction>",
      "jurisdiction_a_position": "<what jurisdiction A requires or permits on this point>",
      "jurisdiction_b_position": "<what jurisdiction B requires or permits on this point>",
      "conflict_description": "<precise description of why these positions conflict or create tension>",
      "practical_impact": "<what a company actually has to decide or do differently as a result>",
      "affected_companies": "<what types of companies are most affected>",
      "resolution_options": [
        "<a practical approach a company could take to navigate this conflict>"
      ],
      "safest_approach": "<the most conservative approach that satisfies both jurisdictions, or null if impossible>"
    }}
  ],
  "harmonised_areas": [
    {{
      "area": "<topic or requirement where jurisdictions are aligned>",
      "jurisdictions": ["<list>"],
      "description": "<what they agree on>"
    }}
  ],
  "highest_common_denominator": "<description of what a company would need to do to comply with the strictest version of every requirement across all jurisdictions - the 'if you satisfy this, you satisfy all' posture>",
  "jurisdiction_risk_ranking": [
    {{
      "jurisdiction": "<name>",
      "compliance_complexity": "<one of: High | Medium | Low>",
      "rationale": "<why this jurisdiction is easier or harder to comply with>"
    }}
  ]
}}"""


# ── Synthesis Agent ───────────────────────────────────────────────────────────


class SynthesisAgent:
    """
    Produces thematic regulatory landscape syntheses and jurisdiction
    conflict analyses from the documents already in the ARIS database.
    """

    def __init__(self):
        if not is_configured():
            from utils.llm import _provider

            raise ValueError(
                f"LLM provider '{_provider()}' is not configured. "
                "Set the appropriate API key in config/keys.env."
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        topic: str,
        jurisdictions: Optional[List[str]] = None,
        days: int = 365,
        detect_conflicts: bool = True,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Full pipeline: synthesise the landscape then detect conflicts.

        topic         - free-text topic e.g. "AI in healthcare" or "automated hiring"
        jurisdictions - list of jurisdiction codes to include; None = all in DB
        days          - how far back to look for relevant documents
        detect_conflicts - whether to run conflict detection after synthesis
        force_refresh - re-run even if a recent synthesis for this topic exists

        Returns a combined result dict with both synthesis and conflict data.
        """
        # Check for a recent cached synthesis on this topic
        topic_key = _topic_key(topic, jurisdictions)
        if not force_refresh:
            existing = get_existing_synthesis(topic_key, max_age_days=7)
            if existing:
                log.info("Returning cached synthesis for topic: %s", topic)
                return existing

        log.info(
            "Starting synthesis: topic='%s' jurisdictions=%s", topic, jurisdictions
        )

        # 1. Gather relevant documents
        docs = self._gather_documents(topic, jurisdictions, days)
        if not docs:
            return {
                "id": None,
                "topic": topic,
                "error": f"No summarized documents found for topic '{topic}'"
                + (f" in jurisdictions {jurisdictions}" if jurisdictions else ""),
                "docs_used": 0,
            }

        log.info(
            "Synthesis using %d documents across %d jurisdictions",
            len(docs),
            len({d["jurisdiction"] for d in docs}),
        )

        # 2. Run thematic synthesis
        synthesis = self._run_synthesis(topic, docs)
        if not synthesis:
            return {
                "id": None,
                "topic": topic,
                "error": "Synthesis failed",
                "docs_used": len(docs),
            }

        # 3. Run conflict detection
        conflicts = None
        if detect_conflicts and len({d["jurisdiction"] for d in docs}) >= 2:
            conflicts = self._run_conflict_detection(topic, docs, synthesis)

        # 4. Build combined result
        result = {
            "id": None,  # set after save
            "topic_key": topic_key,
            "topic": topic,
            "jurisdictions": list({d["jurisdiction"] for d in docs}),
            "docs_used": len(docs),
            "doc_ids": [d["id"] for d in docs],
            "synthesis": synthesis,
            "conflicts": conflicts,
            "generated_at": datetime.utcnow().isoformat(),
            "model_used": CLAUDE_MODEL,
        }

        # 5. Persist
        synthesis_id = save_synthesis(result)
        result["id"] = synthesis_id
        log.info(
            "Synthesis saved (ID %s): %d docs, %d conflicts found",
            synthesis_id,
            len(docs),
            len(conflicts.get("conflicts", [])) if conflicts else 0,
        )

        return result

    def synthesise(
        self,
        topic: str,
        jurisdictions: Optional[List[str]] = None,
        days: int = 365,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Run synthesis only (no conflict detection)."""
        return self.run(
            topic,
            jurisdictions,
            days,
            detect_conflicts=False,
            force_refresh=force_refresh,
        )

    def detect_conflicts_for_topic(
        self, topic: str, jurisdictions: Optional[List[str]] = None, days: int = 365
    ) -> Dict[str, Any]:
        """Run conflict detection directly, synthesising first if needed."""
        return self.run(
            topic, jurisdictions, days, detect_conflicts=True, force_refresh=True
        )

    def list_suggested_topics(self) -> List[Dict[str, Any]]:
        """
        Analyse the database and suggest synthesis topics based on what
        document clusters already exist - so you know what's worth synthesising.
        """
        summaries = get_recent_summaries(days=365)
        if not summaries:
            return []

        # Collect impact areas from all summarised documents
        area_counts: Dict[str, Dict] = {}
        for s in summaries:
            for area in s.get("impact_areas") or []:
                if area not in area_counts:
                    area_counts[area] = {
                        "topic": area,
                        "doc_count": 0,
                        "jurisdictions": set(),
                        "has_high_urgency": False,
                    }
                area_counts[area]["doc_count"] += 1
                area_counts[area]["jurisdictions"].add(s.get("jurisdiction", ""))
                if s.get("urgency") in ("High", "Critical"):
                    area_counts[area]["has_high_urgency"] = True

        # Convert sets to lists and sort by cross-jurisdictional breadth  - doc count
        suggestions = []
        for area, info in area_counts.items():
            jurs = list(info["jurisdictions"] - {""})
            if len(jurs) < 2 or info["doc_count"] < 2:
                continue
            suggestions.append(
                {
                    "topic": area,
                    "doc_count": info["doc_count"],
                    "jurisdictions": sorted(jurs),
                    "jurisdiction_count": len(jurs),
                    "has_high_urgency": info["has_high_urgency"],
                    "synthesis_value": len(jurs) * info["doc_count"],
                }
            )

        return sorted(suggestions, key=lambda x: x["synthesis_value"], reverse=True)

    # ── Document gathering ────────────────────────────────────────────────────

    def _gather_documents(
        self, topic: str, jurisdictions: Optional[List[str]], days: int
    ) -> List[Dict[str, Any]]:
        """
        Find documents in the database relevant to the topic.
        Combines keyword matching on title/summary with impact area matching.
        """
        all_summaries = get_recent_summaries(days=days, jurisdiction=None)
        topic_lower = topic.lower()
        topic_words = set(re.findall(r"\b[a-z]{3,}\b", topic_lower))

        scored = []
        for doc in all_summaries:
            # Filter by jurisdiction if specified
            if jurisdictions and doc.get("jurisdiction") not in jurisdictions:
                continue

            score = _relevance_to_topic(doc, topic_lower, topic_words)
            if score > 0:
                scored.append((score, doc))

        # Sort by relevance descending, cap at MAX_DOCS_PER_SYNTHESIS
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [doc for _, doc in scored[:MAX_DOCS_PER_SYNTHESIS]]

        # Always include at least docs with matching impact areas
        if not selected:
            # Fallback: broader match
            for doc in all_summaries:
                if jurisdictions and doc.get("jurisdiction") not in jurisdictions:
                    continue
                title = (doc.get("title") or "").lower()
                if any(w in title for w in topic_words if len(w) > 4):
                    selected.append(doc)
            selected = selected[:MAX_DOCS_PER_SYNTHESIS]

        return selected

    # ── Synthesis pass ────────────────────────────────────────────────────────

    def _run_synthesis(self, topic: str, docs: List[Dict]) -> Optional[Dict]:
        """Send documents to Claude for thematic synthesis."""
        jurisdictions = sorted({d.get("jurisdiction", "Unknown") for d in docs})
        dates = [
            d.get("published_date") or d.get("fetched_at")
            for d in docs
            if d.get("published_date")
        ]
        date_range = (
            f"{min(dates)[:10]} to {max(dates)[:10]}" if dates else "various dates"
        )

        doc_blocks = []
        for i, doc in enumerate(docs, 1):
            block = _format_doc_for_synthesis(i, doc)
            doc_blocks.append(block)

        prompt = SYNTHESIS_PROMPT.format(
            topic=topic,
            doc_count=len(docs),
            jurisdictions=", ".join(jurisdictions),
            date_range=date_range,
            documents="\n\n".join(doc_blocks),
        )

        return self._call_claude(prompt, SYNTHESIS_SYSTEM, SYNTHESIS_MAX_TOKENS)

    # ── Conflict detection pass ───────────────────────────────────────────────

    def _run_conflict_detection(
        self, topic: str, docs: List[Dict], synthesis: Dict
    ) -> Optional[Dict]:
        """
        Compare regulatory requirements across jurisdictions to find conflicts.
        Groups documents by jurisdiction and sends comparative summaries to Claude.
        """
        # Build per-jurisdiction summaries
        by_jur: Dict[str, List[Dict]] = {}
        for doc in docs:
            jur = doc.get("jurisdiction", "Unknown")
            by_jur.setdefault(jur, []).append(doc)

        if len(by_jur) < 2:
            log.info("Only one jurisdiction represented - skipping conflict detection")
            return None

        jur_blocks = []
        for jur, jur_docs in sorted(by_jur.items()):
            block = _format_jurisdiction_block(jur, jur_docs, synthesis)
            jur_blocks.append(block)

        prompt = CONFLICT_PROMPT.format(
            topic=topic,
            jurisdiction_summaries="\n\n".join(jur_blocks),
        )

        return self._call_claude(prompt, CONFLICT_SYSTEM, CONFLICT_MAX_TOKENS)

    # ── Claude caller ─────────────────────────────────────────────────────────

    def _call_claude(self, prompt: str, system: str, max_tokens: int) -> Optional[Dict]:
        try:
            raw = call_llm(prompt=prompt, system=system, max_tokens=max_tokens)
            data = _safe_parse_json(raw)
            if not data:
                log.error("SynthesisAgent: LLM returned unparseable JSON")
            return data
        except LLMError as e:
            log.error("SynthesisAgent LLM error: %s", e)
            return None
        except Exception as e:
            log.error("SynthesisAgent unexpected error: %s", e)
            return None


# ── Formatting helpers ────────────────────────────────────────────────────────


def _format_doc_for_synthesis(index: int, doc: Dict) -> str:
    """Format a single document summary for inclusion in the synthesis prompt."""
    parts = [
        f"[{index}] {doc.get('title', 'Untitled')}",
        f"Jurisdiction: {doc.get('jurisdiction', '?')} | "
        f"Type: {doc.get('doc_type', '?')} | "
        f"Status: {doc.get('status', '?')} | "
        f"Published: {(doc.get('published_date') or '')[:10]}",
    ]

    if doc.get("plain_english"):
        parts.append(f"Summary: {doc['plain_english']}")

    reqs = doc.get("requirements") or []
    if reqs:
        parts.append("Requirements: " + "; ".join(str(r) for r in reqs[:4]))

    actions = doc.get("action_items") or []
    if actions:
        parts.append("Action items: " + "; ".join(str(a) for a in actions[:3]))

    deadline = doc.get("deadline")
    if deadline:
        parts.append(f"Deadline: {deadline}")

    areas = doc.get("impact_areas") or []
    if areas:
        parts.append(f"Impact areas: {', '.join(str(a) for a in areas)}")

    return "\n".join(parts)


def _format_jurisdiction_block(jur: str, docs: List[Dict], synthesis: Dict) -> str:
    """Format all documents from one jurisdiction for the conflict prompt."""
    lines = [f"=== {jur} ==="]

    # Include cumulative obligations from synthesis that apply to this jurisdiction
    synth_data = synthesis or {}
    for obl in synth_data.get("cumulative_obligations", []):
        if jur in (obl.get("source_jurisdictions") or []):
            lines.append(f"[OBLIGATION] {obl['obligation']}")

    for doc in docs[:8]:  # cap at 8 docs per jurisdiction
        lines.append(f"\nDocument: {doc.get('title', 'Untitled')}")
        lines.append(
            f"Type: {doc.get('doc_type', '?')} | Status: {doc.get('status', '?')}"
        )

        if doc.get("plain_english"):
            lines.append(f"Summary: {doc['plain_english']}")

        reqs = doc.get("requirements") or []
        for r in reqs[:5]:
            lines.append(f"  • REQUIRES: {r}")

        deadline = doc.get("deadline")
        if deadline:
            lines.append(f"  • DEADLINE: {deadline}")

    return "\n".join(lines)


def _relevance_to_topic(doc: Dict, topic_lower: str, topic_words: set) -> float:
    """Score how relevant a document is to a topic (0.0 = not relevant)."""
    score = 0.0
    title = (doc.get("title") or "").lower()
    summary = (doc.get("plain_english") or "").lower()
    areas = [str(a).lower() for a in (doc.get("impact_areas") or [])]
    reqs = " ".join(str(r).lower() for r in (doc.get("requirements") or []))

    # Direct topic phrase match
    if topic_lower in title:
        score += 0.5
    if topic_lower in summary:
        score += 0.3

    # Word overlap
    title_words = set(re.findall(r"\b[a-z]{3,}\b", title))
    summary_words = set(re.findall(r"\b[a-z]{3,}\b", summary))
    area_words = set(w for a in areas for w in re.findall(r"\b[a-z]{3,}\b", a))

    overlap_title = len(topic_words & title_words) / max(len(topic_words), 1)
    overlap_summary = len(topic_words & summary_words) / max(len(topic_words), 1)
    overlap_areas = len(topic_words & area_words) / max(len(topic_words), 1)

    score += overlap_title * 0.4
    score += overlap_summary * 0.2
    score += overlap_areas * 0.3

    # Requirements/action items mention topic
    if any(w in reqs for w in topic_words if len(w) > 4):
        score += 0.1

    return min(score, 1.0)


def _topic_key(topic: str, jurisdictions: Optional[List[str]]) -> str:
    """Stable hash key for a topic + jurisdiction combination."""
    raw = topic.lower().strip()
    if jurisdictions:
        raw += "::" + ",".join(sorted(jurisdictions))
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _safe_parse_json(raw: str) -> Optional[Dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
    return None
