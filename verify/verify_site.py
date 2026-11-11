#!/usr/bin/env python3
"""
Independent check of every number the website shows.

It reads the original data (data/games.csv, data/player_stats.csv), recomputes
each stat from its definition in plain Python (no code shared with the site),
and compares it with what the site actually displayed, as captured by
verify/extract.js into verify/out/*.json.

Usage:  python verify/verify_site.py        (writes verify/report.txt)
"""
import csv
import json
import math
import re
import sys
from collections import Counter
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "out"
TEAM = "Athens Pistols"
NA = "–"

# --------------------------------------------------------------------------- formatting (same rules as a browser)
def isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

def jsround(x):
    return math.floor(x + 0.5)

def fixed(x, nd):
    d = Decimal(abs(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)
    s = format(d, "f")
    return "-" + s if x < 0 else s

def jsfix(v, nd): return float(fixed(v, nd))   # +x.toFixed(nd) in a browser (ties round up, unlike Python's round)
def f0(v): return f"{jsround(v):,}" if isnum(v) else NA
def f1(v): return fixed(v, 1) if isnum(v) else NA
def f2(v): return fixed(v, 2) if isnum(v) else NA
def fp(v): return fixed(v * 100, 1) + "%" if isnum(v) else NA
def fp0(v): return f"{jsround(v * 100)}%" if isnum(v) else NA
def fs1(v): return (("+" if v > 0 else "−" if v < 0 else "±") + fixed(abs(v), 1)) if isnum(v) else NA
def fsi(v): return (("+" if v > 0 else "−" if v < 0 else "±") + str(abs(jsround(v)))) if isnum(v) else NA
def S(v): return "" if v is None else str(v)

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
def fdate(iso, long=False):
    y, m, d = iso[:4], iso[5:7], iso[8:10]
    return f"{int(d)} {MON[int(m) - 1]} {y}" if long else f"{d}/{m}/{y[2:]}"
def season_label(s):
    m = re.fullmatch(r"(\d{2})/(\d{2})", s or "")
    return f"20{m[1]}–{m[2]}" if m else (s or "")
def plural(n, w, wp=None): return f"{f0(n)} {w if n == 1 else (wp or w + 's')}"
def rec_txt(r): return f"{r['w']}–{r['l']}"
def rid(s): return re.sub(r"[^A-Za-z0-9-]", "-", str(s))
def ratio(n, d): return n / d if (isnum(d) and d > 0 and isnum(n)) else None

def split_name(raw):
    t = (raw or "").strip().split()
    i = next((k for k, x in enumerate(t) if x.endswith(".")), -1)
    return (" ".join(t[i + 1:]), " ".join(t[:i])) if 0 < i < len(t) - 1 else None
def disp(raw):
    s = split_name(raw); return f"{s[0]} {s[1]}" if s else (raw or "")
def short(raw):
    s = split_name(raw); return f"{s[0][0]}. {s[1]}" if s else (raw or "")

COMP = {
    "W.Master": ("Winter Master League", "Winter Master", "League", "Winter league"),
    "S.Master": ("Summer Master League", "Summer Master", "League", "Summer league"),
    "W.Evolution": ("Winter Evolution League", "Winter Evolution", "League", "Winter league"),
    "S.Evolution": ("Summer Evolution League", "Summer Evolution", "League", "Summer league"),
    "W.Development 1": ("Winter Development League", "Winter Development", "League", "Winter league"),
    "Athens Superbet Cup": ("Cup", "Cup", "Cup", "Cup"),
}
def comp(c):
    if c in COMP:
        n, s, t, p = COMP[c]
    else:
        cup = "cup" in (c or "").lower()
        n = s = c or "Other"; t = "Cup" if cup else "League"
        p = "Cup" if cup else ("Summer league" if (c or "").startswith("S.") else "Winter league")
    return {"name": n, "short": s, "type": t, "phase": p}

# --------------------------------------------------------------------------- load the original data
def ival(s): return int(s) if s not in ("", None) else None

games = []
with open(ROOT / "data" / "games.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        g = dict(r)
        for k in ("team_score", "opp_score", "round", "team_q1", "team_q2", "team_q3", "team_q4", "team_ot", "opp_q1", "opp_q2", "opp_q3", "opp_q4", "opp_ot"):
            g[k] = ival(r[k])
        g["result"] = r["result"] or None
        g["forfeit"] = r["forfeit"] == "True" or r["status"] == "forfeit"
        g["decided"] = g["result"] in ("W", "L")
        g["real"] = (not g["forfeit"]) and r["status"] == "played" and g["decided"] and g["team_score"] is not None and g["opp_score"] is not None
        g["mg"] = g["team_score"] - g["opp_score"] if g["real"] else None
        g["ci"] = comp(r["competition"])
        g["okey"] = r["opponent_id"] or ("name-" + rid(r["opponent"] or "unknown"))
        games.append(g)
games.sort(key=lambda g: g["date"])
for i, g in enumerate(games):
    g["i"] = i
    g["rid"] = rid(g["game_id"]) if g["game_id"] else f"x{i}"
G_BY_ID = {g["game_id"]: g for g in games if g["game_id"]}
G_BY_RID = {g["rid"]: g for g in games}
SEASONS = sorted({g["season"] for g in games if g["season"]})
OPP_NAME = {}
for g in games:
    OPP_NAME[g["okey"]] = g["opponent"]

SK = ["min", "pts", "eff", "reb", "oreb", "dreb", "ast", "stl", "tov", "blk", "ftm", "fta", "fg2m", "fg2a", "fg3m", "fg3a"]
TK = SK + ["fgm", "fga"]
def zero(): return dict({k: 0 for k in TK}, n=0)
def add(a, b):
    for k in TK: a[k] += b[k]
    a["n"] += 1
def total(ls):
    t = zero()
    for l in ls: add(t, l)
    t["n"] = len(ls)
    return t
def poss(T): return T["fga"] + 0.44 * T["fta"] - T["oreb"] + T["tov"]

lines = []
with open(ROOT / "data" / "player_stats.csv", encoding="utf-8-sig", newline="") as f:
    for idx, r in enumerate(csv.DictReader(f)):
        g = G_BY_ID.get(r["game_id"])
        if not g:
            continue
        l = {k: (float(r[k]) if "." in r[k] else int(r[k])) if r[k] not in ("",) else 0 for k in SK}
        l.update(idx=idx, g=g, gid=r["game_id"], us=r["is_our_team"] == "True", mvp=r["mvp"] == "True", player=r["player"],
                 key=r["player_id"] or ("n-" + r["player"]), team_id=r["team_id"], team=r["team"])
        l["fgm"] = l["fg2m"] + l["fg3m"]; l["fga"] = l["fg2a"] + l["fg3a"]
        l["gs"] = l["pts"] + 0.4 * l["fgm"] - 0.7 * l["fga"] - 0.4 * (l["fta"] - l["ftm"]) + 0.7 * l["oreb"] + 0.3 * l["dreb"] + l["stl"] + 0.7 * l["ast"] + 0.7 * l["blk"] - l["tov"]
        l["cats"] = sum(1 for v in (l["pts"], l["reb"], l["ast"], l["stl"], l["blk"]) if v >= 10)
        lines.append(l)

BOX = {}
for l in lines:
    b = BOX.setdefault(l["gid"], {"g": l["g"], "us": [], "them": []})
    (b["us"] if l["us"] else b["them"]).append(l)
for b in BOX.values():
    b["usT"], b["themT"] = total(b["us"]), total(b["them"])
    b["usOK"] = len(b["us"]) > 0 and b["usT"]["pts"] == b["g"]["team_score"]
    b["themOK"] = len(b["them"]) > 0 and b["themT"]["pts"] == b["g"]["opp_score"]
    b["both"] = len(b["us"]) > 0 and len(b["them"]) > 0
    b["full"] = b["usOK"] and b["themOK"]
for l in lines:
    b = BOX[l["gid"]]
    l["tm"], l["op"] = (b["usT"], b["themT"]) if l["us"] else (b["themT"], b["usT"])
    l["share"] = l["min"] / (l["tm"]["min"] / 5) if l["tm"]["min"] > 0 else 0
    l["ctx"] = b["both"]
def box(g): return BOX.get(g["game_id"]) if g and g["game_id"] else None

PL, OPL = {}, {}
for l in lines:
    reg = PL if l["us"] else OPL
    p = reg.setdefault(l["key"], {"id": l["key"], "rid": rid(l["key"]), "lines": [], "teams": {}})
    p["name"] = l["player"]; p["lines"].append(l); p["teams"].setdefault(l["team_id"], l["team"])
    p["teams"][l["team_id"]] = l["team"]
for p in list(PL.values()) + list(OPL.values()):
    p["disp"], p["short"] = disp(p["name"]), short(p["name"])
for p in PL.values():
    p["lines"].sort(key=lambda l: l["g"]["i"])
PL_BY_RID = {p["rid"]: p for p in PL.values()}
def p_of(l): return (PL if l["us"] else OPL)[l["key"]]

# --------------------------------------------------------------------------- stats definitions
DEFAULT_F = {"seasons": [], "comps": [], "opp": "", "venue": "all", "result": "all", "forfeits": True}

def game_ok(g, F, ignore_season=False, ignore_opp=False):
    if not ignore_season and F["seasons"] and g["season"] not in F["seasons"]: return False
    if F["comps"] and g["competition"] not in F["comps"]: return False
    if not ignore_opp and F["opp"] and g["okey"] != F["opp"]: return False
    if F["venue"] != "all" and g["home_away"] != F["venue"]: return False
    if F["result"] != "all" and g["result"] != F["result"]: return False
    return True
def fgames(F, **kw): return [g for g in games if game_ok(g, F, **kw)]
def lines_for(G, us=True):
    ids = {g["game_id"] for g in G}
    return [l for l in lines if l["us"] == us and l["gid"] in ids]
def box_games(G): return [g for g in G if box(g) and box(g)["us"]]
def auto_min(G): return max(1, min(10, jsround(len(box_games(G)) * 0.2)))

def record(G, F):
    w = l = fw = fl = 0
    for g in G:
        if not g["decided"]: continue
        if g["forfeit"]:
            if not F["forfeits"]: continue
            if g["result"] == "W": fw += 1
            else: fl += 1
        if g["result"] == "W": w += 1
        else: l += 1
    return {"w": w, "l": l, "fw": fw, "fl": fl, "n": w + l, "pct": ratio(w, w + l)}

def streaks(G, F):
    best = {"W": 0, "L": 0}; cur = None; ln = 0
    for g in G:
        if not g["decided"] or (g["forfeit"] and not F["forfeits"]): continue
        if g["result"] == cur: ln += 1
        else: cur, ln = g["result"], 1
        best[cur] = max(best[cur], ln)
    return {"bestW": best["W"], "bestL": best["L"], "cur": cur, "len": ln}

def four(A, B):
    return {"efg": ratio(A["fgm"] + 0.5 * A["fg3m"], A["fga"]), "tov": ratio(A["tov"], A["fga"] + 0.44 * A["fta"] + A["tov"]),
            "orb": ratio(A["oreb"], A["oreb"] + B["dreb"]), "ftr": ratio(A["ftm"], A["fga"])}

def team_agg(G, F):
    r = record(G, F)
    real = [g for g in G if g["real"]]
    pf = sum(g["team_score"] for g in real); pa = sum(g["opp_score"] for g in real)
    full = [g for g in real if box(g) and box(g)["full"]]
    U, O = zero(), zero()
    for g in full:
        add(U, box(g)["usT"]); add(O, box(g)["themT"])
    pU, pO = poss(U), poss(O)
    r.update(real=real, nReal=len(real), ppg=ratio(pf, len(real)), oppg=ratio(pa, len(real)), mg=ratio(pf - pa, len(real)),
             full=full, nFull=len(full), U=U, O=O, ortg=ratio(100 * U["pts"], pU), drtg=ratio(100 * O["pts"], pO),
             net=(100 * U["pts"] / pU - 100 * O["pts"] / pO) if (full and pU > 0 and pO > 0) else None,
             pace=(pU + pO) / 2 / len(full) if full else None, fUs=four(U, O), fOp=four(O, U))
    return r

def agg(ls):
    a = total(ls)
    a.update(gp=len(ls), mvp=sum(l["mvp"] for l in ls), dd=sum(l["cats"] >= 2 for l in ls), td=sum(l["cats"] >= 3 for l in ls),
             gsum=sum(l["gs"] for l in ls), p20=sum(l["pts"] >= 20 for l in ls), p30=sum(l["pts"] >= 30 for l in ls),
             w=sum(l["g"]["result"] == "W" for l in ls), l=sum(l["g"]["result"] == "L" for l in ls))
    reals = [l["g"]["mg"] for l in ls if l["g"]["real"]]
    a["winp"] = ratio(a["w"], a["w"] + a["l"]); a["mgp"] = ratio(sum(reals), len(reals))
    a["fgp"] = ratio(a["fgm"], a["fga"]); a["p2"] = ratio(a["fg2m"], a["fg2a"]); a["p3"] = ratio(a["fg3m"], a["fg3a"]); a["ftp"] = ratio(a["ftm"], a["fta"])
    a["efg"] = ratio(a["fgm"] + 0.5 * a["fg3m"], a["fga"]); a["ts"] = ratio(a["pts"], 2 * (a["fga"] + 0.44 * a["fta"]))
    a["tpar"] = ratio(a["fg3a"], a["fga"]); a["ftr"] = ratio(a["fta"], a["fga"])
    a["ato"] = a["ast"] / a["tov"] if a["tov"] > 0 else None
    a["tovp"] = ratio(a["tov"], a["fga"] + 0.44 * a["fta"] + a["tov"])
    n = dict.fromkeys(["use", "ast", "orb", "drb", "trb", "stl", "blk"], 0.0); d = dict(n)
    for x in ls:
        if not x["ctx"] or not x["share"] > 0: continue
        s, T, O = x["share"], x["tm"], x["op"]
        n["use"] += x["fga"] + 0.44 * x["fta"] + x["tov"]; d["use"] += s * (T["fga"] + 0.44 * T["fta"] + T["tov"])
        n["ast"] += x["ast"]; d["ast"] += s * T["fgm"] - x["fgm"]
        n["orb"] += x["oreb"]; d["orb"] += s * (T["oreb"] + O["dreb"])
        n["drb"] += x["dreb"]; d["drb"] += s * (T["dreb"] + O["oreb"])
        n["trb"] += x["reb"]; d["trb"] += s * (T["reb"] + O["reb"])
        n["stl"] += x["stl"]; d["stl"] += s * poss(O)
        n["blk"] += x["blk"]; d["blk"] += s * O["fg2a"]
    for k, out in (("use", "usg"), ("ast", "astp"), ("orb", "orbp"), ("drb", "drbp"), ("trb", "trbp"), ("stl", "stlp"), ("blk", "blkp")):
        a[out] = ratio(n[k], d[k])
    return a
def pg(a, k): return ratio(a[k], a["gp"])
def p40(a, k): return ratio(a[k] * 40, a["min"])

def player_rows(ls):
    groups = {}
    for l in ls: groups.setdefault(l["key"], []).append(l)
    return [{"p": p_of(v[0]), "ls": v, "a": agg(v)} for v in groups.values()]

def top_scorer_pts(g):
    b = box(g)
    return max(l["pts"] for l in b["us"]) if b and b["us"] else None

def pctile(val, pop):
    if not isnum(val): return None
    vs = [v for v in pop if isnum(v)]
    if not vs: return None
    below = sum(v < val for v in vs); eq = sum(v == val for v in vs)
    return jsround(100 * (below + 0.5 * eq) / len(vs))
RADAR = [lambda a: p40(a, "pts"), lambda a: p40(a, "reb"), lambda a: p40(a, "ast"), lambda a: p40(a, "stl"), lambda a: p40(a, "blk"),
         lambda a: a["ts"], lambda a: -a["tovp"] if isnum(a["tovp"]) else None, lambda a: p40(a, "eff")]

def filter_note(F):
    parts = []
    if F["seasons"]: parts.append(", ".join(season_label(s) for s in F["seasons"]))
    if F["comps"]: parts.append(", ".join(comp(c)["short"] for c in F["comps"]))
    if F["opp"]: parts.append("vs " + OPP_NAME.get(F["opp"], ""))
    if F["venue"] != "all": parts.append("Home games" if F["venue"] == "Home" else "Away games")
    if F["result"] != "all": parts.append("Wins only" if F["result"] == "W" else "Losses only")
    return " · ".join(parts) if parts else "All games since 2019"
def vs_txt(g): return ("vs " if g["home_away"] == "Home" else "at ") + g["opponent"]
def res_text(g):
    if not g["decided"]: return "Forfeit" if g["status"] == "forfeit" else "No result"
    return g["result"] + (" Forfeit" if g["forfeit"] else "")
def score_text(g): return f"{g['team_score']}–{g['opp_score']}" if g["team_score"] is not None and g["opp_score"] is not None else NA
def flags_text(g):
    b = box(g)
    if g["real"] and (not b or not b["us"]): return "No box"
    if g["real"] and b and not b["usOK"]: return "Partial box"
    return ""

# --------------------------------------------------------------------------- comparison bookkeeping
class Checker:
    def __init__(self):
        self.n = 0; self.fail = []; self.pages = Counter()
    def bad(self, where, msg): self.fail.append(f"{where}: {msg}")
    def txt(self, where, shown, exp):
        """Exact text match (numbers inside are formatted exactly the way the browser formats them)."""
        self.n += 1
        if exp == "" and shown in (None, ""): return
        if shown == exp: return
        self.bad(where, f"shows {shown!r}, expected {exp!r}")
    def num(self, where, shown, value, fmt):
        self.n += 1
        exp = fmt(value)
        if shown == exp: return
        if isnum(value) and shown in (fmt(value + 1e-9), fmt(value - 1e-9)): return
        self.bad(where, f"shows {shown!r}, expected {exp!r}")
    def eq(self, where, shown, exp):
        self.n += 1
        if shown != exp: self.bad(where, f"shows {shown!r}, expected {exp!r}")
    def close(self, where, shown, exp, tol=1e-6):
        self.n += 1
        if shown is None and exp is None: return
        if shown is None or exp is None or abs(shown - exp) > tol: self.bad(where, f"chart value {shown!r}, expected {exp!r}")
    def series(self, where, shown, exp, tol=1e-6):
        if shown is None or len(shown) != len(exp):
            self.n += 1; self.bad(where, f"chart has {None if shown is None else len(shown)} points, expected {len(exp)}"); return
        for i, (a, b) in enumerate(zip(shown, exp)):
            self.close(f"{where}[{i}]", a, b, tol)

C = Checker()

def tbl(s, tid=None, panel=None):
    for t in s["tables"]:
        if (tid and t["id"] == tid) or (panel and t["panel"] == panel): return t
    return None
def chart(s, cid): return next((c for c in s["charts"] if c["id"] == cid), None)
def kpis(s): return {k["l"]: k for k in s["kpis"]}
def facts(s, panel=None): return {f["l"]: f for f in s["facts"] if panel is None or f["panel"] == panel}
def lead(s, panel): return next((x["items"] for x in s["leads"] if x["panel"] == panel), None)
def panel_sub(s, title): return next((sub for t, sub in s["panelSubs"] if t == title), None)
def row_rid(row, prefix):
    h = row["href"] or next((x for x in row["links"] if x.startswith("#" + prefix + "-")), None)
    return h[len(prefix) + 2:] if h and h.startswith("#" + prefix + "-") else None

def check_kpi(where, K, label, v, s=None):
    k = K.get(label)
    if not k: C.n += 1; C.bad(where, f"missing tile {label!r}"); return
    C.txt(f"{where} tile '{label}'", k["v"], v)
    if s is not None: C.txt(f"{where} tile '{label}' subtitle", k["s"], s)

def check_rows(where, t, expected, key_fn, spec, ordered=False, exact_set=True):
    """expected: list of (key, obj). spec: {column label: (fn(obj) -> value, formatter)}"""
    if t is None:
        C.n += 1; C.bad(where, "table missing"); return
    exp = dict(expected)
    shown = []
    for row in t["rows"]:
        if row["empty"]: continue
        k = key_fn(row); shown.append(k)
        obj = exp.get(k)
        if obj is None:
            C.n += 1; C.bad(where, f"unexpected row {row['cells'][:3]}"); continue
        for label, (fn, fmt) in spec.items():
            if label not in t["head"]:
                C.n += 1; C.bad(where, f"missing column {label!r}"); continue
            cell = row["cells"][t["head"].index(label)]
            if fmt is S: C.txt(f"{where} [{row['cells'][0]}] {label}", cell, fn(obj))
            elif fmt == "top": check_top(f"{where} [{row['cells'][0]}] {label}", cell, obj)
            else: C.num(f"{where} [{row['cells'][0]}] {label}", cell, fn(obj), fmt)
    if exact_set:
        C.eq(f"{where} row count", len(shown), len(exp))
        missing = [k for k in exp if k not in set(shown)]
        if missing: C.n += 1; C.bad(where, f"rows missing: {missing[:5]}")
    if ordered:
        C.eq(f"{where} row order", shown, [k for k, _ in expected])

def check_top(where, cell, g):
    exp = top_scorer_pts(g)
    C.n += 1
    if exp is None:
        if cell != NA: C.bad(where, f"shows {cell!r}, expected '–'")
        return
    m = re.fullmatch(r"(.+) (\d+)", cell or "")
    if not m or int(m[2]) != exp:
        C.bad(where, f"shows {cell!r}, expected top score {exp}"); return
    names = {p_of(l)["short"] for l in box(g)["us"] if l["pts"] == exp}
    if m[1] not in names: C.bad(where, f"top scorer {m[1]!r} not among {names}")

def game_spec(cols):
    spec = {
        "Date": (lambda g: fdate(g["date"]), S), "Opponent": (lambda g: g["opponent"], S),
        "H/A": (lambda g: "Home" if g["home_away"] == "Home" else "Away", S), "Result": (res_text, S),
        "Score": (score_text, S), "+/−": (lambda g: g["mg"], fsi),
        "Competition": (lambda g: g["ci"]["short"] + (f" · MD {g['round']}" if g["round"] else ""), S),
        "Season": (lambda g: season_label(g["season"]), S), "Top scorer": (lambda g: g, "top"), "": (flags_text, S)}
    return {k: v for k, v in spec.items() if k in cols}

def check_games_table(where, t, G, ordered=False):
    if t is None: C.n += 1; C.bad(where, "table missing"); return
    check_rows(where, t, [(g["rid"], g) for g in G], lambda r: row_rid(r, "game"), game_spec(t["head"]), ordered=ordered)

PG = lambda k: (lambda r: pg(r["a"], k), f1)
TOT = lambda k: (lambda r: r["a"][k], f0)
P40 = lambda k: (lambda r: p40(r["a"], k), f1)
PCT = lambda k: (lambda r: r["a"][k], fp)
MA = lambda m, a: (lambda r: f"{f0(r['a'][m])}-{f0(r['a'][a])}", S)
def player_spec(mode):
    base = {"Player": (lambda r: r["p"]["disp"], S), "GP": TOT("gp")}
    if mode == "pg":
        base.update({"MIN": PG("min"), "PTS": PG("pts"), "REB": PG("reb"), "OREB": PG("oreb"), "DREB": PG("dreb"), "AST": PG("ast"), "STL": PG("stl"), "BLK": PG("blk"), "TOV": PG("tov"), "EFF": PG("eff"), "GmSc": PG("gsum"), "FG%": PCT("fgp"), "3P%": PCT("p3"), "FT%": PCT("ftp"), "MVP": TOT("mvp")})
    elif mode == "tot":
        base.update({"MIN": TOT("min"), "PTS": TOT("pts"), "REB": TOT("reb"), "OREB": TOT("oreb"), "DREB": TOT("dreb"), "AST": TOT("ast"), "STL": TOT("stl"), "BLK": TOT("blk"), "TOV": TOT("tov"), "FG": MA("fgm", "fga"), "3P": MA("fg3m", "fg3a"), "FT": MA("ftm", "fta"), "EFF": TOT("eff"), "MVP": TOT("mvp"), "DD": TOT("dd"), "TD": TOT("td"), "20+": TOT("p20")})
    elif mode == "p40":
        base.update({"MIN": PG("min"), "PTS": P40("pts"), "REB": P40("reb"), "OREB": P40("oreb"), "DREB": P40("dreb"), "AST": P40("ast"), "STL": P40("stl"), "BLK": P40("blk"), "TOV": P40("tov"), "FGA": P40("fga"), "FTA": P40("fta"), "EFF": P40("eff")})
    elif mode == "shoot":
        base.update({"FG": MA("fgm", "fga"), "FG%": PCT("fgp"), "2P": MA("fg2m", "fg2a"), "2P%": PCT("p2"), "3P": MA("fg3m", "fg3a"), "3P%": PCT("p3"), "FT": MA("ftm", "fta"), "FT%": PCT("ftp"), "eFG%": PCT("efg"), "TS%": PCT("ts"), "3PA rate": PCT("tpar"), "FT rate": PCT("ftr")})
    elif mode == "adv":
        base.update({"MIN": PG("min"), "USG%": PCT("usg"), "TS%": PCT("ts"), "AST%": PCT("astp"), "TOV%": PCT("tovp"), "AST/TO": (lambda r: r["a"]["ato"], f2), "ORB%": PCT("orbp"), "DRB%": PCT("drbp"), "TRB%": PCT("trbp"), "STL%": PCT("stlp"), "BLK%": PCT("blkp"), "GmSc": PG("gsum"), "EFF": PG("eff"), "W–L": (lambda r: f"{r['a']['w']}–{r['a']['l']}", S), "Win%": (lambda r: r["a"]["winp"], fp0), "+/− team": (lambda r: r["a"]["mgp"], fs1)})
    return base
def split_spec(first):
    return {first: (lambda r: r["lab"], S), "GP": TOT("gp"), "W–L": (lambda r: f"{r['a']['w']}–{r['a']['l']}", S),
            "MIN": PG("min"), "PTS": PG("pts"), "REB": PG("reb"), "AST": PG("ast"), "STL": PG("stl"), "BLK": PG("blk"), "TOV": PG("tov"), "EFF": PG("eff"),
            "FG%": PCT("fgp"), "3P%": PCT("p3"), "FT%": PCT("ftp"), "TS%": PCT("ts"), "MVP": TOT("mvp")}
BOX_SPEC = {
    "MIN": (lambda l: l["min"], f0), "PTS": (lambda l: l["pts"], f0), "REB": (lambda l: l["reb"], f0), "OR": (lambda l: l["oreb"], f0), "DR": (lambda l: l["dreb"], f0),
    "AST": (lambda l: l["ast"], f0), "STL": (lambda l: l["stl"], f0), "TOV": (lambda l: l["tov"], f0), "BLK": (lambda l: l["blk"], f0),
    "FG": (lambda l: f"{l['fgm']}-{l['fga']}", S), "FG%": (lambda l: ratio(l["fgm"], l["fga"]), fp0),
    "2P": (lambda l: f"{l['fg2m']}-{l['fg2a']}", S), "3P": (lambda l: f"{l['fg3m']}-{l['fg3a']}", S), "FT": (lambda l: f"{l['ftm']}-{l['fta']}", S),
    "EFF": (lambda l: l["eff"], f0), "GmSc": (lambda l: l.get("gs"), f1)}

def check_foot(where, t, obj, spec, label):
    if not t or not t["foot"]: C.n += 1; C.bad(where, "totals row missing"); return
    row = t["foot"][0]
    C.txt(f"{where} totals label", row[0], label)
    for lab, (fn, fmt) in spec.items():
        if lab not in t["head"]: continue
        cell = row[t["head"].index(lab)]
        if fmt is S: C.txt(f"{where} totals {lab}", cell, fn(obj))
        else: C.num(f"{where} totals {lab}", cell, fn(obj), fmt)

def check_lead_list(where, items, rows, val, fmt, x=None, n=5):
    exp = rows[:n]
    if items is None:
        C.n += 1
        if exp: C.bad(where, "list missing")
        return
    C.eq(f"{where} length", len(items), len(exp))
    for i, (it, r) in enumerate(zip(items, exp)):
        C.txt(f"{where} #{i + 1} name", it["name"], r["p"]["disp"])
        C.num(f"{where} #{i + 1} value", it["v"], val(r), fmt)
        if x: C.txt(f"{where} #{i + 1} detail", it["x"], x(r))

# --------------------------------------------------------------------------- page checks
def check_overview(s, F, w):
    G = fgames(F); ta = team_agg(G, F); st = streaks(G, F)
    hero = dict((k, v) for k, v in s["hero"])
    C.num(f"{w} hero wins", hero.get("Wins"), ta["w"], f0); C.num(f"{w} hero losses", hero.get("Losses"), ta["l"], f0)
    C.num(f"{w} hero win rate", hero.get("Win rate"), ta["pct"], fp)
    ffn = ta["fw"] + ta["fl"]
    C.txt(f"{w} forfeit note", s["heroNote"] or "", f"Includes {plural(ffn, 'forfeit')} ({ta['fw']} W, {ta['fl']} L)." if ffn else ("" if F["forfeits"] else "Forfeits are left out of the record."))
    nseas = len({g["season"] for g in G})
    span = f"{fdate(G[0]['date'], True)} – {fdate(G[-1]['date'], True)}" if G else "No games match the filters"
    active = F["seasons"] or F["comps"] or F["opp"] or F["venue"] != "all" or F["result"] != "all"
    C.txt(f"{w} hero subtitle", s["heroSub"], f"{span} · {plural(nseas, 'season')} · {plural(len(G), 'game')}" + (" · " + filter_note(F) if active else ""))
    K = kpis(s)
    check_kpi(w, K, "Points per game", f1(ta["ppg"]), f"{plural(ta['nReal'], 'game')} played on court")
    check_kpi(w, K, "Allowed per game", f1(ta["oppg"]), "Opponent points")
    check_kpi(w, K, "Average margin", fs1(ta["mg"]), "Points per game")
    check_kpi(w, K, "Current streak", f"{st['cur']}{st['len']}" if st["cur"] else NA, ("Wins in a row" if st["cur"] == "W" else "Losses in a row") if st["cur"] else "")
    check_kpi(w, K, "Longest win streak", str(st["bestW"]) if st["bestW"] else NA, f"Longest losing run: {st['bestL']}" if st["bestL"] else "")
    check_kpi(w, K, "Close games", rec_txt(record([g for g in G if g["real"] and abs(g["mg"]) <= 5], F)), "Decided by 5 or fewer")
    ss = [x for x in SEASONS if any(g["season"] == x for g in G)]
    c = chart(s, "c-rec")
    if c:
        C.eq(f"{w} record chart seasons", c["labels"], [season_label(x) for x in ss])
        R = [record([g for g in G if g["season"] == x], F) for x in ss]
        C.series(f"{w} record chart wins", c["sets"][0]["data"], [r["w"] for r in R]); C.series(f"{w} record chart losses", c["sets"][1]["data"], [r["l"] for r in R])
    c = chart(s, "c-pts")
    if c:
        ss2 = [x for x in SEASONS if any(g["season"] == x and g["real"] for g in G)]
        A = [team_agg([g for g in G if g["season"] == x], F) for x in ss2]
        C.eq(f"{w} points chart seasons", c["labels"], [season_label(x) for x in ss2])
        C.series(f"{w} points chart scored", c["sets"][0]["data"], [a["ppg"] for a in A]); C.series(f"{w} points chart allowed", c["sets"][1]["data"], [a["oppg"] for a in A])
    rows = player_rows(lines_for(G)); mn = auto_min(G); q = [r for r in rows if r["a"]["gp"] >= mn]
    for title, k in (("Points", "pts"), ("Rebounds", "reb"), ("Assists", "ast"), ("Efficiency", "eff")):
        top = sorted(q, key=lambda r: -(pg(r["a"], k) or 0))
        check_lead_list(f"{w} leaders {title}", lead(s, title), top, lambda r, k=k: pg(r["a"], k), f1, (lambda r: plural(r["a"]["gp"], "game")) if k == "pts" else None)
    C.txt(f"{w} leaders note", panel_sub(s, "Points"), f"Per game · min. {plural(mn, 'game')}")
    real = [g for g in G if g["real"]]; FA = facts(s, "Highlights")
    if real:
        bw = sorted(real, key=lambda g: -g["mg"])[0]
        C.txt(f"{w} biggest win", FA.get("Biggest win", {}).get("v"), fsi(bw["mg"]))
        C.txt(f"{w} biggest win detail", FA.get("Biggest win", {}).get("s"), f"{bw['team_score']}–{bw['opp_score']} {vs_txt(bw)}, {fdate(bw['date'], True)}")
        hs = sorted(real, key=lambda g: -g["team_score"])[0]
        C.txt(f"{w} most points", FA.get("Most points scored", {}).get("v"), str(hs["team_score"]))
        C.txt(f"{w} most points detail", FA.get("Most points scored", {}).get("s"), f"{vs_txt(hs)}, {fdate(hs['date'], True)}")
    ls = lines_for(G)
    if ls:
        bl = sorted(ls, key=lambda l: (-l["pts"], l["g"]["i"]))[0]
        C.txt(f"{w} best scoring game", FA.get("Best scoring game", {}).get("v"), f"{bl['pts']} pts")
        C.txt(f"{w} best scoring game detail", FA.get("Best scoring game", {}).get("s"), f"{p_of(bl)['disp']} {vs_txt(bl['g'])}, {fdate(bl['g']['date'], True)}")
        ct = sorted(rows, key=lambda r: -r["a"]["pts"])[0]
        C.txt(f"{w} leading scorer", FA.get("Leading scorer", {}).get("v"), f0(ct["a"]["pts"]))
        C.txt(f"{w} leading scorer detail", FA.get("Leading scorer", {}).get("s"), f"{ct['p']['disp']} in {plural(ct['a']['gp'], 'game')}")
    check_games_table(f"{w} recent games", tbl(s, "t-recent"), list(reversed(G))[:8], ordered=True)

def check_games(s, F, w):
    G = fgames(F); r = record(G, F)
    C.txt(f"{w} header", s["headSub"], f"{plural(len(G), 'game')} · {rec_txt(r)} · {filter_note(F)}")
    c = chart(s, "c-mg"); real = [g for g in G if g["real"]]
    if c:
        C.eq(f"{w} margin chart dates", c["labels"], [fdate(g["date"]) for g in real]); C.series(f"{w} margin chart", c["sets"][0]["data"], [g["mg"] for g in real])
    check_games_table(f"{w} game log", tbl(s, "t-games"), G)

def check_players(s, F, w, mode, pmin):
    G = fgames(F); rows = player_rows(lines_for(G))
    mn = auto_min(G) if pmin == "auto" else pmin
    q = [r for r in rows if r["a"]["gp"] >= mn]
    C.txt(f"{w} header", s["headSub"], f"{plural(len(rows), 'player')} · {plural(len(box_games(G)), 'game')} with box scores · {filter_note(F)}")
    check_rows(f"{w} leaderboard", tbl(s, "t-players"), [(r["p"]["rid"], r) for r in q], lambda row: row_rid(row, "player"), player_spec(mode))
    roster = sorted(rows, key=lambda r: (-r["a"]["gp"], -r["a"]["pts"]))[:12]
    C.eq(f"{w} card count", len(s["cards"]), len(roster))
    for card, r in zip(s["cards"], roster):
        cw = f"{w} card {r['p']['disp']}"
        C.eq(f"{cw} link", card["href"], "#player-" + r["p"]["rid"])
        ss = [x for x in SEASONS if any(l["g"]["season"] == x for l in r["ls"])]
        span = (season_label(ss[0]) if len(ss) == 1 else f"{season_label(ss[0])[:4]}–{season_label(ss[-1])[-2:]}") if ss else ""
        C.txt(f"{cw} subtitle", card["sub"], f"{span} · {plural(r['a']['gp'], 'game')}" + (f" · {r['a']['mvp']} MVP" if r["a"]["mvp"] else ""))
        for (k, shown) in zip(("pts", "reb", "ast"), card["stats"]):
            C.num(f"{cw} {k}", shown, pg(r["a"], k), f1)
        pts = [l["pts"] for l in sorted(r["ls"], key=lambda l: l["g"]["i"])][-20:]
        C.txt(f"{cw} trend caption", card["cap"] or "", f"Points, last {len(pts)} gameshigh {max(pts)}" if len(pts) > 1 else "")
    c = chart(s, "c-scatter")
    if c:
        exp = sorted((jsfix(pg(r["a"], "pts"), 2), jsfix(r["a"]["ts"] * 100, 2)) for r in q if isnum(pg(r["a"], "pts")) and isnum(r["a"]["ts"]))
        got = sorted((p["x"], p["y"]) for p in c["sets"][0]["data"])
        C.eq(f"{w} scatter point count", len(got), len(exp))
        for (a, b) in zip(got, exp):
            C.close(f"{w} scatter point", a[0], b[0], 0.011); C.close(f"{w} scatter point", a[1], b[1], 0.011)
    mv = sorted([r for r in rows if r["a"]["mvp"]], key=lambda r: (-r["a"]["mvp"], -r["a"]["gp"]))
    check_lead_list(f"{w} MVP list", lead(s, "Most MVP awards"), mv, lambda r: r["a"]["mvp"], f0, lambda r: f"in {plural(r['a']['gp'], 'game')}", n=10)

def check_records(s, F, w, tab):
    G = fgames(F); ls = lines_for(G); rows = player_rows(ls); real = [g for g in G if g["real"]]; st = streaks(G, F)
    FA = facts(s, "Team records")
    def gf(lab, g, v):
        C.txt(f"{w} team record {lab}", FA.get(lab, {}).get("v"), str(v))
        C.txt(f"{w} team record {lab} detail", FA.get(lab, {}).get("s"), f"{g['team_score']}–{g['opp_score']} {vs_txt(g)}, {fdate(g['date'])}")
    if real:
        g = sorted(real, key=lambda g: -g["team_score"])[0]; gf("Most points scored", g, g["team_score"])
        g = sorted(real, key=lambda g: g["opp_score"])[0]; gf("Fewest points allowed", g, g["opp_score"])
        g = sorted(real, key=lambda g: -g["mg"])[0]; gf("Biggest win", g, fsi(g["mg"]))
        g = sorted(real, key=lambda g: g["mg"])[0]; gf("Heaviest loss", g, fsi(g["mg"]))
        g = sorted(real, key=lambda g: g["team_score"])[0]; gf("Fewest points scored", g, g["team_score"])
        g = sorted(real, key=lambda g: -g["opp_score"])[0]; gf("Most points allowed", g, g["opp_score"])
        bq = None
        for g in real:
            for q in ("q1", "q2", "q3", "q4"):
                v = g["team_" + q]
                if v is not None and (bq is None or v > bq[2]): bq = (g, q, v)
        if bq:
            n = int(bq[1][1]); C.txt(f"{w} best quarter", FA.get("Best quarter", {}).get("v"), str(bq[2]))
            C.txt(f"{w} best quarter detail", FA.get("Best quarter", {}).get("s"), f"{n}{['st', 'nd', 'rd', 'th'][n - 1]} quarter, {vs_txt(bq[0])} {fdate(bq[0]['date'])}")
    C.txt(f"{w} longest win streak", FA.get("Longest win streak", {}).get("v"), str(st["bestW"]) if st["bestW"] else NA)
    C.txt(f"{w} longest losing streak", FA.get("Longest losing streak", {}).get("v"), str(st["bestL"]) if st["bestL"] else NA)
    if "rec" in tab:
        k = tab["rec"]
        top = sorted(ls, key=lambda l: (-l[k], l["g"]["i"], l["idx"]))[:15]
        t = tbl(s, "t-rsg")
        C.eq(f"{w} best games ({k}) count", len([r for r in t["rows"] if not r["empty"]]), len(top))
        for i, (row, l) in enumerate(zip(t["rows"], top)):
            hd = t["head"]
            C.txt(f"{w} best games ({k}) #{i + 1} player", row["cells"][hd.index("Player")], p_of(l)["disp"] + (" MVP" if l["mvp"] else ""))
            C.num(f"{w} best games ({k}) #{i + 1} value", row["cells"][2], l[k], f1 if k == "gs" else f0)
            C.txt(f"{w} best games ({k}) #{i + 1} line", row["cells"][hd.index("Line")], f"{l['pts']} pts · {l['reb']} reb · {l['ast']} ast")
            C.txt(f"{w} best games ({k}) #{i + 1} game", row["cells"][hd.index("Game")], f"{res_text(l['g'])} {fdate(l['g']['date'])} {vs_txt(l['g'])}")
    if "car" in tab:
        k = tab["car"]
        top = sorted(rows, key=lambda r: (-r["a"][k], -r["a"]["gp"]))[:15]
        t = tbl(s, "t-rcar")
        check_rows(f"{w} career leaders ({k})", t, [(r["p"]["rid"], r) for r in top], lambda row: row_rid(row, "player"),
                   {"Player": (lambda r: r["p"]["disp"], S), "GP": TOT("gp"), t["head"][2]: TOT(k), "Per game": ((lambda r: None if k == "gp" else pg(r["a"], k)), f1)}, ordered=True)
    if "sb" in tab:
        k = tab["sb"]
        fn = {"ppg": lambda a: pg(a, "pts"), "rpg": lambda a: pg(a, "reb"), "apg": lambda a: pg(a, "ast"), "spg": lambda a: pg(a, "stl"), "effpg": lambda a: pg(a, "eff"), "ts": lambda a: a["ts"] if a["fga"] >= 40 else None}[k]
        fmt = fp if k == "ts" else f1
        gset = {g["game_id"] for g in G}
        ps = []
        for p in PL.values():
            for x in SEASONS:
                xl = [l for l in p["lines"] if l["g"]["season"] == x and l["gid"] in gset]
                if len(xl) >= 5: ps.append({"p": p, "s": x, "a": agg(xl)})
        top = sorted([x for x in ps if isnum(fn(x["a"]))], key=lambda x: -fn(x["a"]))[:15]
        t = tbl(s, "t-rsb")
        C.eq(f"{w} best seasons ({k}) count", len([r for r in t["rows"] if not r["empty"]]), len(top))
        for i, (row, x) in enumerate(zip(t["rows"], top)):
            C.txt(f"{w} best seasons ({k}) #{i + 1} player", row["cells"][1], x["p"]["disp"])
            C.txt(f"{w} best seasons ({k}) #{i + 1} season", row["cells"][2], season_label(x["s"]))
            C.num(f"{w} best seasons ({k}) #{i + 1} value", row["cells"][3], fn(x["a"]), fmt)
            C.num(f"{w} best seasons ({k}) #{i + 1} games", row["cells"][4], x["a"]["gp"], f0)
    t30 = sorted([l for l in ls if l["pts"] >= 30], key=lambda l: -l["pts"])
    items = lead(s, "30-point games") or []
    C.eq(f"{w} 30-point games count", len(items), len(t30))
    for i, (it, l) in enumerate(zip(items, t30)):
        C.txt(f"{w} 30-point game #{i + 1}", f"{it['name']} | {it['v']} | {it['x']}", f"{p_of(l)['disp']} | {l['pts']} | {vs_txt(l['g'])} {fdate(l['g']['date'])}")
    dd = sorted([r for r in rows if r["a"]["dd"]], key=lambda r: -r["a"]["dd"])
    check_lead_list(f"{w} double-doubles", lead(s, "Double-doubles and triple-doubles"), dd, lambda r: r["a"]["dd"], f0, lambda r: plural(r["a"]["td"], "triple-double") if r["a"]["td"] else "", n=10)

def check_compare(s, F, w):
    G = fgames(F); ids = {g["game_id"] for g in G}
    sel = s.get("cmpSel") or []
    if not sel: C.n += 1; return
    players = [PL[i] for i in sel]
    A = [agg([l for l in p["lines"] if l["gid"] in ids]) for p in players]
    def chigh(i):
        ls = [l for l in players[i]["lines"] if l["gid"] in ids]
        return f"{max(l['pts'] for l in ls)} pts" if ls else NA
    METR = [("Games", lambda a: a["gp"], f0), ("Team record", None, None), ("Minutes per game", lambda a: pg(a, "min"), f1),
            ("Points per game", lambda a: pg(a, "pts"), f1), ("Rebounds per game", lambda a: pg(a, "reb"), f1), ("Offensive rebounds", lambda a: pg(a, "oreb"), f1),
            ("Assists per game", lambda a: pg(a, "ast"), f1), ("Steals per game", lambda a: pg(a, "stl"), f1), ("Blocks per game", lambda a: pg(a, "blk"), f1),
            ("Turnovers per game", lambda a: pg(a, "tov"), f1), ("EFF per game", lambda a: pg(a, "eff"), f1), ("Game Score per game", lambda a: pg(a, "gsum"), f1),
            ("Points per 40", lambda a: p40(a, "pts"), f1), ("Rebounds per 40", lambda a: p40(a, "reb"), f1), ("Assists per 40", lambda a: p40(a, "ast"), f1),
            ("FG%", lambda a: a["fgp"], fp), ("2P%", lambda a: a["p2"], fp), ("3P%", lambda a: a["p3"], fp), ("FT%", lambda a: a["ftp"], fp), ("eFG%", lambda a: a["efg"], fp), ("TS%", lambda a: a["ts"], fp),
            ("Usage", lambda a: a["usg"], fp), ("AST%", lambda a: a["astp"], fp), ("TOV%", lambda a: a["tovp"], fp), ("TRB%", lambda a: a["trbp"], fp), ("STL%", lambda a: a["stlp"], fp), ("BLK%", lambda a: a["blkp"], fp),
            ("MVP awards", lambda a: a["mvp"], f0), ("Double-doubles", lambda a: a["dd"], f0), ("20-point games", lambda a: a["p20"], f0), ("Career high", None, None)]
    t = tbl(s, panel="Side by side")
    C.eq(f"{w} compare columns", t["head"][1:], [p["short"] for p in players])
    rowmap = {r["cells"][0]: r["cells"][1:] for r in t["rows"]}
    for lab, fn, fmt in METR:
        cells = rowmap.get(lab)
        if cells is None: C.n += 1; C.bad(w, f"compare row {lab!r} missing"); continue
        for i, a in enumerate(A):
            if lab == "Team record": C.txt(f"{w} compare {lab} {players[i]['short']}", cells[i], f"{a['w']}–{a['l']}")
            elif lab == "Career high": C.txt(f"{w} compare {lab} {players[i]['short']}", cells[i], chigh(i))
            else: C.num(f"{w} compare {lab} {players[i]['short']}", cells[i], fn(a), fmt)
    pop = [r for r in player_rows(lines_for(G)) if r["a"]["gp"] >= auto_min(G)]
    c = chart(s, "c-crad")
    for i, a in enumerate(A):
        C.series(f"{w} compare radar {players[i]['short']}", c["sets"][i]["data"], [pctile(fn(a), [fn(r["a"]) for r in pop]) for fn in RADAR])
    c = chart(s, "c-csea")
    ss = [x for x in SEASONS if any(any(l["g"]["season"] == x and l["gid"] in ids for l in p["lines"]) for p in players)]
    C.eq(f"{w} compare season labels", c["labels"], [season_label(x) for x in ss])
    for i, p in enumerate(players):
        exp = []
        for x in ss:
            xl = [l for l in p["lines"] if l["g"]["season"] == x and l["gid"] in ids]
            exp.append(jsfix(pg(agg(xl), "pts"), 1) if xl else None)
        C.series(f"{w} compare season ppg {p['short']}", c["sets"][i]["data"], exp)
    if len(players) > 1:
        tog = [g for g in G if box(g) and all(any(l["key"] == p["id"] for l in box(g)["us"]) for p in players)]
        rt = team_agg(tog, F); FA = facts(s, "Playing together")
        C.txt(f"{w} games together", FA.get("Games together", {}).get("v"), str(len(tog)))
        C.txt(f"{w} games together detail", FA.get("Games together", {}).get("s"), f"Team record {rec_txt(rt)} ({fp0(rt['pct'])})" if tog else "Never in the same box score")
        if tog: C.txt(f"{w} margin together", FA.get("Average margin together", {}).get("v"), fs1(rt["mg"]))

def opp_rows(G, F):
    groups = {}
    for g in G:
        if g["decided"]: groups.setdefault(g["okey"], []).append(g)
    out = []
    for k, gs in groups.items():
        r = team_agg(gs, F)
        if r["n"] <= 0: continue
        pr = sorted(player_rows(lines_for(gs)), key=lambda x: -x["a"]["pts"])
        out.append({"k": k, "name": OPP_NAME[k], "gs": gs, "r": r, "last": gs[-1], "tl": pr[0] if pr else None})
    return sorted(out, key=lambda x: (-x["r"]["n"], -x["r"]["w"]))

def check_opponents(s, F, w):
    G = fgames(F); rows = opp_rows(G, F)
    C.txt(f"{w} header", s["headSub"], f"{plural(len(rows), 'team')} faced · {filter_note(F)}")
    def tl(x):
        if not x["tl"]: return NA
        return f"{x['tl']['p']['short']} {f0(x['tl']['a']['pts'])} pts"
    spec = {"Opponent": (lambda x: x["name"], S), "GP": (lambda x: x["r"]["n"], f0), "W": (lambda x: x["r"]["w"], f0), "L": (lambda x: x["r"]["l"], f0),
            "Win%": (lambda x: x["r"]["pct"], fp0), "PF": (lambda x: x["r"]["ppg"], f1), "PA": (lambda x: x["r"]["oppg"], f1), "+/−": (lambda x: x["r"]["mg"], fs1),
            "Last game": (lambda x: f"{res_text(x['last'])} {fdate(x['last']['date'])}", S)}
    t = tbl(s, "t-opps")
    check_rows(f"{w} opponents", t, [(rid(x["k"]), x) for x in rows], lambda row: row_rid(row, "opponent"), spec)
    # top scorer column: value must equal the best total (ties allowed)
    byk = {rid(x["k"]): x for x in rows}
    ci = t["head"].index("Top Pistols scorer vs them")
    for row in t["rows"]:
        x = byk.get(row_rid(row, "opponent"))
        if not x: continue
        C.n += 1
        if not x["tl"]:
            if row["cells"][ci] != NA: C.bad(w, f"top scorer vs {x['name']} shows {row['cells'][ci]!r}")
            continue
        best = x["tl"]["a"]["pts"]
        names = {r["p"]["short"] for r in player_rows(lines_for(x["gs"])) if r["a"]["pts"] == best}
        m = re.fullmatch(r"(.+) ([\d,]+) pts", row["cells"][ci] or "")
        if not m or int(m[2].replace(",", "")) != best or m[1] not in names: C.bad(w, f"top scorer vs {x['name']} shows {row['cells'][ci]!r}, expected {best} pts by one of {names}")
    c = chart(s, "c-opp")
    if c:
        r14 = rows[:14]
        C.eq(f"{w} opponents chart labels", c["labels"], [x["name"] for x in r14])
        C.series(f"{w} opponents chart wins", c["sets"][0]["data"], [x["r"]["w"] for x in r14]); C.series(f"{w} opponents chart losses", c["sets"][1]["data"], [x["r"]["l"] for x in r14])
    opl = player_rows(lines_for(G, us=False))
    key = lambda r: (r["p"]["disp"], ", ".join(r["p"]["teams"].values()), r["a"]["gp"], r["a"]["pts"])
    exp = {}
    for r in opl: exp[key(r)] = r
    spec = {"Player": (lambda r: r["p"]["disp"], S), "Team": (lambda r: ", ".join(r["p"]["teams"].values()), S), "GP": TOT("gp"), "PTS": TOT("pts"), "PTS/G": PG("pts"),
            "REB/G": PG("reb"), "AST/G": PG("ast"), "EFF/G": PG("eff"), "TS%": PCT("ts"), "Best": (lambda r: max(l["pts"] for l in r["ls"]), f0)}
    t = tbl(s, "t-oppl"); hd = t["head"]
    check_rows(f"{w} opponent players", t, list(exp.items()), lambda row: (row["cells"][hd.index("Player")], row["cells"][hd.index("Team")], int(row["cells"][hd.index("GP")].replace(",", "")), int(row["cells"][hd.index("PTS")].replace(",", ""))), spec)

def check_seasons(s, F, w):
    G = fgames(F, ignore_season=True); rows = []
    for x in SEASONS:
        gs = [g for g in G if g["season"] == x]
        if not gs: continue
        r = team_agg(gs, F); pr = player_rows(lines_for(gs))
        thr = max(1, jsround(len(box_games(gs)) * 0.3))
        cand = sorted([p for p in pr if p["a"]["gp"] >= thr], key=lambda p: -pg(p["a"], "pts"))
        rows.append({"s": x, "gs": gs, "r": r, "ts": cand[0] if cand else None, "comps": list(dict.fromkeys(g["ci"]["short"] for g in gs))})
    C.txt(f"{w} header", s["headSub"], f"{plural(len(rows), 'season')} · the season filter doesn't apply on this page")
    spec = {"Season": (lambda x: season_label(x["s"]), S), "GP": (lambda x: x["r"]["n"], f0), "W": (lambda x: x["r"]["w"], f0), "L": (lambda x: x["r"]["l"], f0),
            "Win%": (lambda x: x["r"]["pct"], fp0), "PF": (lambda x: x["r"]["ppg"], f1), "PA": (lambda x: x["r"]["oppg"], f1), "+/−": (lambda x: x["r"]["mg"], fs1),
            "ORtg": (lambda x: x["r"]["ortg"], f1), "DRtg": (lambda x: x["r"]["drtg"], f1), "Pace": (lambda x: x["r"]["pace"], f1),
            "Top scorer": (lambda x: f"{x['ts']['p']['short']} {f1(pg(x['ts']['a'], 'pts'))}" if x["ts"] else NA, S), "Competitions": (lambda x: ", ".join(x["comps"]), S)}
    check_rows(f"{w} seasons table", tbl(s, "t-seasons"), [(x["s"].replace("/", ""), x) for x in rows], lambda row: row_rid(row, "season"), spec)
    c = chart(s, "c-swin")
    ss = [x for x in SEASONS if any(g["season"] == x and g["decided"] for g in G)]
    R = [record([g for g in G if g["season"] == x], F) for x in ss]
    C.eq(f"{w} win-rate chart labels", c["labels"], [season_label(x) for x in ss])
    C.series(f"{w} win-rate chart", c["sets"][0]["data"], [jsfix(r["pct"] * 100, 1) if isnum(r["pct"]) else None for r in R])
    c = chart(s, "c-snet")
    ss = [x for x in SEASONS if any(g["season"] == x and g["real"] for g in G)]
    C.series(f"{w} margin chart", c["sets"][0]["data"], [team_agg([g for g in G if g["season"] == x], F)["mg"] for x in ss])

def check_team(s, F, w):
    G = fgames(F); r = team_agg(G, F); real = [g for g in G if g["real"]]
    C.txt(f"{w} header", s["headSub"], f"{filter_note(F)} · {plural(r['nFull'], 'game')} with complete box scores for both teams")
    K = kpis(s)
    check_kpi(w, K, "Offensive rating", f1(r["ortg"]), "Points per 100 possessions"); check_kpi(w, K, "Defensive rating", f1(r["drtg"]), "Allowed per 100 possessions")
    check_kpi(w, K, "Net rating", fs1(r["net"]), "Per 100 possessions"); check_kpi(w, K, "Pace", f1(r["pace"]), "Possessions per game")
    check_kpi(w, K, "Points per game", f1(r["ppg"]), f"Allowed {f1(r['oppg'])}"); check_kpi(w, K, "Record", rec_txt(r), f"{fp0(r['pct'])} wins")
    vs = next((v for v in s["vs"] if v["panel"] == "Four factors"), None)
    expff = {"Shooting (eFG%)": "efg", "Turnovers (TOV%)": "tov", "Off. rebounding (ORB%)": "orb", "Free throws (FT rate)": "ftr"}
    for lab, a, b in vs["rows"]:
        k = expff[lab]; C.num(f"{w} four factors {lab} Pistols", a, r["fUs"][k], fp); C.num(f"{w} four factors {lab} opponents", b, r["fOp"][k], fp)
    c = chart(s, "c-trat")
    ss = [x for x in SEASONS if any(g["season"] == x for g in G)]
    A = [team_agg([g for g in G if g["season"] == x], F) for x in ss]
    C.series(f"{w} ratings chart ORtg", c["sets"][0]["data"], [a["ortg"] for a in A]); C.series(f"{w} ratings chart DRtg", c["sets"][1]["data"], [a["drtg"] for a in A])
    n = r["nFull"]; U, O = r["U"], r["O"]
    per = lambda k: (lambda T: ratio(T[k], n))
    rows = [("Points", per("pts"), f1), ("FG%", lambda T: ratio(T["fgm"], T["fga"]), fp), ("2P%", lambda T: ratio(T["fg2m"], T["fg2a"]), fp), ("3P%", lambda T: ratio(T["fg3m"], T["fg3a"]), fp),
            ("FT%", lambda T: ratio(T["ftm"], T["fta"]), fp), ("3-point attempts", per("fg3a"), f1), ("Share of shots from 3", lambda T: ratio(T["fg3a"], T["fga"]), fp),
            ("Free throw attempts", per("fta"), f1), ("Rebounds", per("reb"), f1), ("Offensive rebounds", per("oreb"), f1), ("Defensive rebounds", per("dreb"), f1),
            ("Assists", per("ast"), f1), ("Assisted baskets", lambda T: ratio(T["ast"], T["fgm"]), fp), ("Steals", per("stl"), f1), ("Blocks", per("blk"), f1), ("Turnovers", per("tov"), f1), ("EFF", per("eff"), f1)]
    t = tbl(s, "t-tavg"); rm = {row["cells"][0]: row["cells"] for row in t["rows"]}
    for lab, fn, fmt in rows:
        cells = rm.get(lab)
        if not cells: C.n += 1; C.bad(w, f"per-game row {lab!r} missing"); continue
        a, b = fn(U), fn(O)
        C.num(f"{w} per-game {lab} Pistols", cells[1], a, fmt); C.num(f"{w} per-game {lab} opponents", cells[2], b, fmt)
        d = a - b if isnum(a) and isnum(b) else None
        C.txt(f"{w} per-game {lab} difference", cells[3], (fs1(d * 100) + "%" if fmt is fp else fs1(d)) if d is not None else NA)
    qG = [g for g in real if g["team_q1"] is not None and g["team_q4"] is not None]
    qa = lambda side, q: ratio(sum(g[f"{side}_{q}"] or 0 for g in qG), len(qG))
    t = tbl(s, "t-tq"); rm = {row["cells"][0]: row["cells"] for row in t["rows"]}
    for i, q in enumerate(("q1", "q2", "q3", "q4")):
        lab = ["1st", "2nd", "3rd", "4th"][i] + " quarter"; cells = rm[lab]
        wq = sum(g["team_" + q] > g["opp_" + q] for g in qG); lq = sum(g["team_" + q] < g["opp_" + q] for g in qG)
        C.num(f"{w} {lab} scored", cells[1], qa("team", q), f1); C.num(f"{w} {lab} allowed", cells[2], qa("opp", q), f1)
        C.num(f"{w} {lab} +/-", cells[3], qa("team", q) - qa("opp", q) if qG else None, fs1)
        C.txt(f"{w} {lab} won-lost-tied", cells[4], f"{wq}–{lq}–{len(qG) - wq - lq}"); C.num(f"{w} {lab} won %", cells[5], ratio(wq, len(qG)), fp0)
    qc = [g for g in real if g["team_q1"] is not None]
    c = chart(s, "c-tq")
    C.series(f"{w} quarter chart Pistols", c["sets"][0]["data"], [ratio(sum(g["team_" + q] or 0 for g in qc), len(qc)) for q in ("q1", "q2", "q3", "q4")])
    C.series(f"{w} quarter chart opponents", c["sets"][1]["data"], [ratio(sum(g["opp_" + q] or 0 for g in qc), len(qc)) for q in ("q1", "q2", "q3", "q4")])
    half = lambda g: (g["team_q1"] + g["team_q2"]) - (g["opp_q1"] + g["opp_q2"])
    three = lambda g: (g["team_q1"] + g["team_q2"] + g["team_q3"]) - (g["opp_q1"] + g["opp_q2"] + g["opp_q3"])
    FS = facts(s, "Game situations")
    for lab, fn in (("Leading at halftime", lambda g: half(g) > 0), ("Trailing at halftime", lambda g: half(g) < 0), ("Leading after 3 quarters", lambda g: three(g) > 0), ("Trailing after 3 quarters", lambda g: three(g) < 0)):
        C.txt(f"{w} {lab}", FS.get(lab, {}).get("v"), rec_txt(record([g for g in qG if fn(g)], F)))
    cb = sorted([g for g in qG if g["result"] == "W" and half(g) < 0], key=half)
    C.txt(f"{w} biggest comeback", FS.get("Biggest comeback", {}).get("v"), f"{-half(cb[0])} pts" if cb else NA)
    bl = sorted([g for g in qG if g["result"] == "L" and half(g) > 0], key=lambda g: -half(g))
    C.txt(f"{w} biggest lead lost", FS.get("Biggest lead lost", {}).get("v"), f"{half(bl[0])} pts" if bl else NA)
    FC = facts(s, "Close games and blowouts")
    for lab, lo, hi in (("Decided by 1–5", 0, 5), ("Decided by 6–10", 6, 10), ("Decided by 11–20", 11, 20), ("Decided by 21+", 21, 999)):
        C.txt(f"{w} {lab}", FC.get(lab, {}).get("v"), rec_txt(record([g for g in real if lo <= abs(g["mg"]) <= hi], F)))
    ot = [g for g in real if g["team_ot"] is not None or g["opp_ot"] is not None]
    C.txt(f"{w} overtime games", FC.get("Overtime games", {}).get("v"), rec_txt(record(ot, F)))
    c = chart(s, "c-thist")
    bins = [(-999, -21), (-20, -11), (-10, -6), (-5, -1), (1, 5), (6, 10), (11, 20), (21, 999)]
    C.series(f"{w} margin histogram", c["sets"][0]["data"], [sum(lo <= g["mg"] <= hi for g in real) for lo, hi in bins])
    def splits(defs):
        out = []
        for lab, fn in defs:
            r2 = team_agg([g for g in G if fn(g)], F)
            if r2["n"]: out.append((lab, {"lab": lab, "r": r2}))
        return out
    sspec = {"Split": (lambda x: x["lab"], S), "GP": (lambda x: x["r"]["n"], f0), "W": (lambda x: x["r"]["w"], f0), "L": (lambda x: x["r"]["l"], f0),
             "Win%": (lambda x: x["r"]["pct"], fp0), "PF": (lambda x: x["r"]["ppg"], f1), "PA": (lambda x: x["r"]["oppg"], f1), "+/−": (lambda x: x["r"]["mg"], fs1)}
    first = lambda row: row["cells"][0]
    check_rows(f"{w} splits", tbl(s, "t-tsplit"), splits([("Home", lambda g: g["home_away"] == "Home"), ("Away", lambda g: g["home_away"] == "Away"), ("League games", lambda g: g["ci"]["type"] == "League"),
                                                         ("Cup games", lambda g: g["ci"]["type"] == "Cup"), ("Winter leagues", lambda g: g["ci"]["phase"] == "Winter league"), ("Summer leagues", lambda g: g["ci"]["phase"] == "Summer league")]), first, sspec)
    months = [(MON[m], (lambda g, m=m: int(g["date"][5:7]) - 1 == m)) for m in (8, 9, 10, 11, 0, 1, 2, 3, 4, 5, 6, 7)]
    check_rows(f"{w} by month", tbl(s, "t-tmonth"), splits(months), first, sspec)
    dows = [(DOW[d], (lambda g, d=d: (date.fromisoformat(g["date"]).weekday() + 1) % 7 == d)) for d in (1, 2, 3, 4, 5, 6, 0)]
    check_rows(f"{w} by weekday", tbl(s, "t-tdow"), splits(dows), first, sspec)

def check_player(s, F, w, pid):
    p = PL[pid]; G = fgames(F); ids = {g["game_id"] for g in G}
    ls = [l for l in p["lines"] if l["gid"] in ids]; allp = p["lines"]; a = agg(ls)
    seas_all = [x for x in SEASONS if any(l["g"]["season"] == x for l in allp)]
    C.txt(f"{w} header", s["raw"], f"{p['name']} · {fdate(allp[0]['g']['date'], True)} – {fdate(allp[-1]['g']['date'], True)} · {plural(len(seas_all), 'season')}, {plural(len(allp), 'game')} in total")
    C.eq(f"{w} season chips", s["chips"], [season_label(x) for x in seas_all])
    if not ls:
        C.eq(f"{w} empty message shown", s["empty"], True); return
    K = kpis(s)
    check_kpi(w, K, "Games", str(a["gp"]), f"{a['w']}–{a['l']} team record")
    check_kpi(w, K, "Points", f1(pg(a, "pts")), f"{f0(a['pts'])} total")
    check_kpi(w, K, "Rebounds", f1(pg(a, "reb")), f"{f1(pg(a, 'oreb'))} off · {f1(pg(a, 'dreb'))} def")
    check_kpi(w, K, "Assists", f1(pg(a, "ast")), f"{f2(a['ato'])} per turnover")
    check_kpi(w, K, "EFF", f1(pg(a, "eff")), f"Game Score {f1(pg(a, 'gsum'))}")
    check_kpi(w, K, "True shooting", fp(a["ts"]), f"eFG {fp(a['efg'])}")
    check_kpi(w, K, "MVP awards", str(a["mvp"]), f"{a['dd']} double-doubles")
    check_kpi(w, K, "Minutes", f1(pg(a, "min")), f"USG {fp(a['usg'])}")
    p2, p3, pf = a["fg2m"] * 2, a["fg3m"] * 3, a["ftm"]
    if p2 + p3 + pf:
        C.eq(f"{w} points source", s["legend"], [f"2-pointers {f0(p2)} pts · {fp(a['p2'])}", f"3-pointers {f0(p3)} pts · {fp(a['p3'])}", f"Free throws {f0(pf)} pts · {fp(a['ftp'])}"])
    aW = agg([l for l in ls if l["g"]["result"] == "W"]); aL = agg([l for l in ls if l["g"]["result"] == "L"])
    c = chart(s, "c-pwl"); cats = ["pts", "reb", "ast", "stl", "blk", "tov", "eff"]
    C.series(f"{w} wins/losses chart wins", c["sets"][0]["data"], [pg(aW, k) for k in cats]); C.series(f"{w} wins/losses chart losses", c["sets"][1]["data"], [pg(aL, k) for k in cats])
    C.txt(f"{w} wins/losses note", panel_sub(s, "In wins vs losses"), f"Per game in {plural(aW['gp'], 'win')} and {plural(aL['gp'], 'loss', 'losses')} · true shooting {fp(aW['ts'])} in wins, {fp(aL['ts'])} in losses")
    check_player_season_chart(w, s, ls, "pts")
    pop = [r for r in player_rows(lines_for(G)) if r["a"]["gp"] >= auto_min(G)]
    C.series(f"{w} radar", chart(s, "c-pradar")["sets"][0]["data"], [pctile(fn(a), [fn(r["a"]) for r in pop]) for fn in RADAR])
    ss = [x for x in SEASONS if any(l["g"]["season"] == x for l in ls)]
    c = chart(s, "c-pts-ts")
    def ts_pct(ls2):
        v = agg(ls2)["ts"]; return jsfix(v * 100, 1) if isnum(v) else None
    C.series(f"{w} TS chart player", c["sets"][0]["data"], [ts_pct([l for l in ls if l["g"]["season"] == x]) for x in ss])
    C.series(f"{w} TS chart team", c["sets"][1]["data"], [ts_pct(lines_for([g for g in G if g["season"] == x])) for x in ss])
    srows = [(season_label(x), {"lab": season_label(x), "a": agg([l for l in ls if l["g"]["season"] == x])}) for x in ss]
    t = tbl(s, "t-pseasons"); check_rows(f"{w} seasons", t, srows, lambda row: row["cells"][0], split_spec("Season"), ordered=True)
    check_foot(f"{w} seasons", t, {"a": a, "lab": "Total"}, {k: v for k, v in split_spec("Season").items() if k != "Season"}, "All shown")
    defs = [("Home", lambda l: l["g"]["home_away"] == "Home"), ("Away", lambda l: l["g"]["home_away"] == "Away"), ("Wins", lambda l: l["g"]["result"] == "W"), ("Losses", lambda l: l["g"]["result"] == "L"),
            ("League games", lambda l: l["g"]["ci"]["type"] == "League"), ("Cup games", lambda l: l["g"]["ci"]["type"] == "Cup"), ("Winter leagues", lambda l: l["g"]["ci"]["phase"] == "Winter league"),
            ("Summer leagues", lambda l: l["g"]["ci"]["phase"] == "Summer league"), ("Close games (≤5)", lambda l: l["g"]["real"] and abs(l["g"]["mg"]) <= 5), ("Blowouts (15+)", lambda l: l["g"]["real"] and abs(l["g"]["mg"]) >= 15)]
    sp = [(lab, {"lab": lab, "a": agg(x)}) for lab, fn in defs for x in [[l for l in ls if fn(l)]] if x]
    check_rows(f"{w} splits", tbl(s, "t-psplits"), sp, lambda row: row["cells"][0], split_spec("Split"), ordered=True)
    om = {}
    for l in ls: om.setdefault(l["g"]["okey"], []).append(l)
    orows = [(OPP_NAME[k], {"lab": OPP_NAME[k], "a": agg(x), "best": max(l["pts"] for l in x)}) for k, x in om.items()]
    spec = dict(split_spec("Opponent"), Best=(lambda r: r["best"], f0))
    check_rows(f"{w} vs opponents", tbl(s, "t-popp"), orows, lambda row: row["cells"][0], spec)
    FH = facts(s, "Career highs")
    for lab, k in (("Points", "pts"), ("Rebounds", "reb"), ("Assists", "ast"), ("Steals", "stl"), ("Blocks", "blk"), ("3-pointers", "fg3m"), ("EFF", "eff"), ("Minutes", "min")):
        best = ls[0]
        for l in ls:
            if l[k] > best[k]: best = l
        f_ = FH.get(lab, {})
        C.txt(f"{w} career high {lab}", f_.get("v"), str(best[k]))
        C.txt(f"{w} career high {lab} game", f_.get("s"), f"{vs_txt(best['g'])}, {fdate(best['g']['date'])}")
    played = {l["g"]["season"] for l in ls}; mine = {l["gid"] for l in ls}
    pool = [g for g in G if g["season"] in played and g["real"] and box(g) and box(g)["us"]]
    wg = [g for g in pool if g["game_id"] in mine]; wo = [g for g in pool if g["game_id"] not in mine]
    rw, ro = team_agg(wg, F), team_agg(wo, F); FW = facts(s, "With and without")
    C.txt(f"{w} team when he plays", FW.get("Team when he plays", {}).get("v"), rec_txt(rw))
    C.txt(f"{w} team when he plays detail", FW.get("Team when he plays", {}).get("s"), f"{fp0(rw['pct'])} wins · {fs1(rw['mg'])} avg margin · {plural(rw['nReal'], 'game')}")
    C.txt(f"{w} team when he sits", FW.get("Team when he sits", {}).get("v"), rec_txt(ro) if wo else NA)
    C.txt(f"{w} team when he sits detail", FW.get("Team when he sits", {}).get("s"), f"{fp0(ro['pct'])} wins · {fs1(ro['mg'])} avg margin · {plural(ro['nReal'], 'game')}" if wo else "Played every game in these seasons")
    mates = {}
    for l in ls:
        for m in box(l["g"])["us"]:
            if m["key"] == p["id"]: continue
            e = mates.setdefault(m["key"], {"p": PL[m["key"]], "n": 0, "w": 0}); e["n"] += 1; e["w"] += l["g"]["result"] == "W"
    top = sorted(mates.values(), key=lambda e: -e["n"])[:8]
    items = lead(s, "Most games together") or []
    C.eq(f"{w} teammates count", len(items), len(top))
    for i, (it, e) in enumerate(zip(items, top)):
        C.txt(f"{w} teammate #{i + 1}", f"{it['name']} | {it['x']} | {it['v']}", f"{e['p']['disp']} | {e['w']}–{e['n'] - e['w']} | {e['n']}")
    gl = {"Date": (lambda l: fdate(l["g"]["date"]), S), "Opponent": (lambda l: vs_txt(l["g"]), S), "Result": (lambda l: f"{res_text(l['g'])} {score_text(l['g'])}", S),
          "Competition": (lambda l: l["g"]["ci"]["short"], S), "MVP": (lambda l: "MVP" if l["mvp"] else "", S)}
    gl.update(BOX_SPEC)
    check_rows(f"{w} game log", tbl(s, "t-plog"), [(l["g"]["rid"], l) for l in ls], lambda row: row_rid(row, "game"), gl)

SEAM = {"pts", "reb", "ast", "stl", "blk", "eff", "gsum", "min", "fg3m"}
def check_player_season_chart(w, s, ls, m):
    c = chart(s, "c-psea")
    ss = [x for x in SEASONS if any(l["g"]["season"] == x for l in ls)]
    C.eq(f"{w} season chart ({m}) labels", c["labels"], [season_label(x) for x in ss])
    C.series(f"{w} season chart ({m})", c["sets"][0]["data"], [pg(agg([l for l in ls if l["g"]["season"] == x]), m) for x in ss])

def check_opponent(s, F, w, okey):
    G = [g for g in games if g["okey"] == okey and game_ok(g, F, ignore_opp=True)]
    r = team_agg(G, F); real = [g for g in G if g["real"]]
    C.txt(f"{w} title", s["headTitle"], f"{TEAM} vs {OPP_NAME[okey]}")
    active = F["seasons"] or F["comps"] or F["venue"] != "all" or F["result"] != "all"
    C.txt(f"{w} header", s["headSub"], f"{plural(len(G), 'game')} · first {fdate(G[0]['date'], True) if G else NA} · last {fdate(G[-1]['date'], True) if G else NA}" + (" · " + filter_note(F) if active else ""))
    K = kpis(s)
    check_kpi(w, K, "Record", rec_txt(r), f"{fp0(r['pct'])} wins"); check_kpi(w, K, "Points per game", f1(r["ppg"]), f"Allowed {f1(r['oppg'])}")
    check_kpi(w, K, "Average margin", fs1(r["mg"]), plural(r["nReal"], "game") + " on court")
    best = sorted(real, key=lambda g: -g["mg"])[0] if real else None; worst = sorted(real, key=lambda g: g["mg"])[0] if real else None
    check_kpi(w, K, "Best result", fsi(best["mg"]) if best else NA, f"{best['team_score']}–{best['opp_score']}, {fdate(best['date'])}" if best else "")
    check_kpi(w, K, "Worst result", fsi(worst["mg"]) if worst else NA, f"{worst['team_score']}–{worst['opp_score']}, {fdate(worst['date'])}" if worst else "")
    qg = [g for g in real if g["team_q1"] is not None]
    qa = lambda side, q: ratio(sum(g[f"{side}_{q}"] or 0 for g in qg), len(qg))
    check_kpi(w, K, "By quarter", fs1(qa("team", "q1") - qa("opp", "q1")) if qg else NA, f"1st Q avg margin · 4th Q {fs1(qa('team', 'q4') - qa('opp', 'q4'))}" if qg else "")
    c = chart(s, "c-om")
    if real:
        C.series(f"{w} meetings chart", c["sets"][0]["data"] if c else None, [g["mg"] for g in real])
    check_games_table(f"{w} games", tbl(s, "t-og"), list(reversed(G)))
    ours = player_rows(lines_for(G)); theirs = player_rows(lines_for(G, us=False))
    best_ = lambda r: max(l["pts"] for l in r["ls"])
    spec = {"Player": (lambda r: r["p"]["disp"], S), "GP": TOT("gp"), "W–L": (lambda r: f"{r['a']['w']}–{r['a']['l']}", S), "PTS": TOT("pts"), "PTS/G": PG("pts"), "REB/G": PG("reb"),
            "AST/G": PG("ast"), "STL/G": PG("stl"), "EFF/G": PG("eff"), "TS%": PCT("ts"), "Best": (best_, f0)}
    check_rows(f"{w} our players", tbl(s, "t-oours"), [(r["p"]["rid"], r) for r in ours], lambda row: row_rid(row, "player"), spec)
    spec2 = {"Player": (lambda r: r["p"]["disp"], S), "GP": TOT("gp"), "PTS": TOT("pts"), "PTS/G": PG("pts"), "REB/G": PG("reb"), "AST/G": PG("ast"), "EFF/G": PG("eff"), "TS%": PCT("ts"), "Best": (best_, f0)}
    t = tbl(s, "t-otheirs")
    check_rows(f"{w} their players", t, [((r["p"]["disp"], r["a"]["gp"], r["a"]["pts"]), r) for r in theirs],
               lambda row: (row["cells"][0], int(row["cells"][1].replace(",", "")), int(row["cells"][2].replace(",", ""))), spec2)

def check_season(s, F, w, season):
    G = [g for g in games if g["season"] == season and game_ok(g, F, ignore_season=True)]
    r = team_agg(G, F)
    comps = list(dict.fromkeys(g["competition"] for g in G))
    C.txt(f"{w} title", s["headTitle"], season_label(season))
    C.txt(f"{w} header", s["headSub"], f"{plural(len(G), 'game')} · {', '.join(comp(c)['name'] for c in comps)}")
    K = kpis(s)
    check_kpi(w, K, "Record", rec_txt(r), f"{fp0(r['pct'])} wins"); check_kpi(w, K, "Points per game", f1(r["ppg"]), f"Allowed {f1(r['oppg'])}")
    check_kpi(w, K, "Average margin", fs1(r["mg"])); check_kpi(w, K, "Offensive rating", f1(r["ortg"]), "Points per 100 possessions")
    check_kpi(w, K, "Defensive rating", f1(r["drtg"]), "Allowed per 100 possessions"); check_kpi(w, K, "Pace", f1(r["pace"]), "Possessions per game")
    FA = facts(s, None)
    for c in comps:
        rc = team_agg([g for g in G if g["competition"] == c], F); f_ = FA.get(comp(c)["name"], {})
        C.txt(f"{w} {comp(c)['name']} record", f_.get("v"), rec_txt(rc))
        C.txt(f"{w} {comp(c)['name']} detail", f_.get("s"), f"{fp0(rc['pct'])} wins · {f1(rc['ppg'])}–{f1(rc['oppg'])} per game")
    real = [g for g in G if g["real"]]
    C.series(f"{w} margin chart", chart(s, "c-sm")["sets"][0]["data"], [g["mg"] for g in real])
    spec = {"Player": (lambda r: r["p"]["disp"], S), "GP": TOT("gp"), "MIN": PG("min"), "PTS": PG("pts"), "REB": PG("reb"), "AST": PG("ast"), "STL": PG("stl"), "BLK": PG("blk"), "TOV": PG("tov"),
            "EFF": PG("eff"), "FG%": PCT("fgp"), "3P%": PCT("p3"), "TS%": PCT("ts"), "MVP": TOT("mvp"), "W–L": (lambda r: f"{r['a']['w']}–{r['a']['l']}", S)}
    check_rows(f"{w} players", tbl(s, "t-sp"), [(r["p"]["rid"], r) for r in player_rows(lines_for(G))], lambda row: row_rid(row, "player"), spec)
    check_games_table(f"{w} games", tbl(s, "t-sg"), list(reversed(G)))

def check_game(s, w, gid):
    g = G_BY_ID[gid]; b = box(g)
    sb = s.get("scoreboard") or {}
    C.txt(f"{w} meta", sb.get("meta"), f"{g['ci']['name']} {season_label(g['season'])}" + (f" · Matchday {g['round']}" if g["round"] else "") + f" · {fdate(g['date'], True)} · {'Home' if g['home_away'] == 'Home' else 'Away'}")
    C.txt(f"{w} our score", sb.get("us"), str(g["team_score"]) if g["team_score"] is not None else NA)
    C.txt(f"{w} their score", sb.get("them"), str(g["opp_score"]) if g["opp_score"] is not None else NA)
    C.txt(f"{w} opponent", sb.get("oppName"), g["opponent"]); C.txt(f"{w} result", sb.get("res"), res_text(g))
    qs = ["q1", "q2", "q3", "q4"] + (["ot"] if g["team_ot"] is not None or g["opp_ot"] is not None else [])
    if g["team_q1"] is not None and g["opp_q1"] is not None:
        exp = [["Quarter"] + [("OT" if q == "ot" else q[1:]) for q in qs] + ["T"],
               [TEAM] + [S(g["team_" + q]) if g["team_" + q] is not None else NA for q in qs] + [S(g["team_score"])],
               [g["opponent"]] + [S(g["opp_" + q]) if g["opp_" + q] is not None else NA for q in qs] + [S(g["opp_score"])]]
        C.eq(f"{w} quarter table", sb.get("qt"), exp)
        lab = {"q1": "1st", "q2": "2nd", "q3": "3rd", "q4": "4th", "ot": "OT"}
        c = chart(s, "c-gq")
        C.eq(f"{w} quarter chart labels", c["labels"], [lab[q] for q in qs])
        C.series(f"{w} quarter chart Pistols", c["sets"][0]["data"], [g["team_" + q] for q in qs]); C.series(f"{w} quarter chart opponent", c["sets"][1]["data"], [g["opp_" + q] for q in qs])
        c = chart(s, "c-gr")
        for side, i in (("team", 0), ("opp", 1)):
            run, acc = [0], 0
            for q in qs: acc += g[side + "_" + q] or 0; run.append(acc)
            C.series(f"{w} running score {side}", c["sets"][i]["data"], run)
    notes = []
    if g["forfeit"]: notes.append(f"This game was a forfeit ({'won' if g['result'] == 'W' else 'lost'} 20–0 on paper). It counts in the record but has no stats.")
    elif not g["decided"]: notes.append("No result was recorded for this game (bye, cancelled or postponed).")
    elif not b or not b["us"]: notes.append("basketaki has no box score for this game.")
    elif not b["usOK"]: notes.append(f"The basketaki box score for this game is incomplete: {TEAM} players add up to {b['usT']['pts']} of the {g['team_score']} points.")
    if b and b["them"] and not b["themOK"] and g["real"]: notes.append(f"The opponent's box score is incomplete ({b['themT']['pts']} of {g['opp_score']} points).")
    C.eq(f"{w} notes", s["notes"], notes)
    if b and b["both"]:
        vs = next(v for v in s["vs"] if v["panel"] == "Team comparison")
        V = {"FG%": (lambda T: ratio(T["fgm"], T["fga"]), fp0), "2P%": (lambda T: ratio(T["fg2m"], T["fg2a"]), fp0), "3P%": (lambda T: ratio(T["fg3m"], T["fg3a"]), fp0), "FT%": (lambda T: ratio(T["ftm"], T["fta"]), fp0),
             "Rebounds": (lambda T: T["reb"], f0), "Off. reb.": (lambda T: T["oreb"], f0), "Assists": (lambda T: T["ast"], f0), "Steals": (lambda T: T["stl"], f0), "Blocks": (lambda T: T["blk"], f0), "Turnovers": (lambda T: T["tov"], f0), "EFF": (lambda T: T["eff"], f0)}
        C.eq(f"{w} comparison rows", [r[0] for r in vs["rows"]], list(V))
        for lab, x, y in vs["rows"]:
            fn, fmt = V[lab]; C.num(f"{w} comparison {lab} Pistols", x, fn(b["usT"]), fmt); C.num(f"{w} comparison {lab} opponent", y, fn(b["themT"]), fmt)
    for tid, side in (("t-box-us", "us"), ("t-box-them", "them")):
        t = tbl(s, tid)
        if not (b and b[side]):
            C.eq(f"{w} {tid} absent", t is None, True); continue
        spec = dict({"Player": (lambda l: disp(l["player"]) + (" MVP" if l["mvp"] else ""), S)}, **BOX_SPEC)
        exp = [((disp(l["player"]), l["pts"], l["min"], l["reb"]), l) for l in b[side]]
        check_rows(f"{w} {tid}", t, exp, lambda row: (re.sub(r" MVP$", "", row["cells"][0]), int(row["cells"][2]), int(row["cells"][1]), int(row["cells"][3])), spec)
        tot = dict(b[side + "T"]); tot.pop("gs", None)
        check_foot(f"{w} {tid}", t, tot, BOX_SPEC, "Team totals")
    meet = [x for x in games if x["okey"] == g["okey"] and x is not g]
    if meet: check_games_table(f"{w} other meetings", tbl(s, "t-meet"), list(reversed(meet)), ordered=True)

def check_finder(s, w):
    C.eq(f"{w} entries the search could not find", s["missing"], [])
    opp_keys = {k for k in OPP_NAME if any(g["okey"] == k and g["decided"] for g in games)}
    C.eq(f"{w} number of entries", len(s["finder"]), len(PL) + len(opp_keys) + len(SEASONS))
    for e in s["finder"]:
        h = e["href"]
        if h.startswith("#player-"):
            p = PL_BY_RID[h[len("#player-"):]]
            ss = [x for x in SEASONS if any(l["g"]["season"] == x for l in p["lines"])]
            C.txt(f"{w} {p['disp']} name", e["label"], p["disp"])
            C.txt(f"{w} {p['disp']} games and seasons", e["sub"], f"{plural(len(p['lines']), 'game')} · {season_label(ss[0])}" + (f" to {season_label(ss[-1])}" if len(ss) > 1 else ""))
        elif h.startswith("#opponent-"):
            k = next(k for k in opp_keys if rid(k) == h[len("#opponent-"):])
            dec = [g for g in games if g["okey"] == k and g["decided"]]; wn = sum(g["result"] == "W" for g in dec)
            C.txt(f"{w} {OPP_NAME[k]} name", e["label"], OPP_NAME[k])
            C.txt(f"{w} {OPP_NAME[k]} record", e["sub"], f"{wn}–{len(dec) - wn} in {plural(len(dec), 'game')}")
        elif h.startswith("#season-"):
            x = next(x for x in SEASONS if x.replace("/", "") == h[len("#season-"):])
            C.txt(f"{w} season {x} name", e["label"], season_label(x))
            C.txt(f"{w} season {x} games", e["sub"], plural(sum(g["season"] == x for g in games), "game"))
    scraped = json.loads((ROOT / "data" / "stats.json").read_text(encoding="utf-8")).get("scraped_at", "")
    C.txt(f"{w} footer counts", s["footer"][0], f"Data from basketaki.com · {plural(len(games), 'game')} · {plural(len(PL), 'player')}")
    C.txt(f"{w} footer date", s["footer"][1], f"Last updated {fdate(scraped[:10], True)}" if scraped else "")

# --------------------------------------------------------------------------- run
def main():
    files = sorted(OUT.glob("*.json"))
    done = OUT / "_done.json"
    if not done.exists():
        sys.exit("verify/out/_done.json not found: run verify/extract.js in the site first.")
    meta = json.loads(done.read_text(encoding="utf-8"))
    for f in files:
        if f.name == "_done.json": continue
        s = json.loads(f.read_text(encoding="utf-8"))
        F = dict(DEFAULT_F, **(s.get("filters") or {}))
        parts = f.stem.split("__")
        sc, kind = parts[0], parts[1]
        w = f"[{sc}] {f.stem.split('__', 1)[1]}"
        before = C.n
        try:
            if kind == "overview": check_overview(s, F, w)
            elif kind == "games": check_games(s, F, w)
            elif kind == "players": check_players(s, F, w, s["mode"], s["pmin"])
            elif kind == "records": check_records(s, F, w, {k: s[k] for k in ("rec", "car", "sb") if k in s})
            elif kind == "compare": check_compare(s, F, w)
            elif kind == "opponents": check_opponents(s, F, w)
            elif kind == "seasons": check_seasons(s, F, w)
            elif kind == "team": check_team(s, F, w)
            elif kind == "player": check_player(s, F, w, s["pid"])
            elif kind == "psea":
                p = PL[s["pid"]]; ids = {g["game_id"] for g in fgames(F)}
                check_player_season_chart(w, s, [l for l in p["lines"] if l["gid"] in ids], s["metric"])
            elif kind == "opponent": check_opponent(s, F, w, s["okey"])
            elif kind == "season": check_season(s, F, w, s["season"])
            elif kind == "game": check_game(s, w, s["gid"])
            elif kind == "finder": check_finder(s, w)
            else: continue
        except Exception as e:  # a crash in a check is reported as a failure, never hidden
            C.n += 1; C.bad(w, f"check crashed: {type(e).__name__}: {e}")
        C.pages[kind] += 1
        if C.n == before: C.bad(w, "no values were checked on this page")
    lines_out = [
        "Website verification report",
        "===========================",
        f"Snapshots checked: {sum(C.pages.values())} ({', '.join(f'{k}: {v}' for k, v in sorted(C.pages.items()))})",
        f"Displayed values compared with an independent recomputation from data/*.csv: {C.n:,}",
        f"Mismatches: {len(C.fail)}",
        f"Page errors seen while capturing: {len(meta.get('errors', []))}",
        "",
    ]
    lines_out += [f"  {x}" for x in C.fail[:400]]
    if meta.get("errors"): lines_out += ["", "Errors during capture:"] + [f"  {e}" for e in meta["errors"][:50]]
    lines_out.append("")
    lines_out.append("RESULT: " + ("ALL DISPLAYED VALUES MATCH THE DATA" if not C.fail and not meta.get("errors") else "PROBLEMS FOUND (see above)"))
    report = "\n".join(lines_out)
    (HERE / "report.txt").write_text(report + "\n", encoding="utf-8")
    print(report)

if __name__ == "__main__":
    main()
