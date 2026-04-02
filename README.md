# ARIS — Automated Regulatory Intelligence System

**Monitor. Baseline. Compare. Interpret. Consolidate. Trend. Horizon. Enforce. Learn. Act.**

ARIS is a fully local, agentic system that monitors **AI regulation and data privacy law** across all 50 US states, 9 international jurisdictions, and US Federal agencies. It ships with 32 curated baseline regulations, fetches live documents from official government APIs and enforcement feeds, uses Claude to interpret and analyse them, detects changes, tracks regulatory velocity, scans the regulatory horizon for upcoming regulations, consolidates obligations, compares jurisdictions side by side, performs company-specific compliance gap analysis — and learns from your feedback to improve over time. Everything runs in a browser dashboard or from the command line.

Everything runs on your machine. No SaaS subscription, no data leaving your environment, no per-query costs beyond your own API key.

---

## License

ARIS is licensed under the **Elastic License 2.0 (ELv2)**. You may use, copy, and modify it for personal, educational, and non-commercial purposes. You may not sell it, offer it as a commercial product or service, or use it as the basis of a paid product without express written permission. See [LICENSE](LICENSE) for full terms.

Copyright © 2026 Mitch Kwiatkowski

**Disclaimer:** ARIS is an informational research tool only. Nothing it produces constitutes legal, compliance, or regulatory advice. Always consult qualified legal counsel before making compliance decisions.

---

## What It Does

| # | Feature | API Calls | Description |
|---|---------|-----------|-------------|
| 1 | **Baselines** | None | 32 curated baselines covering settled AI regulation and data privacy law. Always available offline. |
| 2 | **Fetch** | None | Concurrent fetch from all 50 US states, 9 international jurisdictions, and 5 US Federal sources. |
| 3 | **Filter** | None | Domain-aware keyword pre-screening (150+ terms) with false-positive protection. Skipped docs recorded with reason. |
| 4 | **Interpret** | Claude | Plain-English summaries, urgency ratings, requirements, action items, deadlines. Domain-specific prompts. |
| 5 | **Change detection** | Claude | Baseline-aware diffs — compares new documents against settled law, not just prior versions. |
| 6 | **Consolidation** | Optional | De-duplicated obligation register from all 32 baselines. Fast mode: zero API calls. Full mode: one Claude call. |
| 7 | **Trends & velocity** | None | Jurisdiction velocity chart (rolling 12-month window), impact-area heatmap, acceleration alerts. |
| 8 | **Horizon scanning** | None | Unified Regulatory Agenda, congressional hearings, EU Work Programme, UK Parliament, plus seeded upcoming events. |
| 9 | **Compare** | Claude | Side-by-side structured comparison of any two of the 32 baselines. |
| 10 | **Synthesis** | Claude | Cross-document regulatory landscape with conflict detection. Export to .docx. |
| 11 | **Gap analysis** | Claude | Company-profile compliance gaps, phased roadmap. Export to .docx. |
| 12 | **Enforcement** | None | 10 live sources: FTC, SEC, CFPB, EEOC, DOJ, ICO (UK), CourtListener, Google News, Regulatory Oversight, Courthouse News. Story grouping deduplicates coverage. |
| 13 | **Document review** | None | Feedback marks documents Relevant / Partially Relevant / Not Relevant. |
| 14 | **Autonomous learning** | Claude (periodic) | Every processed document feeds the relevance model. False-positive sources are down-weighted automatically. Documents Claude scores ≤ 0.15 auto-archive. |
| 15 | **PDFs** | None | Auto-download PDFs from Federal Register, EUR-Lex, UK legislation; accept manual uploads. |
| 16 | **Notifications** | None | Email (SMTP) and Slack webhook digests on critical findings and scheduled runs. |
| 17 | **Scheduled monitoring** | None | Two-track background scheduler: jurisdiction monitoring on specific days/times, enforcement monitoring every N hours. Both survive server restarts. |
| 18 | **Knowledge graph** | None | Interactive force-directed graph of relationships between baselines and documents: cross-references, genealogical links, semantic connections, conflict edges. |
| 19 | **Q&A (Ask ARIS)** | Claude | RAG-powered question answering across all documents and baselines with source citations. |

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
```

The server binds to `127.0.0.1` (localhost only) by default. Set `ARIS_HOST=0.0.0.0` in `config/keys.env` only if you need LAN access — ARIS has no authentication layer.

---

## Browser Views

Navigate using the left sidebar. The sidebar is organized into four sections: Monitor, Research, Analysis, and System.

### Dashboard (`/`)

The main overview page. Shows at a glance:

- **Alert rail** — critical-urgency documents, unreviewed High/Critical changes, upcoming horizon deadlines within 30 days, pending-summarization count with a "Run →" action link
- **Regulatory Pulse** — sparkline velocity chart showing document activity per jurisdiction over the past 30 days, with acceleration alert chips for fast-moving areas
- **Top impact areas** — ranked by document count (Product Development, Data Privacy, Healthcare AI, Regulatory Compliance, AI Governance)
- **Coverage tiles** — active jurisdiction count and horizon item count, split by AI Reg and Privacy domains
- **Next Deadlines** — upcoming horizon events sorted by days remaining
- **Recent Enforcement** — latest enforcement actions with source badges
- **Regulatory Horizon** — urgency bucket cards (Within 30d / 30–180d / 180d+ / TBD) with a full list below

> Navigate to the Dashboard via the sidebar or by going to `http://localhost:8000/`. Note: the URL `/dashboard` is not a registered route — always navigate from the sidebar or via `/`.

<img width="2854" height="1650" alt="image" src="https://github.com/user-attachments/assets/373bc79b-77ab-400f-a3d3-cb408cf689fa" />

### Documents (`/documents`)

Paginated list of all fetched documents with filtering, sorting, and a slide-out detail panel.

**Layout and density:**
- **Table view (default)** — compact 40px rows showing 15–20 documents per screen. Columns: urgency indicator, title + agency, published date, fetched date, jurisdiction, doc type, urgency badge.
- **Grid view** — card layout showing two to three lines of the plain-English summary per document. Toggle between views using the List/Grid buttons in the header.

**Filtering:**
- **Search** — full-text search across titles and plain-English summaries
- **Jurisdiction** — filter to a single jurisdiction (50 US states + Federal + 9 international)
- **Urgency** — Critical / High / Medium / Low / Skipped
- **Doc type** — Bill / Regulation / Rule / Legislation / Publication/Guidance / etc.
- **Date range** — 14 days / 30 days / 90 days / 6 months / 1 year / All time
- All filters are independent and combinable. Active filters appear as dismissable chips below the filter row showing the active combination and result count. Click **Clear all** to reset.

**Sorting:** Click any column header in table view to sort by that column. Clicking again toggles ascending/descending. Available sort columns: Published date, Fetched date, Jurisdiction, Urgency.

**Date columns:** Published date and Fetched date are distinct columns. Documents with no official publication date (e.g. RSS-sourced items) show `—` in the Published column. This makes it clear which documents have been officially published vs. only fetched.

**Pending documents:** If documents are awaiting summarization, an orange badge in the header shows the count. Click **Process N pending** to go directly to Run Agents for that task.

**Pagination:** Numbered page buttons with first/last ellipsis, a **Go to** input for jumping directly to any page, and a **Per page** selector (50 / 100 / 200).

**Document status indicators:**
- Coloured dot (left edge of row) — urgency level: red = Critical, orange = High, yellow = Medium, grey = Low, dim grey = Pending/Skipped
- **PENDING** badge — document fetched but not yet summarized
- **SKIPPED** badge — document failed the relevance pre-filter; click to see the exact reason
- ✓ green checkmark — you marked this document Relevant
- ◐ yellow icon — you marked this document Partially Relevant

**Detail panel:** Click any row to open a slide-out panel on the right showing full metadata (both dates, type, agency, status, deadline), the plain-English summary, impact areas, mandatory requirements, recommendations, action items, change history, and feedback buttons. From the detail panel you can also generate a **Compliance Checklist** or run a **Compare** diff against another document by ID.

**Tabs:** Switch between **Active** (all non-archived documents) and **Archived** (documents you marked Not Relevant — retained for reference but removed from the review queue).

**Export:** Click **Export** in the header to download all active documents as JSON.

<img width="2830" height="1628" alt="image" src="https://github.com/user-attachments/assets/9bc8aa32-7cab-4b3d-9b9e-2eea5d415428" />

### Changes (`/changes`)

All detected regulatory changes — version updates, addenda, and amendments — compared against the 32 baselines.

**Filters:** Search (keyword across change summaries), date window (7 / 14 / 30 / 90 days), severity (Critical / High / Medium / Low), change type (Version Updates / Addenda), and an **Unreviewed only** toggle. Domain filter (All / AI Regulation / Data Privacy) is in the header.

**Keyboard triage** — move through changes without touching the mouse:

| Key | Action |
|-----|--------|
| `J` / `↓` | Move to next change |
| `K` / `↑` | Move to previous change |
| `Space` or `Enter` | Mark focused change as reviewed and advance |
| `E` | Expand / collapse the focused card |
| `U` | Toggle Unreviewed only filter |
| `R` | Reload the list |

The focused card is highlighted with an accent ring and auto-scrolls into view. Keyboard shortcuts only fire when focus is not inside a text input.

**Mark all reviewed:** When unreviewed items exist, a **Mark all reviewed** button appears in the header to bulk-clear the entire visible list.

**Change cards** show severity badge, change type, document title, base document ID → new document ID, date detected, and a plain-English change summary. Expand a card to read the full assessment.

### Trends (`/trends`)

Regulatory velocity data for the past 12 months.

- **Jurisdiction velocity chart** — rolling 12-month sparklines per jurisdiction, colour-coded by activity level. Shows document count and trend direction (↑ accelerating / → stable / ↓ slowing).
- **Acceleration alerts** — jurisdictions or impact areas with significant recent acceleration
- **Top impact areas** — ranked by total document count with per-area counts
- Domain filter applies to all charts.

<img width="2572" height="1632" alt="image" src="https://github.com/user-attachments/assets/7ee45161-c907-41fc-ac2a-a2e231e0d3c0" />

### Horizon (`/horizon`)

Forward-looking regulatory calendar.

- Items are categorised: Within 30 days / 30–180 days / 180+ days / TBD
- Sources: Unified Regulatory Agenda (federal rules), Congress.gov hearings, EU Work Programme, UK Parliament Bills, plus 17 seeded upcoming events
- Filters: domain (AI Reg / Privacy) and time window
- Each item shows: title, jurisdiction, anticipated date, countdown in days, and type (Deadline / Proposed Rule / Hearing / Effective Date)

<img width="2362" height="1606" alt="image" src="https://github.com/user-attachments/assets/7535ca6a-6a47-4c3f-b674-69356415b450" />

### Enforcement (`/enforcement`)

Enforcement actions and litigation from 10 sources.

**Sources panel (left):** Each source listed with its item count. Click a source to filter. Setup notes appear for any source requiring additional API keys.

**Story grouping:** Multiple articles covering the same case are collapsed into one card with a "N more articles about this story" toggle. This prevents the same verdict or enforcement action from appearing dozens of times.

**Item types:** Enforcement actions, litigation filings, news stories. Filtered by All / AI Regulation / Data Privacy in the header. Click **Fetch Latest** to trigger an immediate enforcement fetch.

**Domain filter:** Toggle between All / AI Regulation / Data Privacy using the pills in the top-right.

<img width="2848" height="1620" alt="image" src="https://github.com/user-attachments/assets/fa557c1e-fb17-4b24-9d75-3615ec2ad112" />
Note that non-AI and non-data stories in the image above were part of a bug in the enforcement agent code that has since been fixed.

### Baselines (`/baselines`)

32 pre-loaded baseline regulations. Always available offline, no API calls required.

- **Domain tabs** — AI Regulation (19 baselines) / Data Privacy (13 baselines)
- **Jurisdiction filter** — filter to a specific jurisdiction
- Each baseline shows: jurisdiction, status, overview text, key obligations, key prohibitions, and relevant documents fetched against it
- Baselines are the anchor for all change detection — ARIS compares new documents against these settled laws

### Compare (`/compare`)

Side-by-side Claude comparison of any two of the 32 baselines.

Select two baselines from the dropdowns and click **Compare**. Claude produces a structured analysis covering: scope differences, key similarities, key conflicts, compliance implications, and overall assessment.

### Concept Map (`/concepts`)

Cross-jurisdiction concept analysis. Shows how the same regulatory concepts (consent, risk classification, transparency requirements, etc.) are defined differently across jurisdictions.

<img width="2832" height="1578" alt="image" src="https://github.com/user-attachments/assets/0fa257b9-9593-4d2f-beb4-7c0c98903566" />

### Graph (`/graph`)

Interactive knowledge graph of regulatory relationships.

**Layout presets:**
- **Organic** (default) — force-directed with natural clustering
- **Concentric** — ranked by connection count; the most-connected nodes (e.g. EU AI Act with 43 connections) sit at the centre
- **Hierarchy** — tree-like top-down structure
- **Circle** — even radial arrangement
- **Grid** — uniform grid layout

**Interaction:**
- Scroll to zoom, drag to pan
- Click a node to highlight its neighbourhood — all non-connected nodes dim
- Hover a node for a tooltip showing type, jurisdiction, urgency, degree (connection count), and status
- Hover an edge to see the relationship type, concept, evidence text, and strength bar
- Use the **Search** box to find nodes by name or jurisdiction — matching nodes highlight and the viewport flies to them
- Click the **Legend** items (bottom-left) to toggle specific edge types on/off
- **Jurisdiction colour key** (top-right) shows the colour assigned to each active jurisdiction

**Edge types:** Cross-reference (blue), Genealogical (green), Shared Concept (amber), Implements (green), Conflict (red dashed)

**Node types:** Baselines rendered as circles; documents as rounded rectangles. Hub nodes (15+ connections) are larger with bold labels.

Click **Rebuild** to re-detect all relationships across baselines and documents. The build is synchronous — the graph reloads automatically when complete.

<img width="2832" height="1634" alt="image" src="https://github.com/user-attachments/assets/8292021a-830f-4d61-bf84-6fdad6765bf9" />

### Timeline (`/timeline`)

Chronological regulatory timeline. Documents plotted by published/effective date, filterable by domain and jurisdiction.

### Ask ARIS (`/ask`)

RAG-powered question answering across all 32 baselines and all summarized documents.

Type any compliance question. ARIS retrieves the most relevant passages using TF-IDF similarity, then passes them to Claude as context. Responses include citations showing which document each claim came from.

**Index status:** The index must be built before Ask ARIS can answer questions. Go to **Run Agents** and run at least one summarization pass. The index rebuilds automatically after each summarization run.

**Example questions:**
- "What are the consent requirements under GDPR compared to CCPA?"
- "Which jurisdictions require algorithmic impact assessments?"
- "What are the deadlines for EU AI Act compliance for high-risk AI?"
- "What enforcement actions has the FTC taken against AI companies?"

<img width="2840" height="1628" alt="image" src="https://github.com/user-attachments/assets/b05fd4e3-b334-4aac-a271-98d158d25f7e" />

### Briefs (`/briefs`)

One-page regulatory briefs per jurisdiction, generated by Claude. Covers: current status, key requirements, recent changes, and upcoming deadlines. Domain-filterable.

### Obligations (`/register`)

De-duplicated obligation register consolidated across all 32 baselines.

- **Fast mode** — keyword consolidation, zero API calls, instant results
- **Full mode** — Claude semantic consolidation, eliminates near-duplicate obligations across jurisdictions

Filter by jurisdiction, domain, or obligation category. Export the full register.

### Synthesis (`/synthesis`)

Cross-jurisdiction narrative synthesis with conflict detection.

Select a topic and jurisdictions. Claude identifies: common themes, jurisdictional conflicts (where laws directly contradict), compliance gaps, and emerging trends. Export to `.docx`.

<img width="2842" height="1644" alt="image" src="https://github.com/user-attachments/assets/3139d5c9-2dd0-4c7e-8287-285d35fe0c1c" />

### Gap Analysis (`/gap`)

Company-specific compliance gap analysis.

1. Create a **Company Profile** (industry, size, AI use cases, data types handled, current maturity level)
2. Select a domain (AI Regulation / Data Privacy / Both)
3. Click **Run Analysis**

Claude analyses each baseline against your profile and produces: a posture score per jurisdiction, specific gap cards for each unmet requirement, a phased compliance roadmap, and priority action items. Export to `.docx`.

<img width="2844" height="1616" alt="image" src="https://github.com/user-attachments/assets/bd39aac1-29c2-4e0a-a68c-4592eb7b2abd" />

### Watchlist (`/watchlist`)

Keyword-based document alerts. Add keywords and ARIS surfaces any fetched document containing them. Domain-filterable.

### PDF Ingest (`/pdf`)

Two modes:
- **Manual upload** — drag and drop a PDF onto the upload zone
- **Auto-download** — ARIS automatically downloads PDFs linked from Federal Register, EUR-Lex, and UK legislation documents as part of normal fetch runs

PDFs are extracted, added to the document database, and processed through the standard summarization pipeline.

### Run Agents (`/run`)

Trigger fetch and summarization runs from the browser.

**Pending documents banner:** If documents are awaiting summarization, a green banner shows the count with a **Process pending** button. This runs summarization only (no fetch), processing the existing pending queue without pulling new documents.

**Source grid:** A compact regional grid of all 50 US states. Click individual states or regional groups (Northeast, Southeast, etc.) to select them. Sources are also grouped by: Federal, International (9 jurisdictions), and Enforcement.

**Options:**
- **Lookback window** — how many days back to search (1–730 days)
- **Domain** — All / AI Regulation / Data Privacy
- **Run AI summarization** — enable/disable Claude summarization in this run
- **Max documents to summarize** — cap the batch size (1–500)
- **Force Summarize** — bypass the relevance pre-filter; re-processes previously Skipped documents

**First-run detection:** On first use (no summaries yet), Force Summarize is enabled automatically to ensure the initial batch processes fully.

**Live log:** A terminal-style log streams progress in real time: source track results, fetch counts, summarization progress, and completion summary.

**Result card:** After each run, a summary card shows: documents fetched, documents summarized, pending count, and a breakdown of urgency levels in the new batch.

<img width="2588" height="1620" alt="image" src="https://github.com/user-attachments/assets/3c9a25d8-21e7-4553-a2fb-2ccd083ba3c6" />

### Learning (`/learning`)

Visibility into ARIS's autonomous relevance model.

- **Source quality scores** — per-source relevance rate (0.0–1.0). Sources with consistently high scores are trusted; low scores are down-weighted.
- **Keyword weights** — terms that have been up-weighted or down-weighted based on feedback patterns
- **False positive patterns** — document patterns that consistently produce irrelevant results and are now filtered
- **Feedback summary** — totals for Relevant, Partially Relevant, Not Relevant, and auto-archived decisions
- **Prompt adaptations** — count of times Claude's summarization prompt has been adjusted based on feedback

The learning model updates continuously. Every document you mark Not Relevant adds signal. Every Skipped document (pre-filter rejection) also feeds the model automatically.

<img width="2388" height="1550" alt="image" src="https://github.com/user-attachments/assets/caa2c2a5-7fb2-42e2-9a03-21af09d6867e" />

### Settings (`/settings`)

**API Keys** — status indicators for all configured keys (Anthropic, Regulations.gov, Congress.gov, LegiScan, CourtListener). Shows as green/red dots. Keys are set in `config/keys.env`, not through this form.

**Jurisdiction toggles** — enable or disable specific US states and international jurisdictions. Disabled jurisdictions are skipped during fetch runs. Changes take effect on the next run.

**Scheduled monitoring (two tracks):**

*Jurisdiction track* — runs state, federal, and international sources on specific days at a configured time:
- Enable/disable toggle
- Day-of-week selector (Mon–Sun toggle buttons)
- Run time picker (displays and accepts local time — stored as UTC internally)
- Domain filter and lookback window
- Shows last run time and next scheduled run

*Enforcement track* — checks enforcement feeds on a recurring interval:
- Enable/disable toggle
- Interval dropdown (1 / 2 / 4 / 6 / 8 / 12 / 24 hours)
- Lookback window
- Shows last run time and next scheduled run

Both tracks run independently. Jurisdiction monitoring is typically set to run on weekdays; enforcement monitoring runs more frequently throughout the day.

**Notifications:**
- **Email** — set `NOTIFY_EMAIL` in `config/keys.env` and configure SMTP settings
- **Slack** — set `SLACK_WEBHOOK_URL` in `config/keys.env`

A digest is sent after each scheduled run that finds new critical or high-severity items.

<img width="2842" height="1612" alt="image" src="https://github.com/user-attachments/assets/0b8c433e-82e0-4f04-9cb9-7a41d79097ee" />

**CLI Quick Reference** — copy-paste ready command examples displayed at the bottom of the page.

---

## Scheduled Monitoring

The two-track scheduler runs in a background thread and survives server restarts.

**Jurisdiction track** fires on the configured days of the week at the configured time. It runs the standard fetch pipeline (state + international + federal sources) with the configured domain and lookback settings.

**Enforcement track** fires every N hours. It fetches from enforcement sources only (FTC, SEC, CFPB, EEOC, DOJ, ICO, CourtListener, Google News, Regulatory Oversight, Courthouse News). Enforcement items do not go through Claude summarization.

**On server restart:** If either track's next scheduled run is in the past (e.g. server was offline when it was due), the scheduler automatically recalculates and sets a fresh next-run time rather than firing immediately.

**Time zone:** All scheduled times are stored internally as UTC. The Settings UI converts to and from your browser's local time automatically — enter times in your local timezone and they will display correctly.

---

## Coverage

### US States (50)

All 50 states monitored via LegiScan API. Ten states also have native legislative feeds:

| Tier | States | Source |
|------|--------|--------|
| **Native + LegiScan** | PA, CA, CO, IL, TX, WA, NY, FL, MN, CT | State-specific XML/API feeds + LegiScan |
| **Active pipeline** | VA, NJ, MA, OR, MD, GA, AZ, NC, MI, OH, NV, UT, IN, TN, KY, SC, WI, MO | LegiScan |
| **Emerging activity** | LA, AL, MS, AR, IA, KS, NE, NM, OK, WV, ID, MT, ND, SD, WY, AK, HI, ME, NH, VT, RI, DE | LegiScan |

> **LegiScan quota:** The free tier allows ~30 API calls/day. Fetching all 50 states uses 50+ calls. Run states in regional batches using the Run Agents grid, or use `python diagnose_legiscan.py` to check quota status before a full run.

### International (9)

| Jurisdiction | Primary Source | Key Instruments |
|-------------|----------------|-----------------|
| European Union | EUR-Lex SPARQL + EU AI Office RSS | EU AI Act, GDPR, Data Act, DSA/DMA |
| United Kingdom | Parliament Bills API + legislation.gov.uk | UK GDPR/DPA 2018, AI Framework |
| Canada | OpenParliament + Canada Gazette + ISED | PIPEDA, CPPA (Bill C-27), AIDA |
| Singapore | PDPC RSS + IMDA RSS | Model AI Governance Framework, PDPA |
| India | PIB RSS (MEITY) | DPDP Act 2023, IndiaAI Mission |
| Brazil | ANPD RSS + Senate RSS | LGPD, AI Bill PL 2338/2023 |
| Japan | METI RSS + Google News fallback | AI Promotion Act (May 2025), AI Guidelines v1.1 |
| South Korea | MSIT press releases | PIPA 2023 amendments, AI Promotion Act |
| Australia | Federal Register API + pinned docs | AI Safety Standard, Privacy Act review |

### US Federal Sources (5)

| Source | Coverage |
|--------|----------|
| Federal Register | Proposed rules, final rules, notices |
| Regulations.gov | Public comment dockets |
| Congress.gov | Bills, hearings, committee activity |
| EU AI Office RSS | EU-level AI governance publications |
| EUR-Lex (pinned) | Core EU legislation |

### Enforcement Sources (10)

| Source | Coverage |
|--------|----------|
| FTC | Press releases — algorithmic bias, AI fraud, dark patterns |
| SEC | EDGAR search — AI fraud, algorithmic manipulation |
| CFPB | Newsroom — automated underwriting, credit scoring |
| EEOC | Newsroom — employment AI discrimination |
| DOJ | Press releases — civil rights AI discrimination |
| ICO (UK) | Media centre — GDPR / data protection enforcement |
| CourtListener | Federal court opinions and dockets (PACER/RECAP) |
| Google News | 7 targeted queries: AI lawsuits, data privacy fines, state AG enforcement, social media verdicts |
| Regulatory Oversight | Troutman Pepper enforcement blog — state AG and FTC actions |
| Courthouse News | State and federal court filings the day they are filed |

---

## Dual-Domain Architecture

ARIS monitors two distinct regulatory domains with separate vocabularies, prompts, baselines, and scoring:

- **AI Regulation** — risk classification, transparency, oversight, prohibited uses, conformity assessment
- **Data Privacy** — consent, individual rights, breach notification, legal bases, international transfers

Every document, summary, change, and horizon item carries a `domain` field (`ai` | `privacy` | `both`). Every view has a three-pill domain filter (All / AI Regulation / Data Privacy) persisted independently per view.

### Relevance Filtering (150+ Terms)

Documents pass through a three-gate pre-filter before consuming any API tokens:

1. **Strong-signal fast path** — unambiguous AI terms ("artificial intelligence", "automated decision", "deepfake") pass immediately
2. **Known false-positive guard** — blocks NAIC, MAID, PAID leave, BRAIN Initiative unless 2+ additional AI terms are present
3. **Scored match** — 150+ term taxonomy; ambiguous terms only count when backed by at least one unambiguous AI term

Pre-filter validation runs against the **bill title only** — not `title + search_keyword` — preventing LegiScan result contamination.

Documents that fail the pre-filter are stored as **Skipped** with the exact reason visible in the Documents view. They feed the autonomous learning model and can be re-processed using Force Summarize.

---

## Autonomous Learning

ARIS improves its own relevance filtering continuously:

- **Every document you mark Not Relevant** adds a signal that down-weights similar documents from the same source
- **Every Skipped document** automatically calls `record_auto_feedback()` with its relevance score as signal
- **Auto-archive** — documents Claude rates ≤ 0.15 automatically move to Archive, stamped `user="aris_auto"`
- **Domain-keyed profiles** — AI and privacy sources accrue quality scores independently
- **False positive patterns** — 47 detected patterns currently identified and filtered
- **Summarization guard** — Skipped documents are excluded from re-summarization on normal runs; Force Summarize re-includes them for one pass

View the current state of the learning model at `/learning`.

---

## Knowledge Graph

The graph view (`/graph`) visualises relationships between the 32 baselines and fetched documents. Click **Rebuild** to re-detect all relationships — this runs synchronously and the graph reloads automatically when complete.

**Relationship types detected:**
- **Cross-reference** — one document explicitly references another
- **Genealogical** — parent/child relationships (e.g. implementing regulation → parent act)
- **Semantic** — shared concept or thematic overlap
- **Implements** — a document implements provisions of a baseline
- **Conflict** — directly contradicting requirements between jurisdictions (shown as red dashed lines)

**Hub nodes** (documents with 15+ connections, such as the EU AI Act with 43 connections) render larger with bold labels and act as visual anchors in any layout.

---

## Regulatory Horizon

Key upcoming dates (as of April 2026):

| Event | Date |
|-------|------|
| UK AI Regulation Bill — Parliamentary Progress | ~60 days |
| Brazil AI Bill (PL 2338/2023) — Full Senate Vote | ~60 days |
| FTC Commercial Surveillance and Data Security Rulemaking | ~60 days |
| Colorado AI Act enforcement effective | Jun 30, 2026 |
| EU AI Act — GPAI obligations apply | Aug 2, 2026 |
| California SB 942 (AI transparency) effective | Aug 2, 2026 |
| EU Data Act fully applicable | Sep 12, 2026 |
| EU AI Act — High-Risk AI obligations | Aug 2, 2027 |

---

## Common Commands

```bash
python main.py run                    # full pipeline (fetch + summarise)
python main.py run --domain ai        # AI regulation only
python main.py run --domain privacy   # data privacy only
python main.py fetch --days 90        # longer lookback
python main.py summarize --force      # bypass pre-filter

python reset.py                       # interactive data reset
python reset.py --documents --learning --yes   # clear docs + learning state
python migrate.py                     # safe to re-run after updates

python diagnose_legiscan.py           # diagnose LegiScan quota and session issues
python diagnose_legiscan.py MI OH NV  # test specific states only
```

---

## After Updating Files

```bash
python migrate.py          # adds new tables/columns — safe to re-run
cd ui && npm install       # only needed if package.json changed (new npm dependency)
cd ui && npm run build     # only if UI source files (.jsx) changed
python server.py           # restart
```

---

## Configuration (`config/keys.env`)

| Setting | Default | Description |
|---------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | `anthropic` / `openai` / `ollama` / `gemini` |
| `ANTHROPIC_API_KEY` | — | Required for all AI features |
| `REGULATIONS_GOV_KEY` | — | Free — federal rulemaking dockets |
| `CONGRESS_GOV_KEY` | — | Free — US bills and hearings |
| `LEGISCAN_KEY` | — | Free — all 50 US state legislatures (~30 calls/day free tier) |
| `COURTLISTENER_KEY` | — | Optional free token — higher rate limits for court data |
| `ACTIVE_DOMAINS` | `both` | `ai` / `privacy` / `both` |
| `LOOKBACK_DAYS` | `30` | Days back for document searches |
| `ARIS_HOST` | `127.0.0.1` | Set to `0.0.0.0` for LAN access (no auth — use caution) |
| `NOTIFY_EMAIL` | — | Recipient for email notifications |
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook URL |

---

## LegiScan Quota Management

The free LegiScan tier allows approximately 30 API calls per day. ARIS uses `getMasterList` (1 call per state), so fetching all 50 states in one run requires 50 calls — above the free limit.

**Strategies to stay within quota:**
- Use the Run Agents regional state grid to fetch one region per day (~10–15 states)
- Increase the lookback window (e.g. 90 days) so each run captures more history per call
- Run `python diagnose_legiscan.py` to confirm quota status before a large run
- Upgrade to LegiScan paid plan ($9/month) for unrestricted calls

When quota is exhausted, ARIS logs `LEGISCAN API ERROR` in the Run Agents log window, sets a session-level quota guard to stop burning further calls, and continues processing any non-LegiScan sources normally.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

288+ tests across multiple test files. All run without live API calls.

---

## Repository Files

| File | Purpose |
|------|---------| 
| `server.py` | FastAPI REST server — 80+ endpoints |
| `main.py` | CLI entry point |
| `migrate.py` | Database migrations — safe to re-run |
| `reset.py` | Interactive data reset tool |
| `diagnose_legiscan.py` | Standalone LegiScan diagnostic |
| `config/keys.env` | API keys and settings (not committed) |
| `config/keys.env.example` | Template for keys.env |
| `LICENSE` | Elastic License 2.0 — non-commercial use |
| `CHANGELOG.md` | Version history |
| `CONTRIBUTING.md` | How to add state agents, run tests, submit PRs |
| `SECURITY.md` | Network exposure, key storage, vulnerability reporting |
| `pyproject.toml` | Python 3.11+ requirement, pytest config |
| `.gitignore` | Excludes keys.env, database, caches, build artifacts |

---

## Windows Setup Notes

ARIS is developed on Unix/macOS but runs on Windows. Two issues are known on Windows:

**SyntaxError: Non-UTF-8 code** — Python on Windows defaults to ASCII encoding. All ARIS Python files include `# -*- coding: utf-8 -*-` as line 1. If you receive this error, run:

```python
import pathlib
DECL = b'# -*- coding: utf-8 -*-\n'
for p in pathlib.Path('.').rglob('*.py'):
    if 'node_modules' in str(p) or '__pycache__' in str(p):
        continue
    raw = p.read_bytes()
    if b'coding: utf-8' not in raw[:50]:
        p.write_bytes(DECL + raw)
        print(f'fixed: {p}')
```

**npm run build fails with "stream did not contain valid UTF-8"** — extend the fix above to target `.js` and `.jsx` files, or save the affected file as UTF-8 in your editor.

---

## Design Principles

**Baselines are the starting point.** ARIS knows what each law requires before fetching a single new document. Every analysis is anchored to settled law.

**Signal quality over coverage.** A compliance tool that surfaces noise erodes trust faster than it builds it. The pre-filter, false-positive blocklist, and autonomous learning loop all serve this goal.

**Everything runs locally.** Database, cache, PDFs, learning state, all 32 baselines, and the horizon calendar live on your machine.

**Zero-cost features first.** Browse baselines, view the obligation register, check velocity, and see the horizon calendar without spending a single API token.

**Transparency over silence.** Pre-filter rejections are recorded as `Skipped` with the reason visible in the UI. Auto-archived documents are stamped `user="aris_auto"`. LegiScan quota errors surface in the run log rather than failing silently.

**Graceful degradation.** Failed source tracks don't block others. The seeded horizon dataset ensures the horizon view is never empty when live APIs are unavailable. International sources with unreliable feeds (e.g. Japan's METI) fall back to Google News RSS automatically.
