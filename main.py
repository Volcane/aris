#!/usr/bin/env python3
"""
ARIS — AI Regulation Intelligence System
Main CLI entry point.

Usage:
  python main.py run                          # fetch + summarize (full pipeline)
  python main.py fetch                        # fetch only
  python main.py fetch --source federal       # federal sources only
  python main.py fetch --source PA            # PA state only
  python main.py summarize                    # summarize pending docs
  python main.py report                       # print dashboard
  python main.py report --days 7              # last 7 days
  python main.py report --jurisdiction PA     # PA only
  python main.py report --urgency High        # filter by urgency
  python main.py export --format json         # export to JSON
  python main.py export --format markdown     # export to Markdown
  python main.py watch --interval 24          # run every 24h
  python main.py status                       # show DB stats
"""

import sys
from pathlib import Path

import click
from rich.console import Console

# Ensure project root is on path when run directly
sys.path.insert(0, str(Path(__file__).parent))

console = Console()


@click.group()
def cli():
    """ARIS — AI Regulation Intelligence System\n
    Monitors Federal and state AI legislation, interprets the language,
    and delivers actionable business summaries."""
    pass


# ── run ───────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--days",    default=30,  show_default=True, help="Look back N days for new documents")
@click.option("--limit",   default=50,  show_default=True, help="Max documents to summarize per run")
def run(days, limit):
    """Full pipeline: fetch all sources, then summarize with AI."""
    from agents.orchestrator import Orchestrator
    from utils.reporter import print_banner, make_progress

    print_banner()
    orchestrator = Orchestrator()

    with make_progress() as progress:
        fetch_task = progress.add_task("Fetching documents…", total=None)
        fetched    = orchestrator.fetch(lookback_days=days)
        progress.update(fetch_task, completed=1, total=1,
                        description=f"Fetched {fetched} new/updated documents")

        summ_task  = progress.add_task(f"Summarizing (up to {limit})…", total=limit)

        def cb(current, total):
            progress.update(summ_task, completed=current, total=total,
                            description=f"Summarizing {current}/{total}…")

        summarized = orchestrator.summarize(limit=limit, progress_callback=cb)
        progress.update(summ_task, completed=summarized, total=summarized,
                        description=f"Summarized {summarized} documents")

    console.print(f"\n[bold green]✓[/bold green] Fetch: {fetched} new   "
                  f"[bold green]✓[/bold green] Summarized: {summarized}")
    console.print("[dim]Run 'python main.py report' to view results.[/dim]")


# ── fetch ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--source",  default=None,
              help="Source to fetch: 'federal', 'state', or a state code like 'PA'")
@click.option("--days",    default=30, show_default=True)
def fetch(source, days):
    """Fetch documents from sources without AI summarization."""
    from agents.orchestrator import Orchestrator
    from utils.reporter import print_banner, make_progress

    print_banner()
    orchestrator = Orchestrator()
    sources      = [source] if source else None

    with make_progress() as progress:
        task = progress.add_task("Fetching…", total=None)
        count = orchestrator.fetch(sources=sources, lookback_days=days)
        progress.update(task, completed=1, total=1,
                        description=f"Done — {count} new/updated documents")

    console.print(f"\n[bold green]✓[/bold green] Saved {count} new/updated documents to database")


# ── summarize ─────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--limit", default=50, show_default=True,
              help="Max documents to summarize")
def summarize(limit):
    """Run AI summarization on all pending documents in the database."""
    from agents.orchestrator import Orchestrator
    from utils.reporter import print_banner, make_progress

    print_banner()
    orchestrator = Orchestrator()

    with make_progress() as progress:
        task = progress.add_task(f"Summarizing (up to {limit})…", total=limit)

        def cb(current, total):
            progress.update(task, completed=current, total=total,
                            description=f"Summarizing {current}/{total}…")

        count = orchestrator.summarize(limit=limit, progress_callback=cb)

    console.print(f"\n[bold green]✓[/bold green] Created {count} AI summaries")


# ── report ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--days",         default=30,   show_default=True)
@click.option("--jurisdiction", default=None, help="Filter by jurisdiction: 'Federal' or state code")
@click.option("--urgency",      default=None,
              type=click.Choice(["Low", "Medium", "High", "Critical"]),
              help="Filter by urgency level")
def report(days, jurisdiction, urgency):
    """Display the AI regulation intelligence dashboard."""
    from utils.reporter import print_report
    print_report(days=days, jurisdiction=jurisdiction, urgency_filter=urgency)


# ── export ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--format", "fmt",
              default="markdown",
              type=click.Choice(["json", "markdown"]),
              show_default=True)
@click.option("--days",    default=30, show_default=True)
@click.option("--output",  default=None, help="Output file path (default: auto-named in ./output/)")
def export(fmt, days, output):
    """Export summaries to JSON or Markdown."""
    from utils.reporter import export_json, export_markdown

    if fmt == "json":
        path = export_json(days=days, filepath=output)
    else:
        path = export_markdown(days=days, filepath=output)

    console.print(f"[bold green]✓[/bold green] Exported to [underline]{path}[/underline]")


# ── status ────────────────────────────────────────────────────────────────────

@cli.command()
def status():
    """Show database statistics and configuration status."""
    from utils.reporter import print_banner, print_stats
    from config.settings import (
        ANTHROPIC_API_KEY, REGULATIONS_GOV_KEY,
        CONGRESS_GOV_KEY, LEGISCAN_KEY
    )
    from config.states import ENABLED_STATES

    print_banner()
    print_stats()

    console.print("\n[bold]API Key Status[/bold]")
    keys = {
        "Anthropic (required)":    ANTHROPIC_API_KEY,
        "Regulations.gov":         REGULATIONS_GOV_KEY,
        "Congress.gov":            CONGRESS_GOV_KEY,
        "LegiScan":                LEGISCAN_KEY,
    }
    for name, key in keys.items():
        icon = "[green]✓[/green]" if key else "[red]✗[/red]"
        console.print(f"  {icon}  {name}")

    console.print(f"\n[bold]Enabled States[/bold]: {', '.join(ENABLED_STATES) or 'None'}")


# ── watch ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--interval", default=24, show_default=True,
              help="Hours between runs")
@click.option("--days",     default=7,  show_default=True,
              help="Lookback window for each run")
def watch(interval, days):
    """Run the pipeline continuously on a schedule (Ctrl+C to stop)."""
    from agents.scheduler import run_watch
    console.print(
        f"[bold]Starting ARIS watch mode[/bold] — "
        f"running every [blue]{interval}h[/blue], "
        f"lookback [blue]{days}d[/blue]"
    )
    run_watch(interval_hours=interval, lookback_days=days)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
