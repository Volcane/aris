# AI Regulation Intelligence System (ARIS)

A fully local, agentic system that monitors, fetches, interprets, and summarizes AI-related legislation and regulations from Federal and state repositories — delivering actionable business intelligence.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        ARIS  Orchestrator                       │
│                        (main.py / cli.py)                       │
└───────────┬─────────────────────────────────────────────────────┘
            │
     ┌──────▼──────┐
     │  Scheduler  │  (runs continuously or on-demand)
     └──────┬──────┘
            │
  ┌─────────▼──────────────────────────────────┐
  │              Source Agents                  │
  │  ┌──────────────┐  ┌──────────────────────┐ │
  │  │ FederalAgent │  │  StateAgent (PA+more)│ │
  │  │              │  │                      │ │
  │  │ • FedRegister│  │ • LegiScan API       │ │
  │  │ • Regulations│  │ • PA Legis XML Feed  │ │
  │  │   .gov API   │  │ • Extensible base    │ │
  │  │ • Congress   │  │   class for 50 states│ │
  │  │   .gov API   │  └──────────────────────┘ │
  │  └──────────────┘                            │
  └─────────────────────────────────────────────┘
            │
  ┌─────────▼──────────────────────────────────┐
  │            Interpretation Agent             │
  │    (Claude API via Anthropic SDK)           │
  │                                             │
  │  • Classifies document type & relevance     │
  │  • Extracts requirements vs. recommendations│
  │  • Maps to business impact categories       │
  │  • Generates compliance action items        │
  └─────────────────────────────────────────────┘
            │
  ┌─────────▼──────────────────────────────────┐
  │             Output & Storage                │
  │                                             │
  │  • SQLite local database                    │
  │  • JSON exports                             │
  │  • Markdown / HTML reports                  │
  │  • Console dashboard (Rich)                 │
  └─────────────────────────────────────────────┘
```

---

## Data Sources

### Federal
| Source | API | Key Required | Coverage |
|--------|-----|--------------|----------|
| Federal Register | `federalregister.gov/api/v1` | No | Rules, Proposed Rules, EOs, Notices |
| Regulations.gov | `api.regulations.gov/v4` | Yes (free) | Rulemaking dockets, comments |
| Congress.gov | `api.congress.gov/v3` | Yes (free) | Bills, resolutions |

### State — Pennsylvania
| Source | API | Key Required | Coverage |
|--------|-----|--------------|----------|
| LegiScan | `api.legiscan.com` | Yes (free) | Bills across all 50 states + Congress |
| PA General Assembly | `legis.state.pa.us/data/` | No | PA XML bill feed (hourly updates) |

### Extensible to Other States
The `StateAgent` base class in `sources/state_agent_base.py` defines the interface. Adding a new state requires implementing one small subclass (≈30 lines).

---

## Quick Start

### 1. Install
```bash
cd ai-reg-tracker
pip install -r requirements.txt
```

### 2. Configure API Keys
```bash
cp config/keys.env.example config/keys.env
# Edit config/keys.env with your free API keys:
#   ANTHROPIC_API_KEY      — https://console.anthropic.com
#   REGULATIONS_GOV_KEY    — https://open.gsa.gov/api/regulationsgov/
#   CONGRESS_GOV_KEY       — https://api.congress.gov/sign-up/
#   LEGISCAN_KEY           — https://legiscan.com/legiscan (free tier)
```

### 3. Run
```bash
# Full scan + summarize
python main.py run

# Fetch only (no AI summarization)
python main.py fetch --source federal

# Summarize already-fetched documents
python main.py summarize

# Show dashboard of latest findings
python main.py report

# Watch mode (runs every N hours)
python main.py watch --interval 24
```

---

## Output

Each regulation or bill produces a structured summary:

```json
{
  "id": "FR-2025-18737",
  "title": "Notice of RFI: Regulatory Reform on AI",
  "source": "federal_register",
  "doc_type": "Notice",
  "status": "Open for Comment",
  "published": "2025-09-26",
  "jurisdiction": "Federal",
  "agency": "OSTP",
  "url": "https://federalregister.gov/...",
  "ai_summary": {
    "plain_english": "...",
    "requirements": ["..."],
    "recommendations": ["..."],
    "action_items": ["..."],
    "deadline": "2025-10-27",
    "impact_areas": ["AI Development", "Compliance"],
    "urgency": "High"
  }
}
```

---

## Adding a New State

```python
# sources/states/virginia.py
from sources.state_agent_base import StateAgentBase

class VirginiaAgent(StateAgentBase):
    state_code = "VA"
    state_name = "Virginia"
    legiscan_state = "VA"

    # Optional: override if the state has its own XML/RSS feed
    def get_native_feed_url(self):
        return None  # Use LegiScan only
```

Then register it in `config/states.py`:
```python
ENABLED_STATES = ["PA", "VA"]
```

---

## File Structure

```
ai-reg-tracker/
├── main.py                    # CLI entry point
├── requirements.txt
├── config/
│   ├── keys.env.example       # API key template
│   ├── settings.py            # Global settings
│   └── states.py              # Enabled states registry
├── agents/
│   ├── orchestrator.py        # Coordinates all agents
│   ├── scheduler.py           # Cron / interval runner
│   └── interpreter.py         # Claude-powered analysis
├── sources/
│   ├── federal_agent.py       # Federal Register + Regs.gov + Congress
│   ├── state_agent_base.py    # Abstract base for all states
│   └── states/
│       ├── pennsylvania.py    # PA-specific implementation
│       └── __init__.py
├── utils/
│   ├── db.py                  # SQLite helpers
│   ├── cache.py               # Request caching
│   ├── reporter.py            # Console + file output
│   └── logger.py
├── output/                    # Generated reports land here
└── tests/
    ├── test_federal.py
    └── test_pa.py
```
