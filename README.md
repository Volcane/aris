# ARIS — AI Regulation Intelligence System

**Monitor. Interpret. Act.**

ARIS is a fully local, agentic system that automatically monitors AI-related legislation and regulations across US Federal agencies, US state legislatures, and international jurisdictions. It fetches documents from public government APIs, uses Claude (Anthropic) to interpret legal language, detects when regulations change, and delivers plain-English summaries with concrete compliance action items — all through a browser-based dashboard or command-line interface.

Everything runs on your local machine. No cloud storage. No data sharing beyond the government APIs being queried and the Anthropic API for AI analysis.

---

## What It Does

1. **Fetches** — Pulls AI-related documents from official government APIs on a schedule or on demand across three independent tracks: US Federal, US States, and International
2. **Filters** — Eliminates irrelevant documents using keyword pre-screening before spending any AI tokens
3. **Interprets** — Sends each document to Claude, which identifies mandatory requirements vs. voluntary recommendations and generates concrete compliance action items
4. **Detects changes** — Automatically compares new document versions against what was previously stored, and identifies when a new document amends or reinterprets an existing regulation
5. **Stores** — Saves everything to a local SQLite database including full change history
6. **Reports** — Browser dashboard with five views, plus CLI export to Markdown or JSON

---

## Coverage

### US Federal
| Source | What It Covers | API Key |
|--------|---------------|---------|
| Federal Register | Final rules, proposed rules, executive orders, presidential memoranda, notices | None required |
| Regulations.gov | Full rulemaking dockets, public comment periods | Free — register at open.gsa.gov |
| Congress.gov | House and Senate bills, resolutions | Free — register at api.congress.gov |

### US States
| State | Sources | API Key |
|-------|---------|---------|
| Pennsylvania | LegiScan API + PA General Assembly XML feed (updated hourly) | LegiScan free tier |
| All other states | LegiScan API (50-state coverage, ready to activate) | LegiScan free tier |

### International
| Jurisdiction | Sources | API Key |
|-------------|---------|---------|
| European Union | EUR-Lex Cellar SPARQL endpoint, EU AI Office RSS, pinned AI Act documents | None required |
| United Kingdom | UK Parliament Bills API, legislation.gov.uk Atom feed, GOV.UK Search API | None required |
| Canada | OpenParliament.ca API, Canada Gazette RSS (Parts I & II), ISED news feed | None required |
| Japan | METI English press release RSS, pinned METI/MIC AI guidelines | None required |
| China | Pinned CAC regulatory documents | None required |
| Australia | Pinned DISR Voluntary AI Safety Standard | None required |

---

## How Claude Is Used

Every document passes through `agents/interpreter.py`, which sends it to Claude via the Anthropic API. Claude returns a structured JSON object containing:

- **`plain_english`** — A 2–3 sentence summary any non-lawyer can understand
- **`requirements`** — Legally mandatory obligations (Must / Shall / Required to…)
- **`recommendations`** — Non-mandatory guidance and best practices
- **`action_items`** — Specific steps your legal or compliance team should take
- **`deadline`** — Comment periods or effective dates extracted from the document
- **`impact_areas`** — Business domains affected (Healthcare AI, Hiring Algorithms, Marketing, etc.)
- **`urgency`** — Low / Medium / High / Critical
- **`relevance_score`** — How directly the document applies to AI regulation (0.0–1.0)

Documents with a relevance score below 0.3 are dropped. A fast keyword pre-filter runs before any API call to keep costs low.

Claude is also used in the **diff agent** to compare document versions and analyse addenda, and in the **checklist generator** to produce actionable compliance checklists.

---

## Folder Structure

Place all files exactly as shown. Create the folders first, then place the files. Every folder marked with `__init__.py` needs that file created as a blank empty text file.

```
ai-reg-tracker/
│
├── main.py                              ← CLI entry point
├── server.py                            ← FastAPI server for the browser UI
├── requirements.txt                     ← Python dependencies
│
├── config/
│   ├── __init__.py                      ← Empty file (required)
│   ├── keys.env.example                 ← Copy to keys.env and fill in your API keys
│   ├── keys.env                         ← Your actual API keys (never commit this)
│   ├── settings.py                      ← Global settings, keywords, API base URLs
│   └── jurisdictions.py                 ← Toggle US states and international on/off
│
├── agents/
│   ├── __init__.py                      ← Empty file (required)
│   ├── interpreter.py                   ← Claude-powered document analysis
│   ├── diff_agent.py                    ← Version comparison and addendum analysis
│   ├── orchestrator.py                  ← Coordinates all three fetch tracks
│   └── scheduler.py                     ← Watch mode / recurring scheduled runs
│
├── sources/
│   ├── __init__.py                      ← Empty file (required)
│   ├── federal_agent.py                 ← Federal Register, Regulations.gov, Congress.gov
│   ├── state_agent_base.py              ← Abstract base class for all US state agents
│   │
│   ├── states/                          ← US State agents (one file per state)
│   │   ├── __init__.py                  ← Empty file (required)
│   │   ├── pennsylvania.py              ← PA: LegiScan + PA General Assembly XML feed
│   │   └── virginia.py                  ← Template for adding other states
│   │
│   └── international/                   ← International jurisdiction agents
│       ├── __init__.py                  ← Empty file (required)
│       ├── base.py                      ← Abstract base class for all international agents
│       ├── eu.py                        ← European Union: EUR-Lex SPARQL + EU AI Office RSS
│       ├── uk.py                        ← United Kingdom: Parliament + legislation.gov.uk + GOV.UK
│       ├── canada.py                    ← Canada: OpenParliament + Gazette RSS + ISED feed
│       └── stubs.py                     ← Japan, China, Australia — ready to activate
│
├── utils/
│   ├── __init__.py                      ← Empty file (required)
│   ├── db.py                            ← SQLite database (documents, summaries, diffs, links)
│   ├── cache.py                         ← HTTP response cache, retry logic, keyword filter
│   └── reporter.py                      ← Terminal dashboard + Markdown/JSON export
│
├── tests/
│   ├── test_suite.py                    ← Federal and PA agent tests
│   ├── test_international.py            ← EU, UK, Canada, and stub agent tests
│   └── test_diff.py                     ← Diff agent and change detection tests
│
├── ui/                                  ← React frontend (browser dashboard)
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx                     ← React entry point
│       ├── index.css                    ← Global styles
│       ├── App.jsx                      ← Shell layout and navigation
│       ├── api.js                       ← All API calls to the FastAPI backend
│       ├── components.jsx               ← Shared UI components
│       └── views/
│           ├── Dashboard.jsx            ← Overview, stats, charts, recent activity
│           ├── Documents.jsx            ← Filterable table with detail panel and tools
│           ├── Changes.jsx              ← Version diffs and addenda with inline highlights
│           ├── RunAgents.jsx            ← On-demand agent execution with live log
│           ├── Watchlist.jsx            ← Saved keyword searches with match counts
│           ├── Graph.jsx                ← Interactive document relationship graph
│           └── Settings.jsx             ← API key status, configuration, CLI reference
│
└── output/                              ← Created automatically on first run
    ├── aris.db                          ← SQLite database
    ├── watchlist.json                   ← Saved watchlist entries
    ├── .cache/                          ← HTTP response cache
    └── aris_report_YYYYMMDD.md          ← Exported reports
```

---

## Setup

### Prerequisites

- **Python 3.10 or higher**
- **Node.js 18 or higher** — needed to build the browser UI. Download from [nodejs.org](https://nodejs.org). You only need it once to build the frontend; after that only Python needs to run.

### 1. Install Python Dependencies

```bash
cd ai-reg-tracker
pip install -r requirements.txt
```

### 2. Get Your API Keys

All keys are free. Register at the links below and paste them into `config/keys.env`.

| Key | Where to Get It | Required? |
|-----|----------------|-----------|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys | **Yes** — needed for all AI features |
| `REGULATIONS_GOV_KEY` | https://open.gsa.gov/api/regulationsgov/ | Recommended |
| `CONGRESS_GOV_KEY` | https://api.congress.gov/sign-up/ | Recommended |
| `LEGISCAN_KEY` | https://legiscan.com/legiscan | Required for US state monitoring |

```bash
cp config/keys.env.example config/keys.env
# Open keys.env in any text editor and paste your keys
```

### 3. Verify Setup

```bash
python main.py status
```

This shows which API keys are configured, which jurisdictions are enabled, and database statistics.

---

## Starting the Browser UI

You need two terminals the first time. After the initial `npm install`, you can use either workflow.

**Development mode (hot reload — best while making changes):**
```bash
# Terminal 1
python server.py

# Terminal 2
cd ui
npm install
npm run dev
# Open http://localhost:5173
```

**Production mode (single terminal, single port):**
```bash
cd ui
npm install
npm run build        # builds ui/dist/ — only needed once, or after UI changes
cd ..
python server.py
# Open http://localhost:8000
```

The API documentation is always available at `http://localhost:8000/docs`.

---

## Browser UI — The Six Views

### Dashboard
The home screen. Shows stat cards (total documents, summarized, changes, critical diffs), an urgency distribution bar chart for the last 14 days, a jurisdiction breakdown, recent detected changes flagged by severity, and the latest documents. Refreshes every 8 seconds.

### Documents
A filterable, searchable, paginated table of everything in the database. Filter by jurisdiction, urgency, document type, and date range. Free-text search across titles and AI summaries. Click any row to open the detail panel showing the full AI summary, requirements, recommendations, action items, impact areas, and change history. Two tools available per document:

- **Checklist Generator** — Claude produces a structured compliance checklist organised by timeframe (Immediate / Near-Term / Ongoing / Documentation / Team Responsibilities), with checkboxes. Downloadable as Markdown.
- **Compare** — Enter any other document ID to run a side-by-side diff using the diff agent.

Export the current filtered view to JSON with one click.

### Changes
All detected regulatory changes — both version updates (same regulation republished with different content) and addenda (a separate document that modifies an existing regulation). Each card shows the severity, change type, and summary. Expand any card for the full diff view: a two-column layout with added requirements on the left and removed/relaxed requirements on the right, plus deadline changes, definition clarifications, penalty changes, new action items, and an overall compliance assessment. Mark each change as reviewed to track your team's progress.

Filter by severity (Critical / High / Medium / Low), change type, and whether it has been reviewed.

### Run Agents
A control panel for triggering the full pipeline on demand. Checkbox grid for every available source (each with a description of what it covers), lookback window selector, and toggles for AI summarization and change detection. A live scrolling log window streams agent output in real time so you can see exactly what is being fetched and processed. Shows a summary result when the run completes.

### Watchlist
Saved keyword searches that act as persistent alerts. Each entry has a name, one or more keywords, and optional jurisdiction filters. The system matches every document in the database against your watchlist and shows a count of matching documents per entry. Expand any entry to see the matching documents. Add and remove entries at any time.

### Graph
An interactive force-directed graph of document relationships built from the `document_links` table. Nodes are coloured by urgency level; edges are coloured by relationship type (amends, clarifies, implements, supersedes, version_of). Click any node to open a detail panel showing the document's jurisdiction, type, status, source link, and all its connections. Filter by jurisdiction and zoom to fit. Relationships are created automatically by the diff agent or manually via the CLI or the Documents view.

### Settings
API key status with direct links to register for any missing keys. List of all enabled jurisdictions. Database statistics table. Quick reference card for all CLI commands.

---

## CLI Usage

The CLI is fully functional independently of the browser UI and is the primary way to run scheduled jobs and automation.

### Run the Full Pipeline
```bash
python main.py run                          # fetch all sources + summarize
python main.py run --days 7                 # last 7 days only
python main.py run --limit 100              # summarize up to 100 documents
```

### Fetch Without Summarizing
```bash
python main.py fetch                        # all sources
python main.py fetch --source federal       # US Federal only
python main.py fetch --source states        # all enabled US states
python main.py fetch --source international # all international
python main.py fetch --source PA            # Pennsylvania only
python main.py fetch --source EU            # European Union only
python main.py fetch --source GB            # United Kingdom only
python main.py fetch --days 7
```

### Summarize Pending Documents
```bash
python main.py summarize
python main.py summarize --limit 100
```

### View Results
```bash
python main.py report                       # all jurisdictions, last 30 days
python main.py report --days 7
python main.py report --jurisdiction EU
python main.py report --jurisdiction Federal
python main.py report --urgency High
```

### Regulatory Changes
```bash
python main.py changes                      # all recent changes
python main.py changes --severity High      # High and Critical only
python main.py changes --type addendum      # addenda only
python main.py changes --unreviewed         # pending human review

python main.py history FR-2024-00123        # full timeline for one document
python main.py review 42                    # mark diff ID 42 as reviewed

python main.py diff DOC-A DOC-B             # manually compare two documents
python main.py link BASE-ID ADDENDUM-ID     # declare an addendum relationship
```

### Export
```bash
python main.py export --format markdown
python main.py export --format json
python main.py export --format markdown --output my_report.md
```

### Continuous Monitoring
```bash
python main.py watch                        # run every 24 hours (default)
python main.py watch --interval 12
python main.py watch --interval 6 --days 2
```

### System Information
```bash
python main.py status                       # API keys, DB stats, enabled jurisdictions
python main.py agents                       # list all active source agents
```

---

## How Change Detection Works

### Version Updates
When a document you already have in the database is fetched again with different content (the content hash changes), the orchestrator automatically captures the old version and sends both to the diff agent. Claude compares them and returns a structured breakdown of what changed: requirements added, removed, or modified (with a Stricter / More Lenient / Clarified / Scope Changed tag), definition changes, deadline changes, penalty changes, and new vs. obsolete action items. Each comparison is stored as a `DocumentDiff` record in the database and linked to both document versions.

### Addendum Detection
Every time new documents are fetched, the system scans them for signals that they amend or clarify an existing document in the database. It looks for keywords like "amends", "corrigendum", "implementing", "guidelines on", "pursuant to", and checks for CELEX numbers or title word overlap. When a match is found, Claude analyses the addendum against the base regulation's existing summary to identify which provisions are affected, what new obligations arise, and when they take effect. The addendum is stored with a `DocumentLink` connecting it to the base regulation.

### Manual Linking
When the heuristics miss a connection, you can declare it manually:
```bash
python main.py link EU-CELEX-32024R1689 EU-AIOFFICE-guidelines-2025
```
Or use the Compare button in the Documents view.

---

## What Each Document Summary Looks Like

```json
{
  "id": "EU-CELEX-32024R1689",
  "title": "Regulation (EU) 2024/1689 — EU Artificial Intelligence Act",
  "source": "eurlex_pinned",
  "jurisdiction": "EU",
  "doc_type": "Regulation",
  "status": "In Force",
  "agency": "European Commission / European Parliament",
  "published_date": "2024-07-12",
  "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689",
  "plain_english": "The EU AI Act establishes a risk-based framework classifying AI systems
                    into four tiers. Companies placing AI on the EU market or using AI to
                    serve EU users must comply, with penalties up to €35M or 7% of global
                    turnover for violations.",
  "requirements": [
    "Must register high-risk AI systems in the EU database before market placement",
    "Must conduct conformity assessments for all high-risk AI systems",
    "Must implement human oversight mechanisms for high-risk AI deployments",
    "Must cease all prohibited AI practices by 2 February 2025"
  ],
  "recommendations": [
    "Voluntarily follow the GPAI Code of Practice to demonstrate compliance readiness",
    "Establish an AI governance committee to monitor Act implementation milestones"
  ],
  "action_items": [
    "Audit all AI systems in use and classify each by risk tier",
    "Identify systems that qualify as high-risk under Annex III and begin conformity assessment",
    "Assign an EU AI Act compliance owner before the August 2026 full-application deadline"
  ],
  "deadline": "2026-08-02",
  "impact_areas": ["Product Development", "Healthcare AI", "Hiring Algorithms",
                   "Biometric Systems", "EU Market Access"],
  "urgency": "Critical",
  "relevance_score": 1.0
}
```

---

## Adding a New US State

Create `sources/states/new_york.py`:
```python
from sources.state_agent_base import StateAgentBase

class NewYorkAgent(StateAgentBase):
    state_code     = "NY"
    state_name     = "New York"
    legiscan_state = "NY"
    # LegiScan handles everything automatically.
    # Override fetch_native() to add a state-specific XML/RSS feed if available.
```

Add `"NY"` to `ENABLED_US_STATES` in `config/jurisdictions.py`.

---

## Adding a New Country

Create `sources/international/singapore.py`:
```python
from sources.international.base import InternationalAgentBase, parse_date

class SingaporeAgent(InternationalAgentBase):
    jurisdiction_code = "SG"
    jurisdiction_name = "Singapore"
    region            = "Asia-Pacific"
    language          = "en"

    def fetch_native(self, lookback_days=30):
        # Implement fetch from PDPC or MCI publications
        # Return a list of self._make_doc(...) dicts
        return []
```

Add `"SG"` to `ENABLED_INTERNATIONAL` and `"SG": "sources.international.singapore"` to `INTERNATIONAL_MODULE_MAP` in `config/jurisdictions.py`.

Stub classes for Japan, China, and Australia are already in `sources/international/stubs.py`. To activate them, just uncomment their codes in `config/jurisdictions.py`.

---

## Running Tests

```bash
python -m pytest tests/ -v

# Or without pytest:
python -m unittest tests.test_suite -v
python -m unittest tests.test_international -v
python -m unittest tests.test_diff -v
```

54 tests across three test files covering federal agents, PA state agent, international agents, diff agent logic, and database operations.

---

## Configuration Reference

All settings live in `config/keys.env`. Copy from `keys.env.example` to get started.

| Setting | Default | Description |
|---------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required. Your Anthropic API key |
| `REGULATIONS_GOV_KEY` | — | Free key for Regulations.gov |
| `CONGRESS_GOV_KEY` | — | Free key for Congress.gov |
| `LEGISCAN_KEY` | — | Free key for LegiScan (US states) |
| `LOOKBACK_DAYS` | `30` | How many days back to search for new documents |
| `MIN_RELEVANCE_SCORE` | `0.5` | Minimum Claude relevance score to store a summary |
| `DB_PATH` | `./output/aris.db` | Path to the SQLite database file |
| `CACHE_TTL_HOURS` | `6` | How long to cache API responses locally |
| `LOG_LEVEL` | `INFO` | Logging verbosity: DEBUG, INFO, WARNING, ERROR |

---

## Key Design Decisions

**Everything runs locally.** The SQLite database, HTTP cache, watchlist, and exported files all live in the `output/` folder on your machine. Nothing is sent to any external service except the government APIs being queried and the Anthropic API for AI analysis.

**Three independent fetch tracks.** US Federal, US States, and International can each be run, scheduled, or filtered independently. Adding a jurisdiction to one track has no effect on the others.

**Two-stage AI cost control.** A fast keyword pre-filter runs locally before any Claude API call. Claude then applies its own relevance scoring, and documents rated below 0.3 are dropped without being stored.

**Pinned critical documents.** For jurisdictions with landmark legislation already in force (EU AI Act, UK Data Use and Access Act, Canada AIDA status, etc.), the system includes curated document entries that are always present regardless of publication date. This ensures critical compliance obligations are never missed because they fall outside a lookback window.

**Full change history preserved.** Every version comparison and addendum analysis is stored as a new `DocumentDiff` record, never overwriting previous ones. You can reconstruct the complete evolution of any regulation over time.

**HTTP response caching.** All API responses are cached locally for 6 hours by default. Repeated runs do not re-query APIs unnecessarily, and the system can produce reports even when APIs are temporarily unavailable.

**Browser UI is additive, not required.** Every feature accessible in the browser UI is also accessible via the CLI. The server is a thin REST wrapper around the same Python agents and database layer. You can run the system indefinitely without ever starting the UI.
