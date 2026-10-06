#!/usr/bin/env python3
"""wl lib - searchable video library (SQLite + FTS5).

Usage:
  wl lib ingest <T.transcript.json> [--media FILE]     # add/update one transcript (idempotent, keyed by platform:id)
  wl lib search "query" [--platform youtube] [--author example] [--since 20260101] [--limit 10] [--json]
  wl lib list [--platform P] [--limit 20]        wl lib show <video_id>        wl lib stats
  wl lib digest [--days 7] [--platform P] [--author A] [--json]   # markdown digest of videos added recently
FTS5 query syntax works: "exact phrase", term1 OR term2, prefix*, NEAR(a b, 5).
Each hit returns a snippet, speaker, timestamp and a deep link (YouTube &t=, Vimeo #t=, others url + @m:ss).
DB: data/library.db (override with WL_DB).
"""
import argparse, json, os, pathlib, sqlite3, sys, time
from wl_common import DATA, hms, load_transcript, log

DB = pathlib.Path(os.environ.get("WL_DB") or DATA / "library.db")
SCHEMA = """
CREATE TABLE IF NOT EXISTS videos(
  id TEXT PRIMARY KEY, platform TEXT, source_id TEXT, url TEXT, title TEXT, author TEXT, handle TEXT,
  upload_date TEXT, duration REAL, media_path TEXT, transcript_path TEXT, engine TEXT, language TEXT,
  chapters TEXT, highlights TEXT, added_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS segments(
  rowid INTEGER PRIMARY KEY, video_id TEXT, idx INTEGER, speaker TEXT, start_ms INTEGER, end_ms INTEGER, text TEXT);
CREATE INDEX IF NOT EXISTS seg_vid ON segments(video_id);
CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(text, content='segments', content_rowid='rowid', tokenize='porter unicode61');
CREATE TRIGGER IF NOT EXISTS seg_ai AFTER INSERT ON segments BEGIN INSERT INTO segments_fts(rowid, text) VALUES (new.rowid, new.text); END;
CREATE TRIGGER IF NOT EXISTS seg_ad AFTER DELETE ON segments BEGIN INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.rowid, old.text); END;
CREATE VIRTUAL TABLE IF NOT EXISTS videos_fts USING fts5(id UNINDEXED, title, author, chapters, tokenize='porter unicode61');
CREATE TABLE IF NOT EXISTS seen(platform TEXT, item_id TEXT, url TEXT, creator TEXT, status TEXT, tries INTEGER DEFAULT 0,
  last_error TEXT, video_id TEXT, updated_at TEXT, PRIMARY KEY(platform, item_id));
"""
PLAT = {"Youtube": "youtube", "Twitter": "x", "TikTok": "tiktok", "Instagram": "instagram", "Facebook": "facebook",
        "Reddit": "reddit", "Vimeo": "vimeo"}


def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.executescript(SCHEMA); return c


def deeplink(url, platform, ms):
    s = int(ms / 1000)
    if not url:
        return f"@{hms(ms)}"
    if platform == "youtube":
        return url + ("&" if "?" in url else "?") + f"t={s}s"
    if platform == "vimeo":
        return f"{url}#t={s}s"
    return f"{url} @{hms(ms)}"


def chunks(t, target_ms=20000):
    """Utterances split/merged into ~20s searchable segments (keeps speaker turns)."""
    out = []
    words = t.get("words") or []
    for u in t.get("utterances") or []:
        if u["end"] - u["start"] <= target_ms * 1.5 or not words:
            out.append(u); continue
        uw = [w for w in words if u["start"] <= w["start"] <= u["end"]]
        cur = []
        for w in uw:
            cur.append(w)
            if w["end"] - cur[0]["start"] >= target_ms and w["text"][-1:] in ".?!,":
                out.append({"speaker": u["speaker"], "start": cur[0]["start"], "end": w["end"], "text": " ".join(x["text"] for x in cur)}); cur = []
        if cur:
            out.append({"speaker": u["speaker"], "start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(x["text"] for x in cur)})
    return out


def ingest(tpath, media=None):
    t = load_transcript(tpath); info = t.get("info") or {}
    plat = PLAT.get(info.get("extractor_key") or "", None) or (info.get("extractor_key") or "local").lower()
    sid = info.get("id") or pathlib.Path(tpath).stem
    vid = f"{plat}:{sid}"
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    c = db()
    old = c.execute("SELECT added_at FROM videos WHERE id=?", (vid,)).fetchone()
    c.execute("DELETE FROM segments WHERE video_id=?", (vid,)); c.execute("DELETE FROM videos_fts WHERE id=?", (vid,))
    row = dict(id=vid, platform=plat, source_id=sid, url=info.get("webpage_url") or t.get("source"), title=t.get("title"),
               author=info.get("uploader") or info.get("channel"), handle=info.get("uploader_id"),
               upload_date=info.get("upload_date"), duration=t.get("duration") or info.get("duration"),
               media_path=media or t.get("media"), transcript_path=str(pathlib.Path(tpath).resolve()), engine=t.get("engine"),
               language=t.get("language"), chapters=json.dumps(t.get("chapters") or []), highlights=json.dumps(t.get("highlights") or []),
               added_at=old["added_at"] if old else now, updated_at=now)
    c.execute(f"INSERT OR REPLACE INTO videos({','.join(row)}) VALUES({','.join('?'*len(row))})", list(row.values()))
    for i, s in enumerate(chunks(t)):
        c.execute("INSERT INTO segments(video_id, idx, speaker, start_ms, end_ms, text) VALUES(?,?,?,?,?,?)",
                  (vid, i, s.get("speaker"), s["start"], s["end"], s["text"]))
    c.execute("INSERT INTO videos_fts(id, title, author, chapters) VALUES(?,?,?,?)",
              (vid, row["title"] or "", f"{row['author'] or ''} {row['handle'] or ''}",
               " ".join(f"{x.get('headline','')} {x.get('summary','')}" for x in t.get("chapters") or [])))
    c.commit()
    n = c.execute("SELECT count(*) FROM segments WHERE video_id=?", (vid,)).fetchone()[0]
    log("lib", f"ingested {vid} ({n} segments)")
    return vid


def search(q, platform=None, author=None, since=None, limit=10):
    c = db()
    sql = """SELECT v.id, v.platform, v.title, v.author, v.handle, v.url, v.upload_date, s.speaker, s.start_ms, s.end_ms,
             snippet(segments_fts, 0, '**', '**', ' … ', 18) AS snip, bm25(segments_fts) AS score
             FROM segments_fts JOIN segments s ON s.rowid = segments_fts.rowid JOIN videos v ON v.id = s.video_id
             WHERE segments_fts MATCH ?"""
    args = [q]
    if platform:
        sql += " AND v.platform=?"; args.append(platform)
    if author:
        sql += " AND (v.author LIKE ? OR v.handle LIKE ?)"; args += [f"%{author}%"] * 2
    if since:
        sql += " AND v.upload_date >= ?"; args.append(since)
    sql += " ORDER BY score LIMIT ?"; args.append(limit)
    try:
        rows = c.execute(sql, args).fetchall()
    except sqlite3.OperationalError:  # bad FTS syntax -> quote it as a phrase
        args[0] = '"' + q.replace('"', '') + '"'; rows = c.execute(sql, args).fetchall()
    hits = [dict(r, link=deeplink(r["url"], r["platform"], r["start_ms"]), at=hms(r["start_ms"])) for r in rows]
    # title/chapter matches too
    try:
        vrows = c.execute("SELECT v.id, v.title, v.url, v.platform FROM videos_fts f JOIN videos v ON v.id=f.id WHERE videos_fts MATCH ? LIMIT 5", [args[0]]).fetchall()
    except sqlite3.OperationalError:
        vrows = []
    return hits, [dict(r) for r in vrows]


def digest(days=7, platform=None, author=None):
    c = db(); since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - days * 86400))
    q = "SELECT * FROM videos WHERE added_at >= ?"; args = [since]
    if platform:
        q += " AND platform=?"; args.append(platform)
    if author:
        q += " AND (author LIKE ? OR handle LIKE ?)"; args += [f"%{author}%"] * 2
    out = []
    for v in c.execute(q + " ORDER BY platform, upload_date DESC", args).fetchall():
        d = dict(v); ch = json.loads(d["chapters"] or "[]"); hl = json.loads(d["highlights"] or "[]")
        d["chapters"] = [{"at": hms(x.get("start", 0)), "headline": x.get("headline"), "link": deeplink(d["url"], d["platform"], x.get("start", 0))} for x in ch]
        d["highlights"] = [h.get("text") for h in sorted(hl, key=lambda h: -(h.get("rank") or 0))[:5]]
        d["speakers"] = c.execute("SELECT count(DISTINCT speaker) FROM segments WHERE video_id=?", (d["id"],)).fetchone()[0]
        out.append(d)
    return out


def digest_md(items, days):
    lines = [f"# Watch Later digest (last {days} days, {len(items)} videos)", ""]
    for d in items:
        lines.append(f"## {d['title'] or d['id']}")
        lines.append(f"{d['platform']} | {d['author'] or d['handle'] or '?'} | {d['upload_date'] or ''} | {hms((d['duration'] or 0) * 1000)} | "
                     f"{d['speakers']} speaker(s) | {d['url']}")
        for x in d["chapters"][:8]:
            lines.append(f"- [{x['at']}] {x['headline']} - {x['link']}")
        if d["highlights"]:
            lines.append("Key phrases: " + ", ".join(d["highlights"]))
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["ingest", "search", "list", "show", "stats", "digest"]); ap.add_argument("arg", nargs="?")
    ap.add_argument("--media"); ap.add_argument("--platform"); ap.add_argument("--author"); ap.add_argument("--since")
    ap.add_argument("--limit", type=int, default=10); ap.add_argument("--json", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()
    if a.cmd == "ingest":
        print(ingest(a.arg, a.media))
    elif a.cmd == "search":
        hits, vids = search(a.arg, a.platform, a.author, a.since, a.limit)
        if a.json:
            print(json.dumps({"hits": hits, "videos": vids}, indent=1, ensure_ascii=False)); return
        if not hits and not vids:
            print("no matches"); return
        for h in hits:
            print(f"- [{h['at']}] {h['title']} ({h['platform']}, {h['author'] or h['handle'] or '?'}, {h['upload_date'] or ''}) "
                  f"Speaker {h['speaker']}: {h['snip']}\n  {h['link']}")
        if vids:
            print("Title/chapter matches: " + "; ".join(f"{v['title']} <{v['url']}>" for v in vids))
    elif a.cmd == "list":
        c = db(); q = "SELECT id, platform, title, author, upload_date, duration, engine FROM videos"
        rows = c.execute(q + (" WHERE platform=?" if a.platform else "") + " ORDER BY updated_at DESC LIMIT ?",
                         ([a.platform] if a.platform else []) + [a.limit]).fetchall()
        for r in rows:
            print(f"{r['id']} | {r['upload_date'] or ''} | {r['author'] or ''} | {r['title']} | {hms((r['duration'] or 0)*1000)} | {r['engine']}")
    elif a.cmd == "show":
        c = db(); v = c.execute("SELECT * FROM videos WHERE id=?", (a.arg,)).fetchone()
        if not v:
            raise SystemExit("not found")
        d = dict(v); d["chapters"] = json.loads(d["chapters"] or "[]"); d["highlights"] = [h["text"] for h in json.loads(d["highlights"] or "[]")]
        d["segments"] = c.execute("SELECT count(*) FROM segments WHERE video_id=?", (a.arg,)).fetchone()[0]
        print(json.dumps(d, indent=1, ensure_ascii=False))
    elif a.cmd == "digest":
        items = digest(a.days, a.platform, a.author)
        print(json.dumps(items, indent=1, ensure_ascii=False) if a.json else digest_md(items, a.days))
    elif a.cmd == "stats":
        c = db()
        print(json.dumps({"videos": c.execute("SELECT count(*) FROM videos").fetchone()[0],
                          "segments": c.execute("SELECT count(*) FROM segments").fetchone()[0],
                          "by_platform": dict(c.execute("SELECT platform, count(*) FROM videos GROUP BY platform").fetchall()),
                          "seen": dict(c.execute("SELECT status, count(*) FROM seen GROUP BY status").fetchall()),
                          "db": str(DB)}, indent=1))


if __name__ == "__main__":
    main()
