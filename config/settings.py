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
COURTLISTENER_KEY    = os.getenv("COURTLISTENER_KEY", "")   # free at courtlistener.com

# LLM provider keys (set the one matching LLM_PROVIDER)
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY",  "")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY",  "")

# ── LLM Provider ──────────────────────────────────────────────────────────────
# Which LLM to use for all AI features.
# Options: anthropic | openai | ollama | gemini
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")

# Model name. Leave blank to use the provider default:
#   anthropic → claude-sonnet-4-20250514
#   openai    → gpt-4o
#   ollama    → llama3.1
#   gemini    → gemini-1.5-pro
LLM_MODEL    = os.getenv("LLM_MODEL", "")

# Base URL for OpenAI-compatible endpoints (Ollama, Groq, Together AI, LM Studio…)
# Leave blank for official provider endpoints.
# Examples:
#   Groq:        https://api.groq.com/openai/v1
#   Together AI: https://api.together.xyz/v1
#   Ollama:      http://localhost:11434/v1
#   LM Studio:   http://localhost:1234/v1
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")

# ── Paths ─────────────────────────────────────────────────────────────────────
OUTPUT_DIR  = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
DB_PATH     = os.getenv("DB_PATH", str(OUTPUT_DIR / "aris.db"))

# PDF drop folder — place PDFs here for manual ingestion
PDF_DROP_DIR = OUTPUT_DIR / "pdf_inbox"
PDF_DROP_DIR.mkdir(exist_ok=True)

# PDF storage — extracted text and downloaded PDFs
PDF_STORE_DIR = OUTPUT_DIR / "pdfs"
PDF_STORE_DIR.mkdir(exist_ok=True)

# ── Behaviour ─────────────────────────────────────────────────────────────────
LOOKBACK_DAYS       = int(os.getenv("LOOKBACK_DAYS", "30"))
MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "0.5"))
LOG_LEVEL           = os.getenv("LOG_LEVEL", "INFO")

# ── AI keywords used to filter documents ─────────────────────────────────────
# ── AI keyword taxonomy ───────────────────────────────────────────────────────
# The canonical list lives in utils/search.py (150+ terms with synonyms).
# AI_KEYWORDS is kept here for backward compatibility with any code that
# imports it directly; it now imports from the expanded taxonomy.
try:
    from utils.search import AI_TERMS_EXPANDED as AI_KEYWORDS
except ImportError:
    # Fallback if search module not yet available (e.g. first import cycle)
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

# ── Search configuration ──────────────────────────────────────────────────────
# Minimum relevance score to trigger FTS indexing (0.0–1.0)
SEARCH_MIN_INDEX_SCORE = float(os.getenv("SEARCH_MIN_INDEX_SCORE", "0.05"))

# Whether to rebuild the TF-IDF index after each summarisation run
SEARCH_AUTO_REBUILD = os.getenv("SEARCH_AUTO_REBUILD", "true").lower() == "true"

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

# ── Model / token settings (kept for backward compatibility) ─────────────────
# Agents now use utils.llm.call_llm() which reads LLM_PROVIDER / LLM_MODEL
# directly. CLAUDE_MODEL and MAX_TOKENS remain here so any external code
# that imports them still works.
CLAUDE_MODEL  = LLM_MODEL or "claude-sonnet-4-20250514"
MAX_TOKENS    = 2048

# ── HTTP request settings ─────────────────────────────────────────────────────
REQUEST_TIMEOUT    = 30   # seconds
MAX_RETRIES        = 3
RETRY_WAIT_SECONDS = 2
CACHE_TTL_HOURS    = 6    # cache API responses for 6 hours
