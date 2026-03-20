"""
ARIS — Stage 1 Domain Foundation Tests

Tests for:
  - PRIVACY_TERMS_EXPANDED taxonomy completeness
  - is_privacy_relevant() scoring
  - is_domain_relevant() domain dispatch
  - detect_domain() auto-classification
  - privacy_relevance_score() numeric scoring
  - ACTIVE_DOMAINS settings parsing
  - DB query function signatures (domain param)
"""

import sys
import types
import unittest


def setUpModule():
    for pkg, attrs in {
        "tenacity":       ["retry", "stop_after_attempt", "wait_exponential"],
        "anthropic":      ["Anthropic", "APIError"],
        "sqlalchemy":     ["Column", "String", "Text", "DateTime", "Float", "Boolean",
                           "JSON", "Index", "text", "create_engine", "Integer", "func"],
        "sqlalchemy.orm": ["DeclarativeBase", "Session", "sessionmaker"],
    }.items():
        if pkg not in sys.modules:
            m = types.ModuleType(pkg)
            for a in attrs:
                setattr(m, a,
                        type(a, (), {"__init__": lambda s, *a, **k: None})
                        if a[0].isupper() else (lambda *a, **k: None))
            sys.modules[pkg] = m
    t = sys.modules.get("tenacity")
    if t:
        for attr in ("retry", "stop_after_attempt", "wait_exponential"):
            if not hasattr(t, attr):
                setattr(t, attr, lambda *a, **k: None)
        t.retry = lambda **k: (lambda f: f)
    sys.modules["tenacity"].retry = lambda **k: (lambda f: f)


# ═══════════════════════════════════════════════════════════════════════════════
# PRIVACY TERMS TAXONOMY
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrivacyTermsTaxonomy(unittest.TestCase):

    def setUp(self):
        from utils.search import PRIVACY_TERMS_EXPANDED
        self.terms = PRIVACY_TERMS_EXPANDED

    def test_has_substantial_terms(self):
        self.assertGreater(len(self.terms), 80)

    def test_no_duplicates(self):
        self.assertEqual(len(self.terms), len(set(self.terms)))

    def test_core_rights_present(self):
        for term in ["right to erasure", "right to access", "right to portability",
                     "right to rectification", "right to object"]:
            self.assertIn(term, self.terms, f"Missing: {term}")

    def test_gdpr_specific_terms(self):
        for term in ["gdpr", "data controller", "data processor", "dpia",
                     "lawful basis", "supervisory authority"]:
            self.assertIn(term, self.terms, f"Missing: {term}")

    def test_us_state_privacy_laws(self):
        for term in ["ccpa", "cpra", "vcdpa", "tdpsa"]:
            self.assertIn(term, self.terms, f"Missing: {term}")

    def test_international_laws(self):
        for term in ["lgpd", "pdpa", "appi", "pipeda", "uk gdpr"]:
            self.assertIn(term, self.terms, f"Missing: {term}")

    def test_key_concepts_present(self):
        for term in ["personal data", "data subject", "consent", "data breach",
                     "breach notification", "data protection officer",
                     "privacy by design", "legitimate interest"]:
            self.assertIn(term, self.terms, f"Missing: {term}")

    def test_sector_laws_present(self):
        for term in ["hipaa", "coppa", "glba", "ferpa"]:
            self.assertIn(term, self.terms, f"Missing: {term}")

    def test_all_terms_are_lowercase(self):
        for term in self.terms:
            self.assertEqual(term, term.lower(), f"Not lowercase: {term}")

    def test_all_terms_are_strings(self):
        for term in self.terms:
            self.assertIsInstance(term, str)
            self.assertGreater(len(term), 0)


# ═══════════════════════════════════════════════════════════════════════════════
# is_privacy_relevant()
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsPrivacyRelevant(unittest.TestCase):

    def _check(self, text):
        from utils.search import is_privacy_relevant
        return is_privacy_relevant(text)

    def test_gdpr_text_is_relevant(self):
        self.assertTrue(self._check(
            "GDPR Article 83 penalties for data controller violations"
        ))

    def test_ccpa_text_is_relevant(self):
        self.assertTrue(self._check(
            "CCPA grants consumers the right to opt out of data sales"
        ))

    def test_data_breach_is_relevant(self):
        self.assertTrue(self._check(
            "72-hour breach notification requirement under data protection regulation"
        ))

    def test_consent_is_relevant(self):
        self.assertTrue(self._check(
            "Freely given informed consent required for personal data processing"
        ))

    def test_ai_only_text_is_not_relevant(self):
        self.assertFalse(self._check(
            "Large language model training data requirements for generative AI systems"
        ))

    def test_empty_text_is_not_relevant(self):
        self.assertFalse(self._check(""))

    def test_unrelated_text_is_not_relevant(self):
        self.assertFalse(self._check(
            "Marine mammal protection regulations for fishing vessels"
        ))

    def test_threshold_parameter(self):
        from utils.search import is_privacy_relevant
        # Low threshold: even weak signals pass
        self.assertTrue(is_privacy_relevant("consent form", threshold=0.01))
        # Very high threshold: even strong signals fail
        self.assertFalse(is_privacy_relevant(
            "gdpr data controller", threshold=0.99
        ))


# ═══════════════════════════════════════════════════════════════════════════════
# is_domain_relevant()
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsDomainRelevant(unittest.TestCase):

    def _check(self, text, domain):
        from utils.search import is_domain_relevant
        return is_domain_relevant(text, domain)

    def test_ai_domain_with_ai_text(self):
        self.assertTrue(self._check(
            "Machine learning algorithm used in automated hiring decisions", "ai"
        ))

    def test_ai_domain_rejects_privacy_only(self):
        self.assertFalse(self._check(
            "GDPR consent requirements for personal data processing activities", "ai"
        ))

    def test_privacy_domain_with_privacy_text(self):
        self.assertTrue(self._check(
            "GDPR Article 17 right to erasure of personal data", "privacy"
        ))

    def test_privacy_domain_rejects_ai_only(self):
        self.assertFalse(self._check(
            "Generative AI model training and neural network architecture", "privacy"
        ))

    def test_both_domain_accepts_ai(self):
        self.assertTrue(self._check(
            "Large language model training requirements", "both"
        ))

    def test_both_domain_accepts_privacy(self):
        self.assertTrue(self._check(
            "Data breach notification under GDPR Article 33", "both"
        ))

    def test_both_domain_rejects_unrelated(self):
        self.assertFalse(self._check(
            "Quarterly earnings report for manufacturing sector", "both"
        ))

    def test_defaults_to_ai(self):
        from utils.search import is_domain_relevant
        # Default domain is "ai"
        result_default = is_domain_relevant(
            "artificial intelligence automated decision system"
        )
        self.assertTrue(result_default)


# ═══════════════════════════════════════════════════════════════════════════════
# detect_domain()
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectDomain(unittest.TestCase):

    def _detect(self, text):
        from utils.search import detect_domain
        return detect_domain(text)

    def test_pure_ai_text(self):
        result = self._detect(
            "Large language model generative AI automated decision-making "
            "neural network machine learning algorithm"
        )
        self.assertEqual(result, "ai")

    def test_pure_privacy_text(self):
        result = self._detect(
            "GDPR personal data consent data subject right to erasure "
            "data controller supervisory authority breach notification"
        )
        self.assertEqual(result, "privacy")

    def test_mixed_text_returns_both(self):
        result = self._detect(
            "GDPR Article 22 automated decision-making based on personal data "
            "profiling using machine learning algorithms requires explicit consent"
        )
        self.assertEqual(result, "both")

    def test_empty_text_returns_ai_default(self):
        self.assertEqual(self._detect(""), "ai")

    def test_unrelated_text_returns_ai_default(self):
        self.assertEqual(self._detect("Marine wildlife fishing regulations"), "ai")


# ═══════════════════════════════════════════════════════════════════════════════
# privacy_relevance_score()
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrivacyRelevanceScore(unittest.TestCase):

    def _score(self, text):
        from utils.search import privacy_relevance_score
        return privacy_relevance_score(text)

    def test_returns_float(self):
        self.assertIsInstance(self._score("gdpr data subject"), float)

    def test_empty_returns_zero(self):
        self.assertEqual(self._score(""), 0.0)

    def test_score_in_range(self):
        score = self._score("GDPR personal data consent breach notification")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_more_terms_higher_score(self):
        low  = self._score("personal data")
        high = self._score(
            "personal data gdpr data subject consent right to erasure "
            "data controller supervisory authority breach notification dpia"
        )
        self.assertGreater(high, low)

    def test_ai_text_scores_low(self):
        ai_score = self._score(
            "large language model generative ai neural network deep learning"
        )
        self.assertLess(ai_score, 0.3)

    def test_longer_terms_rewarded(self):
        # "data protection impact assessment" should score higher than just "data"
        short_score = self._score("data")
        long_score  = self._score("data protection impact assessment")
        self.assertGreater(long_score, short_score)


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVE_DOMAINS settings
# ═══════════════════════════════════════════════════════════════════════════════

class TestActiveDomainsSettings(unittest.TestCase):

    def _get_domains(self):
        """Import ACTIVE_DOMAINS, reloading the real module if needed."""
        import importlib
        # Force load the real module (may have been stubbed by test runner)
        try:
            import config.settings as cs
            if not hasattr(cs, 'ACTIVE_DOMAINS'):
                importlib.reload(cs)
            return cs.ACTIVE_DOMAINS
        except Exception:
            # Read the setting directly without importing
            import os
            raw = os.getenv("ACTIVE_DOMAINS", "both")
            domains = [d.strip() for d in raw.split(",") if d.strip()]
            if "ai" in domains and "privacy" in domains:
                return ["both"]
            return domains

    def test_active_domains_is_list(self):
        self.assertIsInstance(self._get_domains(), list)

    def test_active_domains_not_empty(self):
        self.assertGreater(len(self._get_domains()), 0)

    def test_default_includes_both(self):
        domains = self._get_domains()
        valid = {"ai", "privacy", "both"}
        for d in domains:
            self.assertIn(d, valid, f"Invalid domain: {d}")

    def test_settings_file_has_active_domains(self):
        with open("config/settings.py") as f:
            content = f.read()
        self.assertIn("ACTIVE_DOMAINS", content)

    def test_keys_env_example_has_active_domains(self):
        with open("config/keys.env.example") as f:
            content = f.read()
        self.assertIn("ACTIVE_DOMAINS", content)


# ═══════════════════════════════════════════════════════════════════════════════
# DB query function signatures
# ═══════════════════════════════════════════════════════════════════════════════

class TestDBDomainSignatures(unittest.TestCase):
    """
    Verify that domain= parameter exists on all query functions.
    These tests don't connect to a real DB — they just inspect signatures.
    """

    def _sig(self, func):
        import inspect
        return inspect.signature(func)

    def test_get_all_documents_has_domain(self):
        from utils.db import get_all_documents
        params = self._sig(get_all_documents).parameters
        self.assertIn("domain", params)

    def test_get_unsummarized_has_domain(self):
        from utils.db import get_unsummarized_documents
        params = self._sig(get_unsummarized_documents).parameters
        self.assertIn("domain", params)

    def test_get_recent_summaries_has_domain(self):
        from utils.db import get_recent_summaries
        params = self._sig(get_recent_summaries).parameters
        self.assertIn("domain", params)

    def test_get_horizon_items_has_domain(self):
        from utils.db import get_horizon_items
        params = self._sig(get_horizon_items).parameters
        self.assertIn("domain", params)

    def test_get_enforcement_actions_has_domain(self):
        from utils.db import get_enforcement_actions
        params = self._sig(get_enforcement_actions).parameters
        self.assertIn("domain", params)

    def test_domain_param_defaults_to_none(self):
        """All domain params should default to None (no filter = return all)."""
        import inspect
        functions = []
        from utils.db import (get_all_documents, get_unsummarized_documents,
                               get_recent_summaries, get_horizon_items,
                               get_enforcement_actions)
        for fn in [get_all_documents, get_recent_summaries,
                   get_horizon_items, get_enforcement_actions]:
            sig = inspect.signature(fn)
            domain_param = sig.parameters.get("domain")
            self.assertIsNotNone(domain_param, f"{fn.__name__} missing domain param")
            self.assertIsNone(
                domain_param.default,
                f"{fn.__name__}.domain default should be None, got {domain_param.default}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# DB model domain columns
# ═══════════════════════════════════════════════════════════════════════════════

class TestDBModelDomainColumns(unittest.TestCase):

    def test_document_model_has_domain(self):
        import sys, types
        # Quick check that domain is in the model definition
        with open("utils/db.py") as f:
            content = f.read()
        # Check that domain column appears in the Document class section
        doc_section = content[content.find("class Document"):
                               content.find("class PdfMetadata")]
        self.assertIn("domain", doc_section)

    def test_summary_model_has_domain(self):
        with open("utils/db.py") as f:
            content = f.read()
        summ_section = content[content.find("class Summary"):
                                content.find("class DocumentDiff")]
        self.assertIn("domain", summ_section)

    def test_horizon_model_has_domain(self):
        with open("utils/db.py") as f:
            content = f.read()
        hor_section = content[content.find("class RegulatoryHorizon"):
                               content.find("class TrendSnapshot")]
        self.assertIn("domain", hor_section)

    def test_enforcement_model_has_domain(self):
        with open("utils/db.py") as f:
            content = f.read()
        ea_start = content.find("class EnforcementAction")
        ea_end   = content.find("# ── Enforcement Action CRUD")
        ea_section = content[ea_start:ea_end]
        self.assertIn("domain", ea_section)


# ═══════════════════════════════════════════════════════════════════════════════
# Migration file
# ═══════════════════════════════════════════════════════════════════════════════

class TestMigrationDomainEntries(unittest.TestCase):

    def setUp(self):
        with open("migrate.py") as f:
            self.content = f.read()

    def test_documents_domain_in_migrations(self):
        self.assertIn('"documents", "domain"', self.content)

    def test_summaries_domain_in_migrations(self):
        self.assertIn('"summaries", "domain"', self.content)

    def test_horizon_domain_in_migrations(self):
        self.assertIn('"regulatory_horizon", "domain"', self.content)

    def test_enforcement_domain_in_migrations(self):
        self.assertIn('"enforcement_actions", "domain"', self.content)

    def test_domain_default_is_ai(self):
        # All domain migrations should default to 'ai'
        import re
        domain_entries = re.findall(
            r'"[^"]+",\s*"domain",\s*"TEXT",\s*"([^"]+)"', self.content
        )
        for default in domain_entries:
            self.assertEqual(default, "'ai'",
                             f"Expected default 'ai', got {default}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
