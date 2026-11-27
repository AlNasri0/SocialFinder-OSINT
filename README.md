# SocialFinder-OSINT

A Flask-based public username profile URL checker across a curated list of social, developer, creator, and community platforms.

**Accuracy note:** “Found” is a conservative heuristic, not proof of identity or account ownership. “Not found” includes missing-page responses and inconclusive cases (for example, access blocks, rate limits, timeouts, or generic pages) so the UI stays limited to the two requested labels without claiming certainty. Open the link to verify. External websites can change routing and login requirements at any time; no tool can guarantee every generated profile link will land on a visible profile.

## Features

- Live progress bar driven by checks completing on the server (not a fake timer).
- Two user-facing states: **Found** and **Not found**.
- Conservative checks for HTTP errors, missing-profile text, generic pages, cross-domain redirects, and profile URL mismatches.
- Curated direct profile URL formats; ambiguous username/ID formats and unreliable search/redirect endpoints are omitted.
- Concurrent checks with modest concurrency, timeouts, and limited response-body reading.
- Username validation, per-process request throttling, responsive UI, and result filters.
- Checks public profile URLs only; does not access private information.

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

Open http://127.0.0.1:5000.

## Deploy

For production, run behind a production WSGI server and disable debug mode:

```bash
gunicorn --workers 2 --threads 4 --timeout 45 app:app
```

The in-memory rate limit is per process and resets on restart. For multiple workers/instances, use a shared limiter. Do not increase concurrency to evade platform rate limits.

## License

No license is currently specified in this repository. Add one if you intend to grant reuse rights.
