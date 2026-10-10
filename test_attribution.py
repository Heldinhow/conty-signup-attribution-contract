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


REFERRAL_URL = (
    "https://app.conty.com/open"
    "?click_id=r_xyz789&channel=referral&referrer_code=JOAO42"
    "&clicked_at=2026-10-02T10:00:00Z"
)


class TestWinningRule(unittest.TestCase):
    def test_two_links_latest_valid_touch_wins(self):
        store = record_first_open("install-2", "2026-10-01T11:00:00Z")
        record_touch(store, parse_link(CAMPAIGN_URL), "2026-10-01T11:00:00Z")
        record_touch(store, parse_link(REFERRAL_URL), "2026-10-02T10:05:00Z")
        res = resolve_signup(store, "2026-10-03T10:00:00Z")
        self.assertFalse(res["is_organic"])
        self.assertEqual(res["origin"]["click_id"], "r_xyz789")
        self.assertEqual(res["origin"]["channel"], "referral")
        by_id = {touch["click_id"]: touch for touch in res["touches"]}
        self.assertEqual(by_id["r_xyz789"]["verdict"], "won")
        self.assertEqual(by_id["r_xyz789"]["reason_code"], "won")
        self.assertEqual(by_id["c_abc123"]["verdict"], "lost")
        self.assertEqual(by_id["c_abc123"]["reason_code"], "superseded")

    def test_timestamp_tie_breaks_by_smallest_click_id(self):
        tied_at = "2026-10-02T10:00:00Z"
        late = (
            "https://app.conty.com/open"
            "?click_id=b_second&channel=community&community_id=funk-rj"
            "&clicked_at=" + tied_at
        )
        early = (
            "https://app.conty.com/open"
            "?click_id=a_first&channel=campaign&campaign_id=summer26"
            "&clicked_at=" + tied_at
        )
        store = record_first_open("install-3", "2026-10-02T10:05:00Z")
        record_touch(store, parse_link(late), "2026-10-02T10:05:00Z")
        record_touch(store, parse_link(early), "2026-10-02T10:06:00Z")
        res = resolve_signup(store, "2026-10-03T10:00:00Z")
        self.assertEqual(res["origin"]["click_id"], "a_first")
        by_id = {touch["click_id"]: touch for touch in res["touches"]}
        self.assertEqual(by_id["a_first"]["reason_code"], "won")
        self.assertEqual(by_id["b_second"]["reason_code"], "superseded")


if __name__ == "__main__":
    unittest.main()
