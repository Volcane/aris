"""
ARIS — New Jersey State Agent

New Jersey is very active on privacy and AI legislation:
  - NJ Privacy Act (multiple versions introduced 2020-2025) — advancing
  - A4972/S3551 (2024) — AI in employment and hiring
  - AI disclosure bills for government use
  - Active 2026 pipeline: NJ runs annual sessions (new session starts 2026)

Sources:
  1. LegiScan API (primary — NJ has annual sessions, new session 2026)
"""

from sources.state_agent_base import StateAgentBase


class NewJerseyAgent(StateAgentBase):
    """New Jersey AI regulation and privacy legislation monitor."""

    state_code     = "NJ"
    state_name     = "New Jersey"
    legiscan_state = "NJ"
