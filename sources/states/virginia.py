"""
ARIS — Virginia State Agent (template / example)

To activate:
  1. Add "VA" to ENABLED_STATES in config/states.py
  2. That's it — this file already implements the base interface via LegiScan

Optional: override fetch_native() to pull Virginia's official RSS/XML feed
if one becomes available at https://lis.virginia.gov/
"""

from sources.state_agent_base import StateAgentBase


class VirginiaAgent(StateAgentBase):
    """
    Virginia AI legislation monitor.
    Uses LegiScan API (free tier, 30k calls/month).
    """

    state_code     = "VA"
    state_name     = "Virginia"
    legiscan_state = "VA"

    # Virginia does not currently expose a public XML/RSS bill feed,
    # so we rely entirely on LegiScan for bill discovery.
    # If Virginia adds a public data API, override fetch_native() here.
