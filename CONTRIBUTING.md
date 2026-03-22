# Contributing to ARIS

Thank you for your interest in ARIS. Contributions are welcome under the terms of the [Elastic License 2.0](LICENSE).

## Before You Start

ARIS is licensed under ELv2. By submitting a contribution, you agree that your contribution will be licensed under the same terms.

**Non-commercial use only.** ARIS may not be used to provide a commercial product or service. Please review the full license before contributing.

## What Makes a Good Contribution

- Bug fixes with a clear description of the problem and how the fix resolves it
- New US state agents (follow the pattern in `sources/states/`)
- New international jurisdiction agents (follow the pattern in `sources/international/`)
- Additional baseline regulation JSON files (follow `data/baselines/index.json` schema)
- Improvements to the relevance scoring and false positive reduction
- UI improvements that add genuine clarity to the views

## What to Avoid

- Changes that introduce new dependencies without strong justification
- Features that require cloud infrastructure or external services beyond the existing API integrations
- Changes to the database schema without a corresponding migration in `migrate.py`

## Development Setup

```bash
git clone <repo-url>
cd ai-reg-tracker
pip install -r requirements.txt
cp config/keys.env.example config/keys.env   # fill in your keys
python migrate.py
cd ui && npm install && npm run build && cd ..
python server.py
```

Run the test suite before submitting:

```bash
python -m pytest tests/ -v
# or
python -m unittest discover tests -v
```

All 636 tests must pass. If you add a new agent or feature, add corresponding tests.

## Adding a US State Agent

1. Create `sources/states/yourstate.py` following the pattern of an existing LegiScan-only state (e.g. `sources/states/virginia.py`)
2. Add the module to `US_STATE_MODULE_MAP` in `config/jurisdictions.py`
3. Add the state code to `ENABLED_US_STATES` in `config/jurisdictions.py`
4. Add a test in `tests/test_suite.py`

States with a native legislative feed (RSS, API, or ZIP download) are higher value — see `sources/states/pennsylvania.py` and `sources/states/california.py` for examples.

## Pull Request Guidelines

- One feature or fix per PR
- Include a clear description of what changed and why
- Reference any related issues
- Ensure tests pass
- Update README.md if you add a new jurisdiction or feature

## Reporting Issues

Open a GitHub issue with:
- ARIS version (or commit hash)
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behaviour
- Relevant log output (`LOG_LEVEL=DEBUG` in `config/keys.env` for verbose output)
