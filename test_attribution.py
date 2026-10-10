"""Attribution contract tests. Expected values are worked by hand from the spec."""

import unittest

from attribution import (
    parse_link,
    record_first_open,
    record_touch,
    resolve_signup,
)

CAMPAIGN_URL = (
    "https://app.conty.com/open"
    "?click_id=c_abc123&channel=campaign&campaign_id=summer26"
    "&clicked_at=2026-10-01T10:00:00Z"
)


class TestCoreHappyPath(unittest.TestCase):
    def test_parse_campaign_link(self):
        touch = parse_link(CAMPAIGN_URL)
        self.assertTrue(touch["valid"])
        self.assertEqual(touch["click_id"], "c_abc123")
        self.assertEqual(touch["channel"], "campaign")
        self.assertEqual(touch["campaign_id"], "summer26")
        self.assertEqual(touch["clicked_at"], "2026-10-01T10:00:00Z")

    def test_single_campaign_touch_wins(self):
        store = record_first_open("install-1", "2026-10-01T10:05:00Z")
        record_touch(store, parse_link(CAMPAIGN_URL), "2026-10-01T10:05:00Z")
        res = resolve_signup(store, "2026-10-02T10:00:00Z")
        self.assertFalse(res["is_organic"])
        self.assertEqual(res["origin"]["channel"], "campaign")
        self.assertEqual(res["origin"]["click_id"], "c_abc123")
        self.assertEqual(res["origin"]["campaign_id"], "summer26")
        self.assertEqual(len(res["touches"]), 1)
        self.assertEqual(res["touches"][0]["verdict"], "won")
        self.assertEqual(res["touches"][0]["reason_code"], "won")


if __name__ == "__main__":
    unittest.main()
