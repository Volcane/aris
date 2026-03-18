"""
ARIS — State Registry
Add state codes here to enable monitoring.
Each state must have a corresponding class in sources/states/.
"""

# States currently enabled for monitoring
ENABLED_STATES = [
    "PA",   # Pennsylvania — fully implemented
    # "VA", # Virginia       — add sources/states/virginia.py to enable
    # "NY", # New York       — add sources/states/new_york.py to enable
    # "CA", # California     — add sources/states/california.py to enable
    # "TX", # Texas          — add sources/states/texas.py to enable
    # "IL", # Illinois       — add sources/states/illinois.py to enable
    # "CO", # Colorado       — add sources/states/colorado.py to enable
]

# Mapping: state code → module path for dynamic import
STATE_MODULE_MAP = {
    "PA": "sources.states.pennsylvania",
    "VA": "sources.states.virginia",
    "NY": "sources.states.new_york",
    "CA": "sources.states.california",
    "TX": "sources.states.texas",
    "IL": "sources.states.illinois",
    "CO": "sources.states.colorado",
}

# LegiScan state code mapping (usually same as USPS code)
LEGISCAN_STATE_MAP = {
    "PA": "PA",
    "VA": "VA",
    "NY": "NY",
    "CA": "CA",
    "TX": "TX",
    "IL": "IL",
    "CO": "CO",
}
