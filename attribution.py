"""Signup attribution contract.

Pure standard library. All timestamps are injected by the caller as
RFC3339 UTC strings (``YYYY-MM-DDTHH:MM:SSZ``); this module never reads
the clock, so every decision is deterministic and reproducible.
"""

from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

ATTRIBUTION_WINDOW_DAYS = 30

_CHANNELS = ("campaign", "referral", "community")
_CHANNEL_IDS = {
    "campaign": "campaign_id",
    "referral": "referrer_code",
    "community": "community_id",
}
_INSTANT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_instant(value):
    """Return a datetime for a whole-second RFC3339 UTC string, else None."""
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.strptime(value, _INSTANT_FORMAT)
    except ValueError:
        return None


def _channel_id(channel, values):
    """Return the channel-specific identifier pair, or {} when absent."""
    key = _CHANNEL_IDS[channel]
    return {key: values[key]} if values.get(key) else {}


def _bump_seen(entries, matches, seen_at):
    """Bump seen_count on the first matching entry; None when no match."""
    for entry in entries:
        if matches(entry):
            entry["seen_count"] += 1
            entry["seen_at"] = seen_at
            return entry
    return None


def parse_link(url):
    """Parse an attribution link into a touch record (webview-safe).

    Everything travels in query params; no referrer header is needed.
    Returns a valid touch dict, or a rejected record with a reason code
    so bad input stays auditable instead of vanishing silently.
    """
    try:
        query = parse_qs(urlparse(url).query)
    except (ValueError, AttributeError):
        return {"valid": False, "reason_code": "invalid", "raw": url}
    params = {key: values[0] for key, values in query.items() if values}
    click_id = params.get("click_id")
    channel = params.get("channel")
    clicked_at = params.get("clicked_at")
    if not click_id or not channel or not clicked_at:
        return {"valid": False, "reason_code": "missing_field", "raw": url}
    if channel not in _CHANNELS:
        return {"valid": False, "reason_code": "unknown_channel", "raw": url}
    if _parse_instant(clicked_at) is None:
        return {"valid": False, "reason_code": "invalid", "raw": url}
    touch = {
        "valid": True,
        "click_id": click_id,
        "channel": channel,
        "clicked_at": clicked_at,
    }
    touch.update(_channel_id(channel, params))
    return touch


def record_first_open(install_id, first_open_at):
    """Create the per-install store anchoring the validity window."""
    if _parse_instant(first_open_at) is None:
        raise ValueError("first_open_at must be RFC3339 UTC")
    return {"install_id": install_id, "first_open_at": first_open_at, "touches": []}


def record_touch(store, parsed_touch, seen_at):
    """Append a touch, or bump seen_count on a repeated click (idempotent)."""
    if _parse_instant(seen_at) is None:
        raise ValueError("seen_at must be RFC3339 UTC")
    if not parsed_touch.get("valid"):
        store["touches"].append(
            {
                "valid": False,
                "reason_code": parsed_touch.get("reason_code", "invalid"),
                "raw": parsed_touch.get("raw"),
                "seen_at": seen_at,
                "seen_count": 1,
            }
        )
        return store
    found = _bump_seen(
        store["touches"],
        lambda entry: entry.get("valid")
        and entry["click_id"] == parsed_touch["click_id"],
        seen_at,
    )
    if found is not None:
        return store
    entry = dict(parsed_touch)
    entry["seen_at"] = seen_at
    entry["seen_count"] = 1
    store["touches"].append(entry)
    return store


def _organic_reason(entries):
    if not entries:
        return "no_touch"
    reasons = {entry["reason_code"] for entry in entries}
    if reasons <= {"invalid", "unknown_channel", "missing_field"}:
        return "all_invalid"
    if reasons == {"after_signup"}:
        return "all_after_signup"
    if reasons == {"out_of_window"}:
        return "all_out_of_window"
    return "no_valid_touch"


def resolve_signup(store, signup_at, window_days=ATTRIBUTION_WINDOW_DAYS):
    """Resolve one signup to exactly one origin, or explicit organic."""
    signup_dt = _parse_instant(signup_at)
    first_open_dt = _parse_instant(store["first_open_at"])
    if signup_dt is None:
        raise ValueError("signup_at must be RFC3339 UTC")
    window_end = first_open_dt + timedelta(days=window_days)

    rows = []
    for entry in store["touches"]:
        if not entry.get("valid"):
            rows.append(_audit_row(entry, "lost", entry["reason_code"]))
            continue
        clicked_dt = _parse_instant(entry["clicked_at"])
        if clicked_dt > signup_dt:
            rows.append(_audit_row(entry, "lost", "after_signup"))
        elif signup_dt > window_end:
            rows.append(_audit_row(entry, "lost", "out_of_window"))
        else:
            rows.append(_audit_row(entry, None, None))

    eligible = [row for row in rows if row["reason_code"] is None]
    # Latest click wins; equal instants break by smallest click_id.
    winner = None
    if eligible:
        best_instant = max(row["_clicked_dt"] for row in eligible)
        tied = [row for row in eligible if row["_clicked_dt"] == best_instant]
        winner = min(tied, key=lambda row: row["click_id"])
        winner["verdict"] = "won"
        winner["reason_code"] = "won"
        for row in eligible:
            if row is not winner:
                row["verdict"] = "lost"
                row["reason_code"] = "superseded"

    for row in rows:
        row.pop("_clicked_dt", None)

    if winner is None:
        return {
            "install_id": store["install_id"],
            "signup_at": signup_at,
            "origin": None,
            "is_organic": True,
            "organic_reason": _organic_reason(rows),
            "window": _window_view(store["first_open_at"], window_end, window_days),
            "touches": rows,
        }
    origin = {"click_id": winner["click_id"], "channel": winner["channel"]}
    origin.update(_channel_id(winner["channel"], winner))
    return {
        "install_id": store["install_id"],
        "signup_at": signup_at,
        "origin": origin,
        "is_organic": False,
        "organic_reason": None,
        "window": _window_view(store["first_open_at"], window_end, window_days),
        "touches": rows,
    }


def _audit_row(entry, verdict, reason_code):
    row = {
        "click_id": entry.get("click_id"),
        "channel": entry.get("channel"),
        "clicked_at": entry.get("clicked_at"),
        "seen_at": entry.get("seen_at"),
        "seen_count": entry.get("seen_count", 1),
        "verdict": verdict,
        "reason_code": reason_code,
        "_clicked_dt": _parse_instant(entry.get("clicked_at")),
    }
    if entry.get("channel") in _CHANNEL_IDS:
        row.update(_channel_id(entry["channel"], entry))
    return row


def _window_view(first_open_at, window_end, window_days):
    return {
        "days": window_days,
        "start": first_open_at,
        "end": window_end.strftime(_INSTANT_FORMAT),
    }
