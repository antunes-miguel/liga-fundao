# Fantasy Fundão (liga-fundao)

Static site tracking an FPL classic mini-league among friends (league 144341), hosted on GitHub Pages from `main`.
UI text is in Portuguese (pt-PT). The owner writes to Claude in English.

## Layout

- `index.html`: the whole site (HTML, CSS and JS in one file, no build step, no dependencies besides Google Fonts).
- `data/fpl.json`: league data (players, points, transfer costs, bench points, captains, starting XIs, chips). **Generated; never edit by hand.**
- `data/names.json`: maps an FPL name or entry id to the name shown on the page (e.g. `"Antonio Moreira": "António Moreira"`).
- `scripts/fetch_fpl.py`: fetches the FPL API and writes `data/fpl.json`. Python stdlib only.
- `scripts/notify.py`: builds and sends the "GWn fechada" push notification when a new gameweek is final, and the deadline reminder (below). `data/notified.json` remembers the last gameweek announced (`last_gw`) and the last one whose deadline was announced (`deadline_gw`) (generated; first run only records `last_gw` and sends nothing).
- `.github/workflows/update-data.yml`: runs every 15 minutes and on manual dispatch: fetch data, send the notification, commit `data/` if it changed. **The 15-minute rhythm comes from an outside trigger, not from GitHub's `schedule`** (see "Triggering the updater" below). "Run workflow" with `test_notification` ticked only sends a test push.
- `manifest.webmanifest` + `sw.js`: installable app (PWA). The app's name is "Fantasy Fundão" everywhere (manifest `name` and `short_name`, `apple-mobile-web-app-title`, page title, OneSignal site name). iOS puts it in "from <name>" under every notification and keeps the name saved when the icon was added, so a rename only reaches phones that re-add the icon. The service worker serves page/data network-first (cached copy offline) and images/fonts cache-first. **Bump `VERSION` in `sw.js` when adding files to its `SHELL` list.**
- `assets/crest.png` (white, transparent), `assets/icon-180.png` (favicon, iPhone home screen), `assets/icon-192.png`, `icon-512.png`, `icon-maskable-512.png` (app icons). `LF.png` and `GARDUNHA-*.jpg` are old and unused.

## Data flow

- **Final vs provisional.** Final gameweeks (FPL `finished && data_checked`) come from FPL's season history. A gameweek **under way** (deadline passed, not final) is also written, as *provisional*, once a match has started: its points are computed from FPL's live player points (Σ points × multiplier over the picks, with the automatic substitutions; validated against FPL's final numbers for every finished gameweek of the league, 0 differences) because FPL's season-history row for it lags. It goes into the same tables as the final ones (`matchweeks`, `transfers`, `bench`, `captains`, `chips_used`), so standings, debts and leaderboards include it, and `provisional` lists it with `{gw, total, played, live}` (fixtures). The page shows a banner, a "provisória" pill, and `*` on chart/heatmap axes. **`last_gw` is always the last FINAL gameweek**: `notify.py` announces only final gameweeks (and refuses to preview a provisional one). If any manager's squad can't be fetched, the provisional gameweek is left out entirely, so nobody gets a fake 0. What was stored while provisional is recomputed once when the gameweek turns final. `xi` also covers gameweeks that haven't started scoring (squads are locked at the deadline).
- Captain and starting-XI data for finished GWs is reused from the existing `data/fpl.json` (one picks call per player per new GW gives both), so runs stay fast. To rebuild captains, delete the `captains` key and rerun; for XIs, delete `xi`.
- `xi`: GW → player → the 11 FPL player ids picked to start (pick positions 1-11, in pick order, before automatic subs; a Bench Boost week still counts the same 11). `xi_names` maps id → name. Ids, not names, because FPL names are not unique (two "Martinez").
- `index.html` loads `data/fpl.json` into `PLAYERS`, `MATCHWEEKS`, `TRANSFERS`, `CHIPS_USED`. If the fetch fails (e.g. opened from disk), it falls back to the inline copies in the data section. Those inline copies are stale on purpose; don't update them.
- **Edited by hand:** `MANUAL_PAYMENTS` (EUR paid per player, keyed by display name) and `COST_PER_POINT` in `index.html`.
- If a `MANUAL_PAYMENTS` name doesn't match a player, the header shows a red "Pagamentos sem jogador" chip. The fix is usually a `data/names.json` entry.

## Push notifications

- OneSignal (free plan). Public app id in `ONESIGNAL_APP_ID` in `index.html` (empty = feature off, button hidden); the secret `ONESIGNAL_API_KEY` is a GitHub Actions secret. `notify.py` reads the app id from `index.html`.
- **Deadline reminder:** `fetch_fpl.py` stores the next gameweek's deadline in `data/fpl.json` (`next_deadline`: `gw` + UTC `time`, the earliest deadline still in the future). `notify.py` sends one reminder per gameweek once the deadline is within 24 hours (`REMINDER_WINDOW`), with the title "⏰ GW10 Deadline" and the text "Prazo amanhã às 18:30, confirma a equipa e as transferências." ("hoje" if it falls on the same Lisbon day; times are Lisbon time). Runs happen about every 15 minutes (see "Triggering the updater"), so it arrives about 24 h before, or later if the deadline appeared late. It is sent at most once per gameweek (`deadline_gw`), so a deadline FPL moves afterwards is not announced again. No money info.
- One notification per closed gameweek, same for everyone, **no money info**: 🏆 winner (net points), 👑 leader / new leader, 🎯 best captain (points earned with the multiplier), 🪑 most points left on the bench (Bench Boost weeks excluded), 📈 biggest climb (only if ≥2 places, or 1 place shared by at most 2). Preview with `python scripts/notify.py --gw 9`; the deadline reminder previews with `--deadline` (`--send` or the workflow's `preview_deadline` tick box sends it as "(teste)", worded as it will really read, whatever the time left; it uses the deadline already in `data/fpl.json`); add `--send` (or run the workflow with `preview_gw` = 9) to really send that message, marked "(teste)", without touching `data/notified.json`.
- `.github/workflows/send-notification.yml` ("Send custom notification", manual only): sends any text typed in the Run workflow form (`message`, optional `title`, default "Fantasy Fundão") to everyone subscribed. It runs `python scripts/notify.py --title … --message …`, passing the inputs through env vars, and touches neither `data/` nor `data/notified.json`. Unlike the gameweek message it can say anything, so no "no money info" rule applies.
- With notifications on, **OneSignal registers `sw.js`** (our worker `importScripts` the OneSignal worker). The page must not register `sw.js` itself then, or the two registrations replace each other and push stops working.
- The button only shows where push works: Android and desktop browsers, and the installed app on iPhone (iOS 16.4+), never in a Safari tab.
- OneSignal dashboard: integration type **Custom Code** (we call `OneSignal.init` ourselves; the dashboard path fields don't apply), Site URL = the origin only (`https://<owner>.github.io`, no repo path). `serviceWorkerPath` is resolved against the origin and must have no leading slash (e.g. `liga-fundao/sw.js`); the scope is the repo folder.
- The request format (`POST https://api.onesignal.com/notifications`, `Authorization: Key …`, `target_channel: "push"`, `included_segments: ["Total Subscriptions"]`) was checked against OneSignal's docs and with real test runs. The docs' "Subscribed Users" segment does **not exist** in new apps (a send to it silently reaches nobody); use "Total Subscriptions", not "Active Subscriptions" (recent visitors only). HTTP 200 without an `id` means nobody was targeted: run the workflow with `test_notification` and read the log, which then lists the app's audiences with subscriber counts.

## Triggering the updater

- GitHub's own `schedule` in `update-data.yml` is **best effort and unreliable here**: it ran every 4-8 hours instead of the requested hourly (GitHub may delay or silently drop scheduled runs). It stays as a backup only.
- The real trigger is a **cron-job.org** job (free account of the owner), every 15 minutes at :02/:17/:32/:47, sending `POST https://api.github.com/repos/antunes-miguel/liga-fundao/actions/workflows/update-data.yml/dispatches` with body `{"ref":"main"}` and headers `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`. GitHub answers `204`. A dispatched run uses the workflow's default inputs, i.e. a normal run.
- The token is a **fine-grained personal access token** with only `Actions: Read and write` (plus the automatic `Metadata: Read`) on this one repo; it lives in cron-job.org, never in the repo. **It expires on 2027-11-09: create a new one and update the job's `Authorization` header before then**, or updates fall back to GitHub's slow schedule. cron-job.org also disables a job after many failures in a row (the owner has the failure e-mail alert on).
- GitHub marks API version `2022-11-28` as deprecated with sunset on 2028-03-10; update that header (to a newer version listed in the GitHub REST docs) before then.
- If updates seem stale: check the cron-job.org job's history first, then the Actions tab (runs with the `workflow_dispatch` event every ~15 minutes).

## League rules (keep these exact)

- Net score = GW points − transfer cost (hits).
- Each GW, the best net score pays nothing; everyone else owes `(best net − their net) × COST_PER_POINT`. Ties at the top all pay nothing.
- Total = sum of weekly debts. Saldo = Total − Pago (≤ 0 is settled, shown green).
- Standings: total net points desc, then fewer transfer points, then alphabetical.
- Chips: Wildcard, Bench Boost, Triple Captain, Free Hit, each twice a season (`CHIPS_PER_TYPE = 2`).
- Banco de Ouro: cumulative `points_on_bench` per player, **excluding GWs where that player had Bench Boost active**. Sorted desc, ties alphabetical.
- Capitães: per GW the updater stores who actually got the armband (the multiplier >1 pick, so the vice counts if the captain didn't play), their base points, the multiplier, and the best player in that manager's starting XI. Eficiência = Σ captain base pts ÷ Σ best XI pts. Acertos = GWs where captain pts ≥ best. Perdidos = Σ (best − captain) × (multiplier − 1). Sorted by eficiência, then fewer perdidos, then alphabetical.

## Design

- "Onzes Iniciais" panel (`#onze`, hidden if `data/fpl.json` has no `xi`): pick a player and a GW (or the season average) and every other player is ranked by how many of the 11 starters they share (`sharedXI` / `xiSimilarity` in `index.html`); for one GW it lists the shared players. A GW that is under way (in `xi` but not yet in `matchweeks`) is listed as "GWn (a decorrer)" and is the default. The chosen player is saved in `localStorage` (`lf-xi-player`).
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
