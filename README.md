# ARIS — AI Regulation Intelligence System

**Monitor. Baseline. Interpret. Learn. Act.**

ARIS is a fully local, agentic system that monitors AI-related legislation and regulations across US Federal agencies, US state legislatures, and international jurisdictions. It ships with a curated baseline of settled AI law, fetches new documents from official government APIs, uses Claude to interpret and analyse them against the baseline, detects when regulations change, learns from your feedback, performs company-specific compliance gap analysis, and synthesises cross-document intelligence — all through a browser dashboard or the command line.

Everything runs on your local machine. No cloud storage. No external data sharing beyond the government APIs and the Anthropic API for AI analysis. The regulatory baselines require no API calls at all.

---

## What It Does

1. **Baselines** — ships with 9 curated, structured baseline JSON files covering the settled body of AI law across EU, US Federal, UK, Canada, and US state jurisdictions. No API calls. Always available.
2. **Fetches** — pulls new AI-related documents from official government APIs across three independent tracks: US Federal, US States, and International
3. **Filters** — eliminates irrelevant documents using keyword pre-screening and learned source-quality scores before spending any Claude API tokens
4. **Interprets** — sends each document to Claude, which compares it against the baseline and generates plain-English summaries with requirements, action items, and urgency
5. **Detects changes** — automatically compares new document versions against their baseline and prior versions, identifying what changed, what it means, and how severe it is
6. **Learns** — adapts filtering thresholds, keyword weights, and Claude prompt instructions based on your feedback, reducing false positives over time
7. **Prioritises** — scores pending documents by urgency and processes the most important ones first
8. **Synthesises** — reads across all documents on a topic and produces a coherent regulatory landscape narrative with cross-jurisdiction conflict detection
9. **Gap analysis** — compares your company's AI systems and governance practices against baseline obligations and database documents to identify specific, document-anchored compliance gaps
10. **PDFs** — auto-downloads PDFs from Federal Register, EUR-Lex, and UK legislation; accepts manually supplied PDFs from any jurisdiction via drop folder or browser upload

---

## Coverage

### Baseline Regulations (ships with application, no API calls)

| Jurisdiction | Regulation | Status |
|---|---|---|
| EU | EU Artificial Intelligence Act (Regulation 2024/1689) | In Force |
| EU | GDPR — AI-relevant provisions (Article 22, DPIAs, etc.) | In Force |
| Federal | Executive Order 14110 — Safe, Secure, and Trustworthy AI | In Force |
| Federal | NIST AI Risk Management Framework (AI RMF 1.0) | Published |
| Federal | FTC AI Guidance and Enforcement Framework | Active |
| GB | UK AI Regulatory Framework and ICO AI Guidance | Active |
| CA | Artificial Intelligence and Data Act (AIDA / Bill C-27) | Proposed |
| IL | Illinois Artificial Intelligence Policy Act (PA 103-0928) | In Force |
| CO | Colorado AI Act (SB 24-205) | In Force (Feb 2026) |

### Live API Sources

**US Federal** — Federal Register, Regulations.gov, Congress.gov (free API keys)

**US States** — LegiScan API covers all 50 states; Pennsylvania also uses PA General Assembly XML feed

**International** — EU (EUR-Lex SPARQL + EU AI Office RSS), UK (Parliament Bills API + legislation.gov.uk), Canada (OpenParliament + Canada Gazette RSS), Japan / China / Australia (pinned documents)

---

## Folder Structure

```
ai-reg-tracker/
│
├── main.py                              ← CLI entry point
├── server.py                            ← FastAPI REST server
├── requirements.txt
│
├── config/
│   ├── keys.env.example / keys.env      ← API keys
│   ├── settings.py                      ← Global settings, keywords, paths
│   └── jurisdictions.py                 ← Toggle jurisdictions on/off
│
├── data/
│   └── baselines/                       ← Static baseline JSON files (no API needed)
│       ├── index.json                   ← Lists all baselines with metadata
│       ├── eu_ai_act.json               ← EU Artificial Intelligence Act
│       ├── eu_gdpr_ai.json              ← EU GDPR AI-relevant provisions
│       ├── us_eo_14110.json             ← Executive Order 14110
│       ├── us_nist_ai_rmf.json          ← NIST AI Risk Management Framework
│       ├── us_ftc_ai.json               ← FTC AI guidance and enforcement
│       ├── uk_ai_framework.json         ← UK AI regulatory framework
│       ├── canada_aida.json             ← Canada AIDA (Bill C-27)
│       ├── illinois_aipa.json           ← Illinois AI Policy Act
│       └── colorado_ai.json             ← Colorado AI Act (SB 205)
│
├── agents/
│   ├── baseline_agent.py                ← Loads/queries static baselines (no API)
│   ├── interpreter.py                   ← Claude document analysis + learning pre-filter
│   ├── diff_agent.py                    ← Version comparison + addendum analysis (baseline-aware)
│   ├── learning_agent.py                ← Adaptive intelligence: feedback, scoring, adaptation
│   ├── orchestrator.py                  ← Coordinates all tracks + learning hooks
│   ├── scheduler.py                     ← Watch mode / recurring runs
│   ├── synthesis_agent.py               ← Cross-document thematic synthesis + conflict detection
│   └── gap_analysis_agent.py            ← Company-profile compliance gap analysis
│
├── sources/
│   ├── federal_agent.py                 ← Federal Register, Regulations.gov, Congress.gov
│   ├── state_agent_base.py
│   ├── pdf_agent.py                     ← PDF extraction, auto-download, drop folder
│   ├── states/
│   │   └── pennsylvania.py
│   └── international/
│       ├── eu.py / uk.py / canada.py / stubs.py
│
├── utils/
│   ├── db.py                            ← All SQLite tables + CRUD
│   ├── cache.py
│   └── reporter.py
│
├── tests/
│   ├── test_suite.py                    ← Federal + PA agent tests
│   ├── test_international.py            ← EU, UK, Canada, stubs
│   ├── test_diff.py                     ← Diff agent + change detection
│   ├── test_learning.py                 ← Learning agent + feedback
│   ├── test_synthesis.py                ← Synthesis agent + DB
│   ├── test_pdf.py                      ← PDF agent + extraction
│   ├── test_gap_analysis.py             ← Gap analysis agent + profiles
│   └── test_baselines.py                ← Baseline agent + all JSON files
│
├── ui/src/views/
│   ├── Dashboard.jsx                    ← Stats, urgency chart, recent activity
│   ├── Documents.jsx                    ← Filterable table with feedback buttons
│   ├── Changes.jsx                      ← Version diffs and addenda
│   ├── Baselines.jsx                    ← Browse settled regulatory baselines
│   ├── Synthesis.jsx                    ← Cross-document synthesis + conflicts
│   ├── GapAnalysis.jsx                  ← Company profile + gap analysis
│   ├── PDFIngest.jsx                    ← PDF auto-download, upload, drop folder
│   ├── RunAgents.jsx                    ← On-demand pipeline execution
│   ├── Watchlist.jsx                    ← Saved keyword searches
│   ├── Graph.jsx                        ← Document relationship graph
│   ├── Learning.jsx                     ← Feedback, source quality, keyword weights
│   └── Settings.jsx                     ← API keys, jurisdictions, CLI reference
│
└── output/                              ← Created automatically
    ├── aris.db                          ← SQLite database
    ├── watchlist.json
    ├── pdf_inbox/                       ← Drop PDFs here for manual ingestion
    ├── pdfs/                            ← Downloaded and stored PDFs
    └── .cache/                          ← HTTP response cache
```

---

## Database Tables

| Table | Purpose |
|---|---|
| `documents` | Raw documents from all sources (origin: api / pdf_auto / pdf_manual) |
| `summaries` | Claude-generated summaries with requirements, action items, urgency |
| `document_diffs` | Version comparison and addendum analysis results |
| `document_links` | Explicit relationships between documents |
| `feedback_events` | Human relevance feedback driving the learning system |
| `source_profiles` | Rolling quality scores per source and agency |
| `keyword_weights` | Learned per-keyword relevance multipliers |
| `prompt_adaptations` | Claude-generated domain-specific prompt instructions |
| `fetch_history` | Fetch log for adaptive scheduling |
| `thematic_syntheses` | Cross-document synthesis and conflict detection results |
| `company_profiles` | Company profiles for gap analysis |
| `gap_analyses` | Gap analysis results (history preserved) |
| `pdf_metadata` | PDF extraction metadata (path, pages, word count, method) |

---

## Setup

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** — needed once to build the browser UI; download from nodejs.org

### 1. Install dependencies

```bash
cd ai-reg-tracker
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp config/keys.env.example config/keys.env
# Edit keys.env and paste your keys
```

| Key | Source | Required? |
|---|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com/settings/keys | **Yes** |
| `REGULATIONS_GOV_KEY` | open.gsa.gov | Recommended |
| `CONGRESS_GOV_KEY` | api.congress.gov/sign-up | Recommended |
| `LEGISCAN_KEY` | legiscan.com/legiscan | For US states |

### 3. Verify

```bash
python main.py status
```

---

## Starting the Browser UI

**Development** (hot reload):
```bash
# Terminal 1
python server.py

# Terminal 2
cd ui && npm install && npm run dev
# Open http://localhost:5173
```

**Production** (single port):
```bash
cd ui && npm install && npm run build
cd .. && python server.py
# Open http://localhost:8000
```

---

## The Browser UI — Twelve Views

### Dashboard
Stats, urgency chart, jurisdiction breakdown, recent changes and documents. Refreshes every 8 seconds.

### Documents
Filterable, searchable, paginated table of all documents. Unsummarised documents show a **Pending** badge. Detail panel includes the full AI summary, requirements, recommendations, action items, feedback buttons, checklist generator, and compare tool.

### Changes
All detected regulatory changes — version updates and addenda — with expandable diff cards showing side-by-side requirement comparisons, deadline changes, and first actions.

### Baselines
Browse the 9 settled regulatory baselines shipped with the application. Filterable by jurisdiction. Each baseline has tabs for Overview, Obligations (by actor type), Prohibited practices, Timeline, Definitions, Penalties, and Cross-references. Zero API calls — all data is local JSON.

### Synthesis
Cross-document thematic synthesis with jurisdiction conflict detection. Left sidebar with history and suggested topics. Main panel with five tabs: Landscape, Obligations, Conflicts, Definitions, and Posture. Run from suggested topics or enter any topic. Results cached for 7 days.

### Gap Analysis
Company-specific compliance gap analysis. Create a profile (company identity, AI systems, current governance practices) and run it against the baseline obligations and your document database. Results show posture score, gap cards anchored to specific document IDs, compliant areas, a phased roadmap, and the full regulatory scope mapping.

### PDF Ingest
Three tabs: **Auto-Download** (documents already in the DB that have PDF URLs from Federal Register, EUR-Lex, UK legislation), **Upload PDF** (drag-and-drop with full metadata tagging including any free-text jurisdiction), **Drop Folder** (ingests files placed in `output/pdf_inbox/`).

### Run Agents
On-demand pipeline execution with source checkboxes, lookback window, and live scrolling log.

### Watchlist
Saved keyword searches with match counts and document lists.

### Graph
Force-directed document relationship graph. Nodes coloured by urgency; edges by relationship type.

### Learning
Five tabs: Overview, Sources (quality bar charts), Keywords (weight drift), Adaptations (Claude-generated prompt notes), Schedule (optimal fetch timing).

### Settings
API key status, enabled jurisdictions, database statistics, CLI quick reference.

---

## CLI Reference

```bash
# Full pipeline
python main.py run [--days N] [--limit N]

# Fetch
python main.py fetch [--source federal|states|international|PA|EU|GB] [--days N]

# Summarize
python main.py summarize [--limit N]

# Report
python main.py report [--days N] [--jurisdiction X] [--urgency X]

# Changes
python main.py changes [--severity X] [--type X] [--unreviewed]
python main.py history DOC_ID
python main.py review DIFF_ID
python main.py diff DOC_A DOC_B
python main.py link BASE_ID ADDENDUM_ID

# Baselines
python main.py baselines                     # list all loaded baselines
python main.py baselines --jurisdiction EU   # filter by jurisdiction

# Synthesis
python main.py synthesis-topics              # suggested topics from your DB
python main.py synthesise "topic" [-j JURS] [--no-conflicts] [--refresh]
python main.py syntheses [--limit N]

# Gap analysis
python main.py gap-profiles                  # list company profiles
python main.py gap-analyse PROFILE_ID        # run analysis
python main.py gap-analyses [--profile N]    # list results

# PDF
python main.py pdf-candidates                # documents with downloadable PDFs
python main.py pdf-download [--limit N]      # auto-download PDFs
python main.py pdf-inbox                     # list files in drop folder

# Export
python main.py export [--format markdown|json] [--output FILE]

# Watch mode
python main.py watch [--interval N] [--days N]

# System
python main.py status
python main.py agents
```

---

## How the Baseline System Works

The `data/baselines/` directory contains curated JSON files representing the settled body of AI law. They ship with the code and require no API calls.

**In the diff agent:** before building a version-comparison prompt, the diff agent calls `BaselineAgent.format_for_diff_context()` to find the baseline that matches the incoming document. The baseline — its obligations, definitions, timeline, and prohibitions — is prepended to the Claude prompt. Claude can then say "this change adds an obligation not present in the original Act" rather than only describing the delta.

**In the gap analysis agent:** before the scope-mapping Claude call, all baseline obligations for the relevant jurisdictions are loaded and included in the prompt. This means gap analysis works even if the database has few summarised documents — the baselines provide the foundational obligation layer.

**To add a baseline:** create a new JSON file in `data/baselines/` following the schema of an existing file, add an entry to `index.json`, and restart the server. No database migration, no API calls, no recompilation.

---

## How the Learning System Works

Every time you mark a document as **Not Relevant** in the Documents view, three things happen: the source's quality score drops using a Wilson confidence interval, the agency score drops separately, and the matched keyword weights are reduced slightly. On the next fetch, documents from low-quality sources need a higher composite score to pass the pre-filter, which runs entirely locally before any Claude API call.

After 5+ false positives from the same source within 30 days, Claude analyses the pattern and generates a targeted `NOTE:` instruction prepended to all future prompts for that source. You can view, enable, and disable these in the Learning → Adaptations tab.

---

## How Gap Analysis Works

**Step 1:** Create a company profile with your industry, operating jurisdictions, AI systems (name, purpose, data types, deployment status, autonomy level), and current governance practices (seven Yes/No/Unsure checkboxes).

**Step 2:** Run the analysis. Two Claude passes execute:

- **Pass 1 (Scope mapping):** determines which regulations apply to this company and which specific provisions are triggered. Baseline obligations for the relevant jurisdictions are included regardless of what is in the database, so the analysis covers the full settled body of law.
- **Pass 2 (Gap identification):** compares applicable obligations against current practices. Each gap is anchored to a specific document ID, rated by severity, shows what the regulation requires vs what the company has, gives the earliest applicable deadline, and specifies a concrete first action.

**Output:** posture score (0–100), gap cards sorted by severity, compliant areas, a three-phase roadmap, and the full scope mapping for audit purposes.

---

## Running Tests

```bash
python -m pytest tests/ -v

# Or without pytest:
python -m unittest tests.test_suite -v
python -m unittest tests.test_baselines -v
# ... etc.
```

159 tests across 8 test files. All database-dependent test classes pass with real SQLAlchemy installed.

---

## Adding a New Jurisdiction

**New US state:**
```python
# sources/states/new_york.py
from sources.state_agent_base import StateAgentBase

class NewYorkAgent(StateAgentBase):
    state_code     = "NY"
    state_name     = "New York"
    legiscan_state = "NY"
```
Add `"NY"` to `ENABLED_US_STATES` in `config/jurisdictions.py`.

**New country:**
```python
# sources/international/singapore.py
from sources.international.base import InternationalAgentBase

class SingaporeAgent(InternationalAgentBase):
    jurisdiction_code = "SG"
    jurisdiction_name = "Singapore"
    region            = "Asia-Pacific"
    language          = "en"

    def fetch_native(self, lookback_days=30):
        return []   # implement fetch from PDPC or equivalent
```
Add to `ENABLED_INTERNATIONAL` and `INTERNATIONAL_MODULE_MAP` in `config/jurisdictions.py`.

**New baseline:**
Create `data/baselines/singapore_pdpa.json` following the schema in any existing baseline file, then add an entry to `data/baselines/index.json`. Restart the server.

**Manual PDF from any jurisdiction:**
Use the PDF Ingest view → Upload tab, or place the PDF in `output/pdf_inbox/` and use the Drop Folder tab. Jurisdiction is free text — any country or region is supported.

---

## Configuration

Edit `config/keys.env`:

| Setting | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required |
| `REGULATIONS_GOV_KEY` | — | Regulations.gov |
| `CONGRESS_GOV_KEY` | — | Congress.gov |
| `LEGISCAN_KEY` | — | US state monitoring |
| `LOOKBACK_DAYS` | `30` | Days back for new documents |
| `MIN_RELEVANCE_SCORE` | `0.5` | Minimum Claude relevance score |
| `DB_PATH` | `./output/aris.db` | SQLite database path |
| `CACHE_TTL_HOURS` | `6` | HTTP response cache TTL |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR |

---

## Design Principles

**Everything runs locally.** Database, cache, PDF files, learning state, baselines — all on your machine.

**Baselines are the starting point, documents are updates.** The system knows what the EU AI Act requires before any new implementing act arrives. A new document is analysed against that baseline, not in isolation.

**Every gap links to a document.** The gap analysis never produces generic advice. Every gap has a `document_id` you can look up in the Documents view.

**The browser UI is additive.** Every feature is accessible from the CLI. The FastAPI server is a thin REST layer over the same Python agents.

**Learning never blocks operation.** All learning calls are wrapped in try/except with graceful fallback. If the learning agent fails, the pipeline continues.

**Full history preserved.** Every version comparison, gap analysis, synthesis, and feedback event is stored as a new record. Nothing is overwritten.
