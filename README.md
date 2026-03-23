# ARIS — Automated Regulatory Intelligence System

**Monitor. Baseline. Compare. Interpret. Consolidate. Trend. Horizon. Learn. Act.**

ARIS is a fully local, agentic system that monitors **AI regulation and data privacy law** across 18 US states, 10 international jurisdictions, and US Federal agencies. It ships with 31 curated baseline regulations, fetches live documents from official government APIs, uses Claude to interpret and analyse them, detects changes, tracks regulatory velocity, scans the regulatory horizon for planned regulations, consolidates obligations, compares jurisdictions side-by-side, and performs company-specific compliance gap analysis — all through a browser dashboard or the command line.

Everything runs on your machine. No SaaS subscription, no data leaving your environment, no per-query costs beyond your own API key.

---

## License

ARIS is licensed under the **Elastic License 2.0 (ELv2)**. You may use, copy, and modify it for personal, educational, and non-commercial purposes. You may not sell it, offer it as a commercial product or service, or use it as the basis of a paid product without express written permission. See [LICENSE](LICENSE) for the full terms.

Copyright (c) 2026 Mitch Kwiatkowski

**Disclaimer:** ARIS is an informational research tool only. Nothing it produces constitutes legal, compliance, or regulatory advice. Always consult qualified legal counsel before making compliance decisions.

---

## What It Does

| # | Feature | API Calls | Description |
|---|---------|-----------|-------------|
| 1 | **Baselines** | None | 31 curated baselines covering settled AI regulation and data privacy law. Always available. |
| 2 | **Fetch** | None | Concurrent fetch from 18 US states, 10 international jurisdictions, and 5 US Federal sources. |
| 3 | **Filter** | None | Domain-aware keyword pre-screening with false-positive protection for common non-AI acronyms (NAIC, AIDA, MAID, PAID leave). Skipped docs recorded with reason. |
| 4 | **Interpret** | Claude | Plain-English summaries, urgency ratings, requirements, action items, deadlines. Domain-specific prompts. |
| 5 | **Change detection** | Claude | Baseline-aware diffs — compares new documents against settled law, not just prior versions. |
| 6 | **Consolidation** | Optional | De-duplicated obligation register from all 31 baselines. Fast mode: zero API calls. Full mode: one Claude call. |
| 7 | **Trends & velocity** | None | Jurisdiction velocity sparklines, impact-area heatmap, acceleration alerts — all from local DB. |
| 8 | **Horizon scanning** | None | Monitors Unified Regulatory Agenda, congressional hearings, EU Work Programme, UK Parliament, plus 17 seeded known upcoming events. Dashboard widget with urgency buckets and countdowns. |
| 9 | **Compare** | Claude | Side-by-side structured comparison of any two of the 31 baselines. |
| 10 | **Synthesis** | Claude | Cross-document regulatory landscape with conflict detection. Export to .docx. |
| 11 | **Gap analysis** | Claude | Company-profile compliance gaps, phased roadmap. Export to .docx. |
| 12 | **Document review** | None | Feedback marks documents Relevant / Partially Relevant / Not Relevant. |
| 13 | **Autonomous learning** | Claude (periodic) | Every processed document — including Skipped stubs — feeds the relevance model. Sources producing false positives are down-weighted automatically. Documents Claude scores ≤ 0.15 auto-archive. |
| 14 | **PDFs** | None | Auto-download PDFs from Federal Register, EUR-Lex, UK legislation; accept manual uploads. |
| 15 | **Notifications** | None | Email (SMTP) and Slack webhook digests on critical findings and scheduled runs. |
| 16 | **Scheduled monitoring** | None | Background scheduler with configurable interval, domain, and lookback. Survives restarts. |

---

## Browser Views

| View | What It Shows |
|------|---------------|
| **Dashboard** | Alert rail, pulse sparklines, **horizon widget** (urgency buckets + countdown list), system health |
| **Documents** | Active document list with domain filter, review badges, Skipped indicator with exact reason |
| **Changes** | Keyword search, version diffs with severity badges, side-by-side comparisons |
| **Baselines** | Domain tabs (AI Regulation / Data Privacy), jurisdiction filter, obligations and prohibitions |
| **Compare** | Side-by-side Claude analysis of any two of 31 baselines |
| **Trends** | Jurisdiction velocity sparklines, impact-area heatmap, acceleration alerts |
| **Horizon** | 12-month forward calendar with domain filter — deadlines, proposed rules, hearings |
| **Obligations** | De-duplicated obligation register across any jurisdiction set |
| **Ask ARIS** | RAG-powered Q&A across all documents and baselines with citations |
| **Briefs** | One-page regulatory briefs per jurisdiction |
| **Synthesis** | Cross-jurisdiction narratives, conflict maps, .docx export |
| **Gap Analysis** | Company profiles, domain-scoped gap cards, roadmap, .docx export |
| **Enforcement** | FTC, SEC, CFPB, ICO enforcement actions |
| **Graph** | Document relationship network |
| **Concept Map** | Cross-jurisdiction concept analysis |
| **Timeline** | Chronological regulatory timeline |
| **Watchlist** | Keyword-based alerts with domain filter |
| **PDF Ingest** | Upload PDFs or trigger auto-download |
| **Run Agents** | Trigger fetch/summarise; first-run banner; post-run summary with auto-archived count |
| **Learning** | Source quality profiles, keyword weights, prompt adaptations |
| **Settings** | API keys, jurisdiction toggles, scheduled monitoring, notifications |

---

## Coverage

### US States (18)

| State | Native Feed | Key Legislation |
|-------|-------------|-----------------|
| Pennsylvania | palegis.us ZIP + LegiScan | Digital identity, AI deepfakes |
| California | CA Legislature API + LegiScan | SB 53, AB 2013, SB 942 (24+ AI laws) |
| Colorado | leg.colorado.gov API + LegiScan | AI Act SB 24-205 (effective Jun 2026) |
| Illinois | ILGA RSS + LegiScan | AIPA enacted, BIPA |
| Texas | TLO RSS + LegiScan | TRAIGA enacted Jan 2026 |
| Washington | WSL web services + LegiScan | My Health My Data Act |
| New York | NY Senate API + LegiScan | RAISE Act pending |
| Florida | FL Senate API + LegiScan | SB 262, government AI |
| Minnesota | MN Senate RSS + LegiScan | SF 2995 reintroducing 2026 |
| Connecticut | LegiScan | SB 2 reintroducing 2026 |
| Virginia | LegiScan | HB 2094 equivalent reintroducing 2026 |
| New Jersey | LegiScan | NJ Data Privacy Law |
| Massachusetts | LegiScan | AI employment bills |
| Oregon | LegiScan | Consumer Privacy Act in force |
| Maryland | LegiScan | Online Data Privacy Act |
| Georgia | LegiScan | AI employment disclosure |
| Arizona | LegiScan | Chatbot regulation, deepfake disclosure |
| North Carolina | LegiScan | AI Employment Act |

### International (10)

| Jurisdiction | Primary Source | Key Instruments |
|-------------|----------------|-----------------|
| European Union | EUR-Lex + EU AI Office RSS | EU AI Act, GDPR, Data Act, DSA/DMA |
| United Kingdom | Parliament Bills API + legislation.gov.uk | UK GDPR/DPA, AI Framework, DPDI Act |
| Canada | OpenParliament + Canada Gazette | PIPEDA, CPPA (Bill C-27), AIDA |
| Singapore | PDPC RSS + IMDA RSS | Model AI Governance Framework, PDPA |
| India | PIB RSS (MEITY) | DPDP Act 2023, IndiaAI Mission |
| Brazil | ANPD RSS + Senate RSS | LGPD, AI Bill PL 2338/2023 |
| Japan | METI English RSS | AI Business Guidelines, APPI |
| South Korea | MSIT press releases | PIPA 2023 amendments, AI Promotion Act |
| Australia | Voluntary AI Safety Standard (pinned) | AI Safety Standard, Privacy Act review |
| China | Pinned documents | Generative AI Interim Measures |

---

## Dual-Domain Architecture

ARIS monitors two distinct regulatory domains with separate vocabularies, prompts, baselines, and scoring:

- **AI Regulation** — risk classification, transparency, oversight, prohibited uses, conformity assessment
- **Data Privacy** — consent, individual rights, breach notification, legal bases, international transfers

Every document, summary, change, and horizon item carries a `domain` field (`ai` | `privacy` | `both`). Every data view has a three-pill domain filter persisted independently per view.

### False-Positive Protection

The relevance filter uses a three-stage check designed to prevent common false positives from LegiScan searches:

1. **Strong-signal fast path** — unambiguous AI terms ("artificial intelligence", "automated decision", "deepfake") pass immediately
2. **Known false-positive guard** — blocks NAIC, MAID, PAID leave, BRAIN Initiative unless 2+ additional AI terms present
3. **Scored match** — 150+ term taxonomy; ambiguous terms (e.g. "aida") only count when backed by at least one unambiguous AI term

Pre-filter validation runs against the **bill title only**, not `title + search_keyword` — fixing the root cause where any bill returned by a LegiScan keyword query would automatically pass relevance.

---

## Autonomous Learning

ARIS improves its own relevance filtering without user input:

- **Skipped stubs feed the learner** — all three skip gates (pre-filter, no-learner domain check, Claude low score) return a stub dict that flows through the summarisation pipeline and calls `record_auto_feedback()` with the relevance score as signal
- **Auto-archive** — documents Claude rates ≤ 0.15 automatically receive a `not_relevant` feedback event (`user="aris_auto"`) and move to Archive
- **Domain-keyed profiles** — AI and privacy sources accrue quality scores independently so cross-domain noise doesn't contaminate scoring

---

## Regulatory Horizon

17 confirmed upcoming events seeded (March 2026), plus four live API sources. Key dates:

| Event | Date |
|-------|------|
| Colorado AI Act enforcement effective | Jun 30, 2026 |
| EU AI Act — GPAI obligations apply | Aug 2, 2026 |
| California SB 942 (AI transparency) effective | Aug 2, 2026 |
| EU Data Act fully applicable | Sep 12, 2026 |
| EU AI Act — High-Risk AI obligations | Aug 2, 2027 |

The **dashboard Horizon Widget** shows urgency buckets (Within 30d / 30–180d / 180d+ / TBD), countdown badges, stage pills, and jurisdiction chips.

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
```

---

## After Updating Files

```bash
python migrate.py          # adds new tables/columns
cd ui && npm run build     # only if UI source files changed
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
| `LEGISCAN_KEY` | — | Free — all 18 US state legislatures |
| `ACTIVE_DOMAINS` | `both` | `ai` / `privacy` / `both` |
| `LOOKBACK_DAYS` | `30` | Days back for document searches |
| `ARIS_HOST` | `127.0.0.1` | Set to `0.0.0.0` for LAN access (no auth — use caution) |
| `NOTIFY_EMAIL` | — | Recipient for email notifications |
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook URL |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

**636 tests across 18 test files.** All run without live API calls.

---

## Repository Files

| File | Purpose |
|------|---------|
| `LICENSE` | Elastic License 2.0 — non-commercial use |
| `CHANGELOG.md` | Version history |
| `CONTRIBUTING.md` | How to add state agents, run tests, submit PRs |
| `SECURITY.md` | Network exposure, key storage, vulnerability reporting |
| `pyproject.toml` | Python 3.11+ requirement, pytest config |
| `.gitignore` | Excludes keys.env, database, caches, build artifacts |

---

## Windows Setup Notes

ARIS is developed on Unix/macOS but runs on Windows. Two issues are known on Windows that do not occur on other platforms:

**SyntaxError: Non-UTF-8 code** — Python on Windows defaults to ASCII encoding for source files. Any file containing non-ASCII characters (em dashes in comments, box-drawing characters in section dividers, special symbols) will fail to import with `SyntaxError: Non-UTF-8 code starting with '\x97'`.

All ARIS Python files include `# -*- coding: utf-8 -*-` as their first line to declare UTF-8 explicitly. If you receive this error, the encoding declaration is missing from that file. Fix by running this from your project root:

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

Then restart `python server.py`.

**npm run build fails with "stream did not contain valid UTF-8"** — the same issue in `.js` or `.jsx` files. The fix is the same byte-level replacement targeting JavaScript files too (add `.js` and `.jsx` to the suffix check above), or manually open the affected file in a text editor and save it as UTF-8.

---

## Design Principles

**Baselines are the starting point.** ARIS knows what each law requires before fetching a single new document. Every analysis is anchored to settled law.

**Signal quality over coverage.** A compliance tool that surfaces noise erodes trust faster than it builds it. The pre-filter, false-positive blocklist, and autonomous learning loop all serve this goal.

**Everything runs locally.** Database, cache, PDFs, learning state, all 31 baselines, and the horizon calendar live on your machine.

**Zero-cost features first.** Browse baselines, view the obligation register, check velocity, and see the horizon calendar without spending a single API token.

**Transparency over silence.** Pre-filter rejections are recorded as `Skipped` with the reason visible in the UI. Auto-archived documents are stamped `user="aris_auto"`.

**Graceful degradation.** Failed source tracks don't block others. The seeded horizon dataset ensures the horizon view is never empty when live APIs are unavailable.
