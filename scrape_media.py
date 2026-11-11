#!/usr/bin/env python3
"""
Game photos, reports and videos for the website (writes site/media.js and site/media/).

For every played game of the team it reads two tabs of the game's page on basketaki.com:
  - Gallery (/games/<id>/gallery): the pictures basketaki publishes for each game. We keep
    the line-up photo before tip-off, the winning team's photo and the MVP card, and save
    smaller copies in site/media/<basketaki game number>/: a 480px preview and a 1080px
    picture. The originals (1-2.5 MB each) are not kept. The stats card is skipped because
    the site already shows those stats.
  - Article (/games/<id>/article): the headline, the first paragraph of the game report and
    the game's YouTube video, if there is one.

basketaki adds photos, reports and videos a few days after a game, so a game is checked again
on every run for RECHECK_DAYS days after it was played and then marked final and left alone.
Everything is stored in site/media.js itself, so a run only fetches pages for recent games,
only downloads pictures it doesn't have yet, and only rewrites the file when something changed.

Needs Pillow to resize pictures:  python -m pip install pillow
Usage:  python scrape_media.py [--games data/games.csv] [--recheck-days 21]
"""
import argparse
import csv
import html as htmllib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from scrape_basketaki import BASE, Fetcher, parse_html

HERE = Path(__file__).resolve().parent
PREFIX = "window.PISTOLS_MEDIA = "
UA = {"User-Agent": "Mozilla/5.0 (team stats archive script)"}
RECHECK_DAYS = 21
# the pictures we keep, in display order: (our name, basketaki's file name, caption)
KINDS = [("start", "game_start", "Before the game"), ("winners", "winners", "Winners"), ("mvp", "mvp_card", "MVP card")]
FULL_PX, THUMB_PX = 1080, 480
EXCERPT_CHARS = 320

try:
    from PIL import Image
except ImportError:  # checked in main() so --help still works
    Image = None


def get_bytes(url, delay=0.15):
    """Download a file; None if it doesn't exist (basketaki's gallery lists files that were never made)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404, 410):
            return None
        raise
    time.sleep(delay)
    return data


# ------------------------------------------------------------------ gallery
def gallery_urls(html):
    """{basketaki file name: [candidate URLs]} and the game's number on basketaki's picture server."""
    found, num = {}, None
    for m in re.finditer(r"https://[^\s\"',<>]+/games/(\d+)/([a-z_]+)\.(jpe?g|png)", html, re.I):
        num = num or m[1]
        found.setdefault(m[2].lower(), [])
        if m[0] not in found[m[2].lower()]:
            found[m[2].lower()].append(m[0])
    return num, found


def save_picture(data, folder, name):
    """Save a 1080px picture and a 480px preview as progressive JPEGs; returns (width, height)."""
    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode != "RGB":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A") if "A" in img.getbands() else None)
        img = bg
    folder.mkdir(parents=True, exist_ok=True)
    full = img.copy()
    full.thumbnail((FULL_PX, FULL_PX), Image.LANCZOS)
    full.save(folder / f"{name}.jpg", "JPEG", quality=80, optimize=True, progressive=True)
    thumb = img.copy()
    thumb.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
    thumb.save(folder / f"{name}-t.jpg", "JPEG", quality=76, optimize=True, progressive=True)
    return full.size


def photos_for(gallery_html, site_dir):
    num, found = gallery_urls(gallery_html)
    out = []
    if not num:
        return num, out
    folder = site_dir / "media" / num
    for key, remote, caption in KINDS:
        rel, relt = f"media/{num}/{key}.jpg", f"media/{num}/{key}-t.jpg"
        if (site_dir / rel).exists() and (site_dir / relt).exists():
            with Image.open(site_dir / rel) as im:
                size = im.size
        else:
            size = None
            for url in found.get(remote, []):          # .jpeg and .png are both listed; usually only one exists
                data = get_bytes(url)
                if data:
                    size = save_picture(data, folder, key)
                    break
        if size:
            out.append({"kind": key, "caption": caption, "src": rel, "thumb": relt, "w": size[0], "h": size[1]})
    return num, out


# ------------------------------------------------------------------ article
def clean(s):
    return " ".join(htmllib.unescape(s or "").split())


def excerpt(text, limit=EXCERPT_CHARS):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("; "))
    return cut[:end + 1] if end > limit * 0.55 else cut[:cut.rfind(" ")].rstrip(",;:–-") + "…"


def youtube_info(vid):
    """Title (YouTube's public oEmbed endpoint, no key needed) and whether the video is a vertical Short."""
    info = {}
    try:
        url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}")
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            info["title"] = json.loads(r.read().decode("utf-8")).get("title")
    except Exception:  # noqa: BLE001  (a missing title is not worth failing the run)
        pass
    try:  # youtube.com/shorts/<id> only stays on /shorts/ for Shorts; other videos redirect to /watch
        with urllib.request.urlopen(urllib.request.Request(f"https://www.youtube.com/shorts/{vid}", headers=UA, method="HEAD"), timeout=30) as r:
            info["vertical"] = "/shorts/" in r.geturl()
    except Exception:  # noqa: BLE001
        pass
    return info


def article_for(article_html):
    doc = parse_html(article_html)
    post = doc.find("article", "post--single")
    if not post:
        return {}
    out = {}
    title = post.find("h2", "post__title")
    if title and title.text():
        out["headline"] = clean(title.text())
    body = post.find(cls="post__content")
    if body:
        for p in body.find_all("p"):
            txt = clean(p.text())
            if len(txt) > 40:
                out["excerpt"] = excerpt(txt)
                break
        # the game video is an embedded YouTube player inside the report (a second "video" box
        # on the page is part of basketaki's template and always shows the same default video)
        for fr in body.find_all("iframe"):
            m = re.search(r"youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]{6,})", fr.attrs.get("src", ""))
            if m:
                out["video"] = {"id": m[1], **youtube_info(m[1])}
                break
    return out


# ------------------------------------------------------------------ main
def load(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")[len(PREFIX):].rstrip().rstrip(";"))
    except ValueError:
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--games", default=str(HERE / "data" / "games.csv"))
    ap.add_argument("--site", default=str(HERE / "site"))
    ap.add_argument("--cache", default=str(HERE / "data" / "cache"))
    ap.add_argument("--recheck-days", type=int, default=RECHECK_DAYS)
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--limit", type=int, default=0, help="check at most this many games (for testing)")
    args = ap.parse_args()
    if Image is None:
        sys.exit("Pillow is needed to resize the photos. Install it with:  python -m pip install pillow")

    site = Path(args.site)
    out = site / "media.js"
    old = load(out)
    media = dict(old.get("games", {}))
    fetch = Fetcher(Path(args.cache), False, args.delay)
    today = date.today()
    with open(args.games, encoding="utf-8-sig", newline="") as f:
        games = [g for g in csv.DictReader(f) if g.get("game_id") and g.get("status") == "played"]
    games.sort(key=lambda g: g["date"])
    todo = [g for g in games if not media.get(g["game_id"], {}).get("final")]
    if args.limit:
        todo = todo[-args.limit:]
    print(f"{len(games)} played games, {len(todo)} to check for photos, reports and videos.")

    for i, g in enumerate(todo, 1):
        gid = g["game_id"]
        num, photos = photos_for(fetch.get(f"/games/{gid}/gallery", use_cache=False), site)
        art = article_for(fetch.get(f"/games/{gid}/article", use_cache=False))
        age = (today - date.fromisoformat(g["date"])).days
        e = {"final": age > args.recheck_days}
        if photos:
            e.update(num=num, photos=photos)
        if art:
            e.update(art, article=f"{BASE}/games/{gid}/article")
        media[gid] = e
        what = ", ".join(x for x in (f"{len(photos)} photos" if photos else "", "report" if art.get("headline") else "", "video" if art.get("video") else "") if x)
        print(f"[{i:3}/{len(todo)}] {g['date']} {g['opponent'][:28]:<28} {what or 'nothing yet'}")

    payload = {"source": BASE, "recheck_days": args.recheck_days, "games": dict(sorted(media.items()))}
    if payload == old:
        print("No new photos, reports or videos.")
        return
    out.write_text(PREFIX + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    n = [m for m in media.values() if m.get("photos")]
    print(f"Saved {out}: {len(n)} games with photos ({sum(len(m['photos']) for m in n)} photos), "
          f"{sum(1 for m in media.values() if m.get('video'))} videos, {sum(1 for m in media.values() if m.get('headline'))} reports.")


if __name__ == "__main__":
    main()
