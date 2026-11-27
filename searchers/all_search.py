from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse
import re

import requests
from data.sites import SITES

MAX_WORKERS = 8
TIMEOUT = (3.5, 6)
MAX_BODY_BYTES = 60_000
USER_AGENT = (
    "SocialFinder/1.0 (+https://github.com/AlNasri0/SocialFinder-OSINT) "
    "public profile availability checker"
)

NOT_FOUND_MARKERS = (
    "page not found", "user not found", "profile not found", "account not found",
    "this account doesn't exist", "this account does not exist",
    "couldn't find this account", "could not find this account",
    "sorry, this page isn't available", "sorry, this page is not available",
    "doesn't exist", "does not exist", "no such user", "profile unavailable",
    "account is unavailable", "user is unavailable",
)

# Sites known to commonly return generic pages/challenges even for nonexistent accounts.
GENERIC_RESPONSE_HOSTS = {
    "instagram.com", "facebook.com", "linkedin.com", "x.com", "twitter.com",
    "tiktok.com", "snapchat.com", "youtube.com", "discord.com", "telegram.org",
    "pinterest.com",
}


def _read_limited(response):
    chunks = []
    size = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            break
        chunks.append(chunk)
    return b"".join(chunks).decode(response.encoding or "utf-8", errors="ignore").lower()


def _host(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _path_contains_username(url, username):
    parsed = urlparse(url)
    decoded_path = requests.utils.unquote(parsed.path).strip("/").lower()
    decoded_query = requests.utils.unquote(parsed.query).lower()
    target = username.lower()
    return target in decoded_path.split("/") or target in decoded_query


def _check_site(site, template, username):
    url = template.format(quote(username, safe=""))
    host = _host(url)
    result = {
        "site": site, "url": url, "status": "not_found", "label": "Not found",
        "detail": "No reliable confirmation was returned.", "http_status": None,
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        with requests.get(url, headers=headers, timeout=TIMEOUT, stream=True,
                         allow_redirects=True) as response:
            result["http_status"] = response.status_code
            final_url = response.url
            final_host = _host(final_url)

            if response.status_code in (404, 410):
                result["detail"] = "The platform returned a missing-profile response."
                return result
            if response.status_code in (401, 403, 429) or response.status_code >= 500:
                result["detail"] = "Blocked, rate-limited, or server error; not confirmed."
                return result
            if not (200 <= response.status_code < 300):
                result["detail"] = f"Unexpected HTTP response ({response.status_code}); not confirmed."
                return result

            body = _read_limited(response)
            if any(marker in body for marker in NOT_FOUND_MARKERS):
                result["detail"] = "The response indicates that the profile may not exist."
                return result

            if host in GENERIC_RESPONSE_HOSTS:
                result["detail"] = "This site returns generic/login pages; existence not confirmed."
                return result
            if final_host != host:
                result["detail"] = "The link redirected to another domain; profile not confirmed."
                return result
            if not _path_contains_username(final_url, username):
                result["detail"] = "The returned page did not match the requested username."
                return result

            result.update(status="found", label="Found", url=final_url,
                          detail="The response matched the profile URL. Please confirm it is the correct account.")
            return result
    except requests.Timeout:
        result["detail"] = "Timed out; the profile could not be confirmed."
    except requests.RequestException:
        result["detail"] = "Network error; the profile could not be confirmed."
    except Exception:
        result["detail"] = "The check failed; the profile could not be confirmed."
    return result


def iter_username_results(username):
    """Yield each completed site check, allowing the UI to show live progress."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,32}", username or ""):
        return
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(SITES)))) as executor:
        futures = {
            executor.submit(_check_site, site, template, username): site
            for site, template in SITES.items()
        }
        for future in as_completed(futures):
            try:
                yield future.result()
            except Exception:
                site = futures[future]
                yield {
                    "site": site, "url": SITES[site].format(quote(username, safe="")),
                    "status": "not_found", "label": "Not found",
                    "detail": "Unexpected failure; profile not confirmed.", "http_status": None,
                }


def search_username(username):
    """Return checks in stable status/site order; inconclusive checks are not confirmed."""
    results = list(iter_username_results(username))
    order = {"found": 0, "not_found": 1}
    return sorted(results, key=lambda item: (order[item["status"]], item["site"].casefold()))
