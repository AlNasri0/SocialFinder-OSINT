import unittest
from unittest.mock import patch

from searchers import all_search


class FakeResponse:
    def __init__(self, status=200, body="profile content", url="https://example.com/test"):
        self.status_code = status
        self.text = body
        self.url = url
        self.encoding = "utf-8"

    def iter_content(self, chunk_size=8192):
        yield self.text.encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class SearchTests(unittest.TestCase):
    def check(self, response, template="https://example.com/{}"):
        with patch("searchers.all_search.requests.get", return_value=response):
            return all_search._check_site("Example", template, "testuser")

    def test_404_is_not_found(self):
        result = self.check(FakeResponse(status=404))
        self.assertEqual(result["status"], "not_found")

    def test_403_is_unverified(self):
        result = self.check(FakeResponse(status=403))
        self.assertEqual(result["status"], "unverified")

    def test_known_generic_page_host_is_unverified(self):
        response = FakeResponse(url="https://instagram.com/testuser")
        result = self.check(response, "https://instagram.com/{}")
        self.assertEqual(result["status"], "unverified")

    def test_profile_missing_marker(self):
        response = FakeResponse(body="Sorry, this page is not available")
        result = self.check(response)
        self.assertEqual(result["status"], "not_found")

    def test_success_response_is_likely_found(self):
        result = self.check(FakeResponse())
        self.assertEqual(result["status"], "found")

    def test_invalid_username_returns_no_results(self):
        self.assertEqual(all_search.search_username("bad username"), [])
        self.assertEqual(all_search.search_username(""), [])

    def test_parallel_results_are_sorted(self):
        fake_sites = {"Beta": "https://beta.test/{}", "Alpha": "https://alpha.test/{}"}
        statuses = {"Beta": "not_found", "Alpha": "found"}

        def fake_check(site, template, username):
            return {"site": site, "url": template.format(username),
                    "status": statuses[site], "detail": "", "http_status": 200}

        with patch.object(all_search, "SITES", fake_sites), patch.object(
            all_search, "_check_site", side_effect=fake_check
        ):
            results = all_search.search_username("valid_user")
        self.assertEqual([r["site"] for r in results], ["Alpha", "Beta"])

if __name__ == "__main__":
    unittest.main()
