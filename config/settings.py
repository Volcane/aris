"""
ARIS — Global Settings
Loaded once at startup; all modules import from here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve project root and load keys
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / "config" / "keys.env")

# ── API Keys ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
REGULATIONS_GOV_KEY  = os.getenv("REGULATIONS_GOV_KEY", "")
CONGRESS_GOV_KEY     = os.getenv("CONGRESS_GOV_KEY", "")
LEGISCAN_KEY         = os.getenv("LEGISCAN_KEY", "")

# ── Paths ─────────────────────────────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
DB_PATH    = os.getenv("DB_PATH", str(OUTPUT_DIR / "aris.db"))

# ── Behaviour ─────────────────────────────────────────────────────────────────
LOOKBACK_DAYS       = int(os.getenv("LOOKBACK_DAYS", "30"))
MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "0.5"))
LOG_LEVEL           = os.getenv("LOG_LEVEL", "INFO")

# ── AI keywords used to filter documents ─────────────────────────────────────
AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning",
    "generative ai", "large language model", "llm", "neural network",
    "automated decision", "algorithmic", "algorithm", "facial recognition",
    "biometric", "autonomous system", "predictive analytics",
    "natural language processing", "nlp", "computer vision",
    "foundation model", "ai governance", "ai safety", "ai risk",
    "ai transparency", "ai accountability", "ai bias", "ai ethics",
    "responsible ai", "trustworthy ai", "ai regulation",
    "ai disclosure", "deepfake", "synthetic media",
]

# ── Federal Register API ──────────────────────────────────────────────────────
FEDERAL_REGISTER_BASE = "https://www.federalregister.gov/api/v1"
FR_DOC_TYPES          = ["RULE", "PRORULE", "NOTICE", "PRESDOCU"]

# ── Regulations.gov API ───────────────────────────────────────────────────────
REGS_GOV_BASE = "https://api.regulations.gov/v4"

# ── Congress.gov API ──────────────────────────────────────────────────────────
CONGRESS_BASE = "https://api.congress.gov/v3"

# ── LegiScan API ──────────────────────────────────────────────────────────────
LEGISCAN_BASE = "https://api.legiscan.com/"

# ── PA General Assembly native XML feed ──────────────────────────────────────
PA_LEGIS_FEED = "https://www.legis.state.pa.us/cfdocs/legis/home/xml/hbHistXML.cfm"

# ── Anthropic model for interpretation ───────────────────────────────────────
CLAUDE_MODEL  = "claude-sonnet-4-20250514"
MAX_TOKENS    = 2048

# ── HTTP request settings ─────────────────────────────────────────────────────
REQUEST_TIMEOUT    = 30   # seconds
MAX_RETRIES        = 3
RETRY_WAIT_SECONDS = 2
CACHE_TTL_HOURS    = 6    # cache API responses for 6 hours
