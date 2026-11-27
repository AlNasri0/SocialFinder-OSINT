# SocialFinder-OSINT

A Flask-based username checker that builds links to public profile pages across social, developer, gaming, creator, and community platforms.

> **Important:** automated checks are best-effort. Websites may use login walls, bot checks, redirects, or generic HTTP 200 pages. A result marked **Likely found** is not proof that an account exists. Open the profile link to confirm. This tool checks public profile URLs only; it does not access private information.

## Features

- Checks configured platforms in parallel (with a modest concurrency limit).
- Separates **Likely found**, **Not found**, and **Unverified** outcomes instead of treating network errors as missing profiles.
- Uses request timeouts and limits response-body reading.
- URL-encodes usernames and validates input.
- Lightweight per-process request throttling.
- Responsive UI, result summary cards, and status filters.
- Safe external links and explanatory uncertainty notice.

## Run locally

Python 3.10+ recommended.

```bash
git clone https://github.com/AlNasri0/SocialFinder-OSINT.git
cd SocialFinder-OSINT
python -m venv .venv
```

Activate the environment:

- Windows: `.venv\\Scripts\\activate`
- macOS/Linux: `source .venv/bin/activate`

Install and start:

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000.

## Deploy

For production, run behind a production WSGI server (Gunicorn is included), and disable debug mode:

```bash
gunicorn --workers 2 --threads 4 --timeout 45 app:app
```

The in-memory rate limit is per process and resets on restart. For multi-worker or multi-instance deployments, replace it with a shared limiter (Redis, for example), configure proxy trust carefully, and apply platform-specific request policies. Do not increase concurrency to evade platform rate limits.

## How result statuses work

- **Likely found:** a response indicates a page exists, but it may still be a generic page. Verify manually.
- **Not found:** the platform returned a missing-page response or recognizable missing-profile text.
- **Unverified:** blocked, rate-limited, timed out, redirected to an unrelated page, or otherwise inconclusive.

Platform behavior changes frequently; false positives and false negatives are possible. Contributions to `data/sites.py` and conservative platform-specific response checks are welcome.

## License

No license is currently specified in this repository. Add a license file if you intend to grant reuse rights.
