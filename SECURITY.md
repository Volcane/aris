# Security Policy

## Scope

ARIS is a local desktop tool. It does not operate as a public-facing service, store user data in the cloud, or transmit personal data externally. The attack surface is limited to:

- The local FastAPI server (bound to localhost:8000 by default)
- API keys stored in `config/keys.env`
- The SQLite database in `output/`

## Sensitive Data

**API keys** are stored in `config/keys.env` on your local filesystem. This file is excluded from version control via `.gitignore`. Never commit `config/keys.env` to a public repository.

**The SQLite database** (`output/aris.db`) contains fetched regulatory documents and summaries. It does not contain personal data unless you add it to company profiles in the gap analysis feature. The database file is excluded from version control via `.gitignore`.

## Network Exposure

By default the ARIS server binds to `0.0.0.0:8000`, which means it is accessible on your local network. If you are on a shared or untrusted network, restrict it to localhost only by editing `server.py`:

```python
uvicorn.run(app, host="127.0.0.1", port=8000)
```

ARIS has no authentication layer. Do not expose it to the public internet.

## Reporting a Vulnerability

If you discover a security vulnerability in ARIS, please report it privately rather than opening a public GitHub issue.

Open a GitHub Security Advisory on the repository, or contact the maintainer directly. Please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix

We aim to acknowledge reports within 5 business days and provide a resolution timeline within 30 days.

## Dependencies

ARIS depends on third-party Python packages listed in `requirements.txt`. Keep these up to date. Known vulnerability scanning tools such as `pip-audit` or GitHub's Dependabot can help identify issues in dependencies.

```bash
pip install pip-audit
pip-audit
```
