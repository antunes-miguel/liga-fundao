#!/usr/bin/env python3
"""Send the "gameweek closed" push notification when a new GW becomes final.

Runs in GitHub Actions right after scripts/fetch_fpl.py (see
.github/workflows/update-data.yml). Python standard library only.

    python scripts/notify.py              # normal run (used by the workflow)
    python scripts/notify.py --dry-run    # print what would be sent, change nothing
    python scripts/notify.py --gw 9       # preview the message for GW9 (never sends)
    python scripts/notify.py --test       # send a test push (does not touch the state)

How it decides:
- data/notified.json remembers the last gameweek we notified about.
- First run (no state file): just records the current gameweek, sends nothing.
- A newer final gameweek in data/fpl.json: build the message and send it.

Sending uses OneSignal. It needs the app id (read from ONESIGNAL_APP_ID in
index.html, or the ONESIGNAL_APP_ID env var) and the secret ONESIGNAL_API_KEY.
Without them the message is only printed.

The message has no money info: winner, leader, and a few weekly awards.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "fpl.json"
STATE_FILE = ROOT / "data" / "notified.json"
INDEX_FILE = ROOT / "index.html"

DEFAULT_SITE_URL = "https://antunes-miguel.github.io/liga-fundao/"
API_URL = "https://api.onesignal.com/notifications"  # create-message docs: Authorization "Key <app api key>"
# Everyone who ever subscribed. OneSignal's docs still show a "Subscribed Users" segment, but new apps don't have
# one (sending to it reaches nobody); they have "Total Subscriptions", "Active Subscriptions" (recent visitors only), ...
# `python scripts/notify.py --test` prints the app's real audiences when a test reaches nobody.
AUDIENCE = "Total Subscriptions"


# ---------- message ----------

def gw_num(key):
    return int(key[2:])


def name_key(name):
    """Alphabetical order ignoring accents (like the page's localeCompare)."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()


def short_names(players):
    """Same rule as shortName() in index.html: first name, plus the last
    name's initial when two players share a first name."""
    firsts = [p.split()[0] for p in players]
    out = {}
    for p in players:
        parts = p.split()
        shared = firsts.count(parts[0]) > 1
        out[p] = f"{parts[0]} {parts[-1][0]}." if shared and len(parts) > 1 else parts[0]
    return out


def net(data, gw, player):
    return data["matchweeks"].get(gw, {}).get(player, 0) - data["transfers"].get(gw, {}).get(player, 0)


def standings(data, players, gws):
    """Rank (1 = leader) and cumulative net points after the given gameweeks.
    Same rules as the page: points, then fewer transfer points, then name."""
    pts = {p: 0 for p in players}
    trf = {p: 0 for p in players}
    for gw in gws:
        for p in players:
            pts[p] += net(data, gw, p)
            trf[p] += data["transfers"].get(gw, {}).get(p, 0)
    order = sorted(players, key=lambda p: (-pts[p], trf[p], name_key(p)))
    return {p: i + 1 for i, p in enumerate(order)}, pts


def chip_gws(data, player, chip):
    v = data.get("chips_used", {}).get(player, {}).get(chip)
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def fmt_names(group, names):
    s = [names[p] for p in group]
    if len(s) <= 2:
        return " e ".join(s)
    return f"{s[0]}, {s[1]} e mais {len(s) - 2}"


def top_players(values):
    """Players tied for the highest value -> (value, [players alphabetical])."""
    best = max(values.values())
    return best, sorted((p for p, v in values.items() if v == best), key=name_key)


def build_message(data, gw_key):
    players = [p["name"] for p in data["players"]]
    names = short_names(players)
    gws = sorted(data["matchweeks"], key=gw_num)
    upto = gws[: gws.index(gw_key) + 1]
    before = upto[:-1]

    ranks, pts = standings(data, players, upto)
    prev_ranks = standings(data, players, before)[0] if before else None
    lines = []

    # Winner of the week (net points, like the page's "Top")
    best, winners = top_players({p: net(data, gw_key, p) for p in players})
    lines.append(f"🏆 {'Vencedores' if len(winners) > 1 else 'Vencedor'}: {fmt_names(winners, names)} ({best} pts)")

    # Leader, and whether it just changed
    leader = min(players, key=lambda p: ranks[p])
    changed = prev_ranks is not None and min(players, key=lambda p: prev_ranks[p]) != leader
    lines.append(f"👑 {'Novo líder' if changed else 'Líder'}: {names[leader]} ({pts[leader]} pts)")

    # Best captain of the week (points actually earned, so the armband multiplier counts)
    caps = data.get("captains", {}).get(gw_key, {})
    earned = {p: c["pts"] * c["mult"] for p, c in caps.items() if c and c.get("c")}
    if earned:
        best, group = top_players(earned)
        if len(group) == 1:  # name the player too: "Diogo A. (Jackson, 18 pts)"
            lines.append(f"🎯 Capitão: {names[group[0]]} ({caps[group[0]]['c']}, {best} pts)")
        else:
            lines.append(f"🎯 Capitão: {fmt_names(group, names)} ({best} pts)")

    # Most points left on the bench (Bench Boost weeks don't count, as on the page)
    bench = data.get("bench", {}).get(gw_key, {})
    eligible = {p: v for p, v in bench.items() if p in players and gw_key not in chip_gws(data, p, "Bench Boost")}
    if eligible:
        best, group = top_players(eligible)
        if best > 0:
            lines.append(f"🪑 Banco: {fmt_names(group, names)} ({best} pts)")

    # Biggest climb in the standings this week
    if prev_ranks:
        best, group = top_players({p: prev_ranks[p] - ranks[p] for p in players})
        if best >= 2 or (best == 1 and len(group) <= 2):  # a 3-way tie for one place isn't news
            lines.append(f"📈 Maior subida: {fmt_names(group, names)} (▲{best})")

    return f"{gw_key} fechada 🏁", "\n".join(lines)


# ---------- state ----------

def load_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(last_gw):
    state = {"last_gw": last_gw, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# ---------- sending (OneSignal) ----------

def site_url():
    if os.environ.get("SITE_URL"):
        return os.environ["SITE_URL"]
    repo = os.environ.get("GITHUB_REPOSITORY", "")  # "owner/repo" inside Actions
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"
    return DEFAULT_SITE_URL


def onesignal_config():
    app_id = os.environ.get("ONESIGNAL_APP_ID", "").strip()
    if not app_id and INDEX_FILE.exists():
        m = re.search(r'const\s+ONESIGNAL_APP_ID\s*=\s*"([^"]*)"', INDEX_FILE.read_text(encoding="utf-8"))
        app_id = m.group(1).strip() if m else ""
    return app_id, os.environ.get("ONESIGNAL_API_KEY", "").strip()


def send_push(title, body, url):
    """Returns the API response, or None when push isn't configured."""
    app_id, api_key = onesignal_config()
    if not app_id or not api_key:
        return None
    payload = {
        "app_id": app_id,
        "target_channel": "push",
        "included_segments": [AUDIENCE],
        "headings": {"en": title},
        "contents": {"en": body},
        "url": url,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "Authorization": f"Key {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OneSignal answered HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach OneSignal: {exc.reason}") from exc


def api_get(path):
    """GET on the OneSignal API (read only). Returns parsed JSON."""
    _, api_key = onesignal_config()
    req = urllib.request.Request(
        f"https://api.onesignal.com{path}",
        headers={"Accept": "application/json", "Authorization": f"Key {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"could not reach OneSignal: {exc.reason}") from exc


def diagnose():
    """Print which audiences (segments) the app has and how many subscribers each one holds.
    Used when a test notification reaches nobody. Best effort; never prints the API key."""
    app_id, api_key = onesignal_config()
    if not app_id or not api_key:
        return
    print(f"\nDiagnosis for app {app_id}:")
    try:
        segments = api_get(f"/apps/{app_id}/segments?limit=300").get("segments", [])
    except RuntimeError as exc:
        print(f"  Could not list the app's audiences: {exc}")
        return
    if not segments:
        print("  The app has no audiences (segments).")
    for seg in segments:
        try:
            count = api_get(f"/apps/{app_id}/segments/{seg['id']}").get("subscriber_count", "?")
        except RuntimeError as exc:
            count = f"? ({exc})"
        print(f"  - {seg.get('name')!r}: {count} subscriber(s)")


def deliver(title, body):
    """Send and report. Returns True if the request was accepted."""
    print(f"\n--- {title}\n{body}\n---")
    result = send_push(title, body, site_url())
    if result is None:
        print("Push is not configured (app id in index.html + ONESIGNAL_API_KEY secret): message not sent.")
        return False
    if result.get("id"):
        print(f"Sent (id {result['id']}).")
        return True
    # OneSignal answers 200 with "errors" when nobody has subscribed yet
    print(f"OneSignal accepted the request but sent nothing: {result.get('errors') or result}")
    return False


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the message, send nothing, keep the state")
    ap.add_argument("--gw", type=int, help="preview the message for this gameweek (never sends)")
    ap.add_argument("--test", action="store_true", help="send a test notification")
    args = ap.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    last_gw = data["last_gw"]

    if args.test:
        if not deliver("🔔 Notificações ativas", "Se estás a ler isto, vais receber o resumo de cada jornada."):
            diagnose()
            sys.exit("Test notification was not delivered (see the message above).")
        return

    if args.gw:
        title, body = build_message(data, f"GW{args.gw}")
        print(f"{title}\n{body}")
        return

    state = load_state()
    if state is None:
        save_state(last_gw)
        print(f"First run: remembering GW{last_gw} as the last notified gameweek. Nothing sent.")
        return
    if last_gw <= state["last_gw"]:
        print(f"Nothing new (last notified: GW{state['last_gw']}).")
        return

    title, body = build_message(data, f"GW{last_gw}")
    if args.dry_run:
        print(f"[dry run]\n{title}\n{body}")
        return
    try:
        deliver(title, body)
    except RuntimeError as exc:
        # Keep the state, so the next run tries again
        sys.exit(str(exc))
    # Sent, or push isn't set up / nobody subscribed yet: don't repeat for this gameweek
    save_state(last_gw)


if __name__ == "__main__":
    main()
