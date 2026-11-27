# SocialFinder-OSINT

A Flask-based public username profile checker for a curated set of social, creator, developer, gaming, and community platforms.

## Accuracy comes first

A website returning HTTP 200 does **not** prove that a profile exists. Likewise, a timeout, anti-bot challenge, login wall, or HTTP 403 does **not** prove that it does not exist.

The checker therefore reports three outcomes:

- **Found** — the response contained profile-specific evidence matching the requested username and the final URL still matched that username.
- **Not found** — the platform returned an explicit missing-profile response (such as HTTP 404/410 or a recognized missing-profile page).
- **Could not verify** — the platform blocked the request, returned a generic/login page, timed out, redirected elsewhere, or did not provide enough profile evidence.

Only confirmed **Found** results receive a clickable profile link. This reduces misleading links and false positives. Even a Found result is not identity verification: usernames can be impersonated, renamed, or reused.

Some platforms intentionally restrict automated requests. Their results may remain **Could not verify** even when the account exists. Open the platform manually to confirm.

## Features

- Live server-sent progress updates as platform checks complete.
- Results grouped in a stable order: Found, Could not verify, Not found; alphabetically within each group.
- Separate filters and counters for each outcome.
- No clickable profile links for missing or unverified results.
- Conservative response checks for HTTP status, redirects, exact username URL matching, generic pages, and profile-specific page evidence.
- Handles @-prefixed profile paths and username-based subdomains.
- Curated platform URL templates; services requiring numeric IDs or instance-specific handles are intentionally excluded.
- Concurrent checks with bounded worker count, request timeouts, and response-body limits.
- Input validation, per-process request throttling, security headers, and a lightweight health endpoint.
- Unit tests and GitHub Actions CI.

## Run locally

Python 3.10+ is recommended.

```bash
git clone https://github.com/AlNasri0/SocialFinder-OSINT.git
cd SocialFinder-OSINT
python -m venv .venv
```

Activate the environment:

- Windows: `.venv\\Scripts\\activate`
- macOS/Linux: `source .venv/bin/activate`

Install and run:

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

## Run tests

```bash
python -m unittest discover -s tests -v
```

Tests also run automatically on pushes and pull requests to `main` through GitHub Actions.

## Deployment

For production, use a WSGI server and a reverse proxy with HTTPS:

```bash
gunicorn --workers 2 --threads 4 --timeout 60 app:app
```

The built-in in-memory rate limiter is per process and resets on restart. For multi-worker or multi-instance deployments, replace it with a shared limiter (for example Redis-backed). Configure trusted proxy handling carefully before relying on forwarded client IP headers.

Do not increase concurrency to bypass platform rate limits or access controls.

## Responsible use

This project checks publicly accessible profile pages only. Use it lawfully and respectfully. Do not use results to harass, stalk, dox, or make consequential decisions about people. The tool does not identify account owners and cannot guarantee that every platform permits automated checking.

## License

No license is currently specified. Add a license if you intend to grant others permission to reuse, modify, or distribute this project.
