"""
ARIS — Massachusetts Agent

Massachusetts is active on employment AI, data privacy, and facial recognition:
  - Massachusetts Information Privacy Act (MIPA) — advancing
  - HD 5360 / SD 2517 — AI in hiring disclosure requirements
  - Facial recognition moratorium legislation
  - AI governance for state agencies (2024 executive action)
  - Active 2025-2026 pipeline on automated employment decisions

Sources:
  1. LegiScan API (primary)
"""

from sources.state_agent_base import StateAgentBase


class MassachusettsAgent(StateAgentBase):
    """Massachusetts AI regulation and privacy legislation monitor."""

    state_code     = "MA"
    state_name     = "Massachusetts"
    legiscan_state = "MA"
