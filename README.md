\# ARIS — AI Regulation Intelligence System



\*\*Monitor. Interpret. Act.\*\*



ARIS is a fully local, agentic system that automatically monitors AI-related legislation and regulations across US Federal agencies, US state legislatures, and international jurisdictions. It fetches documents from public APIs, uses Claude (Anthropic) to interpret legal language, and delivers plain-English summaries with concrete compliance action items your team can act on immediately.



\---



\## What It Does



1\. \*\*Fetches\*\* — Pulls AI-related documents from official government APIs on a schedule or on demand

2\. \*\*Filters\*\* — Eliminates irrelevant documents using keyword pre-screening before spending any AI tokens

3\. \*\*Interprets\*\* — Sends each document to Claude, which classifies mandatory requirements vs. voluntary recommendations and generates business action items

4\. \*\*Stores\*\* — Saves everything to a local SQLite database on your machine

5\. \*\*Reports\*\* — Displays a terminal dashboard and exports to Markdown or JSON



All data stays on your local machine. No cloud storage. No third-party data sharing.



\---



\## Coverage



\### US Federal

| Source | What It Covers | API Key |

|--------|---------------|---------|

| Federal Register | Final rules, proposed rules, executive orders, presidential memoranda, notices | None required |

| Regulations.gov | Full rulemaking dockets, public comment periods | Free — register at open.gsa.gov |

| Congress.gov | House and Senate bills, resolutions | Free — register at api.congress.gov |



\### US States

| State | Sources | API Key |

|-------|---------|---------|

| Pennsylvania | LegiScan API + PA General Assembly XML feed (updated hourly) | LegiScan free tier |

| All other states | LegiScan API (50-state coverage, ready to activate) | LegiScan free tier |



\### International

| Jurisdiction | Sources | API Key |

|-------------|---------|---------|

| European Union | EUR-Lex Cellar SPARQL endpoint, EU AI Office RSS, pinned AI Act documents | None required |

| United Kingdom | UK Parliament Bills API, legislation.gov.uk Atom feed, GOV.UK Search API | None required |

| Canada | OpenParliament.ca API, Canada Gazette RSS (Parts I \& II), ISED news feed | None required |

| Japan | METI English press release RSS, pinned METI/MIC AI guidelines | None required |

| China | Pinned CAC regulatory documents (no public API available) | None required |

| Australia | Pinned DISR Voluntary AI Safety Standard | None required |



\---



\## How Claude Is Used



Every document passes through `agents/interpreter.py`, which sends it to Claude via the Anthropic API. Claude returns a structured JSON object containing:



\- \*\*`plain\_english`\*\* — A 2–3 sentence summary any non-lawyer can understand

\- \*\*`requirements`\*\* — Legally mandatory obligations (Must / Shall / Required to…)

\- \*\*`recommendations`\*\* — Non-mandatory guidance and best practices

\- \*\*`action\_items`\*\* — Specific steps your legal or compliance team should take

\- \*\*`deadline`\*\* — Comment periods or effective dates extracted from the document

\- \*\*`impact\_areas`\*\* — Business domains affected (Healthcare AI, Hiring Algorithms, Marketing, etc.)

\- \*\*`urgency`\*\* — Low / Medium / High / Critical

\- \*\*`relevance\_score`\*\* — How directly the document applies to AI regulation (0.0–1.0)



Documents with a relevance score below 0.3 are dropped automatically. A fast keyword pre-filter runs before any API call, keeping costs low.



\---



\## Folder Structure



Place all files exactly as shown below. Create the folders first, then place the files inside them. Every folder marked with `\_\_init\_\_.py` needs that file created as an empty blank text file.



```

ai-reg-tracker/

│

├── main.py                              ← CLI entry point — run everything from here

├── requirements.txt                     ← Python dependencies

│

├── config/

│   ├── \_\_init\_\_.py                      ← Empty file (required)

│   ├── keys.env.example                 ← Copy this to keys.env and fill in your keys

│   ├── keys.env                         ← Your actual API keys (never commit this)

│   ├── settings.py                      ← Global settings, keywords, API base URLs

│   └── jurisdictions.py                 ← Toggle US states and international on/off

│

├── agents/

│   ├── \_\_init\_\_.py                      ← Empty file (required)

│   ├── interpreter.py                   ← Claude-powered document analysis

│   ├── orchestrator.py                  ← Coordinates all three fetch tracks

│   └── scheduler.py                     ← Watch mode / recurring scheduled runs

│

├── sources/

│   ├── \_\_init\_\_.py                      ← Empty file (required)

│   ├── federal\_agent.py                 ← Federal Register, Regulations.gov, Congress.gov

│   ├── state\_agent\_base.py              ← Abstract base class all US state agents inherit from

│   │

│   ├── states/                          ← US State agents

│   │   ├── \_\_init\_\_.py                  ← Empty file (required)

│   │   ├── pennsylvania.py              ← PA-specific: LegiScan + PA General Assembly XML

│   │   └── virginia.py                  ← Template / example for adding other states

│   │

│   └── international/                   ← International jurisdiction agents

│       ├── \_\_init\_\_.py                  ← Empty file (required)

│       ├── base.py                      ← Abstract base class all international agents inherit from

│       ├── eu.py                        ← European Union: EUR-Lex SPARQL + EU AI Office RSS

│       ├── uk.py                        ← United Kingdom: Parliament + legislation.gov.uk + GOV.UK

│       ├── canada.py                    ← Canada: OpenParliament + Gazette RSS + ISED feed

│       └── stubs.py                     ← Japan, China, Australia — ready to activate

│

├── utils/

│   ├── \_\_init\_\_.py                      ← Empty file (required)

│   ├── db.py                            ← SQLite database via SQLAlchemy

│   ├── cache.py                         ← HTTP response cache, retry logic, keyword filter

│   └── reporter.py                      ← Terminal dashboard + Markdown/JSON export

│

├── tests/

│   ├── test\_suite.py                    ← Tests for federal and PA agents

│   └── test\_international.py            ← Tests for EU, UK, Canada, and stub agents

│

└── output/                              ← Created automatically on first run — do not create manually

&#x20;   ├── aris.db                          ← SQLite database (all documents + AI summaries)

&#x20;   ├── .cache/                          ← HTTP response cache (avoids redundant API calls)

&#x20;   └── aris\_report\_YYYYMMDD.md          ← Exported reports land here

```



\---



\## Setup



\### 1. Install Dependencies



```bash

cd ai-reg-tracker

pip install -r requirements.txt

```



\### 2. Get Your API Keys



All keys are free. Register at the links below and paste the keys into `config/keys.env`.



| Key | Where to Get It | Required? |

|-----|----------------|-----------|

| `ANTHROPIC\_API\_KEY` | https://console.anthropic.com/settings/keys | \*\*Yes\*\* — needed for all AI summarization |

| `REGULATIONS\_GOV\_KEY` | https://open.gsa.gov/api/regulationsgov/ | Recommended — enables Regulations.gov |

| `CONGRESS\_GOV\_KEY` | https://api.congress.gov/sign-up/ | Recommended — enables Congress.gov bills |

| `LEGISCAN\_KEY` | https://legiscan.com/legiscan | Required for US state monitoring |



```bash

cp config/keys.env.example config/keys.env

\# Open keys.env in any text editor and paste your keys

```



\### 3. Verify Your Setup



```bash

python main.py status

```



This shows which API keys are configured, which jurisdictions are enabled, and database statistics.



\---



\## Usage



\### Run the Full Pipeline



Fetches all sources, then summarizes with Claude:



```bash

python main.py run

```



\### Fetch Without Summarizing



Useful for pulling down documents before you are ready to use AI tokens:



```bash

python main.py fetch                          # all sources

python main.py fetch --source federal         # US Federal only

python main.py fetch --source states          # all enabled US states

python main.py fetch --source international   # all international jurisdictions

python main.py fetch --source PA              # Pennsylvania only

python main.py fetch --source EU              # European Union only

python main.py fetch --source GB              # United Kingdom only

python main.py fetch --days 7                 # last 7 days only

```



\### Summarize Pending Documents



Run Claude on documents already in the database that have not yet been summarized:



```bash

python main.py summarize

python main.py summarize --limit 100          # process up to 100 at a time

```



\### View the Dashboard



```bash

python main.py report                         # all jurisdictions, last 30 days

python main.py report --days 7                # last 7 days

python main.py report --jurisdiction EU       # EU only

python main.py report --jurisdiction Federal  # US Federal only

python main.py report --urgency High          # High and Critical only

```



\### Export Results



```bash

python main.py export --format markdown       # saves to output/aris\_report\_YYYYMMDD.md

python main.py export --format json           # saves to output/aris\_export\_YYYYMMDD.json

python main.py export --format markdown --output my\_report.md   # custom filename

```



\### Continuous Monitoring



Runs the full pipeline on a schedule. Press Ctrl+C to stop:



```bash

python main.py watch                          # runs every 24 hours (default)

python main.py watch --interval 12            # runs every 12 hours

python main.py watch --interval 6 --days 2    # every 6 hours, looking back 2 days

```



\### List Active Agents



```bash

python main.py agents

```



\---



\## What Each Summary Looks Like



```json

{

&#x20; "id": "EU-CELEX-32024R1689",

&#x20; "title": "Regulation (EU) 2024/1689 — EU Artificial Intelligence Act",

&#x20; "source": "eurlex\_pinned",

&#x20; "jurisdiction": "EU",

&#x20; "doc\_type": "Regulation",

&#x20; "status": "In Force",

&#x20; "agency": "European Commission / European Parliament",

&#x20; "published\_date": "2024-07-12",

&#x20; "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689",

&#x20; "plain\_english": "The EU AI Act establishes a risk-based framework classifying AI systems

&#x20;                   into four tiers. Companies placing AI on the EU market or using AI to

&#x20;                   serve EU users must comply, with penalties up to €35M or 7% of global

&#x20;                   turnover for violations.",

&#x20; "requirements": \[

&#x20;   "Must register high-risk AI systems in the EU database before market placement",

&#x20;   "Must conduct conformity assessments for all high-risk AI systems",

&#x20;   "Must implement human oversight mechanisms for high-risk AI deployments",

&#x20;   "Must cease use of prohibited AI practices (social scoring, real-time biometric

&#x20;    surveillance) by 2 February 2025"

&#x20; ],

&#x20; "recommendations": \[

&#x20;   "Voluntarily follow the GPAI Code of Practice to demonstrate compliance readiness",

&#x20;   "Establish an AI governance committee to monitor Act implementation milestones"

&#x20; ],

&#x20; "action\_items": \[

&#x20;   "Audit all AI systems in use and classify each by risk tier (prohibited / high / limited / minimal)",

&#x20;   "Identify systems that qualify as high-risk under Annex III and begin conformity assessment",

&#x20;   "Review all automated decision-making processes for prohibited practices compliance",

&#x20;   "Assign an EU AI Act compliance owner before the August 2026 full-application deadline"

&#x20; ],

&#x20; "deadline": "2026-08-02",

&#x20; "impact\_areas": \["Product Development", "Healthcare AI", "Hiring Algorithms",

&#x20;                  "Biometric Systems", "EU Market Access"],

&#x20; "urgency": "Critical",

&#x20; "relevance\_score": 1.0

}

```



\---



\## Adding a New US State



Create a file at `sources/states/new\_york.py`:



```python

from sources.state\_agent\_base import StateAgentBase



class NewYorkAgent(StateAgentBase):

&#x20;   state\_code     = "NY"

&#x20;   state\_name     = "New York"

&#x20;   legiscan\_state = "NY"

&#x20;   # LegiScan handles everything automatically.

&#x20;   # Override fetch\_native() here if NY publishes its own XML/RSS feed.

```



Then open `config/jurisdictions.py` and add `"NY"` to `ENABLED\_US\_STATES`.



\---



\## Adding a New Country



Create a file at `sources/international/singapore.py`:



```python

from sources.international.base import InternationalAgentBase, parse\_date



class SingaporeAgent(InternationalAgentBase):

&#x20;   jurisdiction\_code = "SG"

&#x20;   jurisdiction\_name = "Singapore"

&#x20;   region            = "Asia-Pacific"

&#x20;   language          = "en"



&#x20;   def fetch\_native(self, lookback\_days=30):

&#x20;       # Implement fetch from PDPC or MCI publications

&#x20;       # Return list of self.\_make\_doc(...) dicts

&#x20;       return \[]

```



Then open `config/jurisdictions.py` and add `"SG"` to `ENABLED\_INTERNATIONAL` and its module path to `INTERNATIONAL\_MODULE\_MAP`.



Stub classes for Japan, China, and Australia are already written in `sources/international/stubs.py` — just uncomment their codes in `config/jurisdictions.py` to activate them.



\---



\## Running Tests



```bash

python -m pytest tests/ -v

```



Or without pytest:



```bash

python -m unittest tests.test\_suite -v

python -m unittest tests.test\_international -v

```



\---



\## Key Design Decisions



\*\*Everything runs locally.\*\* The SQLite database, HTTP cache, and all exported files are stored in the `output/` folder on your machine. Nothing is sent to any external service except the official government APIs being queried and the Anthropic API for summarization.



\*\*Three independent fetch tracks.\*\* US Federal, US States, and International can each be run, scheduled, or filtered independently. Adding a jurisdiction to one track has no effect on the others.



\*\*Two-stage AI cost control.\*\* A fast keyword pre-filter runs locally before any Claude API call. Claude then applies its own relevance scoring, and documents rated below 0.3 are dropped without being stored. This means you only pay for documents that are genuinely AI-regulation-relevant.



\*\*Pinned critical documents.\*\* For jurisdictions with landmark legislation already in force (EU AI Act, Canada AIDA status, UK Data Use and Access Act, etc.), the system includes curated document entries that are always present regardless of publication date. This ensures critical compliance obligations are never missed because they fall outside a lookback window.



\*\*HTTP response caching.\*\* All API responses are cached locally for 6 hours by default, configurable via `CACHE\_TTL\_HOURS` in `keys.env`. This means repeated runs do not re-query APIs unnecessarily, and the system can produce reports even when APIs are temporarily unavailable.



\---



\## Configuration Reference



All settings live in `config/keys.env`. Copy from `keys.env.example` to get started.



| Setting | Default | Description |

|---------|---------|-------------|

| `ANTHROPIC\_API\_KEY` | — | Required. Your Anthropic API key |

| `REGULATIONS\_GOV\_KEY` | — | Free key for Regulations.gov |

| `CONGRESS\_GOV\_KEY` | — | Free key for Congress.gov |

| `LEGISCAN\_KEY` | — | Free key for LegiScan (US states) |

| `LOOKBACK\_DAYS` | `30` | How many days back to search for new documents |

| `MIN\_RELEVANCE\_SCORE` | `0.5` | Minimum Claude relevance score to store a summary |

| `DB\_PATH` | `./output/aris.db` | Path to the SQLite database file |

| `CACHE\_TTL\_HOURS` | `6` | How long to cache API responses |

| `LOG\_LEVEL` | `INFO` | Logging verbosity: DEBUG, INFO, WARNING, ERROR |



