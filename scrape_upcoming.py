#!/usr/bin/env python3
"""
Upcoming games and scouting data for the website (writes site/upcoming.js).

Reads from basketaki.com:
  - the team's schedule (/teams/<team>/schedule): matchday, date and time, opponent, gym
  - the gyms page (/courts): address and map coordinates of every gym
  - the league table of the upcoming games' tournament
  - for every CONFIRMED upcoming game (date and gym known): the opponent's results for the
    CURRENT season only, and the box score of each of those games (both teams)

Box scores are read with the same functions as scrape_basketaki.py, so every number is
parsed exactly like the rest of the site's data. The file is only rewritten when something
changed (a new game, a confirmed date, a new box score), so the daily GitHub run only saves
real updates.

Usage:  python scrape_upcoming.py [--team athens-pistols]
"""
import argparse
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from scrape_basketaki import BASE, Fetcher, parse_html, parse_results, parse_box_score, played, to_int

HERE = Path(__file__).resolve().parent
PREFIX = "window.PISTOLS_UPCOMING = "


def fold(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return " ".join("".join(c for c in s if unicodedata.category(c) != "Mn").split())


# ------------------------------------------------------------------ schedule
def parse_schedule(html):
    doc = parse_html(html)
    out = []
    for tr in doc.find_all("tr"):
        tds = tr.kids("td")
        if len(tds) < 8 or "team-result__date" not in tds[0].classes():
            continue
        opp = next((a for a in tds[2].find_all("a") if re.fullmatch(r"/teams/[^/]+/profile", a.attrs.get("href", ""))), None)
        img = tds[2].find("img")
        game = next((a for a in tds[6].find_all("a") if a.attrs.get("href", "").startswith("/games/")), None)
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{1,2}:\d{2}))?", tds[1].text())
        gym = tds[7].text()
        out.append({
            "round": to_int(tds[0].text()),
            "date": f"{m[3]}-{m[2]}-{m[1]}" if m else None,
            "time": m[4] if m and m[4] else None,
            "opponent": tds[2].text(),
            "opponent_id": opp.attrs["href"].split("/")[2] if opp else None,
            "logo": img.attrs.get("src") if img else None,
            "home_away": tds[3].text(),
            "competition": tds[4].text(),
            "season": tds[5].text(),
            "game_id": game.attrs["href"][len("/games/"):] if game else None,
            "gym_name": None if gym in ("", "-") else gym,
        })
    return out


# ------------------------------------------------------------------ gyms
def parse_courts(html):
    doc = parse_html(html)
    courts = {}
    for card in doc.find_all(cls="sponsor-card"):
        ex = card.find(cls="sponsor-card__excerpt")
        if not ex:
            continue
        name = ex.find("h4").text() if ex.find("h4") else ""
        addr = ex.find("span", "text-primary")
        frame = card.find("iframe")
        src = frame.attrs.get("src", "") if frame else ""
        lat, lon = re.search(r"!3d(-?\d+(?:\.\d+)?)", src), re.search(r"!2d(-?\d+(?:\.\d+)?)", src)
        if name:
            courts[fold(name)] = {"name": name, "address": addr.text() if addr else None,
                                  "lat": float(lat[1]) if lat else None, "lon": float(lon[1]) if lon else None}
    return courts


def gym_info(name, courts):
    if not name:
        return None
    c = courts.get(fold(name))
    info = {"name": name, "address": c["address"] if c else None, "lat": c["lat"] if c else None, "lon": c["lon"] if c else None}
    if info["lat"] is not None and info["lon"] is not None:
        info["maps_url"] = f"https://www.google.com/maps/search/?api=1&query={info['lat']},{info['lon']}"
    else:
        from urllib.parse import quote
        info["maps_url"] = "https://www.google.com/maps/search/?api=1&query=" + quote(", ".join(x for x in (name, info["address"]) if x))
    return info


# ------------------------------------------------------------------ league table
def tournament_slug(title):
    m = re.match(r"(.+?\d{2}/\d{2})", title or "")
    return re.sub(r"[^a-z0-9]+", "-", (m[1] if m else title or "").lower()).strip("-")


def parse_standings(html, team_id):
    doc = parse_html(html)
    for table in doc.find_all("table", "table-standings"):
        rows, ours = [], False
        for tr in table.find_all("tr"):
            tds = tr.kids("td")
            if len(tds) < 10:
                continue
            a = tds[1].find("a")
            href = a.attrs.get("href", "") if a else ""
            tid = href.split("/")[2] if href.startswith("/teams/") else None
            if not tid or tid.lower() == "repo":
                continue
            ours = ours or tid == team_id
            img = tds[1].find("img")
            rows.append({"pos": to_int(tds[0].text()), "team": tds[1].text(), "team_id": tid, "logo": img.attrs.get("src") if img else None,
                         "pts": to_int(tds[2].text()), "gp": to_int(tds[3].text()), "w": to_int(tds[4].text()), "l": to_int(tds[5].text()),
                         "streak": tds[6].text() or None, "pf": to_int(tds[7].text()), "pa": to_int(tds[8].text()), "diff": to_int(tds[9].text())})
        if ours:
            return rows
    return None


# ------------------------------------------------------------------ scouting (opponent's current season)
def scout(fetch, opp_id, season):
    team_name, games = parse_results(fetch.get(f"/teams/{opp_id}/results", use_cache=False), opp_id)
    games = [g for g in games if g["season"] == season]
    players = []
    for g in games:
        if g["result"] is None or (g["team_score"] is None and g["opp_score"] is None):
            g["status"] = "no result"
        if not g["game_id"]:
            continue
        kept = [l for l in parse_box_score(fetch.get(f"/games/{g['game_id']}/box-score"), g, opp_id, team_name) if played(l)]
        if (g["team_score"], g["opp_score"]) in ((20, 0), (0, 20)) and not sum(l["pts"] or 0 for l in kept):
            kept, g["status"], g["forfeit"] = [], "forfeit", True
        players.extend(kept)
        ours = [l for l in kept if l["is_our_team"]]
        g["has_box_score"] = bool(ours)
        g["team_players"] = len(ours)
        g["box_score_complete"] = bool(ours) and sum(l["pts"] or 0 for l in ours) == g["team_score"]
    return {"team": team_name, "team_id": opp_id, "season": season, "games": games, "players": players}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team", default="athens-pistols")
    ap.add_argument("--cache", default=str(HERE / "data" / "cache"))
    ap.add_argument("--site", default=str(HERE / "site"))
    ap.add_argument("--delay", type=float, default=0.6)
    args = ap.parse_args()
    fetch = Fetcher(Path(args.cache), False, args.delay)

    print(f"Reading the schedule of {args.team} ...")
    schedule = parse_schedule(fetch.get(f"/teams/{args.team}/schedule", use_cache=False))
    courts = parse_courts(fetch.get("/courts", use_cache=False))
    print(f"{len(schedule)} upcoming games, {len(courts)} gyms known.")

    tournament, standings = None, None
    for g in schedule:
        g["gym"] = gym_info(g.pop("gym_name"), courts)
        g["confirmed"] = bool(g["date"] and g["gym"])
        g["url"] = f"{BASE}/games/{g['game_id']}" if g["game_id"] else None
    first = next((g for g in schedule if g["game_id"]), None)
    if first:
        doc = parse_html(fetch.get(f"/games/{first['game_id']}", use_cache=False))
        h6 = next((h for h in doc.find_all("h6") if "title" in h.classes()), None)
        title = re.match(r"(.+?\d{2}/\d{2})", h6.text()) if h6 else None
        if title:
            slug = tournament_slug(title[1])
            tournament = {"title": title[1], "slug": slug, "url": f"{BASE}/tournaments/{slug}/standings"}
            standings = parse_standings(fetch.get(f"/tournaments/{slug}/standings", use_cache=False), args.team)

    scouting = {}
    for g in schedule:
        if g["confirmed"] and g["opponent_id"] and g["opponent_id"] not in scouting:
            print(f"Scouting {g['opponent']} ({g['season']}) ...")
            scouting[g["opponent_id"]] = scout(fetch, g["opponent_id"], g["season"])
            s = scouting[g["opponent_id"]]
            print(f"  {len(s['games'])} games this season, {len(s['players'])} player lines")

    payload = {"team_id": args.team, "source": f"{BASE}/teams/{args.team}/schedule", "tournament": tournament,
               "standings": standings, "games": schedule, "scouting": scouting}
    out = Path(args.site) / "upcoming.js"
    old = None
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8")[len(PREFIX):].rstrip().rstrip(";"))
        except ValueError:
            old = None
    if old and {k: v for k, v in old.items() if k != "scraped_at"} == payload:
        print("No changes in upcoming games or scouting.")
        return
    payload["scraped_at"] = datetime.now().isoformat(timespec="seconds")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PREFIX + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"Upcoming games updated: {out}")


if __name__ == "__main__":
    main()
