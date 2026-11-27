import unittest
from urllib.parse import urlparse

from data.sites import SITES


class SiteTemplateTests(unittest.TestCase):
    def test_curated_site_list_has_expected_coverage(self):
        self.assertGreaterEqual(len(SITES), 50)

    def test_every_site_template_is_https_and_has_one_handle_slot(self):
        for site, template in SITES.items():
            with self.subTest(site=site):
                self.assertEqual(template.count("{}"), 1)
                parsed = urlparse(template.format("sample_handle"))
                self.assertEqual(parsed.scheme, "https")
                self.assertTrue(parsed.hostname)
                self.assertNotIn(" ", parsed.netloc)

    def test_every_site_template_produces_a_profile_url(self):
        for site, template in SITES.items():
            with self.subTest(site=site):
                url = template.format("sample_handle")
                self.assertIn("sample_handle", url)


if __name__ == "__main__":
    unittest.main()
