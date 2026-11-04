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

    events = get("bootstrap-static/")["events"]
    done = {e["id"] for e in events if e["finished"] and e["data_checked"]}

    league, entries = league_entries()

    players, matchweeks, transfers, chips_used = [], {}, {}, {}
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
        "chips_used": chips_used,
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
