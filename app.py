from collections import defaultdict
from threading import Lock
from time import monotonic
import json
import re

from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from data.sites import SITES
from searchers.all_search import iter_username_results

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024

_RATE_LIMIT = 6
_RATE_WINDOW = 60
_requests = defaultdict(list)
_rate_lock = Lock()


def is_rate_limited(client_ip):
    now = monotonic()
    with _rate_lock:
        # Periodically discard expired client entries to prevent unbounded growth.
        expired = [ip for ip, stamps in _requests.items()
                   if not stamps or now - stamps[-1] >= _RATE_WINDOW]
        for ip in expired:
            _requests.pop(ip, None)

        recent = [stamp for stamp in _requests[client_ip]
                  if now - stamp < _RATE_WINDOW]
        if len(recent) >= _RATE_LIMIT:
            _requests[client_ip] = recent
            return True
        recent.append(now)
        _requests[client_ip] = recent
        return False


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html", total_sites=len(SITES))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "platforms": len(SITES)})


@app.route("/stream", methods=["POST"])
def stream_search():
    username = request.form.get("username", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,32}", username):
        return Response(
            "Invalid username. Use 1–32 letters, numbers, dots, underscores, or hyphens.\n",
            status=400, mimetype="text/plain"
        )
    if is_rate_limited(request.remote_addr or "unknown"):
        return Response(
            "Search limit reached. Please wait a minute and try again.\n",
            status=429, mimetype="text/plain"
        )

    @stream_with_context
    def generate():
        total = len(SITES)
        completed = 0
        yield "data: " + json.dumps({
            "type": "start", "total": total, "username": username
        }) + "\n\n"
        for result in iter_username_results(username):
            completed += 1
            yield "data: " + json.dumps({
                "type": "result", "completed": completed,
                "total": total, "result": result
            }) + "\n\n"
        yield "data: " + json.dumps({
            "type": "complete", "completed": completed, "total": total
        }) + "\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


if __name__ == "__main__":
    app.run(debug=False, threaded=True)
