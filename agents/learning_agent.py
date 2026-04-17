# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 Mitch Kwiatkowski
# ARIS — Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
"""
ARIS — Learning Agent

Enables the system to improve over time based on human feedback and
observed outcomes. Operates across four learning dimensions:

1. RELEVANCE FEEDBACK
   When a user marks a document as irrelevant, the system records what
   signals led to the false positive (source, agency, keywords matched,
   jurisdiction, doc_type) and adjusts future filtering accordingly.
   Conversely, when a document is confirmed relevant, those signals are
   reinforced.

2. SOURCE QUALITY SCORING
   Each source (federal_register, legiscan_pa, eurlex_sparql, etc.) and
   each agency accumulates a rolling quality score based on the ratio of
   relevant to irrelevant documents it produces. Low-scoring sources
   require a higher keyword score to pass pre-filtering.

3. KEYWORD LEARNING
   Tracks which keywords in the AI_KEYWORDS list are most predictive of
   genuinely relevant documents, and which frequently appear in false
   positives. Over time the keyword pre-filter weights adjust.

4. PROMPT ADAPTATION
   When a domain or source consistently produces misclassifications,
   Claude's interpretation prompt is automatically extended with domain-
   specific guidance derived from the feedback pattern.

5. AGENTIC SCHEDULING
   The scheduler learns when each source publishes new documents and
   concentrates fetches accordingly, reducing wasted API calls.

6. PRIORITY QUEUE
   Documents are scored not just for relevance but for analysis urgency
   (deadline proximity, document type, source reliability) and processed
   in priority order.

7. ANOMALY DETECTION
   Documents with unusual structure for their source are flagged for
   review even if keyword scores are low, catching important documents
   that don't fit expected patterns.

All learning state is stored in the SQLite database (learning_* tables)
so it persists across restarts and is fully inspectable.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import anthropic  # kept for backward compat; actual calls go through utils.llm

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, AI_KEYWORDS
from utils.llm import call_llm, is_configured, LLMError
from utils.cache import get_logger, keyword_score

log = get_logger("aris.learning")

# Import db helpers at module level so tests can patch them cleanly
def _db():
    """Lazy import db helpers to avoid circular imports at load time."""
    import utils.db as _db_mod
    return _db_mod


def is_known_false_positive_pattern(doc: dict) -> bool:
    """Module-level re-export so tests can patch agents.learning_agent.is_known_false_positive_pattern."""
    from utils.db import is_known_false_positive_pattern as _fn
    return _fn(doc)


def get_source_profile(source_key: str):
    from utils.db import get_source_profile as _fn
    return _fn(source_key)


# ── Learning Agent ────────────────────────────────────────────────────────────

class LearningAgent:
    """
    Adaptive intelligence layer. Improves ARIS filtering, prioritization,
    and interpretation accuracy over time based on feedback and outcomes.
    """

    def __init__(self):
        pass   # no client needed — calls go through utils.llm

    def _ensure_configured(self):
        """Raise if the LLM provider is not set up."""
        if not is_configured():
            from utils.llm import _provider
            raise ValueError(
                f"LLM provider '{_provider()}' is not configured. "
                "Set the appropriate API key in config/keys.env."
            )

    # ── 1. Feedback recording ─────────────────────────────────────────────────

    def record_feedback(self, doc: Dict[str, Any],
                        feedback: str,
                        reason: Optional[str] = None,
                        user: str = "user") -> Dict[str, Any]:
        """
        Record human feedback on a document's relevance.

        feedback: "relevant" | "not_relevant" | "partially_relevant"
        reason:   free-text explanation of why (optional but valuable)

        Returns the updated source quality score for the document's source.
        """
        from utils.db import save_feedback, get_source_profile, upsert_source_profile

        # Extract signals from the document that caused it to be fetched
        title      = (doc.get("title") or "").lower()
        full_text  = (doc.get("full_text") or "").lower()
        combined   = f"{title} {full_text}"
        source     = doc.get("source", "")
        agency     = doc.get("agency", "") or ""
        jurisdiction = doc.get("jurisdiction", "")
        doc_type   = doc.get("doc_type", "")
        relevance_score = doc.get("relevance_score")  # Claude's rating

        # Which keywords matched this document
        matched_keywords = [kw for kw in AI_KEYWORDS if kw in combined]

        is_positive = feedback == "relevant"
        is_negative = feedback == "not_relevant"

        # Store the feedback event
        save_feedback({
            "document_id":       doc["id"],
            "feedback":          feedback,
            "reason":            reason,
            "source":            source,
            "agency":            agency,
            "jurisdiction":      jurisdiction,
            "doc_type":          doc_type,
            "matched_keywords":  matched_keywords,
            "claude_score":      relevance_score,
            "user":              user,
            "recorded_at":       datetime.utcnow(),
        })

        # Update source quality profile
        profile = get_source_profile(source) or _default_profile(source)
        profile["total_count"]    += 1
        profile["positive_count"] += (1 if is_positive else 0)
        profile["negative_count"] += (1 if is_negative else 0)
        profile["quality_score"]   = _compute_quality_score(profile)
        profile["last_updated"]    = datetime.utcnow().isoformat()
        upsert_source_profile(source, profile)

        # Also update domain-specific profile so AI and privacy sources
        # accrue quality scores independently
        doc_domain = doc.get("domain", "ai")
        if doc_domain and doc_domain != "ai":
            domain_key = f"{source}::{doc_domain}"
            dprofile   = get_source_profile(domain_key) or _default_profile(domain_key)
            dprofile["total_count"]    += 1
            dprofile["positive_count"] += (1 if is_positive else 0)
            dprofile["negative_count"] += (1 if is_negative else 0)
            dprofile["quality_score"]  = _compute_quality_score(dprofile)
            dprofile["last_updated"]   = datetime.utcnow().isoformat()
            upsert_source_profile(domain_key, dprofile)

        # Update agency quality profile
        if agency:
            agency_key = f"agency::{agency[:80]}"
            aprof = get_source_profile(agency_key) or _default_profile(agency_key)
            aprof["total_count"]    += 1
            aprof["positive_count"] += (1 if is_positive else 0)
            aprof["negative_count"] += (1 if is_negative else 0)
            aprof["quality_score"]   = _compute_quality_score(aprof)
            aprof["last_updated"]    = datetime.utcnow().isoformat()
            upsert_source_profile(agency_key, aprof)

        # Update keyword scores based on which keywords matched
        self._update_keyword_scores(matched_keywords, is_positive, is_negative)

        # Trigger prompt adaptation if we have enough negative feedback
        # from this source/domain combination
        adaptation_needed = self._check_adaptation_trigger(source, agency, jurisdiction)
        if adaptation_needed:
            log.info("Adaptation triggered for source=%s agency=%s", source, agency)
            self._adapt_prompt_for_domain(source, agency, jurisdiction)

        log.info(
            "Feedback recorded: %s on %s (source=%s, quality=%.2f)",
            feedback, doc["id"][:40], source, profile["quality_score"]
        )
        return profile

    def record_auto_feedback(self, doc: Dict[str, Any],
                              claude_relevance: float) -> None:
        """
        Record autonomous feedback derived from Claude's own relevance score,
        without any user action required.

        Called after every summarisation. Uses half the weight of human
        feedback so it influences but doesn't dominate source quality scores.

        claude_relevance: 0.0–1.0 from the summary's relevance_score field.
          >= 0.7  → treated as implicit positive signal
          <= 0.20 → treated as implicit negative signal
          between → neutral, no update (ambiguous zone)
        """
        from utils.db import get_source_profile, upsert_source_profile

        source     = doc.get("source", "")
        agency     = (doc.get("agency") or "")[:80]
        doc_domain = doc.get("domain", "ai")

        if not source:
            return

        # Map relevance score to signal strength
        # High confidence positive: 0.7+ (clearly AI/privacy relevant)
        # High confidence negative: 0.20 or below (clearly irrelevant)
        # Ambiguous zone: 0.21–0.69 → skip, don't confuse the signal
        if claude_relevance >= 0.70:
            is_positive, is_negative = True, False
            # Half weight: positive delta 0.025 vs human 0.05
            kw_delta = 0.025
        elif claude_relevance <= 0.20:
            is_positive, is_negative = False, True
            # Half weight: negative delta 0.04 vs human 0.08
            kw_delta = -0.04
        else:
            return   # ambiguous — don't update

        signal = "positive" if is_positive else "negative"
        log.debug(
            "Auto-feedback %s for %s (claude_score=%.2f, source=%s)",
            signal, doc.get("id", "")[:40], claude_relevance, source
        )

        # Update source quality profile (half weight vs human feedback)
        profile = get_source_profile(source) or _default_profile(source)
        # Use fractional counts to represent half-weight signal
        profile["total_count"]    = profile.get("total_count", 0) + 0.5
        profile["positive_count"] = profile.get("positive_count", 0) + (0.5 if is_positive else 0)
        profile["negative_count"] = profile.get("negative_count", 0) + (0.5 if is_negative else 0)
        profile["quality_score"]  = _compute_quality_score(profile)
        profile["last_updated"]   = datetime.utcnow().isoformat()
        upsert_source_profile(source, profile)

        # Domain-specific profile (privacy sources scored separately)
        if doc_domain and doc_domain != "ai":
            dk = f"{source}::{doc_domain}"
            dp = get_source_profile(dk) or _default_profile(dk)
            dp["total_count"]    = dp.get("total_count", 0) + 0.5
            dp["positive_count"] = dp.get("positive_count", 0) + (0.5 if is_positive else 0)
            dp["negative_count"] = dp.get("negative_count", 0) + (0.5 if is_negative else 0)
            dp["quality_score"]  = _compute_quality_score(dp)
            dp["last_updated"]   = datetime.utcnow().isoformat()
            upsert_source_profile(dk, dp)

        # Agency profile
        if agency:
            ak = f"agency::{agency}"
            ap = get_source_profile(ak) or _default_profile(ak)
            ap["total_count"]    = ap.get("total_count", 0) + 0.5
            ap["positive_count"] = ap.get("positive_count", 0) + (0.5 if is_positive else 0)
            ap["negative_count"] = ap.get("negative_count", 0) + (0.5 if is_negative else 0)
            ap["quality_score"]  = _compute_quality_score(ap)
            ap["last_updated"]   = datetime.utcnow().isoformat()
            upsert_source_profile(ak, ap)

        # Update keyword weights at half strength
        title    = (doc.get("title") or "").lower()
        combined = f"{title} {(doc.get('full_text') or '').lower()}"
        matched  = [kw for kw in AI_KEYWORDS if kw in combined]
        if matched:
            from utils.db import get_keyword_weights, save_keyword_weights
            weights = get_keyword_weights()
            for kw in matched:
                weights[kw] = max(0.1, min(2.0, weights.get(kw, 1.0) + kw_delta))
            save_keyword_weights(weights)

    # ── 2. Document scoring (pre-fetch filter) ────────────────────────────────

    def score_document_pre_filter(self, doc: Dict[str, Any]) -> float:
        """
        Compute a composite relevance score BEFORE sending to Claude.
        Returns 0.0–1.0. Below threshold → skip the document entirely.
        """
        title     = (doc.get("title") or "").lower()
        full_text = (doc.get("full_text") or "").lower()
        combined  = f"{title} {full_text}"
        source    = doc.get("source", "")
        agency    = (doc.get("agency") or "")[:80]

        # Privacy documents use privacy relevance scoring, not AI keyword scoring
        doc_domain = doc.get("domain", "ai")
        if doc_domain == "privacy":
            from utils.cache import is_privacy_relevant
            priv_relevant = is_privacy_relevant(combined)
            base_kw = 0.6 if priv_relevant else 0.05
        else:
            kw_score   = keyword_score(combined)
            base_kw    = kw_score

        title_kw_count = sum(1 for kw in AI_KEYWORDS if kw in title)
        title_boost    = min(title_kw_count * 0.1, 0.3)

        # Privacy title boost — check privacy terms in title
        if doc_domain == "privacy":
            from utils.search import PRIVACY_TERMS_EXPANDED
            priv_title_kws = sum(1 for kw in PRIVACY_TERMS_EXPANDED if kw in title)
            title_boost    = min(priv_title_kws * 0.08, 0.3)

        # Use domain-keyed profile when available, fall back to shared profile
        # This ensures privacy sources aren't penalised by AI keyword feedback
        domain_src_key = f"{source}::{doc_domain}" if doc_domain != "ai" else source
        src_profile    = get_source_profile(domain_src_key) or get_source_profile(source)
        src_quality    = src_profile["quality_score"] if src_profile else 0.7

        agency_key     = f"agency::{agency}"
        domain_ag_key  = f"{agency_key}::{doc_domain}" if doc_domain != "ai" else agency_key
        ag_profile     = get_source_profile(domain_ag_key) or get_source_profile(agency_key)
        ag_quality     = ag_profile["quality_score"] if ag_profile else 0.7

        kw_weights  = self._get_keyword_weights()
        weighted_kw = _weighted_keyword_score(combined, kw_weights)

        # For privacy docs weight keyword score less (different vocabulary)
        if doc_domain == "privacy":
            composite = (
                (base_kw     * 0.50) +
                (title_boost * 0.25) +
                (src_quality * 0.15) +
                (ag_quality  * 0.10)
            )
        else:
            composite = (
                (weighted_kw * 0.40) +
                (title_boost * 0.25) +
                (src_quality * 0.20) +
                (ag_quality  * 0.15)
            )
        return min(composite, 1.0)

    def should_skip(self, doc: Dict[str, Any],
                    threshold: Optional[float] = None) -> Tuple[bool, float, str]:
        """
        Determine whether to skip a document entirely based on learned signals.
        Returns (skip: bool, score: float, reason: str)
        """
        # Check explicit false-positive pattern blocklist
        if is_known_false_positive_pattern(doc):
            return True, 0.0, "matches known false-positive pattern"

        score = self.score_document_pre_filter(doc)

        # Dynamic threshold: tighten if source quality is very low
        src_profile = get_source_profile(doc.get("source", ""))
        if src_profile and src_profile.get("quality_score", 1.0) < 0.3 and src_profile.get("total_count", 0) > 10:
            effective_threshold = (threshold or 0.15) * 1.5
        else:
            effective_threshold = threshold or 0.08

        if score < effective_threshold:
            return True, score, f"pre-filter score {score:.2f} below threshold {effective_threshold:.2f}"

        return False, score, "passed"

    # ── 3. Priority queue scoring ─────────────────────────────────────────────

    def score_analysis_priority(self, doc: Dict[str, Any]) -> float:
        """
        Score how urgently a document should be analysed by Claude.
        Higher = process sooner.

        Factors:
          - Document type (Final Rule > Proposed Rule > Notice)
          - Deadline proximity (comment period closing soon)
          - Source quality (reliable sources processed first)
          - Document age (newer = higher priority)
          - Known high-priority agencies / jurisdictions
        """
        score = 0.5   # baseline

        doc_type = (doc.get("doc_type") or "").upper()
        status   = (doc.get("status")   or "").upper()

        # Document type signals
        type_scores = {
            "RULE":           0.9,   "FINAL RULE":         0.9,
            "PRORULE":        0.75,  "PROPOSED RULE":      0.75,
            "REGULATION":     0.85,
            "ENACTED LAW":    0.95,  "ACT OF PARLIAMENT":  0.95,
            "EXECUTIVE ORDER": 0.9,  "PRESIDENTIAL DOCUMENT": 0.9,
            "NOTICE":         0.5,   "GUIDANCE":           0.6,
            "BILL":           0.55,  "FEDERAL BILL":       0.55,
            "GUIDELINES":     0.65,
        }
        for key, val in type_scores.items():
            if key in doc_type or key in status:
                score = max(score, val)
                break

        # Jurisdiction priority
        jur_priority = {
            "Federal": 0.85, "EU": 0.80, "GB": 0.70, "CA": 0.65, "PA": 0.60,
        }
        jur_boost = jur_priority.get(doc.get("jurisdiction", ""), 0.5)
        score = (score + jur_boost) / 2

        # Recency boost (fetched in last 48h)
        fetched_at = doc.get("fetched_at")
        if fetched_at:
            try:
                ft = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00").replace("+00:00", ""))
                hours_old = (datetime.utcnow() - ft).total_seconds() / 3600
                if hours_old < 24:
                    score = min(score + 0.15, 1.0)
                elif hours_old < 48:
                    score = min(score + 0.08, 1.0)
            except Exception:
                pass

        # Comment deadline urgency
        deadline = doc.get("deadline") or ""
        if deadline and len(deadline) >= 10:
            try:
                dl = datetime.strptime(deadline[:10], "%Y-%m-%d")
                days_to_deadline = (dl - datetime.utcnow()).days
                if 0 < days_to_deadline <= 14:
                    score = min(score + 0.25, 1.0)   # urgent: closing soon
                elif 14 < days_to_deadline <= 60:
                    score = min(score + 0.10, 1.0)
            except Exception:
                pass

        return round(score, 3)

    def sort_by_priority(self, docs: List[Dict]) -> List[Dict]:
        """Return documents sorted by analysis priority, highest first."""
        scored = [(doc, self.score_analysis_priority(doc)) for doc in docs]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scored]

    # ── 4. Anomaly detection ──────────────────────────────────────────────────

    def detect_anomalies(self, doc: Dict[str, Any]) -> Optional[str]:
        """
        Flag documents that are structurally unusual for their source.
        Returns an anomaly description or None if document appears normal.
        """
        source   = doc.get("source", "")
        profile  = get_source_profile(source)
        if not profile or profile.get("total_count", 0) < 5:
            return None

        anomalies = []

        title_len = len(doc.get("title") or "")
        avg_len   = profile.get("avg_title_length", 80)
        if avg_len > 0 and (title_len < avg_len * 0.3 or title_len > avg_len * 3):
            anomalies.append(f"Unusual title length ({title_len} vs avg {avg_len:.0f})")

        known_agencies = set(profile.get("known_agencies", []))
        doc_agency     = (doc.get("agency") or "").strip()
        if doc_agency and known_agencies and doc_agency not in known_agencies:
            anomalies.append(f"New agency '{doc_agency}' not previously seen from {source}")

        known_types  = set(profile.get("known_doc_types", []))
        doc_type     = (doc.get("doc_type") or "").strip()
        if doc_type and known_types and doc_type not in known_types:
            anomalies.append(f"Unusual document type '{doc_type}' from {source}")

        return " | ".join(anomalies) if anomalies else None

    def update_source_statistics(self, docs: List[Dict]) -> None:
        """Update rolling statistics for each source based on newly fetched documents."""
        from utils.db import upsert_source_profile

        by_source: Dict[str, List] = defaultdict(list)
        for doc in docs:
            by_source[doc.get("source", "unknown")].append(doc)

        for source, source_docs in by_source.items():
            profile = get_source_profile(source) or _default_profile(source)

            titles    = [d.get("title") or "" for d in source_docs]
            avg_len   = sum(len(t) for t in titles) / len(titles) if titles else 0
            agencies  = list({(d.get("agency") or "").strip() for d in source_docs if d.get("agency")})
            doc_types = list({(d.get("doc_type") or "").strip() for d in source_docs if d.get("doc_type")})

            old_avg = profile.get("avg_title_length", avg_len)
            profile["avg_title_length"] = old_avg * 0.8 + avg_len * 0.2

            known_agencies = set(profile.get("known_agencies", []))
            known_agencies.update(agencies)
            profile["known_agencies"]  = list(known_agencies)[:100]

            known_types = set(profile.get("known_doc_types", []))
            known_types.update(doc_types)
            profile["known_doc_types"] = list(known_types)[:50]

            profile["last_fetch"]   = datetime.utcnow().isoformat()
            profile["last_updated"] = datetime.utcnow().isoformat()
            upsert_source_profile(source, profile)

    # ── 5. Prompt adaptation ──────────────────────────────────────────────────

    def get_adapted_prompt_additions(self, doc: Dict[str, Any]) -> str:
        """
        Returns domain-specific prompt additions derived from learned patterns.
        Called by InterpreterAgent before building the Claude prompt.
        """
        from utils.db import get_prompt_adaptations

        source       = doc.get("source", "")
        agency       = (doc.get("agency") or "")[:80]
        jurisdiction = doc.get("jurisdiction", "")

        adaptations = get_prompt_adaptations()
        additions   = []

        for adapt in adaptations:
            keys = adapt.get("match_keys", {})
            if keys.get("source")       and keys["source"]       != source:       continue
            if keys.get("agency")       and keys["agency"]       not in agency:   continue
            if keys.get("jurisdiction") and keys["jurisdiction"] != jurisdiction: continue
            additions.append(adapt["instruction"])

        return "\n".join(additions) if additions else ""

    def _adapt_prompt_for_domain(self, source: str, agency: str, jurisdiction: str) -> None:
        """
        Use Claude to analyse recent false positives from a domain and
        generate a targeted prompt instruction to reduce future errors.
        """
        from utils.db import get_recent_false_positives, save_prompt_adaptation

        false_positives = get_recent_false_positives(source=source, limit=10)
        if len(false_positives) < 3:
            return   # need at least 3 examples to generalise

        examples = "\n".join(
            f"- Title: {fp.get('title', '')} | Reason given: {fp.get('reason', 'not specified')}"
            for fp in false_positives
        )

        prompt = f"""You are calibrating an AI regulation monitoring system.
The following documents from source '{source}' (agency: '{agency}', jurisdiction: '{jurisdiction}')
were incorrectly identified as AI-relevant regulations but turned out to be irrelevant:

{examples}

Based on these examples, write ONE precise instruction (2-3 sentences) telling the system
what to watch out for from this source to avoid similar false positives in future.
The instruction should be specific to this source/agency pattern, not generic.
Start the instruction with 'NOTE:'.
Respond with only the instruction text, nothing else."""

        try:
            self._ensure_configured()
            instruction = call_llm(prompt=prompt, max_tokens=200)
            if instruction.startswith("NOTE:"):
                save_prompt_adaptation({
                    "match_keys":  {"source": source, "agency": agency[:80], "jurisdiction": jurisdiction},
                    "instruction": instruction,
                    "basis":       f"{len(false_positives)} false positives",
                    "created_at":  datetime.utcnow().isoformat(),
                })
                log.info("Prompt adaptation saved for %s/%s", source, agency)
        except LLMError as e:
            log.error("Prompt adaptation LLM error: %s", e)
        except Exception as e:
            log.error("Prompt adaptation failed: %s", e)

    def _check_adaptation_trigger(self, source: str, agency: str, jurisdiction: str) -> bool:
        """Returns True if enough negative feedback warrants prompt adaptation."""
        from utils.db import count_recent_false_positives
        count = count_recent_false_positives(source=source, days=30)
        return count >= 5   # trigger after 5 false positives from same source

    # ── 6. Keyword weight management ─────────────────────────────────────────

    def _update_keyword_scores(self, matched_keywords: List[str],
                                is_positive: bool, is_negative: bool) -> None:
        from utils.db import get_keyword_weights, save_keyword_weights
        weights = get_keyword_weights()
        delta   = 0.05 if is_positive else (-0.08 if is_negative else 0)
        for kw in matched_keywords:
            current      = weights.get(kw, 1.0)
            weights[kw]  = max(0.1, min(2.0, current + delta))
        save_keyword_weights(weights)

    def _get_keyword_weights(self) -> Dict[str, float]:
        from utils.db import get_keyword_weights
        return get_keyword_weights()

    # ── 7. Adaptive scheduling ────────────────────────────────────────────────

    def get_optimal_fetch_schedule(self) -> Dict[str, Any]:
        """
        Analyse historical fetch results to recommend optimal fetch times
        and lookback windows for each source.

        Returns a dict with per-source recommendations.
        """
        from utils.db import get_fetch_history

        history     = get_fetch_history(days=60)
        schedule    = {}

        # Group by source
        by_source: Dict[str, List] = defaultdict(list)
        for event in history:
            by_source[event.get("source", "")].append(event)

        for source, events in by_source.items():
            # Find which days of week have the highest new-document yield
            day_yields  = defaultdict(list)
            for ev in events:
                fetched = ev.get("fetched_at")
                if fetched:
                    try:
                        dt  = datetime.fromisoformat(str(fetched)[:19])
                        day = dt.weekday()   # 0=Mon, 6=Sun
                        day_yields[day].append(ev.get("new_count", 0))
                    except Exception:
                        pass

            best_days   = sorted(day_yields, key=lambda d: sum(day_yields[d]) / max(len(day_yields[d]), 1), reverse=True)[:3]
            avg_new     = sum(ev.get("new_count", 0) for ev in events) / max(len(events), 1)

            schedule[source] = {
                "best_days_of_week": best_days,
                "avg_new_per_fetch": round(avg_new, 1),
                "recommended_interval_hours": 48 if avg_new < 1 else 24 if avg_new < 5 else 12,
                "note": f"Based on {len(events)} fetch events over 60 days",
            }

        return schedule

    # ── 8. Learning summary report ────────────────────────────────────────────

    def get_learning_report(self) -> Dict[str, Any]:
        """
        Return a comprehensive report of what the system has learned.
        Useful for the UI's Learning view and the CLI's 'learn report' command.
        """
        from utils.db import (
            get_all_source_profiles, get_keyword_weights,
            get_prompt_adaptations, count_feedback_by_type,
            get_false_positive_patterns,
        )

        profiles     = get_all_source_profiles()
        kw_weights   = get_keyword_weights()
        adaptations  = get_prompt_adaptations()
        feedback_cts = count_feedback_by_type()
        fp_patterns  = get_false_positive_patterns()

        # Identify most and least reliable sources
        scored_sources = sorted(
            [(s, p.get("quality_score", 0.7)) for s, p in profiles.items()
             if not s.startswith("agency::") and p.get("total_count", 0) >= 3],
            key=lambda x: x[1], reverse=True
        )

        # Identify keyword drift (keywords that have moved far from default 1.0)
        kw_boosted  = {k: v for k, v in kw_weights.items() if v > 1.3}
        kw_penalised = {k: v for k, v in kw_weights.items() if v < 0.5}

        return {
            "summary": {
                "total_feedback":      sum(feedback_cts.values()),
                "relevant_confirmed":  feedback_cts.get("relevant", 0),
                "not_relevant":        feedback_cts.get("not_relevant", 0),
                "partially_relevant":  feedback_cts.get("partially_relevant", 0),
                "prompt_adaptations":  len(adaptations),
                "false_positive_patterns": len(fp_patterns),
                "sources_tracked":     len([p for p in profiles if not p.startswith("agency::")]),
            },
            "source_quality": {
                "top_sources":      scored_sources[:5],
                "bottom_sources":   scored_sources[-5:] if len(scored_sources) > 5 else [],
                "all_profiles":     {s: p for s, p in profiles.items()},
            },
            "keyword_learning": {
                "total_keywords":   len(AI_KEYWORDS),
                "boosted":          kw_boosted,
                "penalised":        kw_penalised,
                "all_weights":      kw_weights,
            },
            "prompt_adaptations": adaptations,
            "false_positive_patterns": fp_patterns,
            "schedule_recommendations": self.get_optimal_fetch_schedule(),
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _default_profile(source: str) -> Dict[str, Any]:
    return {
        "source":           source,
        "quality_score":    0.70,   # start with neutral trust
        "total_count":      0,
        "positive_count":   0,
        "negative_count":   0,
        "avg_title_length": 80.0,
        "known_agencies":   [],
        "known_doc_types":  [],
        "last_fetch":       None,
        "last_updated":     datetime.utcnow().isoformat(),
    }


def _compute_quality_score(profile: Dict) -> float:
    """
    Wilson score interval lower bound — a statistically robust way to
    estimate true quality from a small number of observations.
    Avoids overconfident scores from very few data points.
    """
    n = profile.get("total_count", 0)
    if n == 0:
        return 0.70   # no data — neutral

    p = profile.get("positive_count", 0) / n
    z = 1.645   # 95% confidence

    # Wilson score lower bound
    numerator   = p + z*z/(2*n) - z * ((p*(1-p)/n + z*z/(4*n*n)) ** 0.5)
    denominator = 1 + z*z/n
    score       = numerator / denominator

    # Floor at 0.1, ceil at 0.98
    return round(max(0.10, min(0.98, score)), 3)


def _weighted_keyword_score(text: str, weights: Dict[str, float]) -> float:
    """
    Compute a keyword score using learned per-keyword weights.
    """
    if not text:
        return 0.0
    lower     = text.lower()
    total_w   = 0.0
    hit_w     = 0.0
    for kw in AI_KEYWORDS:
        w       = weights.get(kw, 1.0)
        total_w += w
        if kw in lower:
            hit_w += w
    if total_w == 0:
        return 0.0
    max_score = min(total_w, sum(sorted([weights.get(k, 1.0) for k in AI_KEYWORDS], reverse=True)[:10]))
    return min(hit_w / max_score, 1.0) if max_score > 0 else 0.0
