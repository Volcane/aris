# Changelog

All notable changes to ARIS are documented here.

## v1.0.0 — March 2026

Initial public release.

### Coverage
- 18 US state legislative agents (PA, CA, CO, IL, TX, WA, NY, FL, MN, CT, VA, NJ, MA, OR, MD, GA, AZ, NC)
- 10 international jurisdiction agents (EU, GB, Canada, Singapore, India, Brazil, Japan, South Korea, Australia, China)
- US Federal sources (Federal Register, Regulations.gov, Congress.gov)
- Enforcement tracking (FTC, SEC, CFPB, ICO, CourtListener)

### Baselines
- 31 pre-loaded baseline regulations (19 AI regulation, 12 data privacy)
- Always available, zero API calls required

### Features
- Dual-domain architecture (AI Regulation + Data Privacy) with separate vocabularies and scoring
- Concurrent fetch via ThreadPoolExecutor (all 28+ source tracks in ~2–3 minutes)
- Regulatory horizon with 17 seeded upcoming events and four live API sources
- Dashboard horizon widget with urgency buckets and countdown display
- Compliance gap analysis with structured posture scoring and .docx export
- Jurisdiction comparison across all 31 baselines
- Thematic synthesis with conflict detection and .docx export
- Obligation register with fast (no-LLM) and full (semantic) modes
- Ask ARIS: RAG-powered Q&A across documents and baselines with citations
- Scheduled monitoring with email and Slack digest notifications
- Autonomous learning: relevance model updates from every processed document
- Auto-archive: documents Claude rates ≤ 0.15 relevance move to Archive automatically
- False positive protection for common non-AI acronyms (NAIC, AIDA, MAID, PAID leave)
- Word boundary enforcement in relevance scoring
- Skipped document visibility: filtered documents shown with exact reason in Documents view

### Technical
- 636 tests across 18 test files
- SQLite database with 17 tables
- FastAPI REST server with 80+ endpoints
- React browser UI with 20 views
- ELv2 license
