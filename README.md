# Liga Fundão

FPL mini-league tracker (league [144341](https://fantasy.premierleague.com/leagues/144341/standings/c)).

## How the data updates

- `.github/workflows/update-data.yml` runs `scripts/fetch_fpl.py` every 6 hours (and on demand from the
  **Actions** tab → *Update FPL data* → *Run workflow*).
- The script reads the league from the FPL API and writes `data/fpl.json`: players, points, transfer
  costs and chips for every **finished** gameweek. It commits only when something changed.
- `index.html` loads `data/fpl.json`. If it can't (e.g. opening the file straight from disk), it uses the
  inline data in the `<script>` block instead.

## What's still manual

- `MANUAL_PAYMENTS` and `COST_PER_POINT` in `index.html`.
- Payments are matched by name, so the names must match the ones in `data/fpl.json`. If one doesn't, the
  page shows a red "Pagamentos sem jogador" chip in the header.

## Renaming players

By default each player is shown with their FPL account name. To show a different name, create
`data/names.json` mapping the FPL entry id (or the FPL name) to the name you want:

```json
{
  "1234567": "Rui Bimba",
  "Joao Pires": "João Pires"
}
```

Entry ids are in `data/fpl.json` under `players[].entry`.
