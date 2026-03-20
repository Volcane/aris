"""
ARIS — Regulatory Q&A Agent

Answers natural-language questions about AI regulation, grounded entirely
in the ARIS corpus (19 baselines + all summarised documents).

Design principles
-----------------
GROUNDED — every factual claim in the answer is tied to a specific passage
  from the corpus. The LLM is explicitly instructed to cite its sources
  inline using [SOURCE: id] markers that the response parser converts into
  structured citation objects for the UI.

HONEST — when the corpus does not contain enough information to answer a
  question, the agent says so rather than generating plausible-sounding text.
  The prompt instructs the LLM to explicitly flag gaps and uncertainties.

MULTI-JURISDICTION — questions like "how does the EU AI Act compare to
  Colorado's approach to risk tiers" are handled by retrieving passages from
  both jurisdictions and asking the LLM to synthesise across them with
  explicit attribution.

FOLLOW-UP AWARE — each response includes 3 suggested follow-up questions
  that deepen the inquiry rather than just rephrasing it. These are generated
  by the LLM based on what it found most interesting or incomplete in the
  retrieved passages.

Response format
---------------
The agent returns a structured dict:
  {
    "answer":     str,                 # full answer text with citations
    "citations":  List[Citation],      # source cards for the UI
    "follow_ups": List[str],           # 3 suggested follow-up questions
    "passages":   List[int],           # passage IDs used
    "model_used": str,
  }

Where Citation = {
    "source_id":    str,   # document/baseline ID
    "source_title": str,
    "jurisdiction": str,
    "section":      str,   # section label (e.g. "Key Definitions")
    "excerpt":      str,   # short quote from the passage
    "source_type":  str,   # "document" or "baseline"
}
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.cache import get_logger
from utils.llm   import call_llm, LLMError

log = get_logger("aris.qa")

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are ARIS — an Automated Regulatory Intelligence System covering AI regulation and data privacy law.
Your role is to answer questions about AI regulation using only the provided source passages.

Rules you must follow in every response:

GROUNDING
- Every factual claim must be supported by one of the provided passages.
- Cite sources inline using the format [SOURCE: X] immediately after the claim,
  where X is the passage source_id (e.g. [SOURCE: eu_ai_act] or [SOURCE: FR-2025-001]).
- If a claim is supported by multiple sources, cite all of them: [SOURCE: eu_ai_act][SOURCE: nist_ai_rmf].
- Never state facts that are not in the provided passages.

HONESTY
- If the passages do not contain enough information to answer the question,
  say so explicitly: "The corpus does not contain sufficient information to answer this."
- Distinguish between what is settled law (in force), what is proposed (not yet final),
  and what is guidance (recommended but not mandatory).
- Note jurisdictional scope explicitly: "Under EU law..." not "Under the law..."
- If sources conflict, note the conflict and explain both positions.

PRECISION
- Use the regulatory terminology from the sources, not paraphrases.
- When citing specific articles or provisions, use the exact numbering from the source.
- Distinguish between providers, deployers, importers, and other defined roles.

FORMAT
- Write in clear, precise prose. Avoid bullet-point lists unless comparing multiple items.
- After the answer, output a JSON block in this exact format:
  ```json
  {
    "follow_ups": [
      "First suggested follow-up question?",
      "Second suggested follow-up question?",
      "Third suggested follow-up question?"
    ]
  }
  ```
- Follow-up questions should probe deeper into the topic, not just restate the question."""


def _build_context(passages: List[Dict]) -> str:
    """Format retrieved passages into a numbered context block."""
    if not passages:
        return "No relevant passages found in the corpus."

    lines = ["REGULATORY CORPUS — RETRIEVED PASSAGES", "=" * 50, ""]
    for i, p in enumerate(passages, 1):
        jur     = p.get("jurisdiction", "")
        title   = p.get("source_title", "")
        section = p.get("section_label", "")
        sid     = p.get("source_id", "")
        stype   = p.get("source_type", "")

        header = f"[PASSAGE {i}]"
        if title:
            header += f" {title}"
        if jur:
            header += f" ({jur})"
        if section:
            header += f" — {section}"
        header += f"\nSource ID: {sid} | Type: {stype}"
        if p.get("chunk_total", 1) > 1:
            header += f" | Part {p['chunk_index']+1} of {p['chunk_total']}"

        lines.append(header)
        lines.append("-" * 40)
        lines.append(p.get("text", "").strip())
        lines.append("")

    return "\n".join(lines)


def _build_prompt(question: str, passages: List[Dict],
                   conversation_history: Optional[List[Dict]] = None) -> str:
    """Assemble the full user prompt."""
    ctx = _build_context(passages)

    history_block = ""
    if conversation_history:
        turns = []
        for turn in conversation_history[-3:]:   # last 3 turns for context
            turns.append(f"Q: {turn.get('question', '')}")
            ans = turn.get("answer", "")
            # Strip citation JSON from previous answers for brevity
            ans_clean = re.sub(r'```json.*?```', '', ans, flags=re.DOTALL).strip()
            turns.append(f"A: {ans_clean[:500]}…" if len(ans_clean) > 500 else f"A: {ans_clean}")
        history_block = "\n\nCONVERSATION HISTORY (for context):\n" + "\n".join(turns)

    return f"""{ctx}{history_block}

QUESTION: {question}

Answer the question using only the passages above. Cite every factual claim with [SOURCE: source_id].
After your answer, provide the follow-up questions JSON block."""


def _parse_response(raw: str, passages: List[Dict]) -> Dict:
    """
    Parse the LLM response into structured answer + citations + follow-ups.
    """
    # Extract follow-up questions JSON
    follow_ups = []
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if json_match:
        try:
            meta = json.loads(json_match.group(1))
            follow_ups = meta.get("follow_ups", [])[:3]
        except (json.JSONDecodeError, KeyError):
            pass

    # Strip the JSON block from the answer text
    answer = re.sub(r'```json.*?```', '', raw, flags=re.DOTALL).strip()

    # Build citations from [SOURCE: id] markers in the answer
    source_ids_cited = set(re.findall(r'\[SOURCE:\s*([^\]]+)\]', answer))

    # Build a lookup from source_id to best passage for that source
    source_passage_map: Dict[str, Dict] = {}
    for p in passages:
        sid = p.get("source_id", "")
        if sid not in source_passage_map:
            source_passage_map[sid] = p

    citations = []
    for sid in source_ids_cited:
        p = source_passage_map.get(sid.strip())
        if not p:
            continue
        # Extract a short excerpt (first 200 chars of the passage)
        text = p.get("text", "")
        excerpt = text[:200].strip()
        if len(text) > 200:
            excerpt += "…"
        citations.append({
            "source_id":    p.get("source_id", ""),
            "source_title": p.get("source_title", ""),
            "jurisdiction": p.get("jurisdiction", ""),
            "section":      p.get("section_label", ""),
            "excerpt":      excerpt,
            "source_type":  p.get("source_type", ""),
        })

    # Clean up citation markers in the display text
    # Keep them inline but make them readable
    answer_clean = re.sub(
        r'\[SOURCE:\s*([^\]]+)\]',
        lambda m: f'[{m.group(1).strip()}]',
        answer
    )

    return {
        "answer":    answer_clean.strip(),
        "citations": citations,
        "follow_ups": follow_ups,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# QA AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class QAAgent:
    """
    Answers regulatory questions grounded in the ARIS corpus.
    """

    def ask(self,
            question: str,
            jurisdiction: Optional[str] = None,
            conversation_history: Optional[List[Dict]] = None,
            max_passages: int = 12,
            save_to_history: bool = True) -> Dict[str, Any]:
        """
        Answer a regulatory question.

        Args:
            question:             Natural-language question.
            jurisdiction:         Optional filter — only retrieve passages
                                  from this jurisdiction.
            conversation_history: Previous turns for follow-up context.
            max_passages:         Maximum passages to include in context.
            save_to_history:      Persist this turn to qa_sessions table.

        Returns:
            {
              answer, citations, follow_ups, passages, retrieval_count, model_used
            }
        """
        if not question or not question.strip():
            return self._error("Question cannot be empty.")

        question = question.strip()
        log.info("Q&A question: %s", question[:80])

        # ── Retrieve passages ─────────────────────────────────────────────────
        try:
            from utils.rag import get_retriever
            retriever = get_retriever()
            retriever.ensure_ready()
            passages = retriever.retrieve(
                question,
                top_k       = max_passages,
                jurisdiction = jurisdiction,
            )
        except Exception as e:
            log.error("Passage retrieval failed: %s", e)
            passages = []

        if not passages:
            result = {
                "answer":           "I could not find any relevant passages in the corpus to answer "
                                    "this question. Try rebuilding the index (POST /api/qa/index/rebuild) "
                                    "or rephrase with more specific regulatory terminology.",
                "citations":        [],
                "follow_ups":       [],
                "passages":         [],
                "retrieval_count":  0,
                "model_used":       "n/a",
            }
            if save_to_history:
                self._save(question, result)
            return result

        # ── Call LLM ──────────────────────────────────────────────────────────
        prompt = _build_prompt(question, passages, conversation_history)

        try:
            from utils.llm import active_model
            raw   = call_llm(
                prompt     = prompt,
                system     = SYSTEM_PROMPT,
                max_tokens = 2000,
            )
            model = active_model()
        except LLMError as e:
            log.error("Q&A LLM call failed: %s", e)
            return self._error(f"LLM error: {e}")

        # ── Parse response ────────────────────────────────────────────────────
        parsed = _parse_response(raw, passages)

        result = {
            **parsed,
            "passages":         [p["id"] for p in passages],
            "retrieval_count":  len(passages),
            "model_used":       model,
        }

        if save_to_history:
            self._save(question, result)

        return result

    @staticmethod
    def _save(question: str, result: Dict) -> None:
        try:
            from utils.db import save_qa_session
            save_qa_session({
                "question":        question,
                "answer":          result.get("answer", ""),
                "citations":       result.get("citations", []),
                "passage_ids":     result.get("passages", []),
                "follow_ups":      result.get("follow_ups", []),
                "model_used":      result.get("model_used", ""),
                "retrieval_count": result.get("retrieval_count", 0),
            })
        except Exception as e:
            log.debug("Could not save Q&A session: %s", e)

    @staticmethod
    def _error(message: str) -> Dict:
        return {
            "answer":          message,
            "citations":       [],
            "follow_ups":      [],
            "passages":        [],
            "retrieval_count": 0,
            "model_used":      "n/a",
            "error":           True,
        }
