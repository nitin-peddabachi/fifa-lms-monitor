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
MIN_SEATS = 50  # only alert on drops with more than this many seats (anti-spam)
HOME_CITY = "Dallas"  # highlighted + sorted to top of each alert


def fetch_data():
    r = requests.get(DATA_URL, headers={"Cache-Control": "no-cache"}, timeout=15)
    r.raise_for_status()
    return r.json()


def load_state():
    """Returns (seen, existed). existed=False means first run -> baseline only."""
    if not os.path.exists(STATE_FILE):
        return {}, False
    with open(STATE_FILE) as f:
        raw = json.load(f)["seen"]
    result = {}
    for item in raw:
        if len(item) == 3:
            result[tuple(item)] = 0
        else:
            result[tuple(item[:3])] = item[3]
    return result, True


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
    # Show HOME_CITY matches first so they don't get lost in a long message.
    items = sorted(by_match.items(), key=lambda kv: kv[1]["city"] != HOME_CITY)
    for match_name, info in items:
        ko = datetime.fromisoformat(info["kickoff"]).astimezone(CT).strftime("%-m/%-d %-I:%M%p CT")
        if info["city"] == HOME_CITY:
            lines.append(f'\n🔴🔴 <b>{match_name} — {info["city"].upper()}</b> 🔴🔴 ({info["stage"]}) | KO: {ko}')
        else:
            lines.append(f'\n<b>{match_name}</b> — {info["city"]} ({info["stage"]}) | KO: {ko}')
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
            by_match[k] = {"city": drop["city"], "stage": drop["stage"], "kickoff": drop["kickoff"], "cats": {}}
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

    seen, state_existed = load_state()
    first_run = not state_existed

    now = datetime.now(timezone.utc)
    # All upcoming matches (any city). Past matches can't have relevant drops.
    upcoming_idxs = {
        i
        for i, m in enumerate(data["matches"])
        if datetime.fromisoformat(m["ko"]) > now
    }

    new_drops = []

    for entry in data["recent"]:
        match_idx, slot_idx, cat_idx, count = entry[:4]
        if match_idx not in upcoming_idxs:
            continue
        if count <= MIN_SEATS:
            continue
        key = (match_idx, slot_idx, cat_idx)
        if key in seen:
            seen[key] = count
            continue
        # First run: baseline everything currently in the feed without alerting,
        # so a cold start doesn't blast the whole ~14-day backlog.
        if first_run:
            seen[key] = count
            continue
        match = data["matches"][match_idx]
        cat = data["categories"][cat_idx] if cat_idx < len(data["categories"]) else "Unknown"
        drop_time = datetime.fromisoformat(data["recent_start"]) + timedelta(
            minutes=slot_idx * data["recent_slot_min"]
        )
        new_drops.append({
            "match": match["m"],
            "city": match.get("city", "?"),
            "stage": match["stage"],
            "kickoff": match["ko"],
            "category": cat,
            "count": count,
            "drop_time": drop_time,
            "key": key,
        })
        seen[key] = count

    if new_drops:
        send_alert("🚨 <b>FIFA LMS Drop</b>", group_by_match(new_drops))

    save_state(seen)
    print(f"Done. {len(new_drops)} new drop(s).")


if __name__ == "__main__":
    main()
