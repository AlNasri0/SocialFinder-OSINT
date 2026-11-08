import requests
from data.sites import SITES


def search_username(username):

    results = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        )
    }

    for site, url_template in SITES.items():

        url = url_template.format(username)

        try:

            response = requests.get(
                url,
                headers=headers,
                timeout=5
            )

            results.append({
                "site": site,
                "found": response.status_code == 200,
                "url": url
            })

        except requests.RequestException:

            results.append({
                "site": site,
                "found": False,
                "url": url
            })

    results.sort(
        key=lambda result: (
            not result["found"],
            result["site"]
        )
    )

    return results