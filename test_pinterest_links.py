"""ReelSalva Pinterest URL validation (no network required)."""
import unittest

from app import clean_link


class PinterestLinksTest(unittest.TestCase):
    def test_full_pin_link(self):
        self.assertEqual(
            clean_link("https://www.pinterest.com/pin/123456789012345/"),
            ("https://www.pinterest.com/pin/123456789012345/", "123456789012345", "pinterest"),
        )

    def test_br_domain_and_tracking_parameters(self):
        self.assertEqual(
            clean_link("https://br.pinterest.com/pin/123456789012/?foo=bar"),
            ("https://www.pinterest.com/pin/123456789012/", "123456789012", "pinterest"),
        )

    def test_pinit_short_link(self):
        self.assertEqual(
            clean_link("https://pin.it/AbC1234"),
            ("https://pin.it/AbC1234", "AbC1234", "pinterest"),
        )

    def test_other_pinterest_page_is_rejected(self):
        with self.assertRaises(ValueError):
            clean_link("https://www.pinterest.com/explore/anything/")

    def test_arbitrary_domain_cannot_masquerade_as_pinterest(self):
        with self.assertRaises(ValueError):
            clean_link("https://pinterest.com.attacker.example/pin/123456789/")

    def test_no_http_or_nonstandard_ports(self):
        for link in ("http://pin.it/AbC1234", "https://pin.it:444/AbC1234"):
            with self.subTest(link=link), self.assertRaises(ValueError):
                clean_link(link)


if __name__ == "__main__":
    unittest.main()
