# FIFA LMS Monitor

Monitors the FIFA "Last Minute Sales" ticket feed for **all upcoming matches** and
sends Telegram alerts when new seat drops appear.

## How it works

- `monitor.py` fetches `https://fifaticketscout.com/data/lms_drops.json`, considers
  every **upcoming** match (any city; past matches are skipped), and alerts on **new**
  drops with **more than 50 seats** (`count > MIN_SEATS`, `MIN_SEATS = 50` — raised
  from 5 to avoid spamming the group now that all matches are watched).
- **Only new drops going forward alert.** State is persisted in `lms_state.json`,
  committed back to `main` by the workflow (`Save state` step). A drop only fires once.
- **Anti-spam design:** (1) on first run / empty state the whole current feed is
  baselined silently (no cold-start storm); (2) all new drops within a single run are
  grouped into one message, so at most one Telegram message per ~5-min run.
- There is intentionally **no time-based freshness filter**. An earlier 30-minute
  `drop_time` filter silently swallowed real drops the feed published late/backfilled
  (e.g. a 4.6k POR v ESP release was missed). "Already handled" is tracked purely via
  `lms_state.json`, not the clock. Do not re-add a drop_time cutoff.
- Alerts go to Telegram; secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set
  as GitHub Actions repo secrets.
- `.github/workflows/lms-monitor.yml` runs `monitor.py` and notifies Telegram on
  failure.

## Scheduling / triggers

The GitHub Actions `schedule:` cron is present but **the real trigger is an external
[cronjob.org](https://cronjob.org) job** that hits the workflow via
`workflow_dispatch` every ~5 minutes. That is why runs show up as `workflow_dispatch`
events rather than `schedule`. If run frequency needs to change, update the cronjob.org
job — not just the workflow cron.

## Data feed notes

The upstream `lms_drops.json` schema can change. `recent` entries are positional
arrays; only the first four fields are used:
`[match_idx, slot_idx, cat_idx, count, ...]`. The code unpacks `entry[:4]` so extra
trailing fields the feed adds don't break parsing.

## Testing locally

Run against the live feed with network sends stubbed so no real Telegram message fires
and `lms_state.json` isn't polluted:

```bash
TELEGRAM_BOT_TOKEN=test TELEGRAM_CHAT_ID=test python3 -c "
import monitor
monitor.send_telegram = lambda *a, **k: None
monitor.send_alert = lambda header, by_match: print('alert:', len(by_match), 'matches')
monitor.main()
"
git checkout -- lms_state.json   # discard test state write
```

## Pushing changes

The workflow auto-commits `chore: state` to `main`, so `git pull --rebase` before
pushing to avoid non-fast-forward rejections.
