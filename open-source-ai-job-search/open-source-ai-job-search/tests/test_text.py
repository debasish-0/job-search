from __future__ import annotations

import unittest

from jobsearch.parsers import basic_profile_hints
from jobsearch.text import normalize_key, safe_http_url, strip_html


class TextTests(unittest.TestCase):
    def test_double_encoded_html_is_cleaned(self) -> None:
        self.assertEqual(
            strip_html("&amp;lt;p&amp;gt;Hello &amp;amp; welcome&amp;lt;/p&amp;gt;"),
            "Hello & welcome",
        )

    def test_technical_tokens_do_not_collide(self) -> None:
        self.assertEqual(normalize_key("C++"), "cplusplus")
        self.assertEqual(normalize_key("C#"), "csharp")
        self.assertNotEqual(normalize_key("C++"), normalize_key("C#"))

    def test_only_http_application_urls_are_accepted(self) -> None:
        self.assertEqual(safe_http_url("javascript:alert(1)"), "")
        self.assertEqual(safe_http_url("file:///tmp/resume"), "")
        self.assertEqual(safe_http_url("https://example.com/apply"), "https://example.com/apply")

    def test_spelled_years_are_detected(self) -> None:
        hints = basic_profile_hints("Candidate\nDeveloper with five years of experience")
        self.assertEqual(hints["years_experience"], 5)


if __name__ == "__main__":
    unittest.main()
