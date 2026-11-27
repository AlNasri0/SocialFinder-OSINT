import unittest
from unittest.mock import patch

from app import app


class AppTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_home_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Social Finder", response.data)

    def test_health_endpoint_reports_platform_count(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertGreater(payload["platforms"], 0)

    def test_security_headers_are_present(self):
        response = self.client.get("/health")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_invalid_username_is_rejected(self):
        response = self.client.post("/stream", data={"username": "not a username"})
        self.assertEqual(response.status_code, 400)

    def test_stream_sends_progress_and_results(self):
        fake_result = {
            "site": "Example", "url": "https://example.com/testuser",
            "status": "found", "label": "Found", "detail": "Profile data matched.",
            "http_status": 200,
        }
        with patch("app.is_rate_limited", return_value=False), patch(
            "app.iter_username_results", return_value=iter([fake_result])
        ):
            response = self.client.post("/stream", data={"username": "testuser"})
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "start"', body)
        self.assertIn('"type": "result"', body)
        self.assertIn('"type": "complete"', body)

    def test_rate_limit_response(self):
        with patch("app.is_rate_limited", return_value=True):
            response = self.client.post("/stream", data={"username": "testuser"})
        self.assertEqual(response.status_code, 429)


if __name__ == "__main__":
    unittest.main()
