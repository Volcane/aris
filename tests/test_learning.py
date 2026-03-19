"""
ARIS — Learning Agent Tests
"""
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock


class TestLearningAgentHelpers(unittest.TestCase):

    def test_compute_quality_score_no_data(self):
        from agents.learning_agent import _compute_quality_score
        score = _compute_quality_score({"total_count": 0})
        self.assertEqual(score, 0.70)

    def test_compute_quality_score_all_positive(self):
        from agents.learning_agent import _compute_quality_score
        score = _compute_quality_score({
            "total_count": 20, "positive_count": 20, "negative_count": 0
        })
        self.assertGreater(score, 0.75)
        self.assertLessEqual(score, 0.98)

    def test_compute_quality_score_all_negative(self):
        from agents.learning_agent import _compute_quality_score
        score = _compute_quality_score({
            "total_count": 20, "positive_count": 0, "negative_count": 20
        })
        self.assertLess(score, 0.3)
        self.assertGreaterEqual(score, 0.10)

    def test_compute_quality_score_mixed(self):
        from agents.learning_agent import _compute_quality_score
        score = _compute_quality_score({
            "total_count": 10, "positive_count": 7, "negative_count": 3
        })
        self.assertGreater(score, 0.4)
        self.assertLess(score, 0.9)

    def test_default_profile_structure(self):
        from agents.learning_agent import _default_profile
        p = _default_profile("federal_register")
        self.assertEqual(p["source"], "federal_register")
        self.assertEqual(p["quality_score"], 0.70)
        self.assertEqual(p["total_count"], 0)
        self.assertIn("known_agencies", p)
        self.assertIn("known_doc_types", p)

    def test_weighted_keyword_score_empty_text(self):
        from agents.learning_agent import _weighted_keyword_score
        score = _weighted_keyword_score("", {})
        self.assertEqual(score, 0.0)

    def test_weighted_keyword_score_with_matches(self):
        from agents.learning_agent import _weighted_keyword_score
        from config.settings import AI_KEYWORDS
        weights = {kw: 1.0 for kw in AI_KEYWORDS}
        text    = "this regulation governs artificial intelligence and machine learning systems"
        score   = _weighted_keyword_score(text, weights)
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_weighted_keyword_score_boosted_keyword(self):
        from agents.learning_agent import _weighted_keyword_score
        from config.settings import AI_KEYWORDS
        weights = {kw: 1.0 for kw in AI_KEYWORDS}
        weights["artificial intelligence"] = 2.0   # boost this keyword
        text_with = "artificial intelligence regulation"
        text_without = "machine learning governance"
        score_with    = _weighted_keyword_score(text_with, weights)
        score_without = _weighted_keyword_score(text_without, weights)
        self.assertGreater(score_with, score_without)


class TestPriorityScoring(unittest.TestCase):

    def setUp(self):
        import sys, types
        for pkg in ['anthropic']:
            m = types.ModuleType(pkg)
            m.Anthropic = type('Anthropic', (), {'__init__': lambda s, **k: None})
            m.APIError  = Exception
            sys.modules[pkg] = m

    def _make_agent(self):
        from agents.learning_agent import LearningAgent
        agent = LearningAgent.__new__(LearningAgent)
        agent._client = None
        return agent

    def test_final_rule_scores_higher_than_notice(self):
        agent = self._make_agent()
        final_rule = {"id": "A", "doc_type": "RULE",   "status": "Final Rule",
                      "jurisdiction": "Federal", "fetched_at": datetime.utcnow().isoformat()}
        notice     = {"id": "B", "doc_type": "NOTICE", "status": "Notice",
                      "jurisdiction": "Federal", "fetched_at": datetime.utcnow().isoformat()}
        self.assertGreater(
            agent.score_analysis_priority(final_rule),
            agent.score_analysis_priority(notice)
        )

    def test_recent_doc_scores_higher(self):
        agent = self._make_agent()
        from datetime import timedelta
        recent = {"id": "R", "doc_type": "RULE", "status": "",
                  "jurisdiction": "Federal",
                  "fetched_at": datetime.utcnow().isoformat()}
        old    = {"id": "O", "doc_type": "RULE", "status": "",
                  "jurisdiction": "Federal",
                  "fetched_at": (datetime.utcnow() - timedelta(days=30)).isoformat()}
        self.assertGreater(
            agent.score_analysis_priority(recent),
            agent.score_analysis_priority(old)
        )

    def test_sort_by_priority_orders_correctly(self):
        agent = self._make_agent()
        docs = [
            {"id": "low",  "doc_type": "NOTICE", "status": "", "jurisdiction": "PA",      "fetched_at": "2024-01-01"},
            {"id": "high", "doc_type": "RULE",   "status": "", "jurisdiction": "Federal", "fetched_at": datetime.utcnow().isoformat()},
            {"id": "mid",  "doc_type": "PRORULE","status": "", "jurisdiction": "EU",      "fetched_at": datetime.utcnow().isoformat()},
        ]
        sorted_docs = agent.sort_by_priority(docs)
        ids = [d["id"] for d in sorted_docs]
        self.assertEqual(ids[0], "high")
        self.assertEqual(ids[-1], "low")

    def test_anomaly_detection_no_history(self):
        agent = self._make_agent()
        with patch("agents.learning_agent.get_source_profile", return_value=None):
            result = agent.detect_anomalies({"source": "test_source", "title": "AI Rule", "agency": "Test"})
            self.assertIsNone(result)  # not enough history

    def test_anomaly_detection_new_agency(self):
        agent = self._make_agent()
        profile = {
            "total_count":      20,
            "avg_title_length": 60.0,
            "known_agencies":   {"EPA", "FDA", "FTC"},
            "known_doc_types":  {"RULE", "NOTICE"},
        }
        with patch("agents.learning_agent.get_source_profile", return_value=profile):
            result = agent.detect_anomalies({
                "source":   "federal_register",
                "title":    "AI Rule Title",
                "agency":   "Brand New Unknown Agency",
                "doc_type": "RULE",
            })
            self.assertIsNotNone(result)
            self.assertIn("New agency", result)

    def test_should_skip_low_score(self):
        agent = self._make_agent()
        with patch.object(agent, "score_document_pre_filter", return_value=0.02):
            with patch("agents.learning_agent.is_known_false_positive_pattern", return_value=False):
                with patch("agents.learning_agent.get_source_profile", return_value=None):
                    skip, score, reason = agent.should_skip({"id": "X", "source": "test"})
                    self.assertTrue(skip)
                    self.assertIn("threshold", reason)

    def test_should_not_skip_high_score(self):
        agent = self._make_agent()
        with patch.object(agent, "score_document_pre_filter", return_value=0.75):
            with patch("agents.learning_agent.is_known_false_positive_pattern", return_value=False):
                with patch("agents.learning_agent.get_source_profile", return_value=None):
                    skip, score, reason = agent.should_skip({"id": "X", "source": "test"})
                    self.assertFalse(skip)

    def test_known_fp_pattern_always_skipped(self):
        agent = self._make_agent()
        with patch("agents.learning_agent.is_known_false_positive_pattern", return_value=True):
            skip, score, reason = agent.should_skip({"id": "X", "source": "test"})
            self.assertTrue(skip)
            self.assertIn("false-positive pattern", reason)


class TestLearningDatabase(unittest.TestCase):

    def setUp(self):
        import utils.db as db_module
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from utils.db import Base
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        db_module._engine  = engine
        db_module._Session = sessionmaker(bind=engine)

    def test_save_and_retrieve_feedback(self):
        from utils.db import save_feedback, get_recent_feedback
        fb_id = save_feedback({
            "document_id":       "DOC-001",
            "feedback":          "not_relevant",
            "reason":            "This is about grain subsidies, not AI",
            "source":            "federal_register",
            "agency":            "USDA",
            "jurisdiction":      "Federal",
            "doc_type":          "RULE",
            "matched_keywords":  ["algorithm"],
            "claude_score":      0.35,
            "user":              "user",
            "recorded_at":       datetime.utcnow(),
        })
        self.assertIsInstance(fb_id, int)

        feedbacks = get_recent_feedback(days=7)
        self.assertEqual(len(feedbacks), 1)
        self.assertEqual(feedbacks[0]["feedback"],  "not_relevant")
        self.assertEqual(feedbacks[0]["agency"],    "USDA")

    def test_source_profile_upsert(self):
        from utils.db import upsert_source_profile, get_source_profile
        profile = {
            "source": "test_source", "quality_score": 0.85,
            "total_count": 10, "positive_count": 8, "negative_count": 2,
        }
        upsert_source_profile("test_source", profile)
        retrieved = get_source_profile("test_source")
        self.assertEqual(retrieved["quality_score"], 0.85)

        # Update
        profile["quality_score"] = 0.90
        upsert_source_profile("test_source", profile)
        updated = get_source_profile("test_source")
        self.assertEqual(updated["quality_score"], 0.90)

    def test_keyword_weights_save_and_retrieve(self):
        from utils.db import save_keyword_weights, get_keyword_weights
        weights = {"artificial intelligence": 1.5, "algorithm": 0.6, "deepfake": 1.2}
        save_keyword_weights(weights)
        retrieved = get_keyword_weights()
        self.assertEqual(retrieved["artificial intelligence"], 1.5)
        self.assertEqual(retrieved["algorithm"], 0.6)

    def test_keyword_weights_single_row(self):
        from utils.db import save_keyword_weights, get_keyword_weights, KeywordWeights, get_session
        save_keyword_weights({"a": 1.0})
        save_keyword_weights({"b": 2.0})  # should replace, not accumulate
        with get_session() as session:
            count = session.query(KeywordWeights).count()
        self.assertEqual(count, 1)
        weights = get_keyword_weights()
        self.assertIn("b", weights)
        self.assertNotIn("a", weights)

    def test_prompt_adaptation_save_and_retrieve(self):
        from utils.db import save_prompt_adaptation, get_prompt_adaptations
        adapt_id = save_prompt_adaptation({
            "match_keys":  {"source": "federal_register", "agency": "USDA"},
            "instruction": "NOTE: USDA Federal Register documents about grain policy often mention 'algorithm' in passing without being about AI regulation.",
            "basis":       "6 false positives",
            "created_at":  datetime.utcnow().isoformat(),
        })
        self.assertIsInstance(adapt_id, int)

        adaptations = get_prompt_adaptations()
        self.assertEqual(len(adaptations), 1)
        self.assertIn("USDA", adaptations[0]["instruction"])

    def test_fetch_history_log(self):
        from utils.db import log_fetch_event, get_fetch_history
        log_fetch_event("federal_register", new_count=3, total_count=15)
        log_fetch_event("federal_register", new_count=1, total_count=12)
        log_fetch_event("legiscan_pa",      new_count=0, total_count=5)

        history = get_fetch_history(days=7)
        self.assertEqual(len(history), 3)
        sources = [h["source"] for h in history]
        self.assertIn("federal_register", sources)
        self.assertIn("legiscan_pa", sources)

    def test_count_feedback_by_type(self):
        from utils.db import save_feedback, count_feedback_by_type
        for fb in ["relevant", "relevant", "not_relevant", "partially_relevant"]:
            save_feedback({
                "document_id": f"DOC-{fb}", "feedback": fb,
                "source": "test", "recorded_at": datetime.utcnow(),
            })
        counts = count_feedback_by_type()
        self.assertEqual(counts.get("relevant", 0), 2)
        self.assertEqual(counts.get("not_relevant", 0), 1)

    def test_is_known_false_positive_pattern(self):
        from utils.db import save_feedback, is_known_false_positive_pattern
        # 8 false positives from same source+agency = auto-block
        for i in range(8):
            save_feedback({
                "document_id": f"DOC-{i}",
                "feedback":    "not_relevant",
                "source":      "legiscan_pa",
                "agency":      "PA General Assembly",
                "recorded_at": datetime.utcnow(),
            })
        doc = {"source": "legiscan_pa", "agency": "PA General Assembly"}
        self.assertTrue(is_known_false_positive_pattern(doc))

        doc2 = {"source": "legiscan_pa", "agency": "Different Agency"}
        self.assertFalse(is_known_false_positive_pattern(doc2))

    def test_stats_include_learning_fields(self):
        from utils.db import save_feedback, get_stats
        save_feedback({
            "document_id": "DOC-STAT",
            "feedback":    "not_relevant",
            "source":      "test",
            "recorded_at": datetime.utcnow(),
        })
        stats = get_stats()
        self.assertIn("total_feedback",     stats)
        self.assertIn("false_positives",    stats)
        self.assertIn("prompt_adaptations", stats)
        self.assertEqual(stats["total_feedback"],  1)
        self.assertEqual(stats["false_positives"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
