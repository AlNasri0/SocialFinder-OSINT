import unittest
from unittest.mock import patch

from searchers import all_search


class FakeResponse:
    def __init__(self, status=200, body='{"username":"testuser","profile":"details","followers_count":12}', url="https://example.com/testuser"):
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

    def test_http_404_is_confirmed_missing(self):
        self.assertEqual(self.check(FakeResponse(status=404))["status"], "not_found")

    def test_http_410_is_confirmed_missing(self):
        self.assertEqual(self.check(FakeResponse(status=410))["status"], "not_found")

    def test_forbidden_is_not_found_not_missing(self):
        result = self.check(FakeResponse(status=403))
        self.assertEqual(result["status"], "not_found")

    def test_rate_limit_is_not_found(self):
        self.assertEqual(self.check(FakeResponse(status=429))["status"], "not_found")

    def test_server_error_is_not_found(self):
        self.assertEqual(self.check(FakeResponse(status=503))["status"], "not_found")

    def test_generic_social_site_is_not_marked_found(self):
        response = FakeResponse(url="https://www.instagram.com/testuser/")
        result = self.check(response, "https://www.instagram.com/{}/")
        self.assertNotEqual(result["status"], "found")

    def test_generic_instagram_metadata_is_not_enough(self):
        response = FakeResponse(
            body='<meta property="og:title" content="testuser"> testuser followers_count',
            url="https://www.instagram.com/testuser/",
        )
        result = self.check(response, "https://www.instagram.com/{}/")
        self.assertEqual(result["status"], "not_found")

    def test_instagram_profile_marker_is_accepted(self):
        response = FakeResponse(
            body='<meta property="og:type" content="profile"><meta property="profile:username" content="testuser"> testuser',
            url="https://www.instagram.com/testuser/",
        )
        result = self.check(response, "https://www.instagram.com/{}/")
        self.assertEqual(result["status"], "found")

    def test_request_limits_are_bounded_for_smooth_searches(self):
        self.assertLessEqual(all_search.MAX_WORKERS, 12)
        self.assertEqual(all_search.TIMEOUT, (3, 5))

    def test_explicit_profile_missing_phrase_is_reported(self):
        response = FakeResponse(body="Sorry, this user profile is not available")
        result = self.check(response)
        self.assertEqual(result["status"], "not_found")
        self.assertIn("explicitly indicates", result["detail"])

    def test_generic_page_not_found_text_is_not_profile_evidence(self):
        response = FakeResponse(
            body='<html><body>Welcome testuser</body><footer>Page not found</footer></html>'
        )
        result = self.check(response)
        self.assertEqual(result["status"], "not_found")
        self.assertIn("not enough profile-specific", result["detail"])

    def test_profile_evidence_is_found(self):
        result = self.check(FakeResponse())
        self.assertEqual(result["status"], "found")

    def test_non_profile_content_type_is_not_found(self):
        response = FakeResponse()
        response.headers = {"Content-Type": "image/png"}
        result = self.check(response)
        self.assertEqual(result["status"], "not_found")
        self.assertIn("non-profile response type", result["detail"])

    def test_result_labels_are_exactly_two_outcomes(self):
        found = all_search._result("Example", "https://example.com/testuser", "found")
        missing = all_search._result("Example", "https://example.com/testuser", "not_found")
        self.assertEqual(found["label"], "Found")
        self.assertEqual(missing["label"], "Not found")

    def test_username_in_generic_page_is_not_enough(self):
        response = FakeResponse(body="welcome testuser, generic home page")
        self.assertEqual(self.check(response)["status"], "not_found")

    def test_tiktok_at_handle_matches_requested_username(self):
        self.assertTrue(all_search._path_contains_username(
            "https://www.tiktok.com/@testuser", "testuser"
        ))

    def test_bandcamp_username_subdomain_matches(self):
        self.assertTrue(all_search._path_contains_username(
            "https://testuser.bandcamp.com/", "testuser"
        ))

    def test_username_punctuation_must_match_exactly(self):
        self.assertTrue(all_search._path_contains_username(
            "https://example.com/test_user", "test_user"
        ))
        for url in (
            "https://example.com/test.user",
            "https://example.com/test-user",
            "https://example.com/testuser",
        ):
            with self.subTest(url=url):
                self.assertFalse(all_search._path_contains_username(url, "test_user"))

    def test_user_path_format_matches_handle(self):
        self.assertTrue(all_search._path_contains_username(
            "https://example.com/user/test_user/", "testuser"
        ))

    def test_profile_data_requires_exact_punctuation(self):
        exact = '{"username":"test_user","profile":"details","followers_count":12}'
        different = '{"username":"testuser","profile":"details","followers_count":12}'
        self.assertTrue(all_search._has_profile_evidence(exact, "test_user"))
        self.assertFalse(all_search._has_profile_evidence(different, "test_user"))

    def test_handle_match_does_not_match_a_longer_word(self):
        self.assertFalse(all_search._body_mentions_username(
            "the account is test_user123", "test_user"
        ))

    def test_slash_is_url_structure_not_username_character(self):
        self.assertTrue(all_search._path_contains_username(
            "https://example.com/@testuser/videos", "testuser"
        ))

    def test_substring_username_does_not_match(self):
        self.assertFalse(all_search._path_contains_username(
            "https://example.com/testuser123", "testuser"
        ))

    def test_tiktok_profile_data_can_be_found(self):
        response = FakeResponse(
            body='{"userInfo":{"user":{"uniqueId":"testuser","nickname":"Test","follower_count":10}}}',
            url="https://www.tiktok.com/@testuser",
        )
        result = self.check(response, "https://www.tiktok.com/@{}")
        self.assertEqual(result["status"], "found")

    def test_redirect_to_another_host_is_not_found(self):
        response = FakeResponse(url="https://login.example.net/testuser")
        result = self.check(response)
        self.assertEqual(result["status"], "not_found")
        self.assertIn("redirected away", result["detail"])

    def test_redirected_404_is_not_reported_as_missing_profile(self):
        response = FakeResponse(
            status=404, body="Page not found",
            url="https://login.example.net/testuser"
        )
        result = self.check(response)
        self.assertIn("redirected away", result["detail"])

    def test_security_challenge_overrides_missing_profile_boilerplate(self):
        response = FakeResponse(
            body="Access denied. Profile not found. Verify you are human.",
        )
        result = self.check(response)
        self.assertIn("security or anti-bot", result["detail"])

    def test_redirect_to_wrong_path_is_not_found(self):
        response = FakeResponse(url="https://example.com/home")
        self.assertEqual(self.check(response)["status"], "not_found")

    def test_timeout_is_not_found(self):
        with patch("searchers.all_search.requests.get", side_effect=all_search.requests.Timeout):
            result = all_search._check_site("Example", "https://example.com/{}", "testuser")
        self.assertEqual(result["status"], "not_found")

    def test_invalid_username_returns_no_results(self):
        self.assertEqual(list(all_search.iter_username_results("bad username")), [])
        self.assertEqual(list(all_search.iter_username_results("")), [])

    def test_parallel_results_are_grouped_and_sorted(self):
        fake_sites = {"Zulu": "https://zulu.test/{}", "Beta": "https://beta.test/{}", "Alpha": "https://alpha.test/{}"}
        statuses = {"Zulu": "not_found", "Beta": "not_found", "Alpha": "found"}

        def fake_check(site, template, username):
            return {"site": site, "url": template.format(username), "status": statuses[site]}

        with patch.object(all_search, "SITES", fake_sites), patch.object(
            all_search, "_check_site", side_effect=fake_check
        ):
            results = all_search.search_username("valid_user")
        self.assertEqual([r["site"] for r in results], ["Alpha", "Beta", "Zulu"])


if __name__ == "__main__":
    unittest.main()
