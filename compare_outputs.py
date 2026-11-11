#!/usr/bin/env python3
"""
Compares the output of the PowerShell scraper (data/) with the Python scraper
(data_py/) cell by cell, and writes validation_report.txt.

Usage:
    python compare_outputs.py [--a data] [--b data_py]
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(path, key_fn):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    keyed, seen = {}, Counter()
    for r in rows:
        k = key_fn(r)
        seen[k] += 1
        keyed[(k, seen[k])] = r        # handles duplicate keys deterministically
    return rows, keyed


def compare(name, a_path, b_path, key_fn, lines):
    a_rows, a = load(a_path, key_fn)
    b_rows, b = load(b_path, key_fn)
    lines.append(f"== {name}")
    lines.append(f"   PowerShell rows: {len(a_rows)}   Python rows: {len(b_rows)}")
    a_cols, b_cols = list(a_rows[0].keys()), list(b_rows[0].keys())
    if a_cols != b_cols:
        lines.append(f"   COLUMN DIFFERENCE: only PowerShell {sorted(set(a_cols) - set(b_cols))}, "
                     f"only Python {sorted(set(b_cols) - set(a_cols))}, same set but different order: {set(a_cols) == set(b_cols)}")
    cols = [c for c in a_cols if c in b_cols]
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    for k in only_a[:20]:
        lines.append(f"   only in PowerShell: {k}")
    for k in only_b[:20]:
        lines.append(f"   only in Python:     {k}")
    diffs = defaultdict(list)
    cells = 0
    for k in sorted(set(a) & set(b)):
        for c in cols:
            cells += 1
            va, vb = (a[k][c] or "").strip(), (b[k][c] or "").strip()
            if va != vb:
                diffs[c].append((k, va, vb))
    n_diff = sum(len(v) for v in diffs.values())
    lines.append(f"   matched rows: {len(set(a) & set(b))}   cells compared: {cells}   cells different: {n_diff}")
    for c, items in diffs.items():
        lines.append(f"   column '{c}': {len(items)} differences, e.g.")
        for k, va, vb in items[:5]:
            lines.append(f"      {k}: PowerShell={va!r}  Python={vb!r}")
    ok = not only_a and not only_b and n_diff == 0 and a_cols == b_cols
    lines.append(f"   RESULT: {'IDENTICAL' if ok else 'DIFFERENCES FOUND'}")
    lines.append("")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=str(HERE / "data"), help="PowerShell output folder")
    ap.add_argument("--b", default=str(HERE / "data_py"), help="Python output folder")
    args = ap.parse_args()
    a, b = Path(args.a), Path(args.b)

    lines = [f"Comparing {a.name}/ (PowerShell scraper) with {b.name}/ (Python scraper)", ""]
    ok_games = compare("games.csv", a / "games.csv", b / "games.csv",
                       lambda r: r["game_id"] or f"{r['date']}|{r['opponent']}", lines)
    ok_players = compare("player_stats.csv", a / "player_stats.csv", b / "player_stats.csv",
                         lambda r: (r["game_id"], r["team_id"], r["player_id"] or r["player"]), lines)
    lines.append("OVERALL: " + ("BOTH SCRAPERS PRODUCED IDENTICAL DATA" if ok_games and ok_players
                                else "DIFFERENCES FOUND - see above"))
    report = "\n".join(lines)
    print(report)
    (HERE / "validation_report.txt").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
