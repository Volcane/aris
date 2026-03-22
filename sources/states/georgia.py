"""
ARIS — Georgia Agent

Georgia is emerging as an active AI regulation state:
  - SB 439 (2024) — AI disclosure in government use
  - Multiple employment AI bills
  - AI in healthcare prior authorisation legislation
  - Active 2026 pipeline: comprehensive AI governance bill expected

Sources:
  1. LegiScan API (primary — GA has annual sessions)
"""

from sources.state_agent_base import StateAgentBase


class GeorgiaAgent(StateAgentBase):
    """Georgia AI regulation and privacy legislation monitor."""

    state_code     = "GA"
    state_name     = "Georgia"
    legiscan_state = "GA"
