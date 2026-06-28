import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = "lms_state.json"
DATA_URL = "https://fifaticketscout.com/data/lms_drops.json"
BOOKING_URL = "https://www.fifa.com/fifaplus/en/tournaments/mens/worldcup/canadamexicousa2026/tickets"
CT = ZoneInfo("America/Chicago")
MIN_SEATS = 5


def fetch_data():
    r = requests.get(DATA_URL, headers={"Cache-Control": "no-cache"}, timeout=15)
    r.raise_for_status()
    return r.json()


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE) as f:
        raw = json.load(f)["seen"]
    result = {}
    for item in raw:
        if len(item) == 3:
            result[tuple(item)] = 0
        else:
            result[tuple(item[:3])] = item[3]
    return result


def save_state(seen):
    with open(STATE_FILE, "w") as f:
        json.dump({"seen": [list(k) + [v] for k, v in seen.items()]}, f)


def send_telegram(text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()


def send_alert(header, by_match):
    lines = [header]
    for match_name, info in by_match.items():
        ko = datetime.fromisoformat(info["kickoff"]).astimezone(CT).strftime("%-m/%-d %-I:%M%p CT")
        lines.append(f'\n<b>{match_name}</b> ({info["stage"]}) | KO: {ko}')
        for cat, d in sorted(info["cats"].items()):
            first = d["first_seen"].astimezone(CT).strftime("%-m/%-d %-I:%M%p CT")
            seat_info = f'{d["count"]} seats'
            if d.get("added"):
                seat_info += f' (+{d["added"]} new)'
            lines.append(f'  • {cat}: {seat_info} (first seen {first})')

    reply_markup = {
        "inline_keyboard": [[{"text": "Book now on FIFA.com", "url": BOOKING_URL}]]
    }
    send_telegram("\n".join(lines), reply_markup=reply_markup)


def group_by_match(drops):
    by_match = {}
    for drop in drops:
        k = drop["match"]
        if k not in by_match:
            by_match[k] = {"stage": drop["stage"], "kickoff": drop["kickoff"], "cats": {}}
        cats = by_match[k]["cats"]
        if drop["category"] not in cats:
            cats[drop["category"]] = {"count": 0, "first_seen": drop["drop_time"]}
        cats[drop["category"]]["count"] += drop["count"]
        if drop.get("added"):
            cats[drop["category"]]["added"] = cats[drop["category"]].get("added", 0) + drop["added"]
        if drop["drop_time"] < cats[drop["category"]]["first_seen"]:
            cats[drop["category"]]["first_seen"] = drop["drop_time"]
    return by_match


def main():
    try:
        data = fetch_data()
    except Exception as e:
        send_telegram(f"⚠️ <b>FIFA LMS Monitor — error fetching data</b>\n{e}")
        sys.exit(1)

    seen = load_state()

    now = datetime.now(timezone.utc)
    dallas_idxs = {
        i
        for i, m in enumerate(data["matches"])
        if m.get("city") == "Dallas"
        and datetime.fromisoformat(m["ko"]) > now
    }

    new_drops = []
    redrops = []

    for entry in data["recent"]:
        match_idx, slot_idx, cat_idx, count = entry
        if match_idx not in dallas_idxs:
            continue
        if count < MIN_SEATS:
            continue
        key = (match_idx, slot_idx, cat_idx)
        match = data["matches"][match_idx]
        cat = data["categories"][cat_idx] if cat_idx < len(data["categories"]) else "Unknown"
        drop_time = datetime.fromisoformat(data["recent_start"]) + timedelta(
            minutes=slot_idx * data["recent_slot_min"]
        )
        base = {
            "match": match["m"],
            "stage": match["stage"],
            "kickoff": match["ko"],
            "category": cat,
            "count": count,
            "drop_time": drop_time,
            "key": key,
        }

        if key not in seen:
            new_drops.append(base)
            seen[key] = count
        elif count > seen[key]:
            redrops.append({**base, "added": count - seen[key]})
            seen[key] = count

    if new_drops:
        send_alert("🚨 <b>FIFA LMS Drop — Dallas</b>", group_by_match(new_drops))

    if redrops:
        send_alert("🔁 <b>FIFA LMS Re-drop — Dallas</b>", group_by_match(redrops))

    save_state(seen)
    print(f"Done. {len(new_drops)} new, {len(redrops)} re-drop(s).")


if __name__ == "__main__":
    main()
