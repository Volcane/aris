# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 Mitch Kwiatkowski
# ARIS — Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
"""
ARIS â€” Reporter
Renders the console dashboard and exports results to Markdown / JSON.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from rich.markdown import Markdown

from config.settings import OUTPUT_DIR
from utils.db import get_recent_summaries, get_stats
from utils.cache import get_logger

log = get_logger("aris.reporter")
console = Console()


# â”€â”€ Urgency colour mapping â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

URGENCY_STYLE = {
    "Critical": "bold red",
    "High": "bold yellow",
    "Medium": "yellow",
    "Low": "dim green",
}


# â”€â”€ Console Dashboard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def print_banner():
    console.print(
        Panel.fit(
            "[bold white]ARIS[/bold white]  [dim]Automated Regulatory Intelligence System[/dim]\n"
            "[dim]Monitoring AI regulation and data privacy law[/dim]",
            border_style="blue",
        )
    )


def print_stats():
    stats = get_stats()
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("Total documents tracked", str(stats["total_documents"]))
    table.add_row("Summarised", str(stats["total_summaries"]))
    table.add_row("Federal documents", str(stats["federal_documents"]))
    table.add_row("State documents", str(stats["state_documents"]))
    table.add_row("Awaiting summarisation", str(stats["pending_summaries"]))

    console.print(
        Panel(table, title="[bold]Database Stats[/bold]", border_style="blue")
    )


def print_report(
    days: int = 30,
    jurisdiction: Optional[str] = None,
    urgency_filter: Optional[str] = None,
):
    """Render the full findings table to the terminal."""
    print_banner()
    print_stats()

    summaries = get_recent_summaries(days=days, jurisdiction=jurisdiction)
    if urgency_filter:
        summaries = [s for s in summaries if s.get("urgency") == urgency_filter]

    if not summaries:
        console.print("[dim]No summaries found for the specified filters.[/dim]")
        return

    # Group by jurisdiction
    by_juris: Dict[str, List] = {}
    for s in summaries:
        key = s.get("jurisdiction", "Unknown")
        by_juris.setdefault(key, []).append(s)

    for juris, items in sorted(by_juris.items()):
        _print_jurisdiction_section(juris, items)


def _print_jurisdiction_section(jurisdiction: str, items: List[Dict]):
    label = "ðŸ›  Federal" if jurisdiction == "Federal" else f"ðŸ¢  {jurisdiction}"
    console.print(
        f"\n[bold blue]{label}[/bold blue]  ({len(items)} item{'s' if len(items) != 1 else ''})"
    )

    table = Table(
        box=box.ROUNDED,
        show_lines=True,
        expand=True,
        border_style="blue",
    )
    table.add_column("Urgency", width=10)
    table.add_column("Title", ratio=3)
    table.add_column("Type / Status", ratio=2)
    table.add_column("Agency", ratio=2)
    table.add_column("Published", width=11)
    table.add_column("Deadline", width=11)

    for item in sorted(
        items, key=lambda x: _urgency_rank(x.get("urgency", "Low")), reverse=True
    ):
        urgency = item.get("urgency", "Low")
        style = URGENCY_STYLE.get(urgency, "")
        pub = (
            item.get("published_date", "")[:10] if item.get("published_date") else "â€”"
        )
        dl = item.get("deadline") or "â€”"

        table.add_row(
            Text(urgency, style=style),
            item.get("title", "")[:80],
            f"{item.get('doc_type', '')} / {item.get('status', '')}",
            (item.get("agency") or "")[:40],
            pub,
            dl,
        )
    console.print(table)

    # Detail cards for High/Critical items
    for item in items:
        if item.get("urgency") in ("High", "Critical"):
            _print_detail_card(item)


def _print_detail_card(item: Dict):
    content = []
    urg_style = URGENCY_STYLE.get(item.get("urgency", "Low"), "")

    content.append(
        f"[{urg_style}]âš   {item.get('urgency', '').upper()}[/{urg_style}]  {item.get('title', '')}\n"
    )
    content.append(f"[dim]{item.get('url', '')}[/dim]\n")
    content.append(f"\n[bold]Summary[/bold]\n{item.get('plain_english', '')}\n")

    reqs = item.get("requirements") or []
    if reqs:
        content.append("\n[bold red]Requirements (Mandatory)[/bold red]")
        for r in reqs:
            content.append(f"  â€¢ {r}")

    actions = item.get("action_items") or []
    if actions:
        content.append("\n[bold yellow]Action Items[/bold yellow]")
        for a in actions:
            content.append(f"  â†’ {a}")

    recs = item.get("recommendations") or []
    if recs:
        content.append("\n[bold green]Recommendations[/bold green]")
        for r in recs:
            content.append(f"  â—‹ {r}")

    areas = item.get("impact_areas") or []
    if areas:
        content.append(f"\n[dim]Impact areas: {', '.join(areas)}[/dim]")

    console.print(
        Panel("\n".join(content), border_style=urg_style or "dim", expand=False)
    )


def _urgency_rank(u: str) -> int:
    return {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}.get(u, 0)


# â”€â”€ Progress bar for summarization â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=True,
    )


# â”€â”€ Export â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def export_json(days: int = 30, filepath: Optional[str] = None) -> str:
    """Export all recent summaries to a JSON file."""
    summaries = get_recent_summaries(days=days)
    path = Path(filepath) if filepath else OUTPUT_DIR / f"aris_export_{_ts()}.json"
    path.write_text(json.dumps(summaries, indent=2, default=str))
    log.info("JSON export saved to %s", path)
    return str(path)


def export_markdown(days: int = 30, filepath: Optional[str] = None) -> str:
    """Export all recent summaries to a formatted Markdown report."""
    summaries = get_recent_summaries(days=days)
    path = Path(filepath) if filepath else OUTPUT_DIR / f"aris_report_{_ts()}.md"

    lines = [
        f"# ARIS â€” Automated Regulatory Intelligence Report",
        f"*Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
        f"*Coverage: last {days} days*",
        "",
    ]

    # Group by jurisdiction
    by_juris: Dict[str, List] = {}
    for s in summaries:
        key = s.get("jurisdiction", "Unknown")
        by_juris.setdefault(key, []).append(s)

    for juris, items in sorted(by_juris.items()):
        label = "Federal" if juris == "Federal" else f"State: {juris}"
        lines.append(f"## {label}\n")

        for item in sorted(
            items, key=lambda x: _urgency_rank(x.get("urgency", "Low")), reverse=True
        ):
            urgency = item.get("urgency", "Low")
            lines.append(f"### {item.get('title', '')}")
            lines.append(
                f"**Urgency:** {urgency}  |  **Published:** {str(item.get('published_date', ''))[:10]}  |  **Deadline:** {item.get('deadline') or 'N/A'}"
            )
            lines.append(
                f"**Source:** [{item.get('source', '')}]({item.get('url', '')})  |  **Agency:** {item.get('agency', '')}"
            )
            lines.append(f"\n**Summary:** {item.get('plain_english', '')}\n")

            reqs = item.get("requirements") or []
            if reqs:
                lines.append("**Mandatory Requirements:**")
                for r in reqs:
                    lines.append(f"- {r}")
                lines.append("")

            actions = item.get("action_items") or []
            if actions:
                lines.append("**Action Items:**")
                for a in actions:
                    lines.append(f"- {a}")
                lines.append("")

            recs = item.get("recommendations") or []
            if recs:
                lines.append("**Recommendations:**")
                for r in recs:
                    lines.append(f"- {r}")
                lines.append("")

            areas = item.get("impact_areas") or []
            if areas:
                lines.append(f"**Impact Areas:** {', '.join(areas)}\n")
            lines.append("---\n")

    path.write_text("\n".join(lines))
    log.info("Markdown report saved to %s", path)
    return str(path)


def _ts() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
