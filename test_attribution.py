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


class TestEdges(unittest.TestCase):
    def test_repeated_click_is_idempotent(self):
        store = record_first_open("install-4", "2026-10-01T10:05:00Z")
        record_touch(store, parse_link(CAMPAIGN_URL), "2026-10-01T10:05:00Z")
        record_touch(store, parse_link(CAMPAIGN_URL), "2026-10-01T10:06:00Z")
        res = resolve_signup(store, "2026-10-02T10:00:00Z")
        self.assertEqual(len(res["touches"]), 1)
        self.assertEqual(res["touches"][0]["seen_count"], 2)
        self.assertEqual(res["origin"]["click_id"], "c_abc123")

    def test_same_click_id_across_installs_is_separate(self):
        first = record_first_open("install-a", "2026-10-01T10:05:00Z")
        second = record_first_open("install-b", "2026-10-01T10:05:00Z")
        record_touch(first, parse_link(CAMPAIGN_URL), "2026-10-01T10:05:00Z")
        record_touch(second, parse_link(CAMPAIGN_URL), "2026-10-01T10:05:00Z")
        self.assertEqual(
            resolve_signup(first, "2026-10-02T10:00:00Z")["origin"]["click_id"],
            "c_abc123",
        )
        self.assertEqual(
            resolve_signup(second, "2026-10-02T10:00:00Z")["origin"]["click_id"],
            "c_abc123",
        )

    def test_out_of_window_touch_loses(self):
        store = record_first_open("install-5", "2026-10-01T10:00:00Z")
        record_touch(store, parse_link(CAMPAIGN_URL), "2026-10-01T10:00:00Z")
        res = resolve_signup(store, "2026-11-05T10:00:00Z")
        self.assertTrue(res["is_organic"])
        self.assertIsNone(res["origin"])
        self.assertEqual(res["organic_reason"], "all_out_of_window")
        self.assertEqual(res["touches"][0]["reason_code"], "out_of_window")

    def test_window_boundary_is_inclusive(self):
        store = record_first_open("install-6", "2026-10-01T10:00:00Z")
        record_touch(store, parse_link(CAMPAIGN_URL), "2026-10-01T10:00:00Z")
        on_edge = resolve_signup(store, "2026-10-31T10:00:00Z")
        self.assertFalse(on_edge["is_organic"])
        past_edge = resolve_signup(store, "2026-10-31T10:00:01Z")
        self.assertTrue(past_edge["is_organic"])
        self.assertEqual(past_edge["organic_reason"], "all_out_of_window")

    def test_post_signup_touch_is_kept_but_never_wins(self):
        store = record_first_open("install-7", "2026-10-01T10:00:00Z")
        record_touch(store, parse_link(CAMPAIGN_URL), "2026-10-01T10:00:00Z")
        late = parse_link(REFERRAL_URL)  # clicked 2026-10-02
        record_touch(store, late, "2026-10-03T10:00:00Z")
        res = resolve_signup(store, "2026-10-01T12:00:00Z")
        self.assertEqual(res["origin"]["click_id"], "c_abc123")
        by_id = {touch["click_id"]: touch for touch in res["touches"]}
        self.assertEqual(by_id["r_xyz789"]["verdict"], "lost")
        self.assertEqual(by_id["r_xyz789"]["reason_code"], "after_signup")

    def test_all_post_signup_is_organic(self):
        store = record_first_open("install-8", "2026-10-01T10:00:00Z")
        record_touch(store, parse_link(REFERRAL_URL), "2026-10-03T10:00:00Z")
        res = resolve_signup(store, "2026-10-01T12:00:00Z")
        self.assertTrue(res["is_organic"])
        self.assertEqual(res["organic_reason"], "all_after_signup")

    def test_invalid_links_become_rejected_rows(self):
        store = record_first_open("install-9", "2026-10-01T10:00:00Z")
        record_touch(store, parse_link("not-a-url"), "2026-10-01T10:00:00Z")
        record_touch(
            store,
            parse_link("https://app.conty.com/open?click_id=x&channel=spam&clicked_at=2026-10-01T10:00:00Z"),
            "2026-10-01T10:01:00Z",
        )
        res = resolve_signup(store, "2026-10-02T10:00:00Z")
        self.assertTrue(res["is_organic"])
        self.assertEqual(res["organic_reason"], "all_invalid")
        self.assertEqual(
            {touch["reason_code"] for touch in res["touches"]},
            {"missing_field", "unknown_channel"},
        )

    def test_non_utc_instant_formats_are_rejected(self):
        base = "https://app.conty.com/open?click_id=c_fmt&channel=campaign&campaign_id=summer26&clicked_at="
        for bad_instant in (
            "2026-10-01T10:00:00+00:00",
            "2026-10-01T10:00:00.000Z",
            "2026-10-01 10:00:00",
            "1780000000",
        ):
            with self.subTest(clicked_at=bad_instant):
                touch = parse_link(base + bad_instant)
                self.assertFalse(touch["valid"])
                self.assertEqual(touch["reason_code"], "invalid")

    def test_empty_store_is_organic_without_touch(self):
        store = record_first_open("install-10", "2026-10-01T10:00:00Z")
        res = resolve_signup(store, "2026-10-02T10:00:00Z")
        self.assertTrue(res["is_organic"])
        self.assertEqual(res["organic_reason"], "no_touch")
        self.assertEqual(res["touches"], [])

    def test_reinstall_starts_a_new_identity(self):
        old = record_first_open("install-old", "2026-10-01T10:00:00Z")
        record_touch(old, parse_link(CAMPAIGN_URL), "2026-10-01T10:00:00Z")
        fresh = record_first_open("install-new", "2026-10-05T10:00:00Z")
        res = resolve_signup(fresh, "2026-10-06T10:00:00Z")
        self.assertTrue(res["is_organic"])
        self.assertEqual(res["organic_reason"], "no_touch")


if __name__ == "__main__":
    unittest.main()
