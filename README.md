# Athens Pistols stats archive

Every game Athens Pistols has played on basketaki.com, from September 2019 to November 2026: results, quarter scores and the full box score (both teams) for every game.
Source: https://www.basketaki.com/teams/athens-pistols/results

## The website

Open **`site/index.html`** (double-click it). It runs straight from this folder and works on phones too. Charts and fonts load from the internet, and everything else is local.

- **Overview:** record, season trends, leaders and highlights
- **Games:** every game by margin, plus a searchable game log. Each game has its own page with the scoreboard, quarter charts, team comparison and both box scores
- **Players:** roster cards and a leaderboard (per game, totals, per 40, shooting, advanced), plus a full profile for every player with per-game stats in wins vs losses, seasons, splits, record against each opponent, career highs, with/without, teammates, a percentile radar and the full game log
- **Opponents:** head-to-head record against every team, each team's own page, and the opponent players who scored most against the Pistols
- **Seasons**, **Team** (ratings, four factors, quarters, game situations, splits), **Records**, and **Compare** for up to 3 players side by side
- **Filters** at the top (season, competition, opponent, home/away, wins/losses, forfeits on/off) apply to every page. Press `/` to find any player, team or season.

## Adding new games

Double-click **`Update stats.bat`**. It downloads any new games from basketaki and refreshes `site/data.js`. Then reload the website. Either scraper can do this. The Python one is `python scrape_basketaki.py`.

## What's here

| File | What it is |
|---|---|
| `site/index.html` | The website (open this) |
| `site/data.js`, `site/logo.png` | Website data (written by the scrapers) and team logo |
| `Update stats.bat` | One-click update: new games and website data |
| `verify/` | Independent check of every number the website shows (see below) |
| `data/games.csv` | **Final data.** One row per game (191 games) |
| `data/player_stats.csv` | **Final data.** One row per player per game, both teams (2,533 lines) |
| `data/stats.json` | Same data combined in one file (for the website) |
| `data_py/` | The same files produced by the Python scraper (identical content, used for validation) |
| `scrape_basketaki.ps1` | Scraper, Windows PowerShell version (no install needed) |
| `scrape_basketaki.py` | Scraper, Python version (standard library only), written independently |
| `compare_outputs.py` | Compares `data/` and `data_py/` cell by cell, writes `validation_report.txt` |
| `validation_report.txt` | Result of the last comparison |

The CSV files open directly in Excel (Greek names display correctly).

## Updating after new games

Either scraper re-downloads the results page and every box score (about 4 minutes):

```
powershell -ExecutionPolicy Bypass -File .\scrape_basketaki.ps1
python scrape_basketaki.py
python compare_outputs.py
```

Downloaded pages are cached in `data\cache` / `data_py\cache`, so a second run only fetches new games. Use `-Refresh` / `--refresh` to re-download everything. Another team works too: `-Team <slug>` / `--team <slug>` (the slug is in the team's basketaki URL).

## games.csv columns

Everything is from Athens Pistols' point of view: `team_*` is Pistols and `opp_*` is the opponent.

- `date`, `season` (e.g. 24/25), `competition` (W.Evolution, S.Master, Athens Superbet Cup…), `tournament` (full title), `round` (matchday number; empty for knockout rounds like "Round of 32")
- `opponent`, `home_away`, `result` (W/L), `team_score`, `opp_score`, `margin`
- `status`: `played`, `forfeit` or `no result`
- `forfeit`: True/False. Forfeits keep their W/L so they count in the record, but have no player stats
- `team_q1..q4`, `team_ot`, `opp_q1..q4`, `opp_ot`: points per quarter
- `has_box_score`, `team_players` (Pistols players with stats), `box_score_complete` (Pistols player points add up to the final score)
- `url`: the game page

## player_stats.csv columns

`game_id`, `date`, `season`, `competition`, `team`, `is_our_team` (True = Pistols), `opponent`, `player`, `player_id`, `mvp`, `min`, `pts`, `eff`, `reb`, `oreb`, `dreb`, `ast`, `stl`, `tov`, `blk`, `ftm`/`fta` (free throws), `fg2m`/`fg2a` (2-pointers), `fg3m`/`fg3a` (3-pointers), `tmr` (the site's ΤΜΡ column, copied as-is; non-zero in only 5 lines).

Shooting percentages are not stored. Calculate them from made/attempted, because the site's own % column is wrong in some 2019–2022 games.

## Data notes

- **Record:** 74 W – 110 L in 184 decided games, including 17 forfeits (6 W, 11 L).
- **No result (7 games):** the 4 games of November 2020 (season stopped), two byes (ΡΕΠΟ), and one 0–0 entry (2020-04-01 vs Office Ηρακλείου).
- **Incomplete box scores on the site (6 games):** some players were never entered, so player points don't add up to the final score. The site's own totals row shows the same gap:
  2022-05-20 Gangsters (35 of 45), 2022-05-25 Hood BC (no Pistols stats at all), 2022-05-31 Paraliers (56 of 61), 2022-06-04 War Gamers (47 of 60), 2022-06-09 Aguanile (36 of 48), 2025-05-13 Σοποτό Veterans (54 of 63).
- **Did-not-play rows** (0 minutes and no stats, mostly roster lists on forfeit pages) are left out, so games-played counts are correct.

## How the data was validated

1. **Two independent scrapers.** The PowerShell version reads the pages by text pattern and fixed column positions. The Python version builds a real HTML tree and finds columns by their header names. Both downloaded the site separately. Result: **identical**: 191 games / 5,539 values and 2,533 player lines / 70,924 values, 0 differences.
2. **Built-in check.** Pistols player points match the final score in every game with stats, except the 6 games listed above, where the site itself is incomplete.
3. **Manual check of 10 random games** against the live site: final score, all quarter scores, all 13 stat columns for every player on both teams, and MVPs. **All matched.**
   2022-03-15 Old School, 2022-09-23 Iguana Pacers, 2022-09-29 Aladalon, 2023-01-11 Aladalon, 2024-04-14 Colombians BC, 2024-06-10 Collectors, 2024-11-12 Reboot, 2025-02-07 Cosa Nostra, 2025-09-16 Πι Stoli α, 2025-11-21 La Bola De Papel.

## How the website's numbers were verified

Every number the website displays was checked against the data with a third, independent program (`verify/verify_site.py`). It reads `data/games.csv` and `data/player_stats.csv` directly and recomputes each stat from its definition in Python, sharing no code with the website.

- **What was captured:** every page of the site, under four filter setups: everything; 2024–25 away games; forfeits left out; cup losses. That covers all 191 game pages, all 66 player profiles, every opponent and season page, every section, all 5 leaderboard modes, every records tab, every season-chart stat, several player comparisons, the search box and the footer. In total that's 1,066 page states.
- **What was compared:** every tile, table cell, totals row, chart data point, list entry and subtitle with a number in it. That's **228,239 displayed values, with 0 mismatches**.
- **Proof the check works:** six wrong values were planted in the captured pages, down to a single last digit (74.0 vs 74.1). All six were caught.
- The full result is in `verify/report.txt`.

To re-run it after an update:

1. `python verify/collect_server.py` (keep it running)
2. Open `http://127.0.0.1:8766/site/index.html`, open the browser console (F12) and run:
   `const s = document.createElement('script'); s.src = '/verify/extract.js'; document.body.appendChild(s);`
3. Wait about 2 minutes, until `window.__vx.progress` shows `done`
4. `python verify/verify_site.py`
