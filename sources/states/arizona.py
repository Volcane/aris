"""
ARIS — Arizona Agent

Arizona is active on AI disclosure and automated decision-making:
  - AI-generated content disclosure requirements
  - Chatbot regulation bills (2025-2026 pipeline active)
  - Employment AI disclosure legislation
  - AI in financial services guidance

Sources:
  1. LegiScan API (primary — AZ has annual sessions)
"""

from sources.state_agent_base import StateAgentBase


class ArizonaAgent(StateAgentBase):
    """Arizona AI regulation and privacy legislation monitor."""

    state_code     = "AZ"
    state_name     = "Arizona"
    legiscan_state = "AZ"
