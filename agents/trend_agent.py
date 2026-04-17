# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 Mitch Kwiatkowski
# ARIS — Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
"""
ARIS — Trend Agent

Computes regulatory velocity, acceleration signals, and impact-area activity
from the accumulated document and summary database.

NO API CALLS. All analytics are computed from local database data using pure
Python and SQLAlchemy queries. Results are cached in trend_snapshots table
and recomputed once per day.

Three core analyses:

1. JURISDICTION VELOCITY
   For each jurisdiction: how many documents and summaries have arrived per
   30-day window over the last 12 months? Which jurisdictions are accelerating
   (pace increasing vs 6 months ago)? Produce a time-series suitable for
   bar/line charts.

2. IMPACT AREA ACTIVITY
   For each impact area tag appearing in summaries: document count, urgency
   distribution, and recent velocity. Rank by activity to produce a heat map
   of which regulatory topics are most active right now.

3. ACCELERATION ALERTS
   Identify jurisdictions and impact areas whose document velocity has
   increased by ≥50% compared to the same period 6 months ago. These are
   the areas needing most immediate attention.

Usage:
    from agents.trend_agent import TrendAgent

    agent = TrendAgent()
    agent.run_snapshot()           # compute + cache all metrics (call daily)

    data = agent.get_velocity()    # jurisdiction velocity time-series
    data = agent.get_heatmap()     # impact area heatmap
    data = agent.get_alerts()      # acceleration alerts
    data = agent.get_summary()     # all three in one dict
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from utils.cache import get_logger

log = get_logger("aris.trend")

# ── Constants ─────────────────────────────────────────────────────────────────

WINDOW_DAYS = 30  # size of each velocity window
LOOKBACK_MONTHS = 12  # how many windows to compute
ACCELERATION_THRESHOLD = 0.50  # 50% increase = acceleration alert
CACHE_HOURS = 24  # snapshot TTL


# ── Trend Agent ───────────────────────────────────────────────────────────────


class TrendAgent:
    """
    Computes and caches regulatory velocity and trend analytics.
    All computation is local — no Claude API calls.
    """

    # ── Public API ─────────────────────────────────────────────────────────────

    def run_snapshot(self) -> Dict[str, int]:
        """
        Compute all metrics and store in trend_snapshots table.
        Returns counts of items stored per snapshot type.
        """
        log.info("Computing trend snapshots")

        docs = self._load_documents()
        summaries = self._load_summaries()

        if not docs:
            log.info("No documents yet — skipping trend snapshot")
            return {"velocity": 0, "heatmap": 0, "alerts": 0}

        velocity = self._compute_velocity(docs)
        heatmap = self._compute_heatmap(summaries)
        alerts = self._compute_alerts(velocity, heatmap)

        self._save_snapshot("velocity", velocity)
        self._save_snapshot("heatmap", heatmap)
        self._save_snapshot("alerts", alerts)

        log.info(
            "Trend snapshots saved: %d velocity, %d heatmap, %d alerts",
            len(velocity),
            len(heatmap),
            len(alerts),
        )
        return {
            "velocity": len(velocity),
            "heatmap": len(heatmap),
            "alerts": len(alerts),
        }

    def get_velocity(self) -> List[Dict[str, Any]]:
        """Return jurisdiction velocity time-series (from cache or recompute)."""
        cached = self._load_snapshot("velocity")
        if cached is not None:
            return cached
        docs = self._load_documents()
        return self._compute_velocity(docs)

    def get_heatmap(self) -> List[Dict[str, Any]]:
        """Return impact area heatmap (from cache or recompute)."""
        cached = self._load_snapshot("heatmap")
        if cached is not None:
            return cached
        summaries = self._load_summaries()
        return self._compute_heatmap(summaries)

    def get_alerts(self) -> List[Dict[str, Any]]:
        """Return acceleration alerts (from cache or recompute)."""
        cached = self._load_snapshot("alerts")
        if cached is not None:
            return cached
        return self._compute_alerts(self.get_velocity(), self.get_heatmap())

    def get_summary(self) -> Dict[str, Any]:
        """Return all trend data in a single dict."""
        velocity = self.get_velocity()
        heatmap = self.get_heatmap()
        alerts = self.get_alerts()

        # Overall stats
        total_docs = sum(v.get("total_documents", 0) for v in velocity)
        last_updated = self._last_snapshot_time()

        return {
            "velocity": velocity,
            "heatmap": heatmap,
            "alerts": alerts,
            "total_docs": total_docs,
            "jurisdictions": len(velocity),
            "impact_areas": len(heatmap),
            "alert_count": len(alerts),
            "last_updated": last_updated,
        }

    # ── Document loading ───────────────────────────────────────────────────────

    def _load_documents(self) -> List[Dict]:
        """Load all documents with their fetch/publish dates and jurisdictions."""
        try:
            from utils.db import get_session
            from utils.db import Document, Summary

            with get_session() as session:
                rows = session.query(
                    Document.id,
                    Document.jurisdiction,
                    Document.source,
                    Document.fetched_at,
                    Document.published_date,
                    Document.doc_type,
                ).all()
                return [
                    {
                        "id": r.id,
                        "jurisdiction": r.jurisdiction or "Unknown",
                        "source": r.source or "",
                        "fetched_at": r.fetched_at,
                        "published_date": r.published_date,
                        "doc_type": r.doc_type or "",
                    }
                    for r in rows
                ]
        except Exception as e:
            log.warning("Could not load documents for trends: %s", e)
            return []

    def _load_summaries(self) -> List[Dict]:
        """Load all summaries with impact areas and urgency."""
        try:
            from utils.db import get_session
            from utils.db import Document, Summary

            with get_session() as session:
                rows = (
                    session.query(
                        Summary.document_id,
                        Summary.urgency,
                        Summary.impact_areas,
                        Summary.relevance_score,
                        Document.jurisdiction,
                        Document.fetched_at,
                        Document.published_date,
                    )
                    .join(Document, Document.id == Summary.document_id)
                    .all()
                )
                return [
                    {
                        "document_id": r.document_id,
                        "urgency": r.urgency or "Low",
                        "impact_areas": r.impact_areas or [],
                        "relevance_score": r.relevance_score or 0,
                        "jurisdiction": r.jurisdiction or "Unknown",
                        "fetched_at": r.fetched_at,
                        "published_date": r.published_date,
                    }
                    for r in rows
                ]
        except Exception as e:
            log.warning("Could not load summaries for trends: %s", e)
            return []

    # ── Velocity computation ───────────────────────────────────────────────────

    def _compute_velocity(self, docs: List[Dict]) -> List[Dict[str, Any]]:
        """
        Compute per-jurisdiction document velocity over LOOKBACK_MONTHS windows.

        Returns a list of jurisdiction objects, each with:
          - windows: list of {label, start, end, count} for each 30-day window
          - total_documents: total docs ever
          - recent_count: docs in the most recent 30 days
          - prior_count: docs in the 30-day window 6 months ago
          - acceleration: (recent - prior) / max(prior, 1) — positive = accelerating
          - trend: "accelerating" | "stable" | "decelerating"
        """
        if not docs:
            return []

        now = datetime.utcnow()

        # Build windows — include current partial month so chart always ends today
        windows: List[Tuple[str, datetime, datetime]] = []
        # Current partial month: from start of this month to now
        current_month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        windows.append((now.strftime("%b %Y"), current_month_start, now))
        # Previous full months going back LOOKBACK_MONTHS
        for i in range(LOOKBACK_MONTHS):
            end = now - timedelta(days=i * WINDOW_DAYS)
            start = end - timedelta(days=WINDOW_DAYS)
            label = start.strftime("%b %Y")
            windows.append((label, start, end))
        windows.reverse()  # chronological order
        # Deduplicate labels (current month may overlap with most recent window)
        seen_labels: set = set()
        deduped = []
        for w in windows:
            if w[0] not in seen_labels:
                seen_labels.add(w[0])
                deduped.append(w)
        windows = deduped

        # Group docs by jurisdiction
        by_jur: Dict[str, List[Dict]] = defaultdict(list)
        for doc in docs:
            by_jur[doc["jurisdiction"]].append(doc)

        results = []
        for jur, jur_docs in sorted(by_jur.items()):
            window_counts = []
            for label, start, end in windows:
                count = sum(
                    1 for d in jur_docs if _doc_date(d) and start <= _doc_date(d) < end
                )
                window_counts.append(
                    {
                        "label": label,
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "count": count,
                    }
                )

            recent_count = window_counts[-1]["count"]
            # Window 6 months ago
            prior_idx = max(0, len(window_counts) - 7)
            prior_count = window_counts[prior_idx]["count"]

            acceleration = (recent_count - prior_count) / max(prior_count, 1)

            if acceleration >= ACCELERATION_THRESHOLD:
                trend = "accelerating"
            elif acceleration <= -ACCELERATION_THRESHOLD:
                trend = "decelerating"
            else:
                trend = "stable"

            # Urgency breakdown from summaries (joined separately — velocity only
            # needs document counts, not summaries; urgency added in heatmap)
            results.append(
                {
                    "jurisdiction": jur,
                    "windows": window_counts,
                    "total_documents": len(jur_docs),
                    "recent_count": recent_count,
                    "prior_count": prior_count,
                    "acceleration": round(acceleration, 3),
                    "trend": trend,
                }
            )

        # Sort by recent count descending
        results.sort(key=lambda x: x["recent_count"], reverse=True)
        return results

    # ── Heatmap computation ────────────────────────────────────────────────────

    def _compute_heatmap(self, summaries: List[Dict]) -> List[Dict[str, Any]]:
        """
        Compute per-impact-area activity from summaries.

        Returns a list of impact area objects, each with:
          - area: the impact area label
          - total: total summaries mentioning this area
          - recent: summaries in the last 30 days
          - urgency_counts: {Critical, High, Medium, Low} counts
          - top_jurisdictions: top 3 jurisdictions by count
          - activity_score: composite score for heat map colour intensity
        """
        if not summaries:
            return []

        now = datetime.utcnow()
        cutoff = now - timedelta(days=WINDOW_DAYS)

        # Aggregate by impact area
        area_data: Dict[str, Dict] = defaultdict(
            lambda: {
                "total": 0,
                "recent": 0,
                "urgency_counts": {"Critical": 0, "High": 0, "Medium": 0, "Low": 0},
                "jurisdictions": defaultdict(int),
            }
        )

        for s in summaries:
            areas = s.get("impact_areas") or []
            if isinstance(areas, str):
                try:
                    areas = json.loads(areas)
                except Exception:
                    areas = [areas]

            date = _doc_date(s)
            is_recent = date and date >= cutoff

            for area in areas:
                area = str(area).strip()
                if not area or area == "null":
                    continue
                d = area_data[area]
                d["total"] += 1
                if is_recent:
                    d["recent"] += 1
                urg = s.get("urgency", "Low") or "Low"
                if urg in d["urgency_counts"]:
                    d["urgency_counts"][urg] += 1
                jur = s.get("jurisdiction", "Unknown")
                d["jurisdictions"][jur] += 1

        if not area_data:
            return []

        max_total = max(d["total"] for d in area_data.values())
        max_recent = max(max(d["recent"] for d in area_data.values()), 1)

        results = []
        for area, d in area_data.items():
            # Activity score: weight recent activity and critical/high urgency
            urg = d["urgency_counts"]
            sev_score = (urg["Critical"] * 3 + urg["High"] * 2 + urg["Medium"]) / max(
                d["total"], 1
            )
            activity = (
                0.6 * d["recent"] / max_recent + 0.4 * d["total"] / max(max_total, 1)
            ) * (1 + sev_score * 0.2)

            top_jurs = sorted(
                d["jurisdictions"].items(), key=lambda x: x[1], reverse=True
            )[:3]

            results.append(
                {
                    "area": area,
                    "total": d["total"],
                    "recent": d["recent"],
                    "urgency_counts": d["urgency_counts"],
                    "top_jurisdictions": top_jurs,
                    "activity_score": round(min(activity, 1.0), 3),
                }
            )

        results.sort(key=lambda x: x["activity_score"], reverse=True)
        return results[:50]  # top 50 areas

    # ── Acceleration alerts ────────────────────────────────────────────────────

    def _compute_alerts(
        self, velocity: List[Dict], heatmap: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Generate acceleration alerts for jurisdictions and impact areas
        whose activity has increased significantly.
        """
        alerts = []

        for v in velocity:
            if v["trend"] == "accelerating" and v["recent_count"] >= 2:
                pct = round(v["acceleration"] * 100)
                alerts.append(
                    {
                        "type": "jurisdiction",
                        "label": v["jurisdiction"],
                        "jurisdiction": v["jurisdiction"],
                        "message": (
                            f"{v['jurisdiction']} has published {v['recent_count']} documents "
                            f"in the last 30 days, up {pct}% from 6 months ago"
                        ),
                        "recent_count": v["recent_count"],
                        "prior_count": v["prior_count"],
                        "acceleration": v["acceleration"],
                        "severity": "High" if v["acceleration"] >= 1.0 else "Medium",
                    }
                )

        for h in heatmap[:20]:  # only alert on most active areas
            if h["recent"] >= 3 and h["activity_score"] >= 0.5:
                crit = h["urgency_counts"].get("Critical", 0)
                high = h["urgency_counts"].get("High", 0)
                if crit + high >= 2:
                    alerts.append(
                        {
                            "type": "impact_area",
                            "label": h["area"],
                            "area": h["area"],
                            "message": (
                                f'"{h["area"]}" has {h["recent"]} new documents this month '
                                f"({crit} Critical, {high} High urgency)"
                            ),
                            "recent_count": h["recent"],
                            "critical_count": crit,
                            "high_count": high,
                            "activity_score": h["activity_score"],
                            "severity": "Critical" if crit >= 2 else "High",
                        }
                    )

        # Sort by severity then count
        sev_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        alerts.sort(key=lambda a: (sev_order.get(a["severity"], 3), -a["recent_count"]))
        return alerts

    # ── Cache management ───────────────────────────────────────────────────────

    def _save_snapshot(self, snapshot_type: str, data: List[Dict]) -> None:
        try:
            from utils.db import get_session, TrendSnapshot

            with get_session() as session:
                # Upsert
                row = (
                    session.query(TrendSnapshot)
                    .filter_by(snapshot_type=snapshot_type)
                    .first()
                )
                if row:
                    row.data_json = data
                    row.computed_at = datetime.utcnow()
                else:
                    session.add(
                        TrendSnapshot(
                            snapshot_type=snapshot_type,
                            data_json=data,
                            computed_at=datetime.utcnow(),
                        )
                    )
                session.commit()
        except Exception as e:
            log.debug("Could not save trend snapshot: %s", e)

    def _load_snapshot(self, snapshot_type: str) -> Optional[List[Dict]]:
        try:
            from utils.db import get_session, TrendSnapshot

            cutoff = datetime.utcnow() - timedelta(hours=CACHE_HOURS)
            with get_session() as session:
                row = (
                    session.query(TrendSnapshot)
                    .filter(
                        TrendSnapshot.snapshot_type == snapshot_type,
                        TrendSnapshot.computed_at >= cutoff,
                    )
                    .first()
                )
                return row.data_json if row else None
        except Exception:
            return None

    def _last_snapshot_time(self) -> Optional[str]:
        try:
            from utils.db import get_session, TrendSnapshot

            with get_session() as session:
                row = (
                    session.query(TrendSnapshot)
                    .order_by(TrendSnapshot.computed_at.desc())
                    .first()
                )
                return row.computed_at.isoformat() if row else None
        except Exception:
            return None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _doc_date(doc: Dict) -> Optional[datetime]:
    """
    Return the document's publication date for trend windowing.

    Uses published_date (when the regulation/rule/document was actually
    published or enacted) rather than fetched_at (when ARIS retrieved it).
    This prevents a spike on the day of the initial fetch and instead shows
    a true picture of regulatory activity volume over time.

    Falls back to fetched_at only when published_date is absent or unparseable.
    """
    # Prefer published_date — the date the regulation was actually issued
    d = doc.get("published_date") or doc.get("fetched_at")
    if isinstance(d, str):
        try:
            return datetime.fromisoformat(d.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            # published_date unparseable — fall back to fetched_at
            fallback = doc.get("fetched_at")
            if isinstance(fallback, str):
                try:
                    return datetime.fromisoformat(
                        fallback.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except Exception:
                    return None
            return fallback
    return d
