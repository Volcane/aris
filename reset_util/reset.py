#!/usr/bin/env python3
"""
ARIS — Reset Tool

Clears fetched data so you can start fresh without reinstalling.
Run with --help to see all options.

Usage:
    python reset.py               # interactive mode — asks what to clear
    python reset.py --documents   # clear documents + summaries only
    python reset.py --full        # clear everything except API keys and baselines
    python reset.py --all         # same as --full
    python reset.py --list        # show what's currently in the database
"""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
# Works whether this file lives in the project root OR in a subdirectory
# like reset_util/ — parent.parent handles the subfolder case.

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR   = PROJECT_ROOT / "output"

# Add project root to path so config imports work from any subfolder
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config.settings import DB_PATH
    DB_FILE = Path(DB_PATH)
except Exception:
    DB_FILE = OUTPUT_DIR / "aris.db"

CACHE_DIR    = OUTPUT_DIR / ".cache"
PDF_INBOX    = OUTPUT_DIR / "pdf_inbox"
PDF_STORE    = OUTPUT_DIR / "pdfs"
MODELS_DIR   = OUTPUT_DIR / "models"

# ── Table groups ──────────────────────────────────────────────────────────────
# Grouped by what they represent and how likely a user is to want to keep them.

# Fetched regulatory content — always safe to clear
DOCUMENT_TABLES = [
    "documents",
    "summaries",
    "document_diffs",
    "document_links",
]

# Analytics computed from documents — derived, always re-computable
ANALYTICS_TABLES = [
    "trend_snapshots",
    "regulatory_horizon",
    "obligation_register_cache",
    "knowledge_graph_edges",
    "concept_map_cache",
    "brief_cache",
    "qa_passages",
    "qa_sessions",
]

# Enforcement actions fetched from FTC/SEC/ICO etc.
ENFORCEMENT_TABLES = [
    "enforcement_actions",
]

# Learning state built from user feedback
LEARNING_TABLES = [
    "feedback_events",
    "source_profiles",
    "keyword_weights",
    "prompt_adaptations",
    "fetch_history",
]

# PDFs — metadata in DB, files on disk
PDF_TABLES = [
    "pdf_metadata",
]

# User-created work product — keep by default
USER_TABLES = [
    "company_profiles",
    "gap_analyses",
    "thematic_syntheses",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    if not DB_FILE.exists():
        print(f"  Database not found at {DB_FILE}")
        print("  Nothing to clear.")
        sys.exit(0)
    return sqlite3.connect(DB_FILE)


def row_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0   # table doesn't exist yet


def clear_tables(conn: sqlite3.Connection, tables: list[str], label: str) -> int:
    total = 0
    for table in tables:
        n = row_count(conn, table)
        if n > 0:
            conn.execute(f"DELETE FROM {table}")
            total += n
    conn.commit()
    # Vacuum to reclaim space
    conn.execute("VACUUM")
    return total


def clear_fts(conn: sqlite3.Connection) -> None:
    """Clear the FTS5 full-text search index (lives inside aris.db)."""
    try:
        conn.execute("DELETE FROM documents_fts")
        conn.commit()
    except sqlite3.OperationalError:
        pass   # table may not exist


def dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / 1_048_576, 1)


def file_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for f in path.rglob("*") if f.is_file())


# ── Show current state ────────────────────────────────────────────────────────

def show_status() -> None:
    print("\n" + "─" * 60)
    print("  ARIS — Current Data Inventory")
    print("─" * 60)

    if not DB_FILE.exists():
        print("  No database found — system is already clean.")
        return

    conn = get_conn()

    sections = [
        ("Documents & Summaries",    DOCUMENT_TABLES),
        ("Analytics & Caches",       ANALYTICS_TABLES + ENFORCEMENT_TABLES),
        ("Learning State",           LEARNING_TABLES),
        ("PDFs (DB records)",        PDF_TABLES),
        ("User Work (profiles/gaps)",USER_TABLES),
    ]

    for label, tables in sections:
        counts = {t: row_count(conn, t) for t in tables}
        total  = sum(counts.values())
        if total == 0:
            print(f"\n  {label}: empty")
            continue
        print(f"\n  {label}: {total:,} rows total")
        for t, n in counts.items():
            if n > 0:
                print(f"    {t:<35s} {n:>6,}")

    conn.close()

    print(f"\n  Database file:   {DB_FILE}  ({round(DB_FILE.stat().st_size/1_048_576, 1)} MB)")
    print(f"  HTTP cache:      {CACHE_DIR}  ({file_count(CACHE_DIR)} files, {dir_size_mb(CACHE_DIR)} MB)")
    print(f"  PDF store:       {PDF_STORE}  ({file_count(PDF_STORE)} files, {dir_size_mb(PDF_STORE)} MB)")
    print(f"  PDF inbox:       {PDF_INBOX}  ({file_count(PDF_INBOX)} files)")
    print("─" * 60 + "\n")


# ── Reset operations ──────────────────────────────────────────────────────────

def reset_documents(conn: sqlite3.Connection, *, keep_user_work: bool = True) -> None:
    """Clear fetched documents, summaries, diffs, analytics, enforcement."""
    tables = DOCUMENT_TABLES + ANALYTICS_TABLES + ENFORCEMENT_TABLES
    n = clear_tables(conn, tables, "documents + analytics")
    clear_fts(conn)
    print(f"  ✓ Documents, summaries, diffs cleared  ({n:,} rows)")


def reset_learning(conn: sqlite3.Connection) -> None:
    """Clear learned source profiles, keyword weights, prompt adaptations."""
    n = clear_tables(conn, LEARNING_TABLES, "learning")
    print(f"  ✓ Learning state cleared  ({n:,} rows)")


def reset_pdfs(conn: sqlite3.Connection) -> None:
    """Clear PDF metadata from DB and delete PDF files from disk."""
    n = clear_tables(conn, PDF_TABLES, "pdfs")
    print(f"  ✓ PDF metadata cleared  ({n:,} rows)")

    for pdf_dir in (PDF_STORE, PDF_INBOX):
        if pdf_dir.exists():
            count = file_count(pdf_dir)
            if count > 0:
                shutil.rmtree(pdf_dir)
                pdf_dir.mkdir(exist_ok=True)
                print(f"  ✓ {pdf_dir.name}/  cleared  ({count} files)")


def reset_user_work(conn: sqlite3.Connection) -> None:
    """Clear company profiles, gap analyses, syntheses — user-created content."""
    n = clear_tables(conn, USER_TABLES, "user work")
    print(f"  ✓ Company profiles, gap analyses, syntheses cleared  ({n:,} rows)")


def reset_http_cache() -> None:
    """Delete all HTTP response cache files."""
    if CACHE_DIR.exists():
        count = file_count(CACHE_DIR)
        if count > 0:
            shutil.rmtree(CACHE_DIR)
            CACHE_DIR.mkdir(exist_ok=True)
            print(f"  ✓ HTTP cache cleared  ({count} files)")
        else:
            print("  ✓ HTTP cache already empty")
    else:
        print("  ✓ HTTP cache dir doesn't exist")


# ── Interactive mode ──────────────────────────────────────────────────────────

def interactive() -> None:
    show_status()

    print("What would you like to clear?\n")
    print("  1. Documents only — fetched docs, summaries, diffs, analytics")
    print("     (keeps: learning state, company profiles, gap analyses, PDFs)")
    print()
    print("  2. Documents + learning — everything above, plus source quality")
    print("     scores, keyword weights, and prompt adaptations")
    print("     (keeps: company profiles, gap analyses, PDFs)")
    print()
    print("  3. Full reset — everything except company profiles and gap analyses")
    print("     (keeps: your work product — profiles, gaps, syntheses)")
    print()
    print("  4. Complete wipe — absolutely everything including your work")
    print("     (same as reinstalling from scratch)")
    print()
    print("  5. Cancel")
    print()

    while True:
        choice = input("Enter choice [1-5]: ").strip()
        if choice in ("1", "2", "3", "4", "5"):
            break
        print("  Please enter 1, 2, 3, 4, or 5.")

    if choice == "5":
        print("\n  Cancelled — nothing changed.\n")
        return

    labels = {
        "1": "documents only",
        "2": "documents + learning state",
        "3": "full reset (keep profiles/gaps)",
        "4": "complete wipe",
    }
    print(f"\n  You selected: {labels[choice]}")

    # Extra confirmation for destructive options
    if choice in ("3", "4"):
        confirm = input("  This cannot be undone. Type YES to confirm: ").strip()
        if confirm != "YES":
            print("  Cancelled — nothing changed.\n")
            return

    print()
    conn = get_conn()

    if choice in ("1", "2", "3", "4"):
        reset_documents(conn)

    if choice in ("2", "3", "4"):
        reset_learning(conn)

    if choice in ("3", "4"):
        reset_http_cache()
        reset_pdfs(conn)

    if choice == "4":
        reset_user_work(conn)

    conn.close()

    print()
    print("  Done. Run `python main.py run` to start fresh.")
    if choice in ("1", "2", "3"):
        print("  Your company profiles and gap analyses are preserved.")
    print()


# ── CLI flags mode ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset ARIS data — start fresh without reinstalling.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reset.py               interactive menu
  python reset.py --list        show current data inventory
  python reset.py --documents   clear docs + summaries only
  python reset.py --full        clear everything except profiles/gaps
  python reset.py --all         complete wipe including profiles/gaps
        """,
    )
    parser.add_argument("--list",      action="store_true", help="show current data inventory and exit")
    parser.add_argument("--documents", action="store_true", help="clear documents, summaries, diffs, analytics")
    parser.add_argument("--learning",  action="store_true", help="clear learning state (source profiles, keyword weights)")
    parser.add_argument("--cache",     action="store_true", help="clear HTTP response cache")
    parser.add_argument("--pdfs",      action="store_true", help="clear PDF files and metadata")
    parser.add_argument("--full",      action="store_true", help="clear all of the above except company profiles and gap analyses")
    parser.add_argument("--all",       action="store_true", help="complete wipe — everything including profiles and gap analyses")
    parser.add_argument("--yes", "-y", action="store_true", help="skip confirmation prompts")

    args = parser.parse_args()

    # No flags → interactive
    if not any(vars(args).values()):
        interactive()
        return

    if args.list:
        show_status()
        return

    # Build operation set
    ops = set()
    if args.all or args.full:
        ops = {"documents", "learning", "cache", "pdfs"}
        if args.all:
            ops.add("user_work")
    else:
        if args.documents: ops.add("documents")
        if args.learning:  ops.add("learning")
        if args.cache:     ops.add("cache")
        if args.pdfs:      ops.add("pdfs")

    if not ops:
        parser.print_help()
        return

    # Confirmation for destructive operations
    if not args.yes:
        show_status()
        desc = ", ".join(sorted(ops))
        print(f"  About to clear: {desc}")
        if "user_work" in ops:
            print("  ⚠  This includes your company profiles and gap analyses.")
        confirm = input("  Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("  Cancelled — nothing changed.\n")
            return

    print()
    conn = get_conn()

    if "documents"  in ops: reset_documents(conn)
    if "learning"   in ops: reset_learning(conn)
    if "pdfs"       in ops: reset_pdfs(conn)
    if "user_work"  in ops: reset_user_work(conn)

    conn.close()

    if "cache" in ops:
        reset_http_cache()

    print()
    print("  Done. Run `python main.py run` to start fresh.")
    if "user_work" not in ops:
        print("  Your company profiles and gap analyses are preserved.")
    print()


if __name__ == "__main__":
    main()
