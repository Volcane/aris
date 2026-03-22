"""
ARIS — Jurisdiction Registry

Single config file controlling which US states and international
jurisdictions are monitored. Edit this file to turn regions on or off.

Jurisdictions are grouped into three independent tracks:
  1. US Federal   — always active (FederalAgent handles this)
  2. US States    — controlled by ENABLED_US_STATES
  3. International — controlled by ENABLED_INTERNATIONAL
"""

# ── US States ─────────────────────────────────────────────────────────────────
# Each entry must have a corresponding class in sources/states/<code>.py

ENABLED_US_STATES = [
    # Tier 1 — fully implemented with native feeds
    "PA",    # Pennsylvania  — LegiScan + palegis.us ZIP feed (hourly)
    "CA",    # California    — LegiScan + CA Legislature API
    "CO",    # Colorado      — LegiScan + leg.colorado.gov API; CO AI Act effective Jun 2026
    "IL",    # Illinois      — LegiScan + ILGA RSS feeds; AIPA enacted
    "TX",    # Texas         — LegiScan + TLO RSS; TRAIGA enacted 2025
    "WA",    # Washington    — LegiScan + WSL web services; MHMD Act, active AI pipeline
    "NY",    # New York      — LegiScan + NY Senate API; RAISE Act pending

    # Tier 2 — LegiScan + supplemental native feeds
    "FL",    # Florida       — LegiScan + FL Senate API; SB 262, govt AI, deepfakes
    "MN",    # Minnesota     — LegiScan + MN Senate RSS; SF 2995 (comprehensive AI) reintroducing
    "CT",    # Connecticut   — LegiScan; SB 2 (comprehensive AI) reintroducing 2026

    # Tier 3 — LegiScan only (comprehensive coverage)
    "VA",    # Virginia      — HB 2094 vetoed 2025, reintroducing 2026
    "NJ",    # New Jersey    — NJ Data Privacy Law, AI employment bills
    "MA",    # Massachusetts — AI employment bills, Data Privacy Act advancing
    "OR",    # Oregon        — Consumer Privacy Act in force, AI deepfake bill
    "MD",    # Maryland      — Online Data Privacy Act, AI employment bills
    "GA",    # Georgia       — AI employment disclosure, government AI
    "AZ",    # Arizona       — Chatbot regulation, deepfake disclosure
    "NC",    # North Carolina — AI Employment Act, state government AI
]

# ── International Jurisdictions ───────────────────────────────────────────────
# Each entry must have a corresponding class in sources/international/<code>.py

ENABLED_INTERNATIONAL = [
    # Fully implemented with live feeds
    "EU",    # European Union — EUR-Lex SPARQL + EU AI Office RSS
    "GB",    # United Kingdom — Parliament Bills + legislation.gov.uk + GOV.UK
    "CA",    # Canada         — OpenParliament + Canada Gazette + ISED feed
    "SG",    # Singapore      — PDPC RSS + IMDA RSS + pinned framework docs
    "IN",    # India          — PIB RSS (MEITY) + DPDP Act + IndiaAI Mission
    "BR",    # Brazil         — ANPD RSS + Senate RSS + LGPD + AI Bill PL2338

    # Pinned docs + available feeds (translation via Claude)
    "JP",    # Japan          — METI English RSS + pinned AI governance docs
    "KR",    # South Korea    — MSIT press releases + PIPA/AI Act pinned docs
    "AU",    # Australia      — Voluntary AI Safety Standard + Federal Register
    # "CN",  # China          — Pinned docs only (no public CAC API)
]

# ── Module path maps ──────────────────────────────────────────────────────────
# Maps jurisdiction code → importable Python module path.
# Used by the orchestrator for dynamic class loading.

US_STATE_MODULE_MAP = {
    "PA": "sources.states.pennsylvania",
    "CA": "sources.states.california",
    "CO": "sources.states.colorado",
    "IL": "sources.states.illinois",
    "TX": "sources.states.texas",
    "WA": "sources.states.washington",
    "NY": "sources.states.new_york",
    "FL": "sources.states.florida",
    "MN": "sources.states.minnesota",
    "CT": "sources.states.connecticut",
    "VA": "sources.states.virginia",
    "NJ": "sources.states.new_jersey",
    "MA": "sources.states.massachusetts",
    "OR": "sources.states.oregon",
    "MD": "sources.states.maryland",
    "GA": "sources.states.georgia",
    "AZ": "sources.states.arizona",
    "NC": "sources.states.north_carolina",
}

INTERNATIONAL_MODULE_MAP = {
    "EU": "sources.international.eu",
    "GB": "sources.international.uk",
    "CA": "sources.international.canada",
    "SG": "sources.international.singapore",
    "IN": "sources.international.india",
    "BR": "sources.international.brazil",
    "JP": "sources.international.stubs",
    "KR": "sources.international.south_korea",
    "AU": "sources.international.stubs",
    "CN": "sources.international.stubs",
}

# ── Class name map ────────────────────────────────────────────────────────────
# When a module contains multiple classes (e.g. stubs.py), specify which
# class to instantiate. If omitted, orchestrator picks the first
# InternationalAgentBase or StateAgentBase subclass it finds.

INTERNATIONAL_CLASS_MAP = {
    "JP": "JapanAgent",
    "CN": "ChinaAgent",
    "AU": "AustraliaAgent",
}

# ── Region display labels ─────────────────────────────────────────────────────
# Used by the reporter to group jurisdictions into sections.

REGION_LABELS = {
    "Federal":       "🏛  US Federal",
    "PA":            "🏢  Pennsylvania (US)",
    "VA":            "🏢  Virginia (US)",
    "NY":            "🏢  New York (US)",
    "CA":            "🏢  California (US)",   # note: state code, not Canada
    "TX":            "🏢  Texas (US)",
    "WA":            "🏢  Washington (US)",
    "FL":            "🏢  Florida (US)",
    "MN":            "🏢  Minnesota (US)",
    "CT":            "🏢  Connecticut (US)",
    "NJ":            "🏢  New Jersey (US)",
    "MA":            "🏢  Massachusetts (US)",
    "OR":            "🏢  Oregon (US)",
    "MD":            "🏢  Maryland (US)",
    "GA":            "🏢  Georgia (US)",
    "AZ":            "🏢  Arizona (US)",
    "NC":            "🏢  North Carolina (US)",
    "EU":            "🇪🇺  European Union",
    "GB":            "🇬🇧  United Kingdom",
    "CA_INTL":       "🇨🇦  Canada",            # disambiguated in reporter
    "JP":            "🇯🇵  Japan",
    "CN":            "🇨🇳  China",
    "AU":            "🇦🇺  Australia",
    "SG":            "🇸🇬  Singapore",
    "KR":            "🇰🇷  South Korea",
    "IN":            "🇮🇳  India",
    "BR":            "🇧🇷  Brazil",
    "SG":            "🇸🇬  Singapore",
    "KR":            "🇰🇷  South Korea",
}

# ── LegiScan state code mapping (US states only) ──────────────────────────────
LEGISCAN_STATE_MAP = {
    "PA": "PA", "CA": "CA", "CO": "CO", "IL": "IL",
    "TX": "TX", "WA": "WA", "NY": "NY", "FL": "FL", "MN": "MN",
    "CT": "CT", "VA": "VA", "NJ": "NJ", "MA": "MA", "OR": "OR",
    "MD": "MD", "GA": "GA", "AZ": "AZ", "NC": "NC",
    # Note: "CA" here means California state; Canada international uses separate map
}

# ── Legacy alias (keeps old imports from states.py working) ──────────────────
ENABLED_STATES  = ENABLED_US_STATES
STATE_MODULE_MAP = US_STATE_MODULE_MAP
