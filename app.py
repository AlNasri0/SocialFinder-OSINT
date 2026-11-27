from collections import defaultdict
from time import monotonic
from threading import Lock

from flask import Flask, render_template, request
from searchers.all_search import search_username

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024  # Search requests should be tiny.

# Lightweight per-process throttling. For multi-worker deployments, use a shared
# store (e.g. Redis) so limits are consistent across workers.
_RATE_LIMIT = 6
_RATE_WINDOW = 60
_requests = defaultdict(list)
_rate_lock = Lock()


def is_rate_limited(client_ip):
    now = monotonic()
    with _rate_lock:
        recent = [t for t in _requests[client_ip] if now - t < _RATE_WINDOW]
        if len(recent) >= _RATE_LIMIT:
            _requests[client_ip] = recent
            return True
        recent.append(now)
        _requests[client_ip] = recent
        return False


@app.route("/", methods=["GET", "POST"])
def home():
    results = []
    username = ""
    error = None
    searched = False

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        searched = True

        if not username:
            error = "Enter a username to search."
        elif len(username) > 32 or not all(
            ch.isalnum() or ch in "._-" for ch in username
        ):
            error = "Use 1–32 letters, numbers, dots, underscores, or hyphens."
        elif is_rate_limited(request.remote_addr or "unknown"):
            error = "Search limit reached. Please wait a minute and try again."
        else:
            results = search_username(username)

    found_count = sum(result["status"] == "found" for result in results)
    not_found_count = sum(result["status"] == "not_found" for result in results)
    unverified_count = sum(result["status"] == "unverified" for result in results)

    return render_template(
        "index.html",
        results=results,
        found_count=found_count,
        not_found_count=not_found_count,
        unverified_count=unverified_count,
        username=username,
        error=error,
        searched=searched,
    )


if __name__ == "__main__":
    app.run(debug=False)
