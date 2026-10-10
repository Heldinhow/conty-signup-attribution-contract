# conty-signup-attribution-contract

Attribution contract for Conty creator signup origin: what travels in the
link, what the app records on first open, and how signup resolves exactly
one auditable origin.

Standard library only. Run the suite with:

```sh
python3 -m unittest
```

## Contract

**What travels in the link.** Everything rides in query params, so links
survive webviews that never send a referrer. Exact parameter names:

| Param | Required | Meaning |
| --- | --- | --- |
| `click_id` | yes | Opaque unique click identifier |
| `channel` | yes | `campaign` \| `referral` \| `community` |
| `clicked_at` | yes | Click instant, RFC3339 UTC (`YYYY-MM-DDTHH:MM:SSZ`) |
| `campaign_id` | campaign only | Campaign identifier |
| `referrer_code` | referral only | Inviter code |
| `community_id` | community only | Community identifier |

`clicked_at` is minted at link generation and may predate first open (an
invite clicked before install is valid). Any other instant format, an
unknown channel, or a missing required field makes the link a rejected
audit row (`invalid`, `unknown_channel`, `missing_field`) — never silent.

**What the app records.** On first open the app creates
`install_id` plus an immutable `first_open_at` anchoring the validity
window, then appends one touch per (`install_id`, `click_id`) with its own
`seen_at` stamp. A repeated click with the same pair only bumps
`seen_count`; the same `click_id` under another install is a separate
touch. A reinstall mints a new install with no migrated touches.

**How signup consumes it.** `resolve_signup(store, signup_at)` returns one
origin or explicit organic. A touch is eligible when `clicked_at <=
signup_at` **and** `signup_at <= first_open_at + 30 days` (both ends
inclusive; `ATTRIBUTION_WINDOW_DAYS = 30`, overridable per call). The
latest eligible touch wins; equal instants at whole-second precision break
by smallest `click_id`. Every touch is listed with `verdict` (`won` /
`lost`) and `reason_code` (`won`, `superseded`, `out_of_window`,
`after_signup`, `invalid` family); re-clicks collapse into a single row
carrying `seen_count` instead of emitting extra rows.
Post-signup touches persist in the audit but never win. No valid touch
means `is_organic: true` with `organic_reason` (`no_touch`,
`all_out_of_window`, `all_after_signup`, `all_invalid`, `no_valid_touch`
for mixed losers). Resolution is one-shot per (`install_id`, `signup_at`).

## Link examples

Campaign:

```text
https://app.conty.com/open?click_id=c_abc123&channel=campaign&campaign_id=summer26&clicked_at=2026-10-01T10:00:00Z
```

Referral:

```text
https://app.conty.com/open?click_id=r_xyz789&channel=referral&referrer_code=JOAO42&clicked_at=2026-10-02T10:00:00Z
```

Community:

```text
https://app.conty.com/open?click_id=m_funk21&channel=community&community_id=funk-rj&clicked_at=2026-10-01T09:00:00Z
```

## Worked signup response

Install `install-demo`, first open `2026-10-01T11:00:00Z`: campaign link
opened twice, referral link once, one unknown-channel link once, one
community link opened after signup; signup `2026-10-03T10:00:00Z`.
Verified output of `resolve_signup`:

```json
{
  "install_id": "install-demo",
  "signup_at": "2026-10-03T10:00:00Z",
  "origin": {
    "click_id": "r_xyz789",
    "channel": "referral",
    "referrer_code": "JOAO42"
  },
  "is_organic": false,
  "organic_reason": null,
  "window": {
    "days": 30,
    "start": "2026-10-01T11:00:00Z",
    "end": "2026-10-31T11:00:00Z"
  },
  "touches": [
    {
      "click_id": "c_abc123",
      "channel": "campaign",
      "clicked_at": "2026-10-01T10:00:00Z",
      "seen_at": "2026-10-01T11:01:00Z",
      "seen_count": 2,
      "verdict": "lost",
      "reason_code": "superseded",
      "campaign_id": "summer26"
    },
    {
      "click_id": "r_xyz789",
      "channel": "referral",
      "clicked_at": "2026-10-02T10:00:00Z",
      "seen_at": "2026-10-02T10:05:00Z",
      "seen_count": 1,
      "verdict": "won",
      "reason_code": "won",
      "referrer_code": "JOAO42"
    },
    {
      "click_id": null,
      "channel": null,
      "clicked_at": null,
      "seen_at": "2026-10-02T11:00:00Z",
      "seen_count": 1,
      "verdict": "lost",
      "reason_code": "unknown_channel"
    },
    {
      "click_id": "m_funk21",
      "channel": "community",
      "clicked_at": "2026-10-04T10:00:00Z",
      "seen_at": "2026-10-04T10:00:00Z",
      "seen_count": 1,
      "verdict": "lost",
      "reason_code": "after_signup",
      "community_id": "funk-rj"
    }
  ]
}
```

The re-clicked campaign touch stays a single row (`seen_count: 2`) but
loses as `superseded` to the later referral touch; the unknown-channel
link is kept as a rejected row; the community link opened after signup is
kept but loses as `after_signup`.

## AI usage

### Done with AI

Stack analysis review, spec-flow gap analysis, the spec and ticket texts,
and the first drafts of `attribution.py`, `test_attribution.py`, and this
README were generated with AI assistance (OpenCode agent session).

### Human review

The human (repo owner) decided the stack, the winning rule, the 30-day
window, the dedup scope, the link payload, the store shape, and the audit
response shape across grilling rounds Q1–Q14; approved the spec, the
ticket breakdown, and every gap fix; and must run the suite and review
this diff before pushing.
