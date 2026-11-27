"""Conservative public-profile availability checks.

A network failure or anti-bot response is never treated as proof that an account
does not exist. Only explicit missing-profile responses are "not_found".
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, unquote, urlparse
import re

import requests
from data.sites import SITES

MAX_WORKERS = 8
TIMEOUT = (4, 8)
MAX_BODY_BYTES = 100_000
USER_AGENT = (
    "SocialFinder/2.0 (+https://github.com/AlNasri0/SocialFinder-OSINT) "
    "public profile availability checker"
)

# These hosts commonly return login shells, bot challenges, or generic pages.
# A 200 response from them is not enough to claim that a profile exists.
GENERIC_RESPONSE_HOSTS = {
    "instagram.com", "facebook.com", "linkedin.com", "x.com", "twitter.com",
    "snapchat.com", "youtube.com", "discord.com", "telegram.org",
    "pinterest.com", "threads.net",
}

# Strong, profile-oriented page markers. The requested username must also occur
# in the response, and the final URL must still identify the requested profile.
PROFILE_MARKERS = (
    'og:type" content="profile', "og:type' content='profile",
    "profile:username", "vcard-username", "user-login",
    '"uniqueid":', '"unique_id":', '"screen_name":',
    '"followers_count":', '"follower_count":', '"is_verified":',
    '"profilepage', "schema.org/person", "schema.org/profilepage",
    '"userinfo":', '"user_info":',
)

# Explicit missing-profile phrases. Kept narrow to avoid matching generic
# footer text or unrelated links on otherwise valid pages.
NOT_FOUND_PATTERNS = (
    r"this user(?:'s|’s)? profile (?:is )?not available",
    r"(?:the )?user (?:was )?not found",
    r"profile not found",
    r"account not found",
    r"this account (?:does not|doesn't) exist",
    r"no such user",
    r"page not found",
    r"this page (?:isn't|is not) available",
    r"could(?: not|n't) find this account",
    r"this profile (?:does not|doesn't) exist",
)

def _host(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")

def _normalize_handle(value):
    """Normalize punctuation commonly varied in profile handles."""
    return re.sub(r"[._-]", "", unquote(str(value)).strip().lstrip("@").casefold())


def _handles_match(candidate, requested):
    """Compare complete handles while tolerating dots, underscores and hyphens."""
    candidate = unquote(str(candidate)).strip().strip("/").lstrip("@")
    requested = unquote(str(requested)).strip().strip("/").lstrip("@")
    return bool(candidate and requested) and (
        candidate.casefold() == requested.casefold()
        or _normalize_handle(candidate) == _normalize_handle(requested)
    )


def _path_contains_username(url, username):
    """Match complete URL path/query/subdomain handles, including @handles."""
    parsed = urlparse(url)
    segments = [unquote(part).strip().lstrip("@")
                for part in parsed.path.split("/") if part]
    query_values = [unquote(part).strip().lstrip("@")
                    for part in re.split(r"[&=]", parsed.query) if part]
    host_labels = (parsed.hostname or "").lower().removeprefix("www.").split(".")
    # Some services use a username subdomain (for example name.bandcamp.com).
    subdomain_match = len(host_labels) > 2 and any(
        _handles_match(label, username) for label in host_labels[:-2]
    )
    return (
        any(_handles_match(part, username) for part in segments)
        or any(_handles_match(part, username) for part in query_values)
        or subdomain_match
    )


def _body_mentions_username(body, username):
    """Find a complete handle in page text, allowing common punctuation changes."""
    target = username.strip().lstrip("@")
    exact = re.search(r"(?<![A-Za-z0-9])" + re.escape(target) + r"(?![A-Za-z0-9])", body, re.I)
    if exact:
        return True
    normalized_body = re.sub(r"[._-]", "", body.casefold())
    normalized_target = _normalize_handle(target)
    if not normalized_target:
        return False
    return re.search(
        r"(?<![a-z0-9])" + re.escape(normalized_target) + r"(?![a-z0-9])",
        normalized_body,
    ) is not None

def _read_limited(response):
    chunks, size = [], 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            break
        chunks.append(chunk)
    encoding = response.encoding or "utf-8"
    return b"".join(chunks).decode(encoding, errors="replace").casefold()

def _has_profile_evidence(body, username):
    return _body_mentions_username(body, username) and any(
        marker in body for marker in PROFILE_MARKERS
    )

def _missing_profile(body):
    return any(re.search(pattern, body, flags=re.IGNORECASE)
               for pattern in NOT_FOUND_PATTERNS)

def _result(site, url, status="unverified", detail="The platform did not provide enough information to verify this profile.", http_status=None):
    labels = {
        "found": "Found",
        "not_found": "Not found",
        "unverified": "Could not verify",
    }
    return {
        "site": site, "url": url, "status": status, "label": labels[status],
        "detail": detail, "http_status": http_status,
    }

def _check_site(site, template, username):
    url = template.format(quote(username, safe=""))
    requested_host = _host(url)
    try:
        with requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/json"},
            timeout=TIMEOUT,
            stream=True,
            allow_redirects=True,
        ) as response:
            code = response.status_code
            final_url = response.url
            final_host = _host(final_url)

            if code in (404, 410):
                return _result(site, url, "not_found",
                               "The platform returned an HTTP missing-page response.", code)
            if code in (401, 403, 429):
                return _result(site, url, detail="The platform restricted or rate-limited the check; account status is unknown.", http_status=code)
            if code >= 500:
                return _result(site, url, detail="The platform encountered a server error; account status is unknown.", http_status=code)
            if not 200 <= code < 300:
                return _result(site, url, detail=f"Unexpected HTTP response ({code}); account status is unknown.", http_status=code)

            body = _read_limited(response)
            if _missing_profile(body):
                return _result(site, url, "not_found",
                               "The page explicitly indicates that this profile is unavailable.", code)

            # Do not accept login pages, generic homepages, or cross-domain
            # redirects as evidence that the requested profile exists.
            if final_host != requested_host:
                return _result(site, url, detail="The profile URL redirected to a different domain; account status is unknown.", http_status=code)
            if requested_host in GENERIC_RESPONSE_HOSTS:
                return _result(site, url, detail="This platform returned a generic or login page; account status is unknown.", http_status=code)
            if not _path_contains_username(final_url, username):
                return _result(site, url, detail="The final page URL does not match the requested username.", http_status=code)
            if not _has_profile_evidence(body, username):
                return _result(site, url, detail="The page did not contain reliable profile-specific data.", http_status=code)

            exact_handle = any(
                unquote(part).strip().lstrip("@").casefold() == username.casefold()
                for part in urlparse(final_url).path.split("/") if part
            )
            detail = (
                "The page returned profile-specific data matching this username."
                if exact_handle else
                "The page returned profile-specific data; its handle differs only by dots, underscores, or hyphens."
            )
            return _result(site, final_url, "found", detail, code)

    except requests.Timeout:
        return _result(site, url, detail="The request timed out; account status is unknown.")
    except requests.RequestException:
        return _result(site, url, detail="A network error prevented verification; account status is unknown.")
    except Exception:
        return _result(site, url, detail="The check failed unexpectedly; account status is unknown.")

def iter_username_results(username):
    """Yield completed checks as they finish, for server-sent UI progress."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,32}", username or ""):
        return
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(SITES)))) as executor:
        futures = {
            executor.submit(_check_site, site, template, username): (site, template)
            for site, template in SITES.items()
        }
        for future in as_completed(futures):
            site, template = futures[future]
            try:
                yield future.result()
            except Exception:
                url = template.format(quote(username, safe=""))
                yield _result(site, url, detail="An unexpected error prevented verification.")

def search_username(username):
    """Return results grouped Found, Could not verify, Not found; alphabetical within groups."""
    rank = {"found": 0, "unverified": 1, "not_found": 2}
    return sorted(
        list(iter_username_results(username)),
        key=lambda item: (rank.get(item["status"], 1), item["site"].casefold()),
    )
