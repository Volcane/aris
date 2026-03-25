# -*- coding: utf-8 -*-
"""
ARIS — Enforcement & Litigation Agent Tests
"""
import json
import sys
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


def setUpModule():
    for pkg, attrs in {
        'tenacity':      ['retry', 'stop_after_attempt', 'wait_exponential'],
        'anthropic':     ['Anthropic', 'APIError'],
        'sqlalchemy':    ['Column', 'String', 'Text', 'DateTime', 'Float', 'Boolean',
                          'JSON', 'Index', 'text', 'create_engine', 'Integer', 'func'],
        'sqlalchemy.orm': ['DeclarativeBase', 'Session', 'sessionmaker'],
    }.items():
        if pkg not in sys.modules:
            m = types.ModuleType(pkg)
            for a in attrs:
                setattr(m, a,
                        type(a, (), {'__init__': lambda s, *a, **k: None})
                        if a[0].isupper() else (lambda *a, **k: None))
            sys.modules[pkg] = m

    # Ensure tenacity has all needed attributes even if already stub-loaded
    t = sys.modules.get('tenacity')
    if t:
        for attr in ('retry', 'stop_after_attempt', 'wait_exponential'):
            if not hasattr(t, attr):
                setattr(t, attr, lambda *a, **k: None)
        t.retry = lambda **k: (lambda f: f)
    sys.modules['tenacity'].retry = lambda **k: (lambda f: f)

    # Ensure config.settings has the COURTLISTENER_KEY attribute
    try:
        import config.settings as cs
        if not hasattr(cs, 'COURTLISTENER_KEY'):
            cs.COURTLISTENER_KEY = ''
    except Exception:
        pass


# ── RSS sample fixtures ────────────────────────────────────────────────────────

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>FTC Press Releases</title>
    <item>
      <title>FTC Takes Action Against Company for Using Deceptive AI Algorithms</title>
      <link>https://www.ftc.gov/news/press-releases/2025/01/ftc-action-ai-algorithms</link>
      <description>The FTC filed a complaint alleging the company used deceptive
        artificial intelligence algorithms to target vulnerable consumers with
        discriminatory automated decision-making in credit scoring.</description>
      <pubDate>Wed, 15 Jan 2025 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>FTC Issues Report on Marine Wildlife Protection</title>
      <link>https://www.ftc.gov/news/2025/01/marine-wildlife</link>
      <description>The FTC released guidance on marine wildlife conservation efforts
        and fishing regulations in the Pacific Northwest region.</description>
      <pubDate>Mon, 13 Jan 2025 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>FTC Settles with Employer Over Algorithmic Hiring Bias</title>
      <link>https://www.ftc.gov/news/press-releases/2025/01/ftc-algorithmic-hiring</link>
      <description>The company agreed to pay $2.5 million civil penalty and stop
        using machine learning algorithms that produced discriminatory outcomes
        in automated hiring decisions. The settlement requires bias audits.</description>
      <pubDate>Fri, 10 Jan 2025 14:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>SEC Litigation Releases</title>
  <entry>
    <title>SEC Charges AI Startup with Fraud in Algorithmic Trading System</title>
    <link href="https://www.sec.gov/litigation/2025-ai-fraud"/>
    <summary>The Securities and Exchange Commission charged a company with securities
      fraud related to misrepresentations about their artificial intelligence
      trading algorithm's performance and risk management capabilities.</summary>
    <published>2025-02-20T10:00:00Z</published>
  </entry>
</feed>"""

EMPTY_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Empty</title></channel></rss>"""

MALFORMED_RSS = "this is not xml at all"


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseRSSFeed(unittest.TestCase):

    def _parse(self, xml):
        from sources.enforcement_agent import _parse_rss_feed
        return _parse_rss_feed(xml)

    def test_parses_rss_items(self):
        items = self._parse(SAMPLE_RSS)
        self.assertEqual(len(items), 3)

    def test_extracts_title(self):
        items = self._parse(SAMPLE_RSS)
        self.assertIn('FTC', items[0]['title'])

    def test_extracts_link(self):
        items = self._parse(SAMPLE_RSS)
        self.assertIn('ftc.gov', items[0]['link'])

    def test_extracts_description(self):
        items = self._parse(SAMPLE_RSS)
        self.assertGreater(len(items[0]['description']), 0)

    def test_extracts_date(self):
        items = self._parse(SAMPLE_RSS)
        self.assertIn('2025', items[0]['date'])

    def test_parses_atom_feed(self):
        items = self._parse(ATOM_FEED)
        self.assertEqual(len(items), 1)
        self.assertIn('SEC', items[0]['title'])

    def test_empty_feed_returns_empty(self):
        items = self._parse(EMPTY_RSS)
        self.assertEqual(items, [])

    def test_malformed_xml_returns_empty(self):
        items = self._parse(MALFORMED_RSS)
        self.assertEqual(items, [])


class TestParseDateFormats(unittest.TestCase):

    def _parse(self, s):
        from sources.enforcement_agent import _parse_rss_date
        return _parse_rss_date(s)

    def test_rss_date_format(self):
        result = self._parse("Wed, 15 Jan 2025 10:00:00 GMT")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 1)

    def test_iso_date_format(self):
        result = self._parse("2025-02-20T10:00:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2025)

    def test_simple_date(self):
        result = self._parse("2025-03-15")
        self.assertIsNotNone(result)
        self.assertEqual(result.month, 3)

    def test_none_returns_none(self):
        self.assertIsNone(self._parse(None))

    def test_empty_returns_none(self):
        self.assertIsNone(self._parse(""))

    def test_garbage_returns_none(self):
        self.assertIsNone(self._parse("not a date at all"))


class TestRelevanceScoring(unittest.TestCase):

    def test_ai_text_is_relevant(self):
        from sources.enforcement_agent import _is_enforcement_relevant
        self.assertTrue(_is_enforcement_relevant(
            "FTC action against company using artificial intelligence algorithms"
        ))

    def test_non_ai_text_not_relevant(self):
        from sources.enforcement_agent import _is_enforcement_relevant
        self.assertFalse(_is_enforcement_relevant(
            "Marine wildlife protection and fishing regulations in Pacific Northwest"
        ))

    def test_score_higher_for_more_terms(self):
        from sources.enforcement_agent import _score_relevance
        s1 = _score_relevance("artificial intelligence")
        s2 = _score_relevance(
            "artificial intelligence machine learning algorithmic discrimination bias"
        )
        self.assertGreater(s2, s1)

    def test_score_in_range(self):
        from sources.enforcement_agent import _score_relevance
        score = _score_relevance("automated decision system facial recognition bias")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_empty_text_scores_zero(self):
        from sources.enforcement_agent import _score_relevance
        self.assertEqual(_score_relevance(""), 0.0)


class TestPenaltyExtraction(unittest.TestCase):

    def _extract(self, text):
        from sources.enforcement_agent import _extract_penalty
        return _extract_penalty(text)

    def test_dollar_million(self):
        result = self._extract("Company agreed to pay $2.5 million civil penalty")
        self.assertIsNotNone(result)
        self.assertIn('2.5', result)

    def test_dollar_amount(self):
        result = self._extract("civil penalty of $500,000 for violations")
        self.assertIsNotNone(result)

    def test_euro_amount(self):
        result = self._extract("GDPR fine of €750,000 imposed by DPC")
        self.assertIsNotNone(result)
        self.assertIn('750', result)

    def test_no_penalty_returns_none(self):
        result = self._extract("FTC investigation launched into AI practices")
        self.assertIsNone(result)


class TestRelatedRegsFinder(unittest.TestCase):

    def _find(self, text):
        from sources.enforcement_agent import _find_related_regs
        return _find_related_regs(text)

    def test_finds_ftc_act(self):
        regs = self._find("violation of Section 5 of the FTC Act")
        self.assertIn("us_ftc_ai", regs)

    def test_finds_gdpr(self):
        regs = self._find("GDPR Article 22 automated decision enforcement")
        # gdpr now maps to eu_gdpr_full (full GDPR baseline added in Stage 2)
        self.assertTrue(
            "eu_gdpr_full" in regs or "eu_gdpr_ai" in regs,
            f"Expected a GDPR baseline in {regs}"
        )

    def test_finds_title_vii(self):
        regs = self._find("discriminatory hiring under Title VII requirements")
        self.assertIn("us_sector_ai", regs)

    def test_finds_colorado_ai(self):
        regs = self._find("Colorado AI Act developer obligations violated")
        self.assertIn("colorado_ai", regs)

    def test_no_match_returns_empty(self):
        regs = self._find("marine wildlife fishing regulations pacific northwest")
        self.assertEqual(regs, [])

    def test_returns_sorted_list(self):
        regs = self._find("GDPR Article 22 and FTC Act Section 5 violations")
        self.assertEqual(sorted(regs), regs)


FTC_MOCK_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>FTC News</title>
    <item>
      <title>FTC Takes Action Against Company for Using Deceptive AI Algorithms</title>
      <description>The FTC filed a complaint alleging the company used deceptive
        artificial intelligence algorithms to target vulnerable consumers with
        discriminatory automated decision-making in credit scoring. Civil penalty $2.5 million.</description>
      <link>https://www.ftc.gov/news/press-releases/2025/01/ftc-action-ai-algorithms</link>
      <pubDate>Wed, 15 Jan 2025 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>FTC Issues Report on Marine Wildlife Protection</title>
      <description>The FTC released guidance on marine wildlife conservation efforts
        and fishing regulations in the Pacific Northwest region.</description>
      <link>https://www.ftc.gov/news/2025/01/marine-wildlife</link>
      <pubDate>Mon, 13 Jan 2025 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>FTC Settles with Employer Over Algorithmic Hiring Bias</title>
      <description>The company agreed to pay $2.5 million civil penalty and stop
        using machine learning algorithms that produced discriminatory outcomes
        in automated hiring decisions. The settlement requires bias audits.</description>
      <link>https://www.ftc.gov/news/press-releases/2025/01/ftc-algorithmic-hiring</link>
      <pubDate>Fri, 10 Jan 2025 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class TestFTCSource(unittest.TestCase):

    def _source(self):
        from sources.enforcement_agent import FTCEnforcementSource
        return FTCEnforcementSource()

    def _fetch(self, days=3650):
        """Helper: mock http_get_text (RSS feed) — FTC now uses RSS not JSON API."""
        src = self._source()
        with patch('sources.enforcement_agent.http_get_text', return_value=FTC_MOCK_RSS):
            return src.fetch(lookback_days=days)

    def test_filters_non_ai_items(self):
        results = self._fetch()
        titles = [r['title'] for r in results]
        self.assertTrue(any('AI' in t or 'Algorithm' in t or 'algorithm' in t.lower()
                            for t in titles))
        self.assertFalse(any('Marine' in t for t in titles))

    def test_normalised_fields_present(self):
        results = self._fetch()
        if results:
            r = results[0]
            for field in ('id', 'source', 'action_type', 'title', 'url',
                           'agency', 'jurisdiction', 'relevance_score'):
                self.assertIn(field, r, f"Missing field: {field}")

    def test_source_is_ftc(self):
        results = self._fetch()
        for r in results:
            self.assertEqual(r['source'], 'ftc')

    def test_jurisdiction_is_federal(self):
        results = self._fetch()
        for r in results:
            self.assertEqual(r['jurisdiction'], 'Federal')

    def test_deduplication_on_multiple_feeds(self):
        results = self._fetch()
        ids = [r['id'] for r in results]
        self.assertEqual(len(ids), len(set(ids)))

    def test_cutoff_filters_old_items(self):
        results = self._fetch(days=1)
        for r in results:
            if r.get('published_date'):
                cutoff = datetime.utcnow() - timedelta(days=1)
                self.assertGreaterEqual(r['published_date'], cutoff)

    def test_penalty_extracted(self):
        results = self._fetch()
        penalty_results = [r for r in results if r.get('penalty_amount')]
        self.assertGreater(len(penalty_results), 0)

    def test_feed_failure_returns_empty(self):
        src = self._source()
        with patch('sources.enforcement_agent.http_get_text',
                   side_effect=Exception("Connection refused")):
            results = src.fetch()
        self.assertEqual(results, [])


class TestICOSource(unittest.TestCase):

    def test_jurisdiction_is_gb(self):
        from sources.enforcement_agent import ICOEnforcementSource
        src = ICOEnforcementSource()
        with patch('sources.enforcement_agent.http_get_text', return_value=SAMPLE_RSS):
            results = src.fetch(lookback_days=3650)
        for r in results:
            self.assertEqual(r['jurisdiction'], 'GB')

    def test_related_regs_includes_gdpr(self):
        from sources.enforcement_agent import ICOEnforcementSource
        src = ICOEnforcementSource()
        with patch('sources.enforcement_agent.http_get_text', return_value=SAMPLE_RSS):
            results = src.fetch(lookback_days=3650)
        for r in results:
            self.assertIn('eu_gdpr_ai', r.get('related_regs', []))


class TestCourtListenerSource(unittest.TestCase):

    def _source(self):
        sys.modules.setdefault('config.settings', types.ModuleType('config.settings'))
        sys.modules['config.settings'].COURTLISTENER_KEY = ''
        from sources.enforcement_agent import CourtListenerSource
        return CourtListenerSource()

    def test_normalises_opinion_type(self):
        from sources.enforcement_agent import CourtListenerSource
        src = CourtListenerSource()
        mock_response = {
            "results": [
                {
                    "id":           "12345",
                    "caseName":     "Smith v. Algorithm Corp.",
                    "court":        "United States District Court, S.D.N.Y.",
                    "dateFiled":    "2025-01-15",
                    "docketNumber": "1:25-cv-00123",
                    "snippet":      "Plaintiff alleges artificial intelligence system used in "
                                    "hiring discriminated against protected class members.",
                    "absolute_url": "/opinion/12345/smith-v-algorithm/",
                }
            ]
        }
        with patch('sources.enforcement_agent.http_get', return_value=mock_response):
            results = src.fetch(lookback_days=3650)
        if results:
            self.assertEqual(results[0]['action_type'], 'opinion')
            self.assertEqual(results[0]['source'], 'courtlistener')
            self.assertIn('courtlistener.com', results[0]['url'])

    def test_empty_results_handled(self):
        from sources.enforcement_agent import CourtListenerSource
        src = CourtListenerSource()
        with patch('sources.enforcement_agent.http_get', return_value={"results": []}):
            results = src.fetch()
        self.assertEqual(results, [])

    def test_api_failure_handled(self):
        from sources.enforcement_agent import CourtListenerSource
        src = CourtListenerSource()
        with patch('sources.enforcement_agent.http_get',
                   side_effect=Exception("API error")):
            results = src.fetch()
        self.assertEqual(results, [])


# ═══════════════════════════════════════════════════════════════════════════════
# NEWS SOURCES: IAPP, REGULATORY OVERSIGHT, COURTHOUSE NEWS
# ═══════════════════════════════════════════════════════════════════════════════

NEWS_MOCK_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>FTC Settles with AI Company Over Deceptive Algorithmic Claims for $3.2 Million</title>
      <description>The Federal Trade Commission reached a settlement with an AI startup
        over allegations the company made deceptive claims about its machine learning algorithms
        used in automated hiring decisions. The consent order requires bias audits.</description>
      <link>https://example.com/ftc-ai-settlement</link>
      <pubDate>Mon, 10 Mar 2025 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>State AG Files Lawsuit Against Data Broker for Privacy Violations</title>
      <description>The state attorney general filed a complaint against a data broker alleging
        violations of the state consumer privacy act for selling personal data without consent.
        Civil penalties of up to $500,000 sought.</description>
      <link>https://example.com/state-ag-privacy-lawsuit</link>
      <pubDate>Fri, 07 Mar 2025 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>AI Startup Raises $50 Million Series B Funding Round</title>
      <description>A generative AI startup announced a major funding round led by venture capital
        firms to expand its large language model capabilities.</description>
      <link>https://example.com/ai-funding</link>
      <pubDate>Thu, 06 Mar 2025 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


class TestNewsEnforcementFilter(unittest.TestCase):
    """Test the stricter news enforcement relevance filter."""

    def test_passes_enforcement_with_domain(self):
        from sources.enforcement_agent import _is_news_enforcement_relevant
        text = "FTC settles with AI company over deceptive algorithmic bias claims $2.5 million"
        self.assertTrue(_is_news_enforcement_relevant(text))

    def test_blocks_general_ai_news(self):
        from sources.enforcement_agent import _is_news_enforcement_relevant
        text = "AI startup raises $50 million to expand large language model capabilities"
        self.assertFalse(_is_news_enforcement_relevant(text))

    def test_blocks_policy_only_news(self):
        from sources.enforcement_agent import _is_news_enforcement_relevant
        text = "New AI regulation proposed in Congress focusing on transparency requirements"
        self.assertFalse(_is_news_enforcement_relevant(text))

    def test_passes_privacy_violation(self):
        from sources.enforcement_agent import _is_news_enforcement_relevant
        text = "Data broker fined for GDPR violation sharing personal data without consent"
        self.assertTrue(_is_news_enforcement_relevant(text))

    def test_passes_class_action(self):
        from sources.enforcement_agent import _is_news_enforcement_relevant
        text = "Class action lawsuit filed against company for biometric data collection"
        self.assertTrue(_is_news_enforcement_relevant(text))


class TestIAPPNewsSource(unittest.TestCase):

    def _source(self):
        from sources.enforcement_agent import IAPPNewsSource
        return IAPPNewsSource()

    def _fetch(self, days=3650):
        with patch("sources.enforcement_agent.http_get_text", return_value=NEWS_MOCK_RSS):
            return self._source().fetch(lookback_days=days)

    def test_filters_non_enforcement_items(self):
        self.assertFalse(any("Series B" in r["title"] for r in self._fetch()))

    def test_passes_enforcement_items(self):
        self.assertGreater(len(self._fetch()), 0)

    def test_source_name(self):
        for r in self._fetch():
            self.assertEqual(r["source"], "iapp")

    def test_required_fields_present(self):
        results = self._fetch()
        if results:
            for field in ("id", "source", "action_type", "title", "url", "relevance_score"):
                self.assertIn(field, results[0])

    def test_html_response_skipped(self):
        with patch("sources.enforcement_agent.http_get_text",
                   return_value="<!DOCTYPE html><html><body>Blocked</body></html>"):
            self.assertEqual(self._source().fetch(), [])

    def test_feed_failure_returns_empty(self):
        with patch("sources.enforcement_agent.http_get_text",
                   side_effect=Exception("Connection refused")):
            self.assertEqual(self._source().fetch(), [])


class TestRegulatoryOversightSource(unittest.TestCase):

    def _source(self):
        from sources.enforcement_agent import RegulatoryOversightSource
        return RegulatoryOversightSource()

    def _fetch(self, days=3650):
        with patch("sources.enforcement_agent.http_get_text", return_value=NEWS_MOCK_RSS):
            return self._source().fetch(lookback_days=days)

    def test_filters_non_enforcement_items(self):
        self.assertFalse(any("Series B" in r["title"] for r in self._fetch()))

    def test_passes_enforcement_items(self):
        self.assertGreater(len(self._fetch()), 0)

    def test_source_name(self):
        for r in self._fetch():
            self.assertEqual(r["source"], "regulatory_oversight")

    def test_feed_failure_returns_empty(self):
        with patch("sources.enforcement_agent.http_get_text",
                   side_effect=Exception("timeout")):
            self.assertEqual(self._source().fetch(), [])


class TestCourthouseNewsSource(unittest.TestCase):

    def _source(self):
        from sources.enforcement_agent import CourthouseNewsSource
        return CourthouseNewsSource()

    def _fetch(self, days=3650):
        with patch("sources.enforcement_agent.http_get_text", return_value=NEWS_MOCK_RSS):
            return self._source().fetch(lookback_days=days)

    def test_filters_non_enforcement_items(self):
        self.assertFalse(any("Series B" in r["title"] for r in self._fetch()))

    def test_passes_enforcement_items(self):
        self.assertGreater(len(self._fetch()), 0)

    def test_action_type_is_litigation(self):
        for r in self._fetch():
            self.assertEqual(r["action_type"], "litigation")

    def test_source_name(self):
        for r in self._fetch():
            self.assertEqual(r["source"], "courthouse_news")

    def test_feed_failure_returns_empty(self):
        with patch("sources.enforcement_agent.http_get_text",
                   side_effect=Exception("timeout")):
            self.assertEqual(self._source().fetch(), [])


# ═══════════════════════════════════════════════════════════════════════════════
# ENFORCEMENT AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnforcementAgent(unittest.TestCase):

    def _agent(self):
        from sources.enforcement_agent import EnforcementAgent
        return EnforcementAgent()

    def test_has_all_sources(self):
        agent = self._agent()
        source_names = {s.NAME for s in agent.sources}
        for expected in ('ftc', 'sec', 'cfpb', 'eeoc', 'doj', 'ico', 'courtlistener'):
            self.assertIn(expected, source_names)

    def test_fetch_all_aggregates_sources(self):
        agent = self._agent()
        mock_action = {
            'id': 'FTC-test123', 'source': 'ftc',
            'action_type': 'enforcement',
            'title': 'Test FTC AI Action',
            'url': 'https://ftc.gov/test',
            'published_date': datetime.utcnow(),
            'agency': 'FTC', 'jurisdiction': 'Federal',
            'respondent': 'Test Corp', 'summary': 'Test summary',
            'related_regs': [], 'outcome': 'settlement',
            'penalty_amount': '$1M', 'ai_concepts': ['bias_fairness'],
            'relevance_score': 0.8, 'raw_json': {},
        }
        for src in agent.sources:
            src.fetch = lambda lookback_days=90: [mock_action]

        with patch('utils.db.upsert_enforcement_action', return_value=True):
            counts = agent.fetch_all(lookback_days=90)

        self.assertIn('new', counts)
        self.assertIn('updated', counts)
        self.assertIn('by_source', counts)

    def test_source_failure_does_not_stop_others(self):
        agent = self._agent()
        # Make first source raise, rest return empty
        def _fail(lookback_days=90):
            raise Exception("Network error")
        agent.sources[0].fetch = _fail
        for src in agent.sources[1:]:
            src.fetch = lambda lookback_days=90: []

        with patch('utils.db.upsert_enforcement_action', return_value=True):
            counts = agent.fetch_all()

        # Should have attempted all sources, recorded 1 failure
        self.assertEqual(counts['failed'], 1)

    def test_low_relevance_actions_filtered(self):
        agent = self._agent()
        low_relevance_action = {
            'id': 'FTC-low', 'source': 'ftc', 'action_type': 'enforcement',
            'title': 'Some action', 'url': '', 'published_date': datetime.utcnow(),
            'agency': 'FTC', 'jurisdiction': 'Federal', 'respondent': '',
            'summary': '', 'related_regs': [], 'outcome': '',
            'penalty_amount': None, 'ai_concepts': [],
            'relevance_score': 0.0,   # below threshold
            'raw_json': {},
        }
        for src in agent.sources:
            src.fetch = lambda lookback_days=90: [low_relevance_action]

        upserted = []
        with patch('utils.db.upsert_enforcement_action',
                   side_effect=lambda a: upserted.append(a) or True):
            agent.fetch_all()

        self.assertEqual(len(upserted), 0)


# ═══════════════════════════════════════════════════════════════════════════════
# CONCEPT INFERENCE
# ═══════════════════════════════════════════════════════════════════════════════

class TestConceptInference(unittest.TestCase):

    def _infer(self, text):
        from sources.enforcement_agent import FTCEnforcementSource
        return FTCEnforcementSource._infer_concepts(text)

    def test_bias_concept_detected(self):
        concepts = self._infer("discriminatory algorithm with racial bias in hiring")
        self.assertIn('bias_fairness', concepts)

    def test_transparency_concept_detected(self):
        concepts = self._infer("failure to disclose AI decision-making process")
        self.assertIn('transparency', concepts)

    def test_automated_decisions_detected(self):
        concepts = self._infer("automated decision system for loan approvals")
        self.assertIn('automated_decisions', concepts)

    def test_biometric_detected(self):
        concepts = self._infer("illegal use of facial recognition technology")
        self.assertIn('biometric', concepts)

    def test_empty_text_returns_empty(self):
        concepts = self._infer("")
        self.assertEqual(concepts, [])


class TestOutcomeInference(unittest.TestCase):

    def _infer(self, text):
        from sources.enforcement_agent import FTCEnforcementSource
        return FTCEnforcementSource._infer_outcome(text)

    def test_settlement(self):
        self.assertEqual(self._infer("company agreed to consent order"), "settlement")

    def test_fine(self):
        self.assertEqual(self._infer("civil money penalty of $1 million"), "fine")

    def test_injunction(self):
        self.assertEqual(self._infer("court issued permanent injunction"), "injunction")

    def test_pending(self):
        self.assertEqual(self._infer("FTC filed complaint against company"), "pending")

    def test_default(self):
        result = self._infer("agency action taken against firm")
        self.assertEqual(result, "enforcement")


if __name__ == "__main__":
    unittest.main(verbosity=2)
