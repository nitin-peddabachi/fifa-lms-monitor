import requests
import json
import os
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = "lms_state.json"
DATA_URL = "https://fifaticketscout.com/data/lms_drops.json"
CUTOFF = datetime(2026, 6, 28, tzinfo=timezone.utc)


def fetch_data():
    r = requests.get(DATA_URL, headers={"Cache-Control": "no-cache"}, timeout=15)
    r.raise_for_status()
    return r.json()


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(tuple(x) for x in json.load(f)["seen"])
    return set()


def save_state(seen):
    with open(STATE_FILE, "w") as f:
        json.dump({"seen": [list(k) for k in seen]}, f)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
        timeout=10,
    )
    r.raise_for_status()


def main():
    data = fetch_data()
    seen = load_state()

    dallas_idxs = {
        i
        for i, m in enumerate(data["matches"])
        if m.get("city") == "Dallas"
        and datetime.fromisoformat(m["ko"]) >= CUTOFF
    }

    new_drops = []
    for entry in data["recent"]:
        match_idx, slot_idx, cat_idx, count = entry
        if match_idx not in dallas_idxs:
            continue
        key = (match_idx, slot_idx, cat_idx)
        if key in seen:
            continue
        match = data["matches"][match_idx]
        cat = data["categories"][cat_idx] if cat_idx < len(data["categories"]) else "Unknown"
        drop_time = datetime.fromisoformat(data["recent_start"]) + timedelta(
            minutes=slot_idx * data["recent_slot_min"]
        )
        new_drops.append(
            {
                "match": match["m"],
                "stage": match["stage"],
                "kickoff": match["ko"],
                "category": cat,
                "count": count,
                "drop_time": drop_time,
                "key": key,
            }
        )

    if new_drops:
        by_match = {}
        for drop in new_drops:
            k = drop["match"]
            if k not in by_match:
                by_match[k] = {"stage": drop["stage"], "kickoff": drop["kickoff"], "drops": []}
            by_match[k]["drops"].append(drop)

        lines = ["🚨 <b>FIFA LMS Drop — Dallas</b>"]
        for match_name, info in by_match.items():
            ko = datetime.fromisoformat(info["kickoff"]).strftime("%-m/%-d %-I:%M%p UTC")
            lines.append(f'\n<b>{match_name}</b> ({info["stage"]}) | KO: {ko}')
            for d in sorted(info["drops"], key=lambda x: x["drop_time"], reverse=True):
                dt = d["drop_time"].strftime("%-m/%-d %-I:%M%p UTC")
                lines.append(f'  • {d["category"]}: {d["count"]} seats (first seen {dt})')

        send_telegram("\n".join(lines))
        for drop in new_drops:
            seen.add(drop["key"])

    save_state(seen)
    print(f"Done. {len(new_drops)} new Dallas drop(s) found.")


if __name__ == "__main__":
    main()
