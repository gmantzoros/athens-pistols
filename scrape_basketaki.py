#!/usr/bin/env python3
"""
Scrapes every game a team has played on basketaki.com: the team's results page,
then each game's box score (player stats for BOTH teams) and quarter scores.

This is an independent re-implementation of scrape_basketaki.ps1, used to
cross-check it. It uses only the Python standard library and parses pages into
a real HTML tree (html.parser) instead of text patterns, and maps stat columns
by their header names instead of by position.

Writes (default folder: data_py):
    games.csv          one row per game, from the team's point of view
    player_stats.csv   one row per player per game (both teams)
    stats.json         everything combined

Usage:
    python scrape_basketaki.py
    python scrape_basketaki.py --team athens-pistols --out data_py --refresh
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://www.basketaki.com"
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}


# ------------------------------------------------------------------ tiny DOM
class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = {k: (v or "") for k, v in (attrs or [])}
        self.children = []
        self.parent = parent

    def classes(self):
        return self.attrs.get("class", "").split()

    def iter(self):
        stack = list(reversed([c for c in self.children if isinstance(c, Node)]))
        while stack:
            n = stack.pop()
            yield n
            stack.extend(reversed([c for c in n.children if isinstance(c, Node)]))

    def find_all(self, tag=None, cls=None):
        return [n for n in self.iter()
                if (tag is None or n.tag == tag) and (cls is None or cls in n.classes())]

    def find(self, tag=None, cls=None):
        for n in self.iter():
            if (tag is None or n.tag == tag) and (cls is None or cls in n.classes()):
                return n
        return None

    def kids(self, *tags):
        return [c for c in self.children if isinstance(c, Node) and c.tag in tags]

    def text(self):
        out = []

        def walk(n):
            for c in n.children:
                if isinstance(c, str):
                    out.append(c)
                elif c.tag not in ("script", "style"):
                    walk(c)
        walk(self)
        return " ".join(" ".join(out).split())

    def ancestor(self, cls):
        p = self.parent
        while p is not None:
            if cls in p.classes():
                return p
            p = p.parent
        return None


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs, self.stack[-1]))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(html):
    b = TreeBuilder()
    b.feed(html)
    b.close()
    return b.root


# ------------------------------------------------------------------ helpers
def to_int(s):
    s = (s or "").strip()
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def to_minutes(s):
    s = (s or "").strip()
    if re.fullmatch(r"\d+", s):
        return int(s)
    m = re.fullmatch(r"(\d+):(\d+)", s)
    return round(int(m[1]) + int(m[2]) / 60, 1) if m else None


def shots(s):
    m = re.search(r"(\d+)\s*/\s*(\d+)", s or "")
    return (int(m[1]), int(m[2])) if m else (None, None)


def iso_date(d):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", d)
    return f"{m[3]}-{m[2]}-{m[1]}" if m else d


LOOKALIKES = str.maketrans("ABEHIKMNOPTXYZ", "ΑΒΕΗΙΚΜΝΟΡΤΧΥΖ")


def norm_header(h):
    h = unicodedata.normalize("NFD", h.upper())
    h = "".join(ch for ch in h if unicodedata.category(ch) != "Mn")
    return h.replace(" ", "").translate(LOOKALIKES)


HEADER_KEYS = {norm_header(k): v for k, v in {
    "Παίχτης": "player", "MVP": "mvp", "Λεπτα": "min", "Ποντοι": "pts",
    "EFF": "eff", "ΡΜΠ": "reb", "Επιθ": "oreb", "Αμυ": "dreb", "ΑΣΙ": "ast",
    "ΚΛΨ": "stl", "ΛΑΘ": "tov", "ΚΟΨ": "blk", "ΒΟΛΕΣ": "ft",
    "2Ποντα": "fg2", "3Ποντα": "fg3", "ΤΜΡ": "tmr", "%": None,
}.items()}
REQUIRED = {"player", "mvp", "min", "pts", "eff", "reb", "oreb", "dreb", "ast",
            "stl", "tov", "blk", "ft", "fg2", "fg3", "tmr"}


class Fetcher:
    def __init__(self, cache_dir, refresh, delay):
        self.cache_dir, self.refresh, self.delay = cache_dir, refresh, delay
        cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, path, use_cache=True):
        f = self.cache_dir / (hashlib.sha1(path.encode()).hexdigest()[:16] + ".html")
        if use_cache and not self.refresh and f.exists():
            return f.read_text(encoding="utf-8")
        req = urllib.request.Request(BASE + path, headers={
            "User-Agent": "Mozilla/5.0 (team stats archive script)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
        time.sleep(self.delay)
        if use_cache and "alc-name" in html:   # cache only pages with player stats
            f.write_text(html, encoding="utf-8")
        return html


# ------------------------------------------------------------------ results page
def parse_results(html, team_id):
    doc = parse_html(html)
    title = doc.find("title")
    team_name = re.split(r"\s+-\s+Basketaki", title.text())[0].strip() if title else team_id
    games, seen = [], set()
    for tr in doc.find_all("tr"):
        tds = tr.kids("td")
        if len(tds) < 8 or "team-result__date" not in tds[0].classes():
            continue
        opp_link = next((a for a in tds[1].find_all("a")
                         if re.fullmatch(r"/teams/[^/]+/profile", a.attrs.get("href", ""))), None)
        game_link = next((a for a in tds[7].find_all("a")
                          if a.attrs.get("href", "").startswith("/games/")), None)
        game_id = game_link.attrs["href"][len("/games/"):] if game_link else None
        opponent = tds[1].text()
        home_away = tds[4].text()
        hs = as_ = None
        m = re.fullmatch(r"(\S+)\s*-\s*(\S+)", tds[3].text())
        if m:
            hs, as_ = to_int(m[1]), to_int(m[2])
        home = home_away == "Home"
        ts, os_ = (hs, as_) if home else (as_, hs)
        key = game_id or f"{tds[0].text()}|{opponent}"
        if key in seen:
            continue
        seen.add(key)
        games.append({
            "game_id": game_id,
            "date": iso_date(tds[0].text()),
            "season": tds[6].text(),
            "competition": tds[5].text(),
            "round": None,
            "tournament": None,
            "opponent": opponent,
            "opponent_id": opp_link.attrs["href"].split("/")[2] if opp_link else None,
            "home_away": home_away,
            "result": tds[2].text() or None,
            "team_score": ts,
            "opp_score": os_,
            "margin": ts - os_ if ts is not None and os_ is not None else None,
            "status": "played",
            "forfeit": False,
            **{f"{side}_{q}": None for side in ("team", "opp") for q in ("q1", "q2", "q3", "q4", "ot")},
            "has_box_score": False,
            "team_players": 0,
            "box_score_complete": False,
            "url": f"{BASE}/games/{game_id}" if game_id else None,
        })
    games.sort(key=lambda g: g["date"])
    return team_name, games


# ------------------------------------------------------------------ box score
def parse_box_score(html, g, team_id, team_name):
    doc = parse_html(html)
    h6 = next((h for h in doc.find_all("h6") if "title" in h.classes()), None)
    if h6:
        g["tournament"] = h6.text()
        m = re.search(r"(\d+)η\s", g["tournament"])
        g["round"] = int(m[1]) if m else None

    sb = doc.find("table", "table__cell-center")
    if sb:
        rows = [[c.text() for c in tr.kids("td", "th")] for tr in sb.find_all("tr")]
        rows = [r for r in rows if r and r[0].lower() != "scoreboard"]
        if len(rows) >= 2:
            home_row, away_row = rows[0], rows[1]
            t_row, o_row = (home_row, away_row) if g["home_away"] == "Home" else (away_row, home_row)
            for i, q in enumerate(("q1", "q2", "q3", "q4", "ot"), start=1):
                g[f"team_{q}"] = to_int(t_row[i]) if i < len(t_row) else None
                g[f"opp_{q}"] = to_int(o_row[i]) if i < len(o_row) else None

    lines = []
    for table in doc.find_all("table", "alc-table-stats"):
        card = table.ancestor("card")
        name_el = card.find(cls="team-meta__name") if card else None
        link = name_el.find("a") if name_el else None
        t_id = link.attrs.get("href", "").split("/")[2] if link else None
        t_name = link.text() if link else None
        is_ours = t_id == team_id

        header = None
        for tr in table.find_all("tr"):
            ths = tr.kids("th")
            if ths:
                header = [HEADER_KEYS.get(norm_header(th.text()), "?" + th.text()) for th in ths]
                missing = REQUIRED - set(header)
                if missing or any(h and h.startswith("?") for h in header):
                    print(f"  WARNING {g['game_id']}: unexpected header {header}", file=sys.stderr)
                continue
            tds = tr.kids("td")
            if not tds or "alc-name" not in tds[0].classes() or header is None:
                continue   # totals row
            rec = {}
            for key, td in zip(header, tds):
                if key is None:
                    continue
                txt = td.text()
                if key == "player":
                    a = td.find("a")
                    href = a.attrs.get("href", "") if a else ""
                    rec["player_id"] = href[len("/players/"):] if href.startswith("/players/") else None
                    rec["player"] = txt
                elif key == "mvp":
                    rec["mvp"] = td.find("i", "fa-trophy") is not None
                elif key == "min":
                    rec["min"] = to_minutes(txt)
                elif key in ("ft", "fg2", "fg3"):
                    rec[key + "m"], rec[key + "a"] = shots(txt)
                else:
                    rec[key] = to_int(txt)
            lines.append({
                "game_id": g["game_id"], "date": g["date"], "season": g["season"],
                "competition": g["competition"], "team_id": t_id, "team": t_name,
                "is_our_team": is_ours,
                "opponent": g["opponent"] if is_ours else team_name,
                "player_id": rec.get("player_id"), "player": rec.get("player"),
                "mvp": rec.get("mvp", False), "min": rec.get("min"), "pts": rec.get("pts"),
                "eff": rec.get("eff"), "reb": rec.get("reb"), "oreb": rec.get("oreb"),
                "dreb": rec.get("dreb"), "ast": rec.get("ast"), "stl": rec.get("stl"),
                "tov": rec.get("tov"), "blk": rec.get("blk"),
                "ftm": rec.get("ftm"), "fta": rec.get("fta"),
                "fg2m": rec.get("fg2m"), "fg2a": rec.get("fg2a"),
                "fg3m": rec.get("fg3m"), "fg3a": rec.get("fg3a"),
                "tmr": rec.get("tmr"),
            })
    return lines


def played(l):
    return bool((l["min"] or 0) > 0 or l["pts"] or l["reb"] or l["ast"] or l["stl"]
                or l["tov"] or l["blk"] or l["fta"] or l["fg2a"] or l["fg3a"])


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team", default="athens-pistols")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "data_py"))
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--site", default=str(Path(__file__).resolve().parent / "site"),
                    help="folder of the website; data.js is written there ('' to skip)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fetch = Fetcher(out / "cache", args.refresh, args.delay)

    print(f"Fetching results page for {args.team} ...")
    team_name, games = parse_results(fetch.get(f"/teams/{args.team}/results", use_cache=False), args.team)
    print(f"Found {len(games)} games.")

    players = []
    for i, g in enumerate(games, start=1):
        if g["result"] is None or (g["team_score"] is None and g["opp_score"] is None):
            g["status"] = "no result"
        if not g["game_id"]:
            print(f"[{i:3}/{len(games)}] {g['date']} {g['opponent']:<28} (no game page)")
            continue
        try:
            html = fetch.get(f"/games/{g['game_id']}/box-score")
        except Exception as e:  # noqa: BLE001
            print(f"  WARNING could not fetch {g['game_id']}: {e}", file=sys.stderr)
            continue
        kept = [l for l in parse_box_score(html, g, args.team, team_name) if played(l)]
        forfeit_score = (g["team_score"], g["opp_score"]) in ((20, 0), (0, 20))
        if forfeit_score and not sum(l["pts"] or 0 for l in kept):
            kept, g["status"], g["forfeit"] = [], "forfeit", True
        players.extend(kept)
        ours = [l for l in kept if l["is_our_team"]]
        g["has_box_score"] = bool(ours)
        g["team_players"] = len(ours)
        g["box_score_complete"] = bool(ours) and sum(l["pts"] or 0 for l in ours) == g["team_score"]
        score = f"{g['team_score']}-{g['opp_score']}"
        print(f"[{i:3}/{len(games)}] {g['date']} {g['opponent']:<28} {g['result'] or '':<2} {score:>7}  players: {len(kept)}")

    incomplete = [g for g in games if g["status"] == "played" and not g["box_score_complete"]]
    for g in incomplete:
        pts = sum(l["pts"] or 0 for l in players if l["game_id"] == g["game_id"] and l["is_our_team"])
        print(f"  incomplete box score on site: {g['date']} vs {g['opponent']} - player points {pts}, final score {g['team_score']}")

    write_csv(out / "games.csv", games)
    write_csv(out / "player_stats.csv", players)
    payload = json.dumps({
        "team_id": args.team, "team": team_name,
        "source": f"{BASE}/teams/{args.team}/results",
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "games": games, "players": players,
    }, ensure_ascii=False)
    (out / "stats.json").write_text(payload, encoding="utf-8")
    if args.site:   # website data: site/data.js is loaded by site/index.html
        site = Path(args.site)
        site.mkdir(parents=True, exist_ok=True)
        (site / "data.js").write_text(f"window.PISTOLS_DATA = {payload};\n", encoding="utf-8")
        print(f"Website data updated: {site / 'data.js'}")

    with_box = sum(1 for g in games if g["has_box_score"])
    print(f"\nDone. {len(games)} games, {with_box} with box scores, {len(players)} player lines. "
          f"Point-sum mismatches: {len(incomplete)}")
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
