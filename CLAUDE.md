# Fantasy Fundão (liga-fundao)

Static site tracking an FPL classic mini-league among friends (league 144341), hosted on GitHub Pages from `main`.
UI text is in Portuguese (pt-PT). The owner writes to Claude in English.

## Layout

- `index.html`: the whole site (HTML, CSS and JS in one file, no build step, no dependencies besides Google Fonts).
- `data/fpl.json`: league data (players, points, transfer costs, bench points, captains, chips). **Generated; never edit by hand.**
- `data/names.json`: maps an FPL name or entry id to the name shown on the page (e.g. `"Antonio Moreira": "António Moreira"`).
- `scripts/fetch_fpl.py`: fetches the FPL API and writes `data/fpl.json`. Python stdlib only.
- `scripts/notify.py`: builds and sends the "GWn fechada" push notification when a new gameweek is final. `data/notified.json` remembers the last gameweek announced (generated; first run only records it and sends nothing).
- `.github/workflows/update-data.yml`: runs hourly and on manual dispatch: fetch data, send the notification, commit `data/` if it changed. "Run workflow" with `test_notification` ticked only sends a test push.
- `manifest.webmanifest` + `sw.js`: installable app (PWA). The service worker serves page/data network-first (cached copy offline) and images/fonts cache-first. **Bump `VERSION` in `sw.js` when adding files to its `SHELL` list.**
- `assets/crest.png` (white, transparent), `assets/icon-180.png` (favicon, iPhone home screen), `assets/icon-192.png`, `icon-512.png`, `icon-maskable-512.png` (app icons). `LF.png` and `GARDUNHA-*.jpg` are old and unused.

## Data flow

- Only gameweeks FPL marks `finished && data_checked` are written, so debts don't move mid-gameweek.
- Captain data for finished GWs is reused from the existing `data/fpl.json` (one picks call per player per new GW), so runs stay fast. To rebuild it, delete the `captains` key and rerun.
- `index.html` loads `data/fpl.json` into `PLAYERS`, `MATCHWEEKS`, `TRANSFERS`, `CHIPS_USED`. If the fetch fails (e.g. opened from disk), it falls back to the inline copies in the data section. Those inline copies are stale on purpose; don't update them.
- **Edited by hand:** `MANUAL_PAYMENTS` (EUR paid per player, keyed by display name) and `COST_PER_POINT` in `index.html`.
- If a `MANUAL_PAYMENTS` name doesn't match a player, the header shows a red "Pagamentos sem jogador" chip. The fix is usually a `data/names.json` entry.

## Push notifications

- OneSignal (free plan). Public app id in `ONESIGNAL_APP_ID` in `index.html` (empty = feature off, button hidden); the secret `ONESIGNAL_API_KEY` is a GitHub Actions secret. `notify.py` reads the app id from `index.html`.
- One notification per closed gameweek, same for everyone, **no money info**: 🏆 winner (net points), 👑 leader / new leader, 🎯 best captain (points earned with the multiplier), 🪑 most points left on the bench (Bench Boost weeks excluded), 📈 biggest climb (only if ≥2 places, or 1 place shared by at most 2). Preview with `python scripts/notify.py --gw 9`.
- With notifications on, **OneSignal registers `sw.js`** (our worker `importScripts` the OneSignal worker). The page must not register `sw.js` itself then, or the two registrations replace each other and push stops working.
- The button only shows where push works: Android and desktop browsers, and the installed app on iPhone (iOS 16.4+), never in a Safari tab.
- OneSignal dashboard: integration type **Custom Code** (we call `OneSignal.init` ourselves; the dashboard path fields don't apply), Site URL = the origin only (`https://<owner>.github.io`, no repo path). `serviceWorkerPath` is resolved against the origin and must have no leading slash (e.g. `liga-fundao/sw.js`); the scope is the repo folder.
- The request format (`POST https://api.onesignal.com/notifications`, `Authorization: Key …`, `target_channel: "push"`, `included_segments: ["Subscribed Users"]`) was checked against OneSignal's docs, but no real push has been sent from a cloud session. HTTP 200 without an `id` means nobody is subscribed. To verify: run the workflow with `test_notification` and read the log.

## League rules (keep these exact)

- Net score = GW points − transfer cost (hits).
- Each GW, the best net score pays nothing; everyone else owes `(best net − their net) × COST_PER_POINT`. Ties at the top all pay nothing.
- Total = sum of weekly debts. Saldo = Total − Pago (≤ 0 is settled, shown green).
- Standings: total net points desc, then fewer transfer points, then alphabetical.
- Chips: Wildcard, Bench Boost, Triple Captain, Free Hit, each twice a season (`CHIPS_PER_TYPE = 2`).
- Banco de Ouro: cumulative `points_on_bench` per player, **excluding GWs where that player had Bench Boost active**. Sorted desc, ties alphabetical.
- Capitães: per GW the updater stores who actually got the armband (the multiplier >1 pick, so the vice counts if the captain didn't play), their base points, the multiplier, and the best player in that manager's starting XI. Eficiência = Σ captain base pts ÷ Σ best XI pts. Acertos = GWs where captain pts ≥ best. Perdidos = Σ (best − captain) × (multiplier − 1). Sorted by eficiência, then fewer perdidos, then alphabetical.

## Design

- Brand (from the Instagram artwork): maroon `--brand #3d0e1e`, stripes `#511726` / `#5d1a2b`, red band `#8b2d3b`, white. Colours are CSS variables in `:root`; use those, not new hex values.
- Fonts: Montserrat 800 uppercase for the wordmark, headings and menu (`--display`); Inter for body text.
- Phones matter most. At ≤640px, tables become compact one-row-per-player grids, with short names via `nameHTML()` / `shortName()` ("Diogo L.").
  Each table panel has a "Tabela completa" button (phones only) that adds `.full-view` to the panel: the full desktop table, scrolling sideways, first column sticky. The compact phone CSS is scoped to `.panel:not(.full-view)`, so new compact rules must be too. The choice is saved per panel in `localStorage` (`lf-full-view`).
- Installed on iPhone the page runs under the status bar (`black-translucent`, `viewport-fit=cover`): body padding and the sticky menu use `env(safe-area-inset-*)`. Keep that when changing top-level layout.
- When the installed app comes back on screen, it reloads if `data/fpl.json` has a newer `updated_at` (checked at most every 5 minutes).
- Standings chart: grey lines plus up to 3 highlighted players. The colours in `HL_COLORS` (blue, gold, green) were checked for contrast and colour blindness on the maroon panel; re-check if you change them. The highlight is saved in `localStorage` (`lf-rank-highlight`).

## Working on it

- `main` is protected: work on a branch and open a PR. The owner merges.
- Test by serving the repo (`python3 -m http.server`) and loading it in Playwright/Chromium at iPhone 13 size and ~1280px desktop. Check for console errors and horizontal overflow (`document.documentElement.scrollWidth`). Opening the file from disk only tests the fallback data.
- To refresh data now: run the "Update FPL data" workflow (Actions tab, or the GitHub API with `workflow_dispatch` on `main`).
- `fantasy.premierleague.com` may be blocked from cloud sessions by the environment's network policy. If so, test the script with mocked responses and say so.
