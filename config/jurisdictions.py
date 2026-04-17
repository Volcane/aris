# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 Mitch Kwiatkowski
# ARIS — Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
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
    "PA",  # Pennsylvania  — LegiScan + palegis.us ZIP feed (hourly)
    "CA",  # California    — LegiScan + CA Legislature API
    "CO",  # Colorado      — LegiScan + leg.colorado.gov API; CO AI Act effective Jun 2026
    "IL",  # Illinois      — LegiScan + ILGA RSS feeds; AIPA enacted
    "TX",  # Texas         — LegiScan + TLO RSS; TRAIGA enacted 2025
    "WA",  # Washington    — LegiScan + WSL web services; MHMD Act, active AI pipeline
    "NY",  # New York      — LegiScan + NY Senate API; RAISE Act pending
    # Tier 2 — LegiScan + supplemental native feeds
    "FL",  # Florida       — LegiScan + FL Senate API; SB 262, govt AI, deepfakes
    "MN",  # Minnesota     — LegiScan + MN Senate RSS; SF 2995 (comprehensive AI) reintroducing
    "CT",  # Connecticut   — LegiScan; SB 2 (comprehensive AI) reintroducing 2026
    # Tier 3 — LegiScan only (comprehensive coverage, active AI/privacy pipeline)
    "VA",  # Virginia      — HB 2094 vetoed 2025, reintroducing 2026
    "NJ",  # New Jersey    — NJ Data Privacy Law, AI employment bills
    "MA",  # Massachusetts — AI employment bills, Data Privacy Act advancing
    "OR",  # Oregon        — Consumer Privacy Act in force, AI deepfake bill
    "MD",  # Maryland      — Online Data Privacy Act, AI employment bills
    "GA",  # Georgia       — AI employment disclosure, government AI
    "AZ",  # Arizona       — Chatbot regulation, deepfake disclosure
    "NC",  # North Carolina — AI Employment Act, state government AI
    "MI",  # Michigan      — Algorithmic accountability, data privacy
    "OH",  # Ohio          — AI employment bills, data privacy advancing
    "NV",  # Nevada        — AI transparency, deepfakes, NV Privacy Law
    "UT",  # Utah          — Utah AI Policy Act enacted 2024; active pipeline
    "IN",  # Indiana       — Consumer Data Protection Act in force 2026
    "TN",  # Tennessee     — ELVIS Act (AI voice/likeness); AI in employment
    "KY",  # Kentucky      — AI accountability, data privacy advancing
    "SC",  # South Carolina — AI governance bills, data privacy advancing
    "WI",  # Wisconsin     — AI employment, data privacy legislation
    "MO",  # Missouri      — AI regulation bills, data privacy advancing
    # Tier 4 — LegiScan only (emerging AI/privacy activity)
    "LA",  # Louisiana     — AI in government, data privacy legislation
    "AL",  # Alabama       — AI oversight, biometric privacy bills
    "MS",  # Mississippi   — AI regulation, data privacy legislation
    "AR",  # Arkansas      — AI governance, data protection legislation
    "IA",  # Iowa          — Consumer Data Protection Act in force 2025
    "KS",  # Kansas        — AI regulation, data privacy advancing
    "NE",  # Nebraska      — Data Privacy Act in force 2025, AI bills
    "NM",  # New Mexico    — AI regulation, data privacy advancing
    "OK",  # Oklahoma      — AI governance, data privacy bills
    "WV",  # West Virginia — AI regulation, data privacy advancing
    "ID",  # Idaho         — AI regulation, data privacy bills
    "MT",  # Montana       — Consumer Data Privacy Act in force 2024
    "ND",  # North Dakota  — AI regulation, data privacy advancing
    "SD",  # South Dakota  — AI regulation, data privacy advancing
    "WY",  # Wyoming       — AI regulation, data privacy bills
    "AK",  # Alaska        — AI governance, data privacy advancing
    "HI",  # Hawaii        — AI bills, data privacy advancing
    "ME",  # Maine         — AI regulation, data privacy advancing
    "NH",  # New Hampshire — AI regulation, data privacy advancing
    "VT",  # Vermont       — AI regulation, data privacy advancing
    "RI",  # Rhode Island  — AI regulation, data privacy advancing
    "DE",  # Delaware      — Personal Data Privacy Act in force 2025
]

# ── International Jurisdictions ───────────────────────────────────────────────
# Each entry must have a corresponding class in sources/international/<code>.py

ENABLED_INTERNATIONAL = [
    # Fully implemented with live feeds
    "EU",  # European Union — EUR-Lex SPARQL + EU AI Office RSS
    "GB",  # United Kingdom — Parliament Bills + legislation.gov.uk + GOV.UK
    "CA",  # Canada         — OpenParliament + Canada Gazette + ISED feed
    "SG",  # Singapore      — PDPC RSS + IMDA RSS + pinned framework docs
    "IN",  # India          — PIB RSS (MEITY) + DPDP Act + IndiaAI Mission
    "BR",  # Brazil         — ANPD RSS + Senate RSS + LGPD + AI Bill PL2338
    # Pinned docs + available feeds (translation via Claude)
    "JP",  # Japan          — METI English RSS + pinned AI governance docs
    "KR",  # South Korea    — MSIT press releases + PIPA/AI Act pinned docs
    "AU",  # Australia      — Voluntary AI Safety Standard + Federal Register
    # "CN",  # China          — Pinned docs only (no public CAC API)
]

# ── Module path maps ──────────────────────────────────────────────────────────
# Maps jurisdiction code → importable Python module path.
# Used by the orchestrator for dynamic class loading.

US_STATE_MODULE_MAP = {
    # Tier 1-2: native feeds
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
    # Tier 3: active AI/privacy pipeline
    "VA": "sources.states.virginia",
    "NJ": "sources.states.new_jersey",
    "MA": "sources.states.massachusetts",
    "OR": "sources.states.oregon",
    "MD": "sources.states.maryland",
    "GA": "sources.states.georgia",
    "AZ": "sources.states.arizona",
    "NC": "sources.states.north_carolina",
    "MI": "sources.states.michigan",
    "OH": "sources.states.ohio",
    "NV": "sources.states.nevada",
    "UT": "sources.states.utah",
    "IN": "sources.states.indiana",
    "TN": "sources.states.tennessee",
    "KY": "sources.states.kentucky",
    "SC": "sources.states.south_carolina",
    "WI": "sources.states.wisconsin",
    "MO": "sources.states.missouri",
    # Tier 4: emerging activity
    "LA": "sources.states.louisiana",
    "AL": "sources.states.alabama",
    "MS": "sources.states.mississippi",
    "AR": "sources.states.arkansas",
    "IA": "sources.states.iowa",
    "KS": "sources.states.kansas",
    "NE": "sources.states.nebraska",
    "NM": "sources.states.new_mexico",
    "OK": "sources.states.oklahoma",
    "WV": "sources.states.west_virginia",
    "ID": "sources.states.idaho",
    "MT": "sources.states.montana",
    "ND": "sources.states.north_dakota",
    "SD": "sources.states.south_dakota",
    "WY": "sources.states.wyoming",
    "AK": "sources.states.alaska",
    "HI": "sources.states.hawaii",
    "ME": "sources.states.maine",
    "NH": "sources.states.new_hampshire",
    "VT": "sources.states.vermont",
    "RI": "sources.states.rhode_island",
    "DE": "sources.states.delaware",
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
    "Federal": "🏛  US Federal",
    "PA": "🏢  Pennsylvania (US)",
    "VA": "🏢  Virginia (US)",
    "NY": "🏢  New York (US)",
    "CA": "🏢  California (US)",  # note: state code, not Canada
    "TX": "🏢  Texas (US)",
    "WA": "🏢  Washington (US)",
    "FL": "🏢  Florida (US)",
    "MN": "🏢  Minnesota (US)",
    "CT": "🏢  Connecticut (US)",
    "NJ": "🏢  New Jersey (US)",
    "MA": "🏢  Massachusetts (US)",
    "OR": "🏢  Oregon (US)",
    "MD": "🏢  Maryland (US)",
    "GA": "🏢  Georgia (US)",
    "AZ": "🏢  Arizona (US)",
    "NC": "🏢  North Carolina (US)",
    "EU": "🇪🇺  European Union",
    "GB": "🇬🇧  United Kingdom",
    "CA_INTL": "🇨🇦  Canada",  # disambiguated in reporter
    "JP": "🇯🇵  Japan",
    "CN": "🇨🇳  China",
    "AU": "🇦🇺  Australia",
    "SG": "🇸🇬  Singapore",
    "KR": "🇰🇷  South Korea",
    "IN": "🇮🇳  India",
    "BR": "🇧🇷  Brazil",
    "SG": "🇸🇬  Singapore",
    "KR": "🇰🇷  South Korea",
}

# ── LegiScan state code mapping (US states only) ──────────────────────────────
LEGISCAN_STATE_MAP = {
    "PA": "PA",
    "CA": "CA",
    "CO": "CO",
    "IL": "IL",
    "TX": "TX",
    "WA": "WA",
    "NY": "NY",
    "FL": "FL",
    "MN": "MN",
    "CT": "CT",
    "VA": "VA",
    "NJ": "NJ",
    "MA": "MA",
    "OR": "OR",
    "MD": "MD",
    "GA": "GA",
    "AZ": "AZ",
    "NC": "NC",
    # Note: "CA" here means California state; Canada international uses separate map
}

# ── Legacy alias (keeps old imports from states.py working) ──────────────────
ENABLED_STATES = ENABLED_US_STATES
STATE_MODULE_MAP = US_STATE_MODULE_MAP
