# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 Mitch Kwiatkowski
# ARIS — Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
"""
ARIS — Database Migration Script

Run this once to bring an existing ARIS database up to date with the
current schema. Safe to run multiple times — skips columns that already exist.

Usage:
    python migrate.py
    python migrate.py --db path/to/custom/aris.db

What it does:
  - Adds missing columns to existing tables (never removes or renames)
  - Creates missing tables from scratch
  - Leaves all existing data untouched

Background:
  SQLAlchemy's Base.metadata.create_all() creates tables that don't exist yet,
  but it does NOT add new columns to existing tables. This script fills that gap
  using raw SQLite ALTER TABLE statements, which are safe and reversible.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# ── Column additions by table ─────────────────────────────────────────────────
#
# Each entry: (table, column, sqlite_type, default_value)
# The default is used both as the SQLite DEFAULT and to backfill existing rows.
#
COLUMN_ADDITIONS = [
    # documents table
    ("documents", "origin", "TEXT", "'api'"),
    ("documents", "domain", "TEXT", "'ai'"),
    # summaries table
    ("summaries", "relevance_score", "REAL", "NULL"),
    ("summaries", "urgency", "TEXT", "NULL"),
    ("summaries", "deadline", "TEXT", "NULL"),
    ("summaries", "requirements", "TEXT", "NULL"),  # JSON stored as TEXT
    ("summaries", "impact_areas", "TEXT", "NULL"),  # JSON stored as TEXT
    ("summaries", "plain_english", "TEXT", "NULL"),
    ("summaries", "action_items", "TEXT", "NULL"),  # JSON stored as TEXT
    ("summaries", "jurisdiction", "TEXT", "NULL"),
    ("summaries", "domain", "TEXT", "'ai'"),
    # document_diffs table
    ("document_diffs", "severity", "TEXT", "NULL"),
    ("document_diffs", "diff_type", "TEXT", "NULL"),
    ("document_diffs", "relationship_type", "TEXT", "NULL"),
    ("document_diffs", "change_summary", "TEXT", "NULL"),
    ("document_diffs", "added_requirements", "TEXT", "NULL"),
    ("document_diffs", "removed_requirements", "TEXT", "NULL"),
    ("document_diffs", "modified_requirements", "TEXT", "NULL"),
    ("document_diffs", "definition_changes", "TEXT", "NULL"),
    ("document_diffs", "deadline_changes", "TEXT", "NULL"),
    ("document_diffs", "penalty_changes", "TEXT", "NULL"),
    ("document_diffs", "scope_changes", "TEXT", "NULL"),
    ("document_diffs", "new_action_items", "TEXT", "NULL"),
    ("document_diffs", "obsolete_action_items", "TEXT", "NULL"),
    ("document_diffs", "overall_assessment", "TEXT", "NULL"),
    ("document_diffs", "model_used", "TEXT", "NULL"),
    ("document_diffs", "reviewed", "INTEGER", "0"),
    ("document_diffs", "reviewed_at", "TEXT", "NULL"),
    # feedback_events table
    ("feedback_events", "source", "TEXT", "NULL"),
    ("feedback_events", "agency", "TEXT", "NULL"),
    ("feedback_events", "jurisdiction", "TEXT", "NULL"),
    ("feedback_events", "keywords", "TEXT", "NULL"),
    # pdf_metadata table (may not exist at all — handled by create_all)
    ("pdf_metadata", "origin", "TEXT", "'pdf_manual'"),
    ("pdf_metadata", "file_path", "TEXT", "NULL"),
    ("pdf_metadata", "page_count", "INTEGER", "NULL"),
    ("pdf_metadata", "word_count", "INTEGER", "NULL"),
    ("pdf_metadata", "method", "TEXT", "NULL"),
    ("pdf_metadata", "extracted_at", "TEXT", "NULL"),
    # regulatory_horizon table
    ("regulatory_horizon", "domain", "TEXT", "'ai'"),
    # enforcement_actions table
    ("enforcement_actions", "domain", "TEXT", "'ai'"),
    # schedule_config — two-track scheduling (jurisdiction + enforcement)
    ("schedule_config", "jur_enabled", "INTEGER", "0"),
    ("schedule_config", "jur_days", "TEXT", "'0,1,2,3,4'"),
    ("schedule_config", "jur_time", "TEXT", "'08:00'"),
    ("schedule_config", "jur_domain", "TEXT", "'both'"),
    ("schedule_config", "jur_lookback", "INTEGER", "7"),
    ("schedule_config", "jur_last_run", "TEXT", "NULL"),
    ("schedule_config", "jur_next_run", "TEXT", "NULL"),
    ("schedule_config", "enf_enabled", "INTEGER", "0"),
    ("schedule_config", "enf_interval_hours", "INTEGER", "6"),
    ("schedule_config", "enf_lookback", "INTEGER", "2"),
    ("schedule_config", "enf_last_run", "TEXT", "NULL"),
    ("schedule_config", "enf_next_run", "TEXT", "NULL"),
]

# ── New tables (create if missing) ─────────────────────────────────────────────

NEW_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS source_profiles (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source      TEXT NOT NULL,
        agency      TEXT,
        jurisdiction TEXT,
        total_fetched INTEGER DEFAULT 0,
        total_relevant INTEGER DEFAULT 0,
        quality_score REAL DEFAULT 0.5,
        updated_at  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS keyword_weights (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        weights_json TEXT NOT NULL,
        updated_at   TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prompt_adaptations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        match_keys  TEXT,
        instruction TEXT,
        basis       TEXT,
        active      INTEGER DEFAULT 1,
        created_at  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fetch_history (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        source       TEXT NOT NULL,
        jurisdiction TEXT,
        fetched_at   TEXT,
        doc_count    INTEGER DEFAULT 0,
        error        TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS schedule_config (
        id              INTEGER PRIMARY KEY DEFAULT 1,
        enabled         INTEGER DEFAULT 0,
        interval_hours  INTEGER DEFAULT 24,
        domain          TEXT DEFAULT 'both',
        lookback_days   INTEGER DEFAULT 7,
        last_triggered  TEXT,
        next_run        TEXT,
        updated_at      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS thematic_syntheses (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        topic_key      TEXT NOT NULL,
        topic          TEXT NOT NULL,
        jurisdictions  TEXT,
        docs_used      INTEGER DEFAULT 0,
        doc_ids        TEXT,
        synthesis_json TEXT,
        conflicts_json TEXT,
        model_used     TEXT,
        generated_at   TEXT,
        starred        INTEGER DEFAULT 0,
        notes          TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS document_links (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        source_doc_id   TEXT NOT NULL,
        target_doc_id   TEXT NOT NULL,
        relationship    TEXT,
        created_at      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_profiles (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        name                     TEXT NOT NULL,
        industry_sector          TEXT,
        company_size             TEXT,
        operating_jurisdictions  TEXT,
        ai_systems               TEXT,
        current_practices        TEXT,
        existing_certifications  TEXT,
        primary_concerns         TEXT,
        recent_changes           TEXT,
        created_at               TEXT,
        updated_at               TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gap_analyses (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id       INTEGER NOT NULL,
        profile_name     TEXT,
        jurisdictions    TEXT,
        docs_examined    INTEGER DEFAULT 0,
        applicable_count INTEGER DEFAULT 0,
        gap_count        INTEGER DEFAULT 0,
        critical_count   INTEGER DEFAULT 0,
        posture_score    INTEGER DEFAULT 0,
        scope_json       TEXT,
        gaps_json        TEXT,
        model_used       TEXT,
        generated_at     TEXT,
        starred          INTEGER DEFAULT 0,
        notes            TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pdf_metadata (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id  TEXT,
        origin       TEXT DEFAULT 'pdf_manual',
        file_path    TEXT,
        page_count   INTEGER,
        word_count   INTEGER,
        method       TEXT,
        extracted_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS regulatory_horizon (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        source           TEXT NOT NULL,
        external_id      TEXT NOT NULL,
        jurisdiction     TEXT NOT NULL,
        title            TEXT NOT NULL,
        description      TEXT,
        agency           TEXT,
        stage            TEXT,
        anticipated_date TEXT,
        url              TEXT,
        ai_score         REAL DEFAULT 0.0,
        fetched_at       TEXT,
        dismissed        INTEGER DEFAULT 0,
        UNIQUE(source, external_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trend_snapshots (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_type TEXT NOT NULL UNIQUE,
        data_json     TEXT,
        computed_at   TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS obligation_register_cache (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        cache_key     TEXT NOT NULL UNIQUE,
        jurisdictions TEXT,
        mode          TEXT,
        register_json TEXT,
        item_count    INTEGER DEFAULT 0,
        computed_at   TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS enforcement_actions (
        id               TEXT PRIMARY KEY,
        source           TEXT NOT NULL,
        action_type      TEXT NOT NULL,
        title            TEXT NOT NULL,
        url              TEXT,
        published_date   TEXT,
        agency           TEXT,
        jurisdiction     TEXT,
        respondent       TEXT,
        summary          TEXT,
        full_text        TEXT,
        related_regs     TEXT,
        outcome          TEXT,
        penalty_amount   TEXT,
        ai_concepts      TEXT,
        relevance_score  REAL DEFAULT 0.0,
        fetched_at       TEXT,
        raw_json         TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS brief_cache (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        topic_key   TEXT NOT NULL UNIQUE,
        topic_label TEXT,
        content     TEXT,
        citations   TEXT,
        model_used  TEXT,
        built_at    TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS concept_map_cache (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        concept_key   TEXT NOT NULL UNIQUE,
        concept_label TEXT,
        entries_json  TEXT,
        entry_count   INTEGER DEFAULT 0,
        model_used    TEXT,
        built_at      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_graph_edges (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id   TEXT NOT NULL,
        source_type TEXT NOT NULL,
        target_id   TEXT NOT NULL,
        target_type TEXT NOT NULL,
        edge_type   TEXT NOT NULL,
        concept     TEXT,
        evidence    TEXT,
        strength    REAL DEFAULT 1.0,
        detected_by TEXT DEFAULT 'system',
        created_at  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qa_passages (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type    TEXT NOT NULL,
        source_id      TEXT NOT NULL,
        source_title   TEXT,
        jurisdiction   TEXT,
        chunk_index    INTEGER DEFAULT 0,
        chunk_total    INTEGER DEFAULT 1,
        section_label  TEXT,
        text           TEXT NOT NULL,
        text_hash      TEXT,
        indexed_at     TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qa_sessions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        question        TEXT NOT NULL,
        answer          TEXT,
        citations       TEXT,
        passage_ids     TEXT,
        follow_ups      TEXT,
        model_used      TEXT,
        retrieval_count INTEGER DEFAULT 0,
        asked_at        TEXT
    )
    """,
]


# ── Migration runner ──────────────────────────────────────────────────────────


def get_existing_columns(conn: sqlite3.Connection, table: str) -> set:
    """Return the set of column names currently in a table."""
    try:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        return set()  # table doesn't exist yet


def get_existing_tables(conn: sqlite3.Connection) -> set:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cursor.fetchall()}


def migrate(db_path: Path) -> None:
    if not db_path.exists():
        print(f"  Database not found at: {db_path}")
        print("  Run the server once first to create it, then re-run this script.")
        sys.exit(1)

    print(f"  Database: {db_path}")
    conn = sqlite3.connect(str(db_path))

    try:
        existing_tables = get_existing_tables(conn)
        print(f"  Existing tables: {sorted(existing_tables)}\n")

        # ── Step 1: Create missing tables ─────────────────────────────────────
        print("Step 1: Creating missing tables...")
        for ddl in NEW_TABLES:
            # Extract table name from DDL for reporting
            name = ddl.strip().split("EXISTS")[1].strip().split("(")[0].strip()
            if name not in existing_tables:
                conn.execute(ddl)
                print(f"  ✓ Created table: {name}")
            else:
                print(f"  · Already exists: {name}")
        conn.commit()

        # ── Step 2: Add missing columns ────────────────────────────────────────
        print("\nStep 2: Adding missing columns...")
        added = 0
        skipped = 0
        for table, column, col_type, default in COLUMN_ADDITIONS:
            existing_cols = get_existing_columns(conn, table)
            if not existing_cols:
                # Table doesn't exist — will have been created above with correct schema
                continue
            if column in existing_cols:
                skipped += 1
                continue
            try:
                if default == "NULL":
                    sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                else:
                    sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type} DEFAULT {default}"
                conn.execute(sql)

                # Backfill existing rows if a non-NULL default is provided
                if default != "NULL":
                    conn.execute(
                        f"UPDATE {table} SET {column} = {default} WHERE {column} IS NULL"
                    )
                conn.commit()
                print(f"  ✓ {table}.{column} ({col_type}, default {default})")
                added += 1
            except sqlite3.OperationalError as e:
                print(f"  ✗ {table}.{column} — {e}")

        print(f"\n  Added {added} columns, skipped {skipped} already-present columns.")

        # ── Step 3: Verify critical columns ───────────────────────────────────
        print("\nStep 3: Verifying critical columns...")
        critical = [
            ("documents", "origin"),
            ("summaries", "relevance_score"),
            ("summaries", "jurisdiction"),
        ]
        all_ok = True
        for table, column in critical:
            cols = get_existing_columns(conn, table)
            if column in cols:
                print(f"  ✓ {table}.{column}")
            else:
                print(f"  ✗ {table}.{column} STILL MISSING — check manually")
                all_ok = False

        if all_ok:
            print("\n✓ Migration complete. All critical columns present.")
        else:
            print("\n⚠ Migration finished with warnings — see above.")

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARIS database migration script")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to aris.db (default: auto-detected from config/settings.py)",
    )
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        # Try to read DB_PATH from config
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from config.settings import DB_PATH

            db_path = Path(DB_PATH)
        except Exception:
            db_path = Path("output/aris.db")

    print("ARIS Database Migration")
    print("=" * 40)
    migrate(db_path)
