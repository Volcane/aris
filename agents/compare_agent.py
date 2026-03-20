"""
ARIS — Compare Agent

Produces a deep conceptual comparison between any two baselines or documents.

Unlike the DiffAgent (which does textual version comparison), the CompareAgent
answers: "How do these two regulations approach the same subject matter
differently?" — useful for cross-jurisdiction analysis.

Output
------
{
  title:           "EU AI Act vs NIST AI RMF",
  summary:         "2-3 sentence overview of key differences in approach",
  agreements:      [{area, description}]   # where they align
  divergences:     [{area, a_approach, b_approach, significance}]
  a_stricter_on:   [str]  # topics where A imposes harder requirements
  b_stricter_on:   [str]
  practical_notes: [str]  # implications for organisations subject to both
  citations:       [{source_id, source_title, jurisdiction}]
  focus:           optional concept that was used to focus the comparison
}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.cache import get_logger
from utils.llm   import call_llm, LLMError, active_model

log = get_logger("aris.compare")

BASELINES_DIR = Path(__file__).parent.parent / "data" / "baselines"

COMPARE_SYSTEM = """You are ARIS, an Automated Regulatory Intelligence System covering AI regulation and data privacy law.
You produce precise, structured comparisons of AI regulations for compliance professionals.
Use only the provided source material. Cite every claim with [SOURCE: id]."""

COMPARE_PROMPT = """Compare these two regulatory frameworks{focus_clause}.

FRAMEWORK A: {title_a} ({id_a})
{text_a}

---

FRAMEWORK B: {title_b} ({id_b})
{text_b}

---

Produce a structured comparison. Respond with a JSON object:
{{
  "summary": "2-3 sentence overview of the key difference in regulatory approach. Cite with [SOURCE: id].",
  "agreements": [
    {{"area": "short label", "description": "where they align. [SOURCE: id]"}}
  ],
  "divergences": [
    {{
      "area":         "short label",
      "a_approach":   "what {id_a} requires/recommends [SOURCE: {id_a}]",
      "b_approach":   "what {id_b} requires/recommends [SOURCE: {id_b}]",
      "significance": "why this difference matters practically"
    }}
  ],
  "a_stricter_on": ["topic where {id_a} is more demanding"],
  "b_stricter_on": ["topic where {id_b} is more demanding"],
  "practical_notes": ["implication for organisations subject to both frameworks"]
}}

Rules:
- Include 2-5 agreements, 3-6 divergences
- Be specific about article/section numbers where available
- Focus on practical differences, not just textual ones
- "stricter" means legally binding and more demanding, not just more detailed
- Respond ONLY with the JSON object, no preamble"""


def _load_baseline(bid: str) -> Optional[Dict]:
    path = BASELINES_DIR / f"{bid}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def _baseline_text(b: Dict, focus: Optional[str] = None, max_chars: int = 4000) -> str:
    """Extract the most relevant sections from a baseline for comparison."""
    skip = {"id", "jurisdiction", "title", "official_title", "short_name",
            "celex", "oj_reference", "last_reviewed"}
    parts = [b.get("overview", "")]

    # If focused, find relevant sections
    focus_lower = (focus or "").lower()
    for key, val in b.items():
        if key in skip or not val:
            continue
        vstr = json.dumps(val).lower()
        # Include if focused keyword matches OR include high-value sections always
        if focus_lower and focus_lower not in vstr:
            if key not in {"obligations_by_actor", "key_obligations",
                           "developer_obligations", "deployer_obligations",
                           "prohibited_practices", "penalties"}:
                continue
        parts.append(f"[{key.replace('_',' ').title()}]\n{json.dumps(val, indent=2)[:1200]}")

    return "\n\n".join(parts)[:max_chars]


def _doc_text(doc: Dict, max_chars: int = 3000) -> str:
    parts = [doc.get("title", ""), doc.get("plain_english", "") or ""]
    reqs = doc.get("requirements") or []
    if reqs:
        parts.append("Requirements: " + "; ".join(
            r if isinstance(r, str) else r.get("description", str(r))
            for r in reqs[:10]
        ))
    full = doc.get("full_text", "") or ""
    if full:
        parts.append(full[:2000])
    return "\n\n".join(p for p in parts if p)[:max_chars]


def _resolve(source_id: str, source_type: str) -> Optional[Dict]:
    """Load a baseline or document by ID."""
    if source_type in ("baseline", "auto"):
        b = _load_baseline(source_id)
        if b:
            return {"type": "baseline", "data": b,
                    "title": b.get("title", source_id),
                    "id": source_id}
    if source_type in ("document", "auto"):
        try:
            from utils.db import get_document, get_summary
            doc  = get_document(source_id)
            summ = get_summary(source_id)
            if doc:
                return {"type": "document",
                        "data": {**doc, **(summ or {})},
                        "title": doc.get("title", source_id),
                        "id": source_id}
        except Exception:
            pass
    return None


class CompareAgent:

    def compare(self,
                id_a:   str,
                id_b:   str,
                type_a: str = "auto",
                type_b: str = "auto",
                focus:  Optional[str] = None) -> Dict[str, Any]:
        """
        Compare two regulations (baselines or documents).

        Returns structured comparison dict. One LLM call.
        """
        src_a = _resolve(id_a, type_a)
        src_b = _resolve(id_b, type_b)

        if not src_a:
            return {"error": f"Could not find source: {id_a}"}
        if not src_b:
            return {"error": f"Could not find source: {id_b}"}

        # Build text representations
        if src_a["type"] == "baseline":
            text_a = _baseline_text(src_a["data"], focus=focus)
        else:
            text_a = _doc_text(src_a["data"])

        if src_b["type"] == "baseline":
            text_b = _baseline_text(src_b["data"], focus=focus)
        else:
            text_b = _doc_text(src_b["data"])

        focus_clause = f" with focus on {focus}" if focus else ""
        prompt = COMPARE_PROMPT.format(
            focus_clause = focus_clause,
            title_a      = src_a["title"],
            id_a         = id_a,
            text_a       = text_a,
            title_b      = src_b["title"],
            id_b         = id_b,
            text_b       = text_b,
        )

        try:
            raw   = call_llm(prompt=prompt, system=COMPARE_SYSTEM, max_tokens=2000)
            model = active_model()
        except LLMError as e:
            return {"error": f"LLM error: {e}"}

        # Parse JSON
        clean = re.sub(r'```json|```', '', raw).strip()
        try:
            result = json.loads(clean)
        except json.JSONDecodeError:
            m = re.search(r'\{.*\}', clean, re.DOTALL)
            if m:
                try:
                    result = json.loads(m.group(0))
                except Exception:
                    result = {"summary": clean[:500], "agreements": [],
                              "divergences": [], "a_stricter_on": [],
                              "b_stricter_on": [], "practical_notes": []}
            else:
                result = {"summary": clean[:500], "agreements": [],
                          "divergences": [], "a_stricter_on": [],
                          "b_stricter_on": [], "practical_notes": []}

        # Build citation objects from [SOURCE: id] in answer
        cited = set(re.findall(r'\[SOURCE:\s*([^\]]+)\]', json.dumps(result)))
        citations = []
        for sid in cited:
            sid = sid.strip()
            src = _resolve(sid, "auto")
            if src:
                citations.append({
                    "source_id":    sid,
                    "source_title": src["title"],
                    "source_type":  src["type"],
                })

        # Clean citation markers in text fields
        def _clean(obj: Any) -> Any:
            if isinstance(obj, str):
                return re.sub(r'\[SOURCE:\s*([^\]]+)\]',
                              lambda m: f'[{m.group(1).strip()}]', obj)
            if isinstance(obj, list):
                return [_clean(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            return obj

        return {
            "title":          f"{src_a['title']} vs {src_b['title']}",
            "source_a":       {"id": id_a, "title": src_a["title"], "type": src_a["type"]},
            "source_b":       {"id": id_b, "title": src_b["title"], "type": src_b["type"]},
            "focus":          focus,
            "model_used":     model,
            **_clean(result),
            "citations":      citations,
        }
