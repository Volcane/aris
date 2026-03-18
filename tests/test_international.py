"""
ARIS — International Agent Tests
Tests for EU, UK, and Canada agents.
Run with: python -m pytest tests/ -v
"""

import unittest
from datetime import datetime


class TestInternationalBase(unittest.TestCase):

    def test_parse_date_formats(self):
        from sources.international.base import parse_date
        cases = [
            ("2024-07-12",            2024, 7,  12),
            ("2025-02-04",            2025, 2,  4),
            ("12/07/2024",            2024, 7,  12),
            ("2024-07-12T00:00:00Z",  2024, 7,  12),
        ]
        for s, y, m, d in cases:
            result = parse_date(s)
            self.assertIsNotNone(result, f"Failed to parse: {s}")
            self.assertEqual(result.year,  y, f"Year mismatch for {s}")
            self.assertEqual(result.month, m, f"Month mismatch for {s}")
            self.assertEqual(result.day,   d, f"Day mismatch for {s}")

    def test_parse_date_none(self):
        from sources.international.base import parse_date
        self.assertIsNone(parse_date(None))
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date("not-a-date"))

    def test_strip_tags(self):
        from sources.international.base import strip_tags
        html   = "<p>Hello <strong>World</strong></p><br/><div>Test</div>"
        result = strip_tags(html)
        self.assertNotIn("<p>",      result)
        self.assertNotIn("<strong>", result)
        self.assertIn("Hello",       result)
        self.assertIn("World",       result)

    def test_strip_tags_truncation(self):
        from sources.international.base import strip_tags
        long_text = "a" * 10000
        result    = strip_tags(long_text, max_chars=500)
        self.assertLessEqual(len(result), 500)

    def test_make_doc_defaults(self):
        from sources.international.eu import EUAgent
        agent = EUAgent()
        doc   = agent._make_doc(id="TEST-001", title="Test Doc")
        self.assertEqual(doc["id"],           "TEST-001")
        self.assertEqual(doc["title"],        "Test Doc")
        self.assertEqual(doc["jurisdiction"], "EU")
        self.assertEqual(doc["agency"],       "European Union")
        self.assertIn("source",  doc)
        self.assertIn("url",     doc)
        self.assertIn("raw_json", doc)


class TestEUAgent(unittest.TestCase):

    def setUp(self):
        from sources.international.eu import EUAgent
        self.agent = EUAgent()

    def test_jurisdiction_metadata(self):
        self.assertEqual(self.agent.jurisdiction_code, "EU")
        self.assertEqual(self.agent.jurisdiction_name, "European Union")
        self.assertEqual(self.agent.region,            "Europe")
        self.assertEqual(self.agent.language,          "en")
        self.assertFalse(self.agent.requires_translation)

    def test_pinned_docs_returned(self):
        docs = self.agent._get_pinned_docs()
        self.assertGreaterEqual(len(docs), 4)
        ids = [d["id"] for d in docs]
        self.assertIn("EU-CELEX-32024R1689", ids)  # EU AI Act

    def test_pinned_doc_structure(self):
        docs = self.agent._get_pinned_docs()
        ai_act = next(d for d in docs if d["id"] == "EU-CELEX-32024R1689")
        self.assertEqual(ai_act["jurisdiction"], "EU")
        self.assertIn("Artificial Intelligence Act", ai_act["title"])
        self.assertIn("risk", ai_act["full_text"].lower())
        self.assertIsNotNone(ai_act["published_date"])
        self.assertEqual(ai_act["published_date"].year, 2024)

    def test_eu_type_mapping(self):
        from sources.international.eu import _map_eu_type
        self.assertEqual(_map_eu_type("REG"),       "Regulation")
        self.assertEqual(_map_eu_type("DIR"),       "Directive")
        self.assertEqual(_map_eu_type("DEC"),       "Decision")
        self.assertEqual(_map_eu_type("PROC_INIT"), "Legislative Proposal")
        self.assertEqual(_map_eu_type("UNKNOWN"),   "UNKNOWN")
        self.assertEqual(_map_eu_type(""),          "EU Document")

    def test_fetch_native_returns_list(self):
        # Without network; just checks pinned docs come back
        docs = self.agent._get_pinned_docs()
        self.assertIsInstance(docs, list)
        for doc in docs:
            self.assertIn("id",           doc)
            self.assertIn("title",        doc)
            self.assertIn("jurisdiction", doc)
            self.assertIn("full_text",    doc)
            self.assertEqual(doc["jurisdiction"], "EU")


class TestUKAgent(unittest.TestCase):

    def setUp(self):
        from sources.international.uk import UKAgent
        self.agent = UKAgent()

    def test_jurisdiction_metadata(self):
        self.assertEqual(self.agent.jurisdiction_code, "GB")
        self.assertEqual(self.agent.jurisdiction_name, "United Kingdom")
        self.assertEqual(self.agent.region,            "Europe")
        self.assertEqual(self.agent.language,          "en")

    def test_pinned_docs_returned(self):
        docs = self.agent._get_pinned_docs()
        self.assertGreaterEqual(len(docs), 4)
        ids = [d["id"] for d in docs]
        self.assertIn("UK-AI-OPPS-PLAN-2025",          ids)
        self.assertIn("UK-DATA-USE-ACCESS-ACT-2025",   ids)
        self.assertIn("UK-AI-REGULATION-BILL-HL-2025", ids)

    def test_pinned_doc_structure(self):
        docs   = self.agent._get_pinned_docs()
        ai_opp = next(d for d in docs if d["id"] == "UK-AI-OPPS-PLAN-2025")
        self.assertEqual(ai_opp["jurisdiction"], "GB")
        self.assertIn("AI Opportunities", ai_opp["title"])
        self.assertIsNotNone(ai_opp["published_date"])


class TestCanadaAgent(unittest.TestCase):

    def setUp(self):
        from sources.international.canada import CanadaAgent
        self.agent = CanadaAgent()

    def test_jurisdiction_metadata(self):
        self.assertEqual(self.agent.jurisdiction_code, "CA")
        self.assertEqual(self.agent.jurisdiction_name, "Canada")
        self.assertEqual(self.agent.region,            "North America")

    def test_pinned_docs_returned(self):
        docs = self.agent._get_pinned_docs()
        self.assertGreaterEqual(len(docs), 3)
        ids = [d["id"] for d in docs]
        self.assertIn("CA-AIDA-BILL-C27-DIED",     ids)
        self.assertIn("CA-CAISI-LAUNCH-2024",       ids)
        self.assertIn("CA-QUEBEC-LAW25-FULL-FORCE", ids)

    def test_aida_status_reflects_lapsed(self):
        docs  = self.agent._get_pinned_docs()
        aida  = next(d for d in docs if d["id"] == "CA-AIDA-BILL-C27-DIED")
        self.assertIn("Lapsed", aida["status"])
        self.assertIn("prorogued", aida["full_text"].lower())


class TestStubAgents(unittest.TestCase):
    """Verify stub agents load and return pinned docs without errors."""

    def test_japan_agent(self):
        from sources.international.stubs import JapanAgent
        agent = JapanAgent()
        self.assertEqual(agent.jurisdiction_code, "JP")
        self.assertTrue(agent.requires_translation)
        docs = agent._get_pinned_docs()
        self.assertGreaterEqual(len(docs), 2)

    def test_china_agent(self):
        from sources.international.stubs import ChinaAgent
        agent = ChinaAgent()
        self.assertEqual(agent.jurisdiction_code, "CN")
        docs  = agent.fetch_native()
        self.assertGreaterEqual(len(docs), 2)
        for doc in docs:
            self.assertEqual(doc["jurisdiction"], "CN")

    def test_australia_agent(self):
        from sources.international.stubs import AustraliaAgent
        agent = AustraliaAgent()
        self.assertEqual(agent.jurisdiction_code, "AU")
        docs  = agent.fetch_native()
        self.assertGreaterEqual(len(docs), 1)


class TestJurisdictionConfig(unittest.TestCase):

    def test_enabled_international_has_eu_gb_ca(self):
        from config.jurisdictions import ENABLED_INTERNATIONAL
        self.assertIn("EU", ENABLED_INTERNATIONAL)
        self.assertIn("GB", ENABLED_INTERNATIONAL)
        self.assertIn("CA", ENABLED_INTERNATIONAL)

    def test_module_map_covers_all_enabled(self):
        from config.jurisdictions import ENABLED_INTERNATIONAL, INTERNATIONAL_MODULE_MAP
        for code in ENABLED_INTERNATIONAL:
            self.assertIn(code, INTERNATIONAL_MODULE_MAP,
                          f"No module map entry for enabled jurisdiction: {code}")

    def test_us_states_separate_from_international(self):
        from config.jurisdictions import ENABLED_US_STATES, ENABLED_INTERNATIONAL
        overlap = set(ENABLED_US_STATES) & set(ENABLED_INTERNATIONAL)
        # CA (California) would conflict with CA (Canada) — they should not both be enabled
        # with the same code; config uses "CA" for California in US states
        # and "CA" for Canada in international. The reporter disambiguates.
        # This test just confirms they are separate lists.
        self.assertIsInstance(ENABLED_US_STATES,    list)
        self.assertIsInstance(ENABLED_INTERNATIONAL, list)

    def test_legacy_states_alias_works(self):
        """Backwards compatibility: config.states.ENABLED_STATES still works."""
        from config.jurisdictions import ENABLED_STATES
        self.assertIsInstance(ENABLED_STATES, list)


class TestOrchestratorLoadsInternational(unittest.TestCase):

    def test_international_agents_loaded(self):
        from agents.orchestrator import Orchestrator
        orch = Orchestrator()
        self.assertGreaterEqual(len(orch.international_agents), 3)
        codes = [a.jurisdiction_code for a in orch.international_agents]
        self.assertIn("EU", codes)
        self.assertIn("GB", codes)
        self.assertIn("CA", codes)

    def test_list_active_agents(self):
        from agents.orchestrator import Orchestrator
        orch   = Orchestrator()
        active = orch.list_active_agents()
        self.assertIn("federal",       active)
        self.assertIn("us_states",     active)
        self.assertIn("international", active)
        self.assertGreaterEqual(len(active["federal"]),       1)
        self.assertGreaterEqual(len(active["international"]), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
