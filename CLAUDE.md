# FIFA LMS Monitor — Dallas

Monitors the FIFA "Last Minute Sales" ticket feed for Dallas matches and sends
Telegram alerts when new seat drops appear.

## How it works

- `monitor.py` fetches `https://fifaticketscout.com/data/lms_drops.json`, filters
  for upcoming **Dallas** matches, and alerts on **new** drops with **more than 5
  seats** (`count > MIN_SEATS`, `MIN_SEATS = 5`).
- State is persisted in `lms_state.json`, committed back to `main` by the workflow
  (`Save state` step) so drops already alerted aren't re-sent.
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
