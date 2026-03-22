# ARIS — Automated Regulatory Intelligence System

**Monitor. Baseline. Compare. Interpret. Consolidate. Trend. Horizon. Learn. Act.**

ARIS is a fully local, agentic system that monitors **AI regulation and data privacy law** across 18 US states, 10 international jurisdictions, and US Federal agencies. It ships with 31 curated baseline regulations, fetches live documents from official government APIs, uses Claude to interpret and analyse them, detects changes, tracks regulatory velocity, scans the regulatory horizon for planned regulations, consolidates obligations, compares jurisdictions side-by-side, and performs company-specific compliance gap analysis — all through a browser dashboard or the command line.

Everything runs on your machine. The 31 baseline regulations, consolidation register, velocity analytics, and horizon calendar require no Claude API calls.

---

## What It Does

| # | Feature | API Calls | Description |
|---|---------|-----------|-------------|
| 1 | **Baselines** | None | 31 curated baselines covering settled AI regulation and data privacy law. Always available. |
| 2 | **Fetch** | None | Concurrent fetch from 18 US states, 10 international jurisdictions, and 5 US Federal sources. |
| 3 | **Filter** | None | Domain-aware keyword pre-screening (separate AI and privacy scoring). Skipped docs recorded with reason. |
| 4 | **Interpret** | Claude | Plain-English summaries, urgency ratings, requirements, action items, deadlines. Domain-specific prompts. |
| 5 | **Change detection** | Claude | Baseline-aware diffs — compares new documents against settled law, not just prior versions. |
| 6 | **Consolidation** | Optional | De-duplicated obligation register from all 31 baselines. Fast mode: zero API calls. Full mode: one Claude call. |
| 7 | **Trends & velocity** | None | Jurisdiction velocity sparklines, impact-area heatmap, acceleration alerts — all from local DB. |
| 8 | **Horizon scanning** | None | Monitors Unified Regulatory Agenda, congressional hearings, EU Work Programme, UK Parliament, plus 17 seeded known upcoming events with confirmed dates. |
| 9 | **Compare** | Claude | Side-by-side structured comparison of any two of the 31 baselines — divergences, agreements, strictness, practical notes. |
| 10 | **Synthesis** | Claude | Cross-document regulatory landscape with conflict detection. Export to .docx. |
| 11 | **Gap analysis** | Claude | Company-profile compliance gaps anchored to specific document IDs, phased roadmap. Export to .docx. |
| 12 | **Document review** | None | Feedback marks documents Relevant / Partially Relevant / Not Relevant. Not-relevant moves to archive. |
| 13 | **Learning** | Claude (periodic) | Adapts keyword weights and source-quality scores from feedback. Domain-aware: AI and privacy sources scored separately. |
| 14 | **PDFs** | None | Auto-download PDFs from Federal Register, EUR-Lex, UK legislation; accept manually supplied PDFs. |
| 15 | **Notifications** | None | Email (SMTP) and Slack webhook digests on critical findings and scheduled run completion. |
| 16 | **Scheduled monitoring** | None | Background scheduler with configurable interval, domain, and lookback. Survives server restarts. |

---

## Browser Views

| View | What It Shows |
|------|---------------|
| **Dashboard** | Alert rail (critical changes, upcoming deadlines), regulatory pulse sparklines, **horizon widget** (upcoming deadlines with countdown), system health |
| **Documents** | Active document list with domain filter, review badges, Skipped indicator with reason |
| **Changes** | Keyword search, version diffs with severity badges, side-by-side requirement comparisons |
| **Baselines** | Domain tabs (AI Regulation / Data Privacy), jurisdiction filter, obligations and prohibitions |
| **Compare** | Side-by-side Claude analysis of any two of 31 baselines — divergences, agreements, strictness by topic |
| **Trends** | Jurisdiction velocity sparklines, impact-area heatmap, acceleration alerts |
| **Horizon** | 12-month forward calendar with domain filter — known upcoming deadlines, proposed rules, hearings |
| **Obligations** | Standalone obligation register across any jurisdiction set |
| **Ask ARIS** | RAG-powered Q&A across all documents and baselines |
| **Briefs** | One-page regulatory briefs per jurisdiction |
| **Synthesis** | Cross-jurisdiction narratives, conflict maps, .docx export |
| **Gap Analysis** | Company profiles, domain-scoped gap cards, roadmap, .docx export |
| **Enforcement** | FTC, SEC, CFPB, ICO enforcement actions |
| **Graph** | Document relationship network |
| **Concept Map** | Cross-jurisdiction concept analysis |
| **Timeline** | Chronological regulatory timeline |
| **Watchlist** | Keyword-based alerts with domain filter |
| **PDF Ingest** | Upload PDFs or trigger auto-download |
| **Run Agents** | Trigger fetch/summarise; first-run auto-detection; post-run summary card |
| **Learning** | Source quality profiles, keyword weights, prompt adaptations |
| **Settings** | API key status, jurisdiction toggles, scheduled monitoring, notification config |

---

## Coverage

### US States (18)

| State | Native Feed | Key Legislation |
|-------|-------------|-----------------|
| Pennsylvania | palegis.us ZIP (hourly) + LegiScan | Digital identity, AI deepfakes |
| California | CA Legislature API + LegiScan | SB 53, AB 2013, SB 942 (24+ AI laws enacted) |
| Colorado | leg.colorado.gov API + LegiScan | AI Act SB 24-205 (effective Jun 2026) |
| Illinois | ILGA RSS + LegiScan | AIPA enacted, BIPA, community college AI |
| Texas | TLO RSS (signed/enrolled) + LegiScan | TRAIGA enacted Jan 2026 |
| Washington | WSL web services + LegiScan | My Health MY Data Act, AI pipeline |
| New York | NY Senate API + LegiScan | RAISE Act pending, algorithmic pricing |
| Florida | FL Senate API + LegiScan | SB 262, government AI, deepfakes |
| Minnesota | MN Senate RSS + LegiScan | SF 2995 comprehensive AI reintroducing 2026 |
| Connecticut | LegiScan | SB 2 comprehensive AI reintroducing 2026 |
| Virginia | LegiScan | HB 2094 equivalent reintroducing 2026 |
| New Jersey | LegiScan | NJ Data Privacy Law, AI employment bills |
| Massachusetts | LegiScan | AI employment bills, Data Privacy Act |
| Oregon | LegiScan | Consumer Privacy Act in force, AI deepfakes |
| Maryland | LegiScan | Online Data Privacy Act, AI employment |
| Georgia | LegiScan | AI employment disclosure, government AI |
| Arizona | LegiScan | Chatbot regulation, deepfake disclosure |
| North Carolina | LegiScan | AI Employment Act, state government AI |

### International (10)

| Jurisdiction | Primary Source | Key Instruments |
|-------------|----------------|-----------------|
| European Union | EUR-Lex SPARQL + EU AI Office RSS | EU AI Act, GDPR, Data Act, DSA/DMA |
| United Kingdom | Parliament Bills API + legislation.gov.uk | UK GDPR/DPA, AI Framework, DPDI Act |
| Canada | OpenParliament + Canada Gazette + ISED | PIPEDA, CPPA (Bill C-27), AIDA |
| Singapore | PDPC RSS + IMDA RSS | Model AI Governance Framework, PDPA |
| India | PIB RSS (MEITY) | DPDP Act 2023, MEITY AI Advisory, IndiaAI Mission |
| Brazil | ANPD RSS + Senate RSS | LGPD, AI Bill PL 2338/2023 |
| Japan | METI English RSS | AI Business Guidelines (METI/MIC), APPI |
| South Korea | MSIT press releases | PIPA 2023 amendments, AI Promotion Act draft |
| Australia | Voluntary AI Safety Standard (pinned) | AI Safety Standard, Privacy Act review |
| China | Pinned documents | Generative AI Interim Measures, Algorithm Regulation |

### US Federal

Federal Register, Regulations.gov, Congress.gov — rules, proposed rules, notices, bills, committee hearings. Both AI and privacy keyword search tracks.

### Enforcement

FTC, SEC, CFPB, EEOC, DOJ press releases; ICO enforcement (UK); CourtListener federal courts (optional key).

---

## Dual-Domain Architecture

ARIS monitors two distinct regulatory domains with separate vocabularies, prompts, baselines, and scoring:

**AI Regulation** — risk classification, transparency, oversight, prohibited uses, conformity assessment.

**Data Privacy** — consent, individual rights, breach notification, legal bases, international transfers.

Every document, summary, change, and horizon item carries a `domain` field (`ai` | `privacy` | `both`). Every data view has a three-pill domain filter persisted independently per view in `localStorage`.

### Domain keyword scoring

AI documents use AI-vocabulary keyword matching (~150 terms). Privacy documents use `is_privacy_relevant()` against ~130 privacy terms. Feedback updates domain-keyed source profiles (`federal_register::privacy` separate from `federal_register`) so AI and privacy quality scores don't cross-contaminate.

---

## Baseline Coverage (31 — no API calls required)

### AI Regulation (19)

| Jurisdiction | Baseline |
|-------------|----------|
| EU | EU AI Act, EU GDPR (AI), EU DSA/DMA, EU AI Liability |
| Federal | EO 14110, NIST AI RMF, FTC AI Guidance, US Sector AI |
| GB | UK AI Framework + ICO |
| CA_STATE | California AI Laws |
| CO | Colorado AI Act |
| IL | Illinois AI Policy Act |
| NY | NYC Local Law 144 |
| CA | Canada AIDA |
| JP | Japan AI Guidelines |
| AU | Australia AI Framework |
| BR | Brazil AI + LGPD |
| SG | Singapore AI Framework |
| INTL | OECD / G7 AI Principles |

### Data Privacy (12)

| Jurisdiction | Baseline |
|-------------|----------|
| EU | GDPR (full), EU Data Act, ePrivacy |
| GB | UK GDPR / DPA 2018 |
| CA_STATE | CCPA / CPRA |
| Federal | US State Privacy (consolidated), US Federal Privacy |
| CA | PIPEDA / CPPA |
| BR | LGPD |
| JP | Japan APPI |
| AU | Australia Privacy Act |
| SG | Singapore PDPA |

---

## Regulatory Horizon

ARIS maintains a forward-looking calendar of regulations that are planned, proposed, or advancing but not yet in force. Four live sources (when network permits):

- **Unified Regulatory Agenda** — every planned US federal rulemaking with anticipated dates
- **Congress.gov hearings** — upcoming committee hearings on AI-relevant bills
- **EUR-Lex in-preparation** — EU legislative initiatives advancing through the Commission
- **UK Parliament whatson** — upcoming UK bill stage dates

Plus a **seeded dataset of 17 confirmed upcoming events** (updated March 2026) covering:

| Event | Jurisdiction | Date |
|-------|-------------|------|
| Colorado AI Act compliance effective | CO | Jun 30, 2026 |
| EU AI Act — GPAI obligations apply | EU | Aug 2, 2026 |
| California SB 942 (AI transparency) effective | CA | Aug 2, 2026 |
| EU Data Act fully applicable | EU | Sep 12, 2026 |
| FTC Commercial Surveillance NPRM | Federal | Jun 2026 (est.) |
| CFPB AI/Automated Underwriting guidance | Federal | Apr 2026 (est.) |
| HHS Algorithmic Healthcare Coverage rules | Federal | Jul 2026 (est.) |
| EEOC AI Employment Tools guidance | Federal | Sep 2026 (est.) |
| Brazil AI Bill (PL 2338) Senate vote | BR | Jun 2026 (est.) |
| India DPDP Rules finalised | IN | Jun 2026 (est.) |
| UK AI Bill parliamentary progress | GB | Jun 2026 (est.) |
| South Korea AI Promotion Act vote | KR | Sep 2026 (est.) |
| EU eIDAS 2.0 wallet deployment | EU | Nov 2026 |
| UK DPDI secondary legislation | GB | Oct 2026 (est.) |
| NIST AI RMF 2.0 | Federal | Dec 2026 (est.) |
| Singapore Model AI Framework v3 | SG | Dec 2026 (est.) |
| EU AI Act — High-Risk AI obligations | EU | Aug 2, 2027 |

The seeded items ensure the horizon view is always meaningful and testable regardless of external API availability. To update the seed, edit `SEEDED_HORIZON` in `sources/horizon_agent.py`.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
pip install pdfplumber pypdf   # optional, for PDF extraction

# 2. Configure API keys
cp config/keys.env.example config/keys.env
# Edit config/keys.env — at minimum set ANTHROPIC_API_KEY

# 3. Run database migration
python migrate.py

# 4. Build the UI (requires Node.js 18+)
cd ui && npm install && npm run build && cd ..

# 5. Start the server
python server.py
# Open http://localhost:8000

# 6. Run agents (first run — Force Summarize auto-enabled)
# Use the browser UI: Run Agents → Run All Sources
# Or from CLI:
python main.py run --domain both
```

---

## Common Commands

```bash
# ── Fetch & analyse ───────────────────────────────────────────────────────────
python main.py run                              # fetch all sources + summarise
python main.py run --domain both                # AI + privacy (default)
python main.py run --domain ai                  # AI regulation only
python main.py run --domain privacy             # data privacy only
python main.py fetch --source states            # states only
python main.py fetch --source federal           # federal only
python main.py fetch --days 90                  # longer lookback
python main.py summarize                        # summarise pending docs
python main.py summarize --force                # bypass pre-filter (clears Skipped)

# ── Baselines (no API calls) ──────────────────────────────────────────────────
python main.py baselines                        # list all 31 baselines
python main.py baselines --jurisdiction EU

# ── Compare / Synthesis ───────────────────────────────────────────────────────
# Via browser: Research → Compare or Research → Synthesis
# Export: click "Export .docx" button in result view

# ── Gap analysis ──────────────────────────────────────────────────────────────
python main.py gap-profiles
python main.py gap-analyse PROFILE_ID

# ── Reset (clear test data) ───────────────────────────────────────────────────
python reset_util/reset.py                      # interactive menu
python reset_util/reset.py --full --yes         # clear all except profiles/gaps

# ── System ────────────────────────────────────────────────────────────────────
python main.py status
python migrate.py                               # safe to re-run
```

---

## Folder Structure

```
ai-reg-tracker/
├── main.py                          ← CLI entry point
├── server.py                        ← FastAPI REST server (port 8000)
├── migrate.py                       ← Database migration (run after updates)
├── requirements.txt
│
├── config/
│   ├── keys.env                     ← Your API keys (never commit this)
│   ├── keys.env.example             ← Template with all options
│   ├── settings.py                  ← Global settings, ACTIVE_DOMAINS
│   └── jurisdictions.py             ← Toggle states and international on/off
│
├── data/baselines/                  ← 31 static JSON baseline files (no API)
│   ├── index.json
│   ├── [19 AI regulation baselines]
│   └── [12 data privacy baselines]
│
├── agents/
│   ├── baseline_agent.py            ← Load and query baselines (domain-aware)
│   ├── compare_agent.py             ← Side-by-side regulation comparison
│   ├── consolidation_agent.py       ← De-duplicated obligation register
│   ├── diff_agent.py                ← Baseline-aware version comparison
│   ├── gap_analysis_agent.py        ← Company-profile compliance gap analysis
│   ├── interpreter.py               ← Claude analysis + domain-aware pre-filter
│   ├── learning_agent.py            ← Adaptive scoring, domain-keyed profiles
│   ├── orchestrator.py              ← Concurrent fetch across all tracks
│   ├── scheduler.py                 ← Watch mode
│   ├── synthesis_agent.py           ← Cross-document synthesis
│   └── trend_agent.py               ← Velocity analytics (no API)
│
├── sources/
│   ├── enforcement_agent.py         ← FTC, SEC, CFPB, ICO, CourtListener
│   ├── federal_agent.py             ← Federal Register, Regulations.gov, Congress.gov
│   ├── horizon_agent.py             ← Horizon scanning + 17-item seed dataset
│   ├── pdf_agent.py                 ← PDF extraction and auto-download
│   ├── state_agent_base.py          ← LegiScan base class
│   ├── states/                      ← 18 state agents
│   │   ├── pennsylvania.py          ← palegis.us ZIP + LegiScan
│   │   ├── california.py            ← CA Legislature API + LegiScan
│   │   ├── colorado.py              ← leg.colorado.gov API + LegiScan
│   │   ├── illinois.py              ← ILGA RSS + LegiScan
│   │   ├── texas.py                 ← TLO RSS + LegiScan
│   │   ├── washington.py            ← WSL web services + LegiScan
│   │   ├── new_york.py              ← NY Senate API + LegiScan
│   │   ├── florida.py               ← FL Senate API + LegiScan
│   │   ├── minnesota.py             ← MN Senate RSS + LegiScan
│   │   └── [connecticut, virginia, new_jersey, massachusetts,
│   │        oregon, maryland, georgia, arizona, north_carolina]
│   └── international/               ← 10 international agents
│       ├── eu.py                    ← EUR-Lex SPARQL + EU AI Office RSS
│       ├── uk.py                    ← Parliament Bills API + legislation.gov.uk
│       ├── canada.py                ← OpenParliament + Canada Gazette + ISED
│       ├── singapore.py             ← PDPC RSS + IMDA RSS
│       ├── india.py                 ← PIB RSS (MEITY)
│       ├── brazil.py                ← ANPD RSS + Senate RSS
│       └── stubs.py                 ← Japan, China, Australia (pinned + METI RSS)
│
├── utils/
│   ├── db.py                        ← SQLite (17 tables + ScheduleConfig)
│   ├── cache.py                     ← HTTP cache, keyword scoring
│   ├── llm.py                       ← LLM abstraction
│   ├── notifier.py                  ← Email (SMTP) + Slack webhook
│   ├── rag.py                       ← RAG passage index (baselines + documents)
│   └── search.py                    ← Full-text search + privacy term taxonomy
│
├── scripts/
│   └── generate_docx.js             ← Node.js Word document generator
│
├── reset_util/
│   └── reset.py                     ← Interactive data reset tool
│
├── tests/                           ← 636 tests across 18 files
│
└── ui/src/views/                    ← 20 React views
    ├── Dashboard.jsx                ← Alert rail + pulse + horizon widget + health
    ├── Compare.jsx                  ← Jurisdiction comparison
    ├── ObligationRegister.jsx       ← Standalone obligation register
    ├── GapAnalysis.jsx              ← Gap analysis with .docx export
    ├── Synthesis.jsx                ← Synthesis with .docx export
    ├── Settings.jsx                 ← Schedule + notifications + API key config
    └── [15 other views]
```

---

## Database (17 tables)

| Table | Purpose |
|-------|---------|
| `documents` | Fetched documents. `domain` column (`ai`/`privacy`/`both`). |
| `summaries` | Claude summaries. `urgency='Skipped'` stubs for pre-filter rejections. |
| `document_diffs` | Version comparisons with severity. `domain` column. |
| `document_links` | Relationships between documents. |
| `pdf_metadata` | PDF extraction records. |
| `feedback_events` | Human relevance feedback. |
| `source_profiles` | Rolling quality scores per source — includes domain-keyed entries. |
| `keyword_weights` | Learned per-keyword weights. |
| `prompt_adaptations` | Claude-generated prompt notes for problem sources. |
| `fetch_history` | Fetch run log. |
| `thematic_syntheses` | Synthesis results. |
| `company_profiles` | Company profiles for gap analysis. |
| `gap_analyses` | Gap analysis results (history preserved). |
| `regulatory_horizon` | Horizon items — live + seeded. `domain` column. |
| `trend_snapshots` | Cached velocity / heatmap / alert data. |
| `obligation_register_cache` | Cached consolidation results. |
| `schedule_config` | Scheduled monitoring configuration. |

---

## Key Concepts

### Concurrent fetch

All source tracks (Federal, each State, each International, Horizon, Enforcement) run concurrently via `ThreadPoolExecutor(max_workers=8)`. A full run with all sources completes in ~2–3 minutes rather than ~12 minutes sequentially. Failed tracks log a warning and don't block others.

### First-run mode

On first run (no real summaries in DB yet), Force Summarize is enabled automatically so the initial batch processes fully without the pre-filter blocking documents from unlearned sources. The Run Agents view shows a yellow banner explaining this. Normal pre-filter behaviour resumes after the first batch.

### Pending vs Skipped documents

Documents that fail the relevance pre-filter receive a `Skipped` summary stub with the reason visible in Documents view. They remain eligible for reprocessing — Force Summarize or `--force` picks them up again. The pending queue uses a LEFT JOIN (not a subquery) for efficient performance at scale.

### Regulatory horizon — seeding

The horizon view is always populated with 17 real upcoming regulatory events (confirmed dates or strong signals as of March 2026), regardless of whether live API calls succeed. Update the `SEEDED_HORIZON` list in `sources/horizon_agent.py` as new events are confirmed.

### Export to Word

Gap analysis and synthesis results can be exported as formatted `.docx` files via the Export button in each result view, or via `GET /api/gap-analyses/{id}/export` and `GET /api/synthesis/{id}/export`. Requires Node.js and the `docx` npm package (`npm install -g docx`).

### Scheduled monitoring

Configure in Settings → Scheduled Monitoring. The schedule survives server restarts (stored in `schedule_config` DB table). After each scheduled run, notifications are sent to configured channels if critical findings are detected.

---

## Configuration (`config/keys.env`)

| Setting | Default | Description |
|---------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required for all AI features |
| `REGULATIONS_GOV_KEY` | — | Free — federal rulemaking dockets |
| `CONGRESS_GOV_KEY` | — | Free — US bills and hearings |
| `LEGISCAN_KEY` | — | Free — all 18 US state legislatures |
| `COURTLISTENER_KEY` | — | Optional — federal court opinions |
| `ACTIVE_DOMAINS` | `both` | `ai` / `privacy` / `both` |
| `LOOKBACK_DAYS` | `30` | Days back for document searches |
| `DB_PATH` | `./output/aris.db` | SQLite location |
| `NOTIFY_EMAIL` | — | Recipient for email notifications |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | — | SMTP sender address |
| `SMTP_PASSWORD` | — | SMTP app password |
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook URL |
| `NOTIFY_ON_CRITICAL` | `true` | Notify on critical-urgency findings |
| `NOTIFY_ON_HIGH` | `true` | Notify on high-urgency findings |
| `NOTIFY_ON_DIGEST` | `true` | Send digest after scheduled runs |

---

## After Updating Files

```bash
python migrate.py          # adds any new tables/columns safely
cd ui && npm run build     # only if UI files changed
python server.py           # restart the server
```

`migrate.py` is safe to run multiple times — skips anything already present.

---

## Running Tests

```bash
python -m pytest tests/ -v
# or:
python -m unittest discover tests -v
```

**636 tests across 18 test files.** All run without live API calls.

---

## Design Principles

**Baselines are the starting point, documents are updates.** ARIS knows what the EU AI Act requires and what GDPR demands before any implementing act arrives. Every analysis is grounded in settled law.

**Two domains, one system.** AI regulation and data privacy share infrastructure but have separate vocabularies, scoring functions, and LLM prompts. A GDPR breach notification article won't be silently dropped by an AI-keyword filter.

**Everything runs locally.** Database, cache, PDFs, learning state, all 31 baselines, velocity analytics, and the horizon calendar live on your machine. The only external calls are to government APIs and Anthropic.

**Zero-cost features first.** Browse 31 baselines, view the obligation register, check regulatory velocity, and see the horizon calendar without spending a single API token. Claude calls are gated behind relevance scoring.

**Transparency over silence.** Pre-filter rejections are recorded as `Skipped` with the reason visible in the UI. API key status in Settings shows exactly which features each missing key disables. Horizon items are always present — the seeded dataset ensures the view is never empty.

**Concurrent by default.** All fetch tracks run in parallel. Failed individual tracks don't block others. A full run with all 28 source tracks completes in ~2–3 minutes.

**Full history preserved.** Every diff, gap analysis, synthesis, feedback event, and trend snapshot is stored as a new record. Nothing is overwritten.

**Graceful degradation.** Every agent wraps its calls in try/except. A failed state source doesn't block the federal fetch. A failed horizon API doesn't empty the horizon view — the seed dataset covers it.
