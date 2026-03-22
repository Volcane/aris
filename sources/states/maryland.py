"""
ARIS — Maryland Agent

Maryland is active on employment AI and automated decision-making:
  - Maryland AI in Employment Act (HB 1325 / SB 872, 2024) — did not pass; reintroduced
  - Maryland Online Data Privacy Act (MODPA, 2024) — enacted
  - Algorithmic accountability bills for government use
  - Active 2026 pipeline: comprehensive AI regulation, facial recognition

Sources:
  1. LegiScan API (primary — MD has annual sessions)
"""

from sources.state_agent_base import StateAgentBase


class MarylandAgent(StateAgentBase):
    """Maryland AI regulation and privacy legislation monitor."""

    state_code     = "MD"
    state_name     = "Maryland"
    legiscan_state = "MD"
