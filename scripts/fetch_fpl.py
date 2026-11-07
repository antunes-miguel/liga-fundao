#!/usr/bin/env python3
"""Fetch Liga Fundão data from the official FPL API and write data/fpl.json.

Runs in GitHub Actions (see .github/workflows/update-data.yml) and needs only
the Python standard library. Run it locally with:

    python scripts/fetch_fpl.py

Only gameweeks that FPL has finished and checked (final bonus points) are
written, so the debts don't move around while matches are still being played.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LEAGUE_ID = 144341

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "fpl.json"
NAMES_FILE = ROOT / "data" / "names.json"

API = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (liga-fundao data updater)"}

# FPL chip ids -> names used on the page
CHIP_NAMES = {
    "wildcard": "Wildcard",
    "bboost": "Bench Boost",
    "3xc": "Triple Captain",
    "freehit": "Free Hit",
}


def get(path, retries=4):
    url = f"{API}/{path}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"GET {url} failed: {exc}") from exc
            time.sleep(2 ** (attempt + 1))


def load_name_overrides():
    """data/names.json maps an FPL entry id (or FPL manager name) to the name
    shown on the page, e.g. {"1234567": "Rui Bimba"}."""
    if not NAMES_FILE.exists():
        return {}
    return json.loads(NAMES_FILE.read_text(encoding="utf-8"))


def captain_pick(picks, live_pts, names):
    """Who actually got the armband (FPL moves it to the vice if the captain
    doesn't play) and the best option in the starting XI that week."""
    xi = [p for p in picks if p["position"] <= 11]
    armband = next((p for p in picks if p["multiplier"] > 1), None)
    best = max(xi, key=lambda p: live_pts.get(p["element"], 0))
    return {
        "c": names.get(armband["element"]) if armband else None,
        "pts": live_pts.get(armband["element"], 0) if armband else 0,
        "mult": armband["multiplier"] if armband else 1,
        "best": names.get(best["element"]),
        "best_pts": live_pts.get(best["element"], 0),
    }


def next_deadline(events, now):
    """The earliest gameweek deadline still in the future, as {"gw": 10, "time": "<UTC ISO>"}.
    None when the season is over. Used by scripts/notify.py for the deadline reminder."""
    upcoming = [(e["deadline_time"], e["id"]) for e in events
                if e.get("deadline_time") and parse_utc(e["deadline_time"]) > now]
    if not upcoming:
        return None
    time_, gw = min(upcoming, key=lambda t: parse_utc(t[0]))
    return {"gw": gw, "time": time_}


def parse_utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def league_entries():
    entries, page = [], 1
    while True:
        data = get(f"leagues-classic/{LEAGUE_ID}/standings/?page_standings={page}")
        entries.extend(data["standings"]["results"])
        if not data["standings"]["has_next"]:
            return data["league"], entries
        page += 1


def main():
    overrides = load_name_overrides()

    boot = get("bootstrap-static/")
    events = boot["events"]
    done = {e["id"] for e in events if e["finished"] and e["data_checked"]}
    player_names = {e["id"]: e["web_name"] for e in boot["elements"]}

    # Finished GWs never change, so reuse captain data we already have
    old_captains = {}
    if OUT_FILE.exists():
        old_captains = json.loads(OUT_FILE.read_text(encoding="utf-8")).get("captains", {})
    live_cache = {}

    def live_points(gw):
        if gw not in live_cache:
            live_cache[gw] = {e["id"]: e["stats"]["total_points"] for e in get(f"event/{gw}/live/")["elements"]}
        return live_cache[gw]

    league, entries = league_entries()

    players, matchweeks, transfers, bench, captains, chips_used = [], {}, {}, {}, {}, {}
    for e in entries:
        entry_id = e["entry"]
        name = overrides.get(str(entry_id)) or overrides.get(e["player_name"]) or e["player_name"]
        players.append({
            "entry": entry_id,
            "name": name,
            "fpl_name": e["player_name"],
            "team": e["entry_name"],
        })

        history = get(f"entry/{entry_id}/history/")
        for gw in history["current"]:
            if gw["event"] not in done:
                continue
            key = f"GW{gw['event']}"
            matchweeks.setdefault(key, {})[name] = gw["points"]
            transfers.setdefault(key, {})[name] = gw["event_transfers_cost"]
            bench.setdefault(key, {})[name] = gw["points_on_bench"]
            cached = old_captains.get(key, {}).get(name)
            if cached is None:
                picks = get(f"entry/{entry_id}/event/{gw['event']}/picks/")["picks"]
                cached = captain_pick(picks, live_points(gw["event"]), player_names)
            captains.setdefault(key, {})[name] = cached

        used = {}
        for chip in history["chips"]:
            if chip["event"] not in done:
                continue
            label = CHIP_NAMES.get(chip["name"], chip["name"])
            used.setdefault(label, []).append(f"GW{chip['event']}")
        chips_used[name] = used

    order = lambda d: dict(sorted(d.items(), key=lambda kv: int(kv[0][2:])))
    out = {
        "league": {"id": league["id"], "name": league["name"]},
        "last_gw": max(done) if done else 0,
        "players": players,
        "matchweeks": order(matchweeks),
        "transfers": order(transfers),
        "bench": order(bench),
        "captains": order(captains),
        "chips_used": chips_used,
        "next_deadline": next_deadline(events, datetime.now(timezone.utc)),
    }

    # Only touch the file (and its timestamp) when the data actually changed,
    # so the workflow doesn't commit every run.
    if OUT_FILE.exists():
        old = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        old.pop("updated_at", None)
        if old == out:
            print("No changes.")
            return

    out["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote data/fpl.json: {len(players)} players, up to GW{out['last_gw']}.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        sys.exit(str(exc))
