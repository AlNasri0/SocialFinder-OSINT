"""Conservative public-profile availability checks.

A network failure or anti-bot response is never treated as proof that an account
does not exist. Only explicit missing-profile responses are "not_found".
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, unquote, urlparse
import re

import requests
from data.sites import SITES

MAX_WORKERS = 10
TIMEOUT = (3, 5)
MAX_BODY_BYTES = 100_000
USER_AGENT = (
    "SocialFinder/2.0 (+https://github.com/AlNasri0/SocialFinder-OSINT) "
    "public profile availability checker"
)

# Login shells and anti-bot responses are not profile evidence. A matching
# profile URL alone is also insufficient: the page must contain handle-specific
# profile metadata below.
BLOCK_PAGE_MARKERS = (
    "captcha", "verify you are human", "unusual traffic",
    "enable javascript and cookies to continue", "checking your browser",
    "access denied", "temporarily blocked",
)

# On these platforms, generic HTML shells frequently include the requested
# handle or follower-related text. Require stronger platform profile metadata.
STRICT_PROFILE_HOSTS = {
    "instagram.com", "facebook.com", "linkedin.com", "x.com", "twitter.com",
    "snapchat.com", "youtube.com", "discord.com", "telegram.org",
    "pinterest.com", "threads.net",
}
STRICT_PROFILE_MARKERS = (
    'og:type" content="profile', "profile:username", '"uniqueid":',
    '"unique_id":', '"screen_name":', '"userinfo":', '"user_info":',
    '"profile_id":', '"channelid":', '"channel_id":',
)

# Strong, profile-oriented page markers. The requested username must also occur
# in the response, and the final URL must still identify the requested profile.
PROFILE_MARKERS = (
    'og:type" content="profile', "og:type' content='profile",
    "og:title", "profile:username", "vcard-username", "user-login",
    '"uniqueid":', '"unique_id":', '"screen_name":',
    '"followers_count":', '"follower_count":', '"is_verified":',
    '"profilepage', "schema.org/person", "schema.org/profilepage",
    '"userinfo":', '"user_info":', '"userprofile":', '"profileuser":',
    'itemprop="name"', 'data-testid="user-', 'class="profile',
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
    r"could(?: not|n't) find this account",
    r"this profile (?:does not|doesn't) exist",
)

def _host(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")

def _handles_match(candidate, requested):
    """Compare complete handles exactly, ignoring case and an optional @ prefix."""
    candidate = unquote(str(candidate)).strip().strip("/").lstrip("@")
    requested = unquote(str(requested)).strip().strip("/").lstrip("@")
    return bool(candidate and requested) and candidate.casefold() == requested.casefold()


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
    # Punctuation is meaningful in usernames. Never collapse dots, underscores,
    # or hyphens: doing so can attribute a different account to this handle.
    return re.search(
        r"(?<![A-Za-z0-9])" + re.escape(target) + r"(?![A-Za-z0-9])",
        body,
        flags=re.IGNORECASE,
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

def _result(site, url, status="not_found", detail="No matching public profile was confirmed.", http_status=None):
    """Return one of the two requested display states.

    not_found means no profile was confirmed by this automated check; details
    explain when the site blocked the request so it is not mistaken for proof
    that the account does not exist.
    """
    label = "Found" if status == "found" else "Not found"
    return {
        "site": site, "url": url, "status": status, "label": label,
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
                return _result(site, url, detail="Not confirmed: the platform blocked or rate-limited automated checking. This does not prove the account is absent.", http_status=code)
            if code >= 500:
                return _result(site, url, detail="Not confirmed: the platform returned a server error. This does not prove the account is absent.", http_status=code)
            if not 200 <= code < 300:
                return _result(site, url, detail=f"Not confirmed: the platform returned HTTP {code}. This does not prove the account is absent.", http_status=code)

            content_type = getattr(response, "headers", {}).get("Content-Type", "").lower()
            if content_type and not any(
                kind in content_type for kind in ("text/html", "application/xhtml+xml", "application/json")
            ):
                return _result(site, url, detail="Not confirmed: the platform returned a non-profile response type.", http_status=code)

            body = _read_limited(response)
            if _missing_profile(body):
                return _result(site, url, "not_found",
                               "The page explicitly indicates that this profile is unavailable.", code)

            # Do not accept login pages, generic homepages, or cross-domain
            # redirects as evidence that the requested profile exists.
            if final_host != requested_host:
                return _result(site, url, detail="Not confirmed: the profile URL redirected away from the platform. The account may still exist.", http_status=code)
            if any(marker in body for marker in BLOCK_PAGE_MARKERS):
                return _result(site, url, detail="Not confirmed: the platform showed a security or anti-bot page. The account may still exist.", http_status=code)
            if not _path_contains_username(final_url, username):
                return _result(site, url, detail="Not confirmed: the final URL did not retain the requested handle.", http_status=code)
            if not _has_profile_evidence(body, username):
                return _result(site, url, detail="Not confirmed: the page did not expose enough profile-specific information. The account may still exist.", http_status=code)
            if requested_host in STRICT_PROFILE_HOSTS and not any(
                marker in body for marker in STRICT_PROFILE_MARKERS
            ):
                return _result(site, url, detail="Not confirmed: this platform returned a generic page rather than strong profile metadata. The account may still exist.", http_status=code)

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
        return _result(site, url, detail="Not confirmed: the request timed out. The account may still exist.")
    except requests.RequestException:
        return _result(site, url, detail="Not confirmed: a network error interrupted the check. The account may still exist.")
    except Exception:
        return _result(site, url, detail="Not confirmed: an unexpected error interrupted the check.")

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
                yield _result(site, url, detail="Not confirmed: an unexpected error interrupted the check.")

def search_username(username):
    """Return results grouped Found then Not found, alphabetically within groups."""
    rank = {"found": 0, "not_found": 1}
    return sorted(
        list(iter_username_results(username)),
        key=lambda item: (rank.get(item["status"], 1), item["site"].casefold()),
    )
