#!/usr/bin/env python3
"""Fetch Liga Fundão data from the official FPL API and write data/fpl.json.

Runs in GitHub Actions (see .github/workflows/update-data.yml) and needs only
the Python standard library. Run it locally with:

    python scripts/fetch_fpl.py

Final gameweeks (FPL has finished and checked them) come from FPL's season history. A gameweek
that is under way (its deadline has passed but FPL hasn't finalised it) is written too, as
PROVISIONAL: its points are worked out from FPL's live player points, the same way FPL does it
(each player's points x his multiplier, with the automatic substitutions), and the top-level
"provisional" list says how many of its matches are played, so the page can warn that the numbers
may still change. "last_gw" is always the last FINAL gameweek: the notifications rely on that.

Besides the points, it stores each manager's starting XI ("xi": GW -> manager -> 11 FPL
player ids, in pick order) and "xi_names" (id -> player name) for the ids used. Ids,
because two players can share a name ("Gabriel"). Unlike the points, the XIs are also
stored for a gameweek that is under way (its deadline has passed, FPL shows the squads
from then on, and they can no longer change), so they don't wait for the final result.
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


def starting_xi(picks):
    """The 11 players the manager picked to start (pick positions 1-11, in that order)."""
    return [p["element"] for p in sorted(picks, key=lambda p: p["position"]) if p["position"] <= 11]


def live_total(picks, subs, live_pts):
    """(points, bench points) of a squad from live player points. FPL's own history gives the same
    numbers once a gameweek is final (checked against all finished gameweeks of the league)."""
    mult = {p["element"]: p["multiplier"] for p in picks}
    for s in subs:  # automatic substitutions: the player who comes in takes the place of the one who goes out
        if s["element_in"] in mult and s["element_out"] in mult:
            if mult[s["element_in"]] == 0:
                mult[s["element_in"]] = mult[s["element_out"]]
            mult[s["element_out"]] = 0
    pts = sum(live_pts.get(el, 0) * m for el, m in mult.items())
    bench = sum(live_pts.get(p["element"], 0) for p in picks if p["position"] > 11 and mult[p["element"]] == 0)
    return pts, bench


def fixture_progress(gw):
    """How far a gameweek is: {"gw", "total", "played", "live"} (played = finished, even if only provisionally)."""
    fixtures = get(f"fixtures/?event={gw}")
    played = sum(1 for f in fixtures if f.get("finished") or f.get("finished_provisional"))
    live = sum(1 for f in fixtures if f.get("started") and not (f.get("finished") or f.get("finished_provisional")))
    return {"gw": gw, "total": len(fixtures), "played": played, "live": live}


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

    now = datetime.now(timezone.utc)
    boot = get("bootstrap-static/")
    events = boot["events"]
    done = {e["id"] for e in events if e["finished"] and e["data_checked"]}
    # Deadline passed but not final yet: squads are visible and locked, results still moving
    under_way = {e["id"] for e in events
                 if e.get("deadline_time") and parse_utc(e["deadline_time"]) <= now and e["id"] not in done}
    player_names = {e["id"]: e["web_name"] for e in boot["elements"]}

    # Finished GWs never change, so reuse the captain and XI data we already have. The exception:
    # what was stored while a GW was still provisional is recomputed once, when the GW becomes final.
    old_captains, old_xi, old_provisional = {}, {}, set()
    if OUT_FILE.exists():
        old = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        old_captains, old_xi = old.get("captains", {}), old.get("xi", {})
        old_provisional = {f"GW{p['gw']}" for p in old.get("provisional", [])}
    live_cache = {}

    def live_points(gw):
        if gw not in live_cache:
            live_cache[gw] = {e["id"]: e["stats"]["total_points"] for e in get(f"event/{gw}/live/")["elements"]}
        return live_cache[gw]

    # How far each gameweek under way is. Its scores are only written once a match has started
    # (before that everybody has 0 and the page would show an empty gameweek).
    progress = {}
    for gw in sorted(under_way):
        try:
            progress[gw] = fixture_progress(gw)
        except RuntimeError as exc:
            print(f"No fixture progress for GW{gw}: {exc}")
    scored = {gw for gw, pr in progress.items() if pr["played"] + pr["live"] >= 1}
    prov_rows = {gw: {} for gw in scored}  # gw -> manager -> provisional numbers
    prov_complete = set(scored)            # dropped for a gameweek if any manager's squad is missing

    league, entries = league_entries()

    players, matchweeks, transfers, bench, captains, xi, chips_used = [], {}, {}, {}, {}, {}, {}
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
            cached = None if key in old_provisional else old_captains.get(key, {}).get(name)
            cached_xi = old_xi.get(key, {}).get(name)
            if cached is None or cached_xi is None:  # one picks call gives both
                picks = get(f"entry/{entry_id}/event/{gw['event']}/picks/")["picks"]
                if cached is None:
                    cached = captain_pick(picks, live_points(gw["event"]), player_names)
                if cached_xi is None:
                    cached_xi = starting_xi(picks)
            captains.setdefault(key, {})[name] = cached
            xi.setdefault(key, {})[name] = cached_xi

        # Gameweeks under way (the loop above only covers final ones): the XI, and, once a match has
        # started, the provisional numbers. Squads are fetched every run for those: the multipliers,
        # automatic substitutions and the live points all keep moving.
        for gw in sorted(under_way):
            key = f"GW{gw}"
            cached_xi = old_xi.get(key, {}).get(name)
            picks_resp = None
            if cached_xi is None or gw in scored:
                try:
                    picks_resp = get(f"entry/{entry_id}/event/{gw}/picks/")
                except RuntimeError as exc:  # not available (yet): the next run tries again
                    print(f"No squad for {name} in {key}: {exc}")
                    prov_complete.discard(gw)
                    if cached_xi is None:
                        continue
            if cached_xi is None:
                cached_xi = starting_xi(picks_resp["picks"])
            xi.setdefault(key, {})[name] = cached_xi
            if gw in scored and picks_resp is not None:
                lp = live_points(gw)
                pts, bench_pts = live_total(picks_resp["picks"], picks_resp.get("automatic_subs", []), lp)
                prov_rows[gw][name] = {
                    "points": pts,
                    "cost": picks_resp["entry_history"]["event_transfers_cost"],
                    "bench": bench_pts,
                    "captain": captain_pick(picks_resp["picks"], lp, player_names),
                    "chip": picks_resp.get("active_chip"),
                }

        used = {}
        for chip in history["chips"]:
            if chip["event"] not in done:
                continue
            label = CHIP_NAMES.get(chip["name"], chip["name"])
            used.setdefault(label, []).append(f"GW{chip['event']}")
        chips_used[name] = used

    # Provisional gameweeks: added to the same tables as the final ones, but only when every manager's
    # numbers are there (a partly filled gameweek would charge somebody 0 points).
    provisional = []
    for gw in sorted(progress):
        key = f"GW{gw}"
        if gw in scored and gw in prov_complete and len(prov_rows[gw]) == len(players):
            for name, r in prov_rows[gw].items():
                matchweeks.setdefault(key, {})[name] = r["points"]
                transfers.setdefault(key, {})[name] = r["cost"]
                bench.setdefault(key, {})[name] = r["bench"]
                captains.setdefault(key, {})[name] = r["captain"]
                chip = CHIP_NAMES.get(r["chip"]) if r["chip"] else None
                if chip:  # chips are locked at the deadline, so they're known from then on
                    chips_used[name].setdefault(chip, []).append(key)
            provisional.append(progress[gw])

    order = lambda d: dict(sorted(d.items(), key=lambda kv: int(kv[0][2:])))
    out = {
        "league": {"id": league["id"], "name": league["name"]},
        "last_gw": max(done) if done else 0,
        "players": players,
        "matchweeks": order(matchweeks),
        "transfers": order(transfers),
        "bench": order(bench),
        "captains": order(captains),
        "xi": order(xi),
        "xi_names": {str(i): player_names.get(i, str(i)) for i in sorted({i for gw in xi.values() for ids in gw.values() for i in ids})},
        "chips_used": chips_used,
        "provisional": provisional,
        "next_deadline": next_deadline(events, now),
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
    extra = f" + provisional {', '.join('GW%d' % p['gw'] for p in provisional)}" if provisional else ""
    print(f"Wrote data/fpl.json: {len(players)} players, final up to GW{out['last_gw']}{extra}.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        sys.exit(str(exc))
