"""
ARIS — Test Suite

Tests use real API calls with mocked responses where keys are absent.
Run with: python -m pytest tests/ -v
"""

import json
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime


# ── Federal Register tests ────────────────────────────────────────────────────

class TestFederalRegisterSource(unittest.TestCase):

    def setUp(self):
        from sources.federal_agent import FederalRegisterSource
        self.source = FederalRegisterSource()

    def test_normalise_produces_required_fields(self):
        raw = {
            "document_number": "2025-12345",
            "title":           "Artificial Intelligence Risk Management Framework",
            "type":            "RULE",
            "publication_date": "2025-01-15",
            "agency_names":    ["National Institute of Standards and Technology"],
            "abstract":        "This rule establishes requirements for AI risk management.",
            "html_url":        "https://federalregister.gov/d/2025-12345",
        }
        doc = self.source._normalise(raw)
        self.assertEqual(doc["id"],           "FR-2025-12345")
        self.assertEqual(doc["source"],       "federal_register")
        self.assertEqual(doc["jurisdiction"], "Federal")
        self.assertEqual(doc["doc_type"],     "RULE")
        self.assertIsNotNone(doc["published_date"])

    def test_status_mapping(self):
        from sources.federal_agent import _map_fr_status
        self.assertEqual(_map_fr_status("RULE"),     "Final Rule")
        self.assertEqual(_map_fr_status("PRORULE"),  "Proposed Rule")
        self.assertEqual(_map_fr_status("NOTICE"),   "Notice")
        self.assertEqual(_map_fr_status("PRESDOCU"), "Presidential Document")
        self.assertEqual(_map_fr_status("UNKNOWN"),  "UNKNOWN")

    @patch("sources.federal_agent.http_get")
    def test_search_filters_non_ai_documents(self, mock_get):
        mock_get.return_value = {
            "results": [
                {
                    "document_number": "2025-00001",
                    "title":           "Grains and Oilseeds Marketing",
                    "type":            "RULE",
                    "publication_date": "2025-01-01",
                    "agency_names":    ["USDA"],
                    "abstract":        "This rule covers grain markets.",
                    "html_url":        "https://example.com",
                },
                {
                    "document_number": "2025-00002",
                    "title":           "Artificial Intelligence in Healthcare",
                    "type":            "RULE",
                    "publication_date": "2025-01-02",
                    "agency_names":    ["FDA"],
                    "abstract":        "This rule addresses AI systems in clinical settings.",
                    "html_url":        "https://example.com",
                },
            ]
        }
        results = self.source.search(lookback_days=30)
        self.assertEqual(len(results), 1)
        self.assertIn("2025-00002", results[0]["id"])


# ── Congress.gov tests ────────────────────────────────────────────────────────

class TestCongressGovSource(unittest.TestCase):

    def test_normalise_bill(self):
        from sources.federal_agent import CongressGovSource
        source = CongressGovSource()
        bill = {
            "title":          "Algorithmic Accountability Act of 2025",
            "type":           "HR",
            "number":         "1234",
            "introducedDate": "2025-03-15",
            "latestAction":   {"text": "Referred to Committee"},
            "sponsors":       [{"fullName": "Rep. Jane Smith (D-CA)"}],
            "url":            "https://api.congress.gov/v3/bill/119/hr/1234",
        }
        doc = source._normalise(bill, congress=119)
        self.assertEqual(doc["id"],           "CONG-119-HR1234")
        self.assertEqual(doc["jurisdiction"], "Federal")
        self.assertIn("Algorithmic", doc["title"])


# ── Keyword / relevance filter tests ─────────────────────────────────────────

class TestKeywordFilter(unittest.TestCase):

    def test_ai_text_is_relevant(self):
        from utils.cache import is_ai_relevant
        self.assertTrue(is_ai_relevant("This bill regulates artificial intelligence systems"))
        self.assertTrue(is_ai_relevant("Machine learning algorithms used in hiring"))
        self.assertTrue(is_ai_relevant("Deepfake detection requirements"))

    def test_non_ai_text_is_not_relevant(self):
        from utils.cache import is_ai_relevant
        self.assertFalse(is_ai_relevant("Farm subsidy program for corn growers"))
        self.assertFalse(is_ai_relevant("Road maintenance budget allocation for 2025"))

    def test_keyword_score_range(self):
        from utils.cache import keyword_score
        score_high = keyword_score("artificial intelligence machine learning algorithmic decision")
        score_low  = keyword_score("weather forecast")
        self.assertGreater(score_high, score_low)
        self.assertGreaterEqual(score_high, 0.0)
        self.assertLessEqual(score_high, 1.0)


# ── Pennsylvania agent tests ──────────────────────────────────────────────────

class TestPennsylvaniaAgent(unittest.TestCase):

    def setUp(self):
        from sources.states.pennsylvania import PennsylvaniaAgent
        self.agent = PennsylvaniaAgent()

    def test_state_metadata(self):
        self.assertEqual(self.agent.state_code,    "PA")
        self.assertEqual(self.agent.state_name,    "Pennsylvania")
        self.assertEqual(self.agent.legiscan_state, "PA")

    def test_build_pa_url_house(self):
        url = self.agent._build_pa_url("House", "1925", "3")
        self.assertIn("H", url)
        self.assertIn("1925", url)

    def test_build_pa_url_senate(self):
        url = self.agent._build_pa_url("Senate", "939", "1")
        self.assertIn("S", url)
        self.assertIn("939", url)

    def test_parse_pa_xml_filters_non_ai_bills(self):
        xml = """<?xml version="1.0"?>
        <BillHistory>
          <Bill BillNumber="100" ShortTitle="Farm Bill for Pennsylvania Agriculture" 
                PrimeSponsor="Rep. Smith" LastAction="Referred to Committee" LastActionDate="2025-01-10"/>
          <Bill BillNumber="200" ShortTitle="Artificial Intelligence Disclosure Requirements" 
                PrimeSponsor="Rep. Jones" LastAction="Passed House" LastActionDate="2025-02-01"/>
          <Bill BillNumber="300" ShortTitle="Algorithmic Decision Transparency in Healthcare"
                PrimeSponsor="Rep. Brown" LastAction="Introduced" LastActionDate="2025-03-01"/>
        </BillHistory>"""

        results = self.agent._parse_pa_xml(xml, "House")
        titles = [r["title"] for r in results]
        self.assertEqual(len(results), 2)
        self.assertTrue(any("Artificial Intelligence" in t for t in titles))
        self.assertTrue(any("Algorithmic" in t for t in titles))
        self.assertFalse(any("Farm Bill" in t for t in titles))

    def test_normalise_legiscan_item(self):
        item = {
            "bill_id":         99999,
            "bill_number":     "HB1925",
            "title":           "AI in Healthcare Transparency Act",
            "status":          1,
            "last_action_date": "2025-10-06",
            "url":             "https://legiscan.com/PA/bill/HB1925/2025",
        }
        doc = self.agent._normalise_legiscan(item)
        self.assertEqual(doc["id"],           "PA-LS-99999")
        self.assertEqual(doc["jurisdiction"], "PA")
        self.assertEqual(doc["status"],       "Introduced")
        self.assertIsInstance(doc["published_date"], datetime)


# ── Database tests ────────────────────────────────────────────────────────────

class TestDatabase(unittest.TestCase):

    def setUp(self):
        """Use an in-memory SQLite DB for tests."""
        import utils.db as db_module
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from utils.db import Base

        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        db_module._engine  = engine
        db_module._Session = sessionmaker(bind=engine)

    def test_upsert_and_retrieve_document(self):
        from utils.db import upsert_document, get_unsummarized_documents
        doc = {
            "id":            "TEST-001",
            "source":        "test",
            "jurisdiction":  "Federal",
            "doc_type":      "RULE",
            "title":         "Test AI Rule",
            "url":           "https://example.com",
            "published_date": datetime(2025, 1, 15),
            "agency":        "Test Agency",
            "status":        "Final Rule",
            "full_text":     "This rule governs artificial intelligence systems.",
            "raw_json":      {"test": True},
        }
        changed = upsert_document(doc)
        self.assertTrue(changed)

        # Second upsert of identical content — should not flag as changed
        changed2 = upsert_document(doc)
        self.assertFalse(changed2)

        pending = get_unsummarized_documents()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].id, "TEST-001")

    def test_upsert_summary(self):
        from utils.db import upsert_document, upsert_summary, get_recent_summaries
        doc = {
            "id":            "TEST-002",
            "source":        "test",
            "jurisdiction":  "PA",
            "doc_type":      "Bill",
            "title":         "PA AI Transparency Bill",
            "url":           "https://example.com",
            "published_date": datetime(2025, 3, 1),
            "agency":        "PA General Assembly",
            "status":        "Introduced",
            "full_text":     "Requires AI disclosure in advertisements.",
            "raw_json":      {},
        }
        upsert_document(doc)
        upsert_summary({
            "document_id":     "TEST-002",
            "plain_english":   "Requires disclosure when AI generates ad content.",
            "requirements":    ["Must label AI-generated content"],
            "recommendations": ["Implement an AI content tracking system"],
            "action_items":    ["Audit all advertising pipelines for AI use"],
            "deadline":        None,
            "impact_areas":    ["Marketing", "Advertising"],
            "urgency":         "Medium",
            "relevance_score": 0.85,
            "model_used":      "claude-test",
        })

        summaries = get_recent_summaries(days=30)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["urgency"], "Medium")


# ── Interpreter JSON parsing tests ───────────────────────────────────────────

class TestInterpreterParsing(unittest.TestCase):

    def test_safe_parse_clean_json(self):
        from agents.interpreter import _safe_parse_json
        raw  = '{"relevance_score": 0.9, "plain_english": "Test summary."}'
        data = _safe_parse_json(raw)
        self.assertEqual(data["relevance_score"], 0.9)

    def test_safe_parse_json_in_markdown_fence(self):
        from agents.interpreter import _safe_parse_json
        raw = '```json\n{"relevance_score": 0.8}\n```'
        data = _safe_parse_json(raw)
        self.assertEqual(data["relevance_score"], 0.8)

    def test_safe_parse_invalid_returns_none(self):
        from agents.interpreter import _safe_parse_json
        data = _safe_parse_json("This is not JSON at all.")
        self.assertIsNone(data)

    def test_truncate(self):
        from agents.interpreter import _truncate
        long_text = "a" * 10000
        result    = _truncate(long_text, 5000)
        self.assertLessEqual(len(result), 5200)  # truncated + note
        self.assertIn("truncated", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
