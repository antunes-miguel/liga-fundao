# Fantasy Fundão (liga-fundao)

Static site tracking an FPL classic mini-league among friends (league 144341), hosted on GitHub Pages from `main`.
UI text is in Portuguese (pt-PT). The owner writes to Claude in English.

## Layout

- `index.html`: the whole site (HTML, CSS and JS in one file, no build step, no dependencies besides Google Fonts). Redesign by a friend of the owner (see Design and `docs/HANDOFF.md`, which holds the design decisions).
- `data/fpl.json`: league data (players, points, transfer costs, bench points, captains, starting XIs, chips). **Generated; never edit by hand.**
- `data/names.json`: maps an FPL name or entry id to the name shown on the page (e.g. `"Antonio Moreira": "António Moreira"`).
- `scripts/fetch_fpl.py`: fetches the FPL API and writes `data/fpl.json`. Python stdlib only.
- `scripts/notify.py`: builds and sends the "GWn fechada" push notification when a new gameweek is final, and the deadline reminder (below). `data/notified.json` remembers the last gameweek announced (`last_gw`) and the last one whose deadline was announced (`deadline_gw`) (generated; first run only records `last_gw` and sends nothing).
- `.github/workflows/update-data.yml`: runs every 15 minutes and on manual dispatch: fetch data, send the notification, commit `data/` if it changed. **The 15-minute rhythm comes from an outside trigger, not from GitHub's `schedule`** (see "Triggering the updater" below). "Run workflow" with `test_notification` ticked only sends a test push.
- `manifest.webmanifest` + `sw.js`: installable app (PWA). The app's name is "Fantasy Fundão" everywhere (manifest `name` and `short_name`, `apple-mobile-web-app-title`, page title, OneSignal site name). iOS puts it in "from <name>" under every notification and keeps the name saved when the icon was added, so a rename only reaches phones that re-add the icon. The service worker serves page/data network-first (cached copy offline) and images/fonts cache-first. **Bump `VERSION` in `sw.js` when adding files to its `SHELL` list.**
- `assets/avatars/<id>.jpg`: the friends' photos (192×192; id = initials, map `ID_BY_NAME` in `index.html`; a player without a file gets a placeholder with initials). `assets/icon-180.png` (iPhone home screen), `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `favicon-32.png` (app icons, from the shield). `assets/crest.png`, `LF.png` and `GARDUNHA-*.jpg` are old and unused.

## Data flow

- **Final vs provisional.** Final gameweeks (FPL `finished && data_checked`) come from FPL's season history. A gameweek **under way** (deadline passed, not final) is also written, as *provisional*, once a match has started: its points are computed from FPL's live player points (Σ points × multiplier over the picks, with the automatic substitutions; validated against FPL's final numbers for every finished gameweek of the league, 0 differences) because FPL's season-history row for it lags. It goes into the same tables as the final ones (`matchweeks`, `transfers`, `bench`, `captains`, `chips_used`), so standings, debts and leaderboards include it, and `provisional` lists it with `{gw, total, played, live}` (fixtures). The page shows a banner, a "provisória" pill, and `*` on chart/heatmap axes. **`last_gw` is always the last FINAL gameweek**: `notify.py` announces only final gameweeks (and refuses to preview a provisional one). If any manager's squad can't be fetched, the provisional gameweek is left out entirely, so nobody gets a fake 0. What was stored while provisional is recomputed once when the gameweek turns final. `xi` also covers gameweeks that haven't started scoring (squads are locked at the deadline).
- Captain and starting-XI data for finished GWs is reused from the existing `data/fpl.json` (one picks call per player per new GW gives both), so runs stay fast. To rebuild captains, delete the `captains` key and rerun; for XIs, delete `xi`.
- `xi`: GW → player → the 11 FPL player ids picked to start (pick positions 1-11, in pick order, before automatic subs; a Bench Boost week still counts the same 11). `xi_names` maps id → name. Ids, not names, because FPL names are not unique (two "Martinez").
- `index.html` fetches `data/fpl.json` and `buildData()` fills `PLAYERS`, `NET` (points − hits), `HITS`, `CHIPS`, `BENCH`, `CAPS`, `XI`, `PROV`. There is **no inline fallback**: if the fetch fails (e.g. opened from disk) the page shows a "Não foi possível carregar" message. Tabs whose data is missing (Capitães, Banco, Onzes) hide themselves.
- **Edited by hand:** `MANUAL_PAYMENTS` (EUR paid per player, keyed by display name: a number, or a list `[{data:'AAAA-MM-DD', valor}]` that also shows dated payments on the profile) and `COST` (cost per point) in `index.html`. Payments cover the oldest weeks first (`coverage()`).
- If a `MANUAL_PAYMENTS` name doesn't match a player, the page footer shows a red "Pagamentos sem jogador" line. The fix is usually a `data/names.json` entry.

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

Redesign (Nov 2026), designed by a friend of the owner; read `docs/HANDOFF.md` before changing it (its section 6 lists decisions not to undo without asking the owner). The handoff's "example data" and "to wire up" lists are obsolete: everything is wired to `data/fpl.json` now.

- Two tabs only: **Jornada** (matchday card with stepper, sticker "1.º lugar" and "Último lugar", pot; panel with Jornada | Geral tables; notification button; footer with cost per point and "Atualizado") and **Insights** (Forma, Evolução, Capitães, Banco, Chips, Onzes). Tapping a player opens the profile (`#jogador-<id>`: week by week, debt grid with payments, season facts). Hash routes: `#jornada`, `#liga`, `#insights`, `#jogador-tm`. Rows are `<button data-player>`, navigation is JS (`go()` / `show()`), not links.
- A gameweek under way (`PROV`): banner at the top of the page, a "Provisória" pill on the matchday card, `*` on axis labels and "(J10 provisória)" in the footer and on shared images. The data rules are in "Data flow".
- Onzes (hidden if `data/fpl.json` has no `xi` for every player) compares the latest gameweek in `xi` (ids, not names). Chips handle two uses per chip (`CHIPS[id][code]` is a list); the grid shows two slots per chip.
- Standings order: total net points, then fewer transfer points (`hitsThrough`), then alphabetical.
- Themes: automatic / light / dark (`ff-theme` in `localStorage`); tokens in `:root` (written twice for dark: `prefers-color-scheme` and `[data-theme]`). Brand colours: `--deep #3D0F1E`, `--wine #5C1A2A`, `--cherry #8B2D3A`, `--forest #1B4332`; use the variables, not new hex values. Fonts: "Premier League" (licensed, not loaded; falls back to Lexend) for display, Inter for text.
- Phones matter most: bottom "liquid glass" tab bar that shrinks on scroll, below 480px tables use short names. Installed on iPhone the page runs under the status bar (`black-translucent`, `viewport-fit=cover`) and uses `env(safe-area-inset-*)`; keep that.
- When the installed app comes back on screen, it reloads if `data/fpl.json` has a newer `updated_at` (checked at most every 5 minutes).
- **Share buttons** (matchday card, Jornada/Geral table, every Insights view, profile debt): draw a 1080×1350 PNG on a canvas (`frameImage`, `drawList`, `drawGrid`; no libraries; avatars loaded from `assets/avatars`) and give it to the Web Share API as a `File`, or offer "Guardar imagem" where files can't be shared. Each view has its own `…Image()` function, so **a new view or column needs its image function updated too**. To test: stub `navigator.canShare` / `navigator.share` in Playwright and read the blob from `#sheet-img`; real phones can't be checked from a cloud session.
- Evolução: grey lines plus any number of highlighted players (default: the top 3; tap names to add or remove). Each highlighted player gets the lowest free colour slot (`hlSlot`, `--s1..--s9`, two palettes for light/dark) and a dash pattern (`DASH`), so colours don't move when others change; the image (`evoImage`) uses the same slots and wraps its legend. The nine colours were chosen by eye, not checked for colour blindness (the dashes help). The highlight is not saved.


## Working on it

- `main` is protected: work on a branch and open a PR. The owner merges.
- Test by serving the repo (`python3 -m http.server`) and loading it in Playwright/Chromium at iPhone 13 size and ~1280px desktop. Check for console errors and horizontal overflow (`document.documentElement.scrollWidth`). Opening the file from disk only tests the fallback data.
- To refresh data now: run the "Update FPL data" workflow (Actions tab, or the GitHub API with `workflow_dispatch` on `main`).
- `fantasy.premierleague.com` may be blocked from cloud sessions by the environment's network policy. If so, test the script with mocked responses and say so.
