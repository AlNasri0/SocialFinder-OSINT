from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
import re

import requests
from data.sites import SITES

# Keep concurrency modest: this is a public-profile checker, not a crawler.
MAX_WORKERS = 10
TIMEOUT = (3.5, 5)
MAX_BODY_BYTES = 80_000

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

# Some services return a generic success page or challenge for every URL.
# These are deliberately conservative: a 200 response is not always proof.
UNVERIFIABLE_HOSTS = {
    "instagram.com", "facebook.com", "linkedin.com", "x.com",
    "twitter.com", "tiktok.com", "snapchat.com", "youtube.com",
    "discord.com", "telegram.org", "pinterest.com",
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


def _check_site(site, template, username):
    encoded = quote(username, safe="")
    url = template.format(encoded)
    result = {
        "site": site,
        "url": url,
        "status": "unverified",
        "label": "Unable to verify",
        "detail": "The platform did not provide a reliable public response.",
        "http_status": None,
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        with requests.get(
            url, headers=headers, timeout=TIMEOUT, stream=True,
            allow_redirects=True
        ) as response:
            result["http_status"] = response.status_code
            final_url = response.url

            if response.status_code in (404, 410):
                result.update(status="not_found", label="Not found",
                             detail="The platform returned a missing-profile response.")
                return result

            if response.status_code in (401, 403, 429) or response.status_code >= 500:
                result["detail"] = (
                    "Access was restricted, rate-limited, or the service had an error."
                )
                return result

            if response.status_code < 200 or response.status_code >= 400:
                result["detail"] = f"Unexpected HTTP response ({response.status_code})."
                return result

            body = _read_limited(response)
            if any(marker in body for marker in NOT_FOUND_MARKERS):
                result.update(status="not_found", label="Not found",
                             detail="The page appears to indicate that this profile is missing.")
                return result

            host = requests.utils.urlparse(url).hostname or ""
            host = host.lower().removeprefix("www.")
            redirected_host = requests.utils.urlparse(final_url).hostname or ""
            redirected_host = redirected_host.lower().removeprefix("www.")

            # Generic landing/login pages are not reliable evidence of a profile.
            if host in UNVERIFIABLE_HOSTS or redirected_host != host:
                result["detail"] = (
                    "This platform may show generic, login, or challenge pages; "
                    "open the link to confirm."
                )
                return result

            if response.status_code == 200:
                result.update(
                    status="found",
                    label="Likely found",
                    detail="The profile URL returned a successful page; verify it manually.",
                )
                return result

            result["detail"] = f"Response was not conclusive (HTTP {response.status_code})."
            return result

    except requests.Timeout:
        result["detail"] = "The request timed out."
    except requests.RequestException:
        result["detail"] = "A network error prevented checking this platform."
    except Exception:
        # Keep an individual site failure from breaking the entire search.
        result["detail"] = "The check could not be completed."

    return result


def search_username(username):
    """Check configured public profile URLs concurrently and return safe statuses."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,32}", username or ""):
        return []

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_check_site, site, template, username): site
            for site, template in SITES.items()
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception:
                results.append({
                    "site": futures[future],
                    "url": SITES[futures[future]].format(quote(username, safe="")),
                    "status": "unverified",
                    "label": "Unable to verify",
                    "detail": "The check failed unexpectedly.",
                    "http_status": None,
                })

    order = {"found": 0, "unverified": 1, "not_found": 2}
    return sorted(results, key=lambda item: (order[item["status"]], item["site"].casefold()))
