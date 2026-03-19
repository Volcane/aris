"""
ARIS — Interpretation Agent

Uses Claude (via Anthropic API) to:
  1. Score relevance of a document to AI regulation
  2. Classify document type and extract structured metadata
  3. Generate a plain-English summary with business action items
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import anthropic

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS
from utils.cache import get_logger, keyword_score

log = get_logger("aris.interpreter")

# Lazy import to avoid circular dependency
def _get_learning_agent():
    try:
        from agents.learning_agent import LearningAgent
        return LearningAgent()
    except Exception:
        return None

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a regulatory intelligence analyst specializing in AI law and policy.
Your job is to read raw legislative and regulatory text and produce structured, actionable 
business intelligence summaries for companies that use or develop AI systems.

You must be precise, neutral, and prioritize information that helps a legal or compliance team 
determine what actions a company must or should take.

Always respond with valid JSON only — no markdown, no extra commentary."""

ANALYSIS_PROMPT_TEMPLATE = """Analyze the following {doc_type} from {jurisdiction} ({source}).

TITLE: {title}
AGENCY / SPONSOR: {agency}
STATUS: {status}
PUBLISHED: {published_date}
URL: {url}

DOCUMENT TEXT:
{text}

---

Return a JSON object with exactly these keys:

{{
  "relevance_score": <float 0.0–1.0, how directly this applies to AI regulation>,
  "plain_english": "<2–3 sentence plain English summary of what this document does>",
  "requirements": [
    "<specific mandatory obligation for companies — use action verbs like 'Must', 'Shall', 'Required to'>",
    ...
  ],
  "recommendations": [
    "<non-mandatory guidance or best practice suggestion>",
    ...
  ],
  "action_items": [
    "<concrete, specific step a company should take in response to this document>",
    ...
  ],
  "deadline": "<ISO date or human-readable deadline if one exists, else null>",
  "impact_areas": [
    "<business area affected — e.g. 'Healthcare AI', 'Hiring Algorithms', 'Data Privacy', 'Marketing', 'Product Development'>",
    ...
  ],
  "urgency": "<one of: Low | Medium | High | Critical>",
  "doc_classification": "<one of: Final Rule | Proposed Rule | Executive Order | Presidential Memorandum | Guidance | Bill (Introduced) | Bill (Passed) | Enacted Law | Notice | Other>"
}}

Rules:
- requirements should only contain things that are LEGALLY MANDATORY
- recommendations should only contain VOLUNTARY or advisory items
- action_items should be specific and actionable (what should the legal/compliance team actually do?)
- relevance_score should be 0.0 if this has nothing to do with AI; 1.0 if it's directly and comprehensively AI-focused
- if the document is only tangentially AI-related (e.g., general tech regulation that mentions AI briefly), score accordingly
- urgency should reflect both the regulatory force (final rule > proposed rule) and timeline
"""

# ── Interpreter class ─────────────────────────────────────────────────────────

class InterpreterAgent:
    """
    Sends document text to Claude and returns a structured summary dict.
    """

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Get your key at https://console.anthropic.com/settings/keys"
            )
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def analyse(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Analyse a single document dict.
        Returns a summary dict ready to be stored in the `summaries` table,
        or None if the document is not AI-relevant.

        Uses the LearningAgent to:
          1. Pre-filter using learned source quality and keyword weights
          2. Inject domain-specific prompt additions from past adaptations
        """
        # ── Stage 1: Learning-aware pre-filter ───────────────────────────────
        learner = _get_learning_agent()

        if learner:
            skip, pre_score, reason = learner.should_skip(doc)
            if skip:
                log.debug("Learning pre-filter skipped %s: %s", doc.get("id"), reason)
                return None
        else:
            # Fallback to basic keyword score
            text_blob = f"{doc.get('title','')} {doc.get('full_text','')}"
            if keyword_score(text_blob) < 0.05:
                log.debug("Skipping low-relevance document: %s", doc["id"])
                return None

        # ── Stage 2: Build prompt with any domain-specific adaptations ────────
        text_blob = f"{doc.get('title','')} {doc.get('full_text','')}"

        # Get learned prompt additions for this source/agency/jurisdiction
        prompt_additions = ""
        if learner:
            prompt_additions = learner.get_adapted_prompt_additions(doc)

        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            doc_type      = doc.get("doc_type", "Document"),
            jurisdiction  = doc.get("jurisdiction", "Unknown"),
            source        = doc.get("source", "Unknown"),
            title         = doc.get("title", ""),
            agency        = doc.get("agency", "N/A"),
            status        = doc.get("status", "Unknown"),
            published_date= str(doc.get("published_date", "Unknown")),
            url           = doc.get("url", ""),
            text          = _truncate(text_blob, max_chars=5000),
        )

        # Inject prompt adaptations before the JSON instruction block
        if prompt_additions:
            prompt = prompt_additions + "\n\n" + prompt

        # ── Stage 3: Claude analysis ──────────────────────────────────────────
        try:
            message = self._client.messages.create(
                model      = CLAUDE_MODEL,
                max_tokens = MAX_TOKENS,
                system     = SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            raw  = message.content[0].text.strip()
            data = _safe_parse_json(raw)
        except anthropic.APIError as e:
            log.error("Anthropic API error for doc %s: %s", doc["id"], e)
            return None
        except json.JSONDecodeError as e:
            log.error("JSON parse error for doc %s: %s", doc["id"], e)
            return None

        if not data:
            return None

        # Final gate: if Claude itself rated relevance < 0.3, skip
        if data.get("relevance_score", 0) < 0.3:
            log.debug("Claude rated doc %s as low relevance (%.2f) — skipping",
                      doc["id"], data.get("relevance_score", 0))
            return None

        return {
            "document_id":     doc["id"],
            "plain_english":   data.get("plain_english", ""),
            "requirements":    data.get("requirements", []),
            "recommendations": data.get("recommendations", []),
            "action_items":    data.get("action_items", []),
            "deadline":        data.get("deadline"),
            "impact_areas":    data.get("impact_areas", []),
            "urgency":         data.get("urgency", "Medium"),
            "relevance_score": float(data.get("relevance_score", 0.5)),
            "model_used":      CLAUDE_MODEL,
        }

    def analyse_batch(self, docs: List[Dict[str, Any]],
                      progress_callback=None) -> List[Dict[str, Any]]:
        """
        Analyse a list of documents. Returns list of successful summary dicts.
        progress_callback(current, total) is called if provided.
        """
        summaries = []
        for i, doc in enumerate(docs):
            if progress_callback:
                progress_callback(i + 1, len(docs))
            try:
                result = self.analyse(doc)
                if result:
                    summaries.append(result)
            except Exception as e:
                log.error("Unexpected error analysing doc %s: %s", doc.get("id"), e)
        return summaries


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[... truncated at {max_chars} chars]"


def _safe_parse_json(raw: str) -> Optional[Dict]:
    """Handle Claude potentially wrapping JSON in markdown fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw   = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find the JSON object in the text
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
    return None
