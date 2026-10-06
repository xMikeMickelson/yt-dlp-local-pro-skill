#!/usr/bin/env python3
"""wl sync - track creators: find new public videos, download, transcribe, ingest (idempotent; routine-friendly).

Usage:
  wl sync [--limit 5] [--platform youtube] [--audio-only] [--no-transcribe] [--dry-run] [--since 20260901]
  wl track add <platform> <handle-or-url>      wl track rm <platform> <handle>      wl track list
Config: config/creators.json  {"youtube": ["@example"], "x": ["example"], "tiktok": ["example"], "instagram": ["example"],
        "facebook": ["https://www.facebook.com/example/videos/..."], "other": ["https://example.com/channel"]}
Listing: YouTube = yt-dlp channel listing (player_skip=webpage) -> RSS feed fallback; X = optional X API v2 (X_BEARER_TOKEN, falls through on 402/429)
-> syndication timeline (often 429 from datacenter IPs) -> explicit post URLs; TikTok = yt-dlp profile listing; Instagram = public
web_profile_info (usually login-walled from datacenter IPs -> reported); Facebook/other = explicit URLs or yt-dlp listing.
State lives in library.db table `seen` (platform,item_id): done items are skipped; failures retried up to 3 times.
"""
import argparse, json, os, pathlib, re, subprocess, sys, time, urllib.request
from wl_common import WL_HOME, DATA, log
import wl_dl, wl_library, wl_transcribe

CFG = pathlib.Path(os.environ.get("WL_CREATORS") or WL_HOME / "config" / "creators.json")


def cfg():
    return json.loads(CFG.read_text()) if CFG.exists() else {}


def save(c):
    CFG.write_text(json.dumps(c, indent=1))


def yt_list(handle, limit):
    url = handle if handle.startswith("http") else (f"https://www.youtube.com/channel/{handle}/videos" if handle.startswith("UC")
                                                     else f"https://www.youtube.com/{handle if handle.startswith('@') else '@'+handle}/videos")
    rc, out, err = wl_dl.run([wl_dl.ytdlp(), "--ignore-config", "--config-locations", wl_dl.config_file(), "--flat-playlist",
                              "--playlist-end", str(limit), "--extractor-args", "youtube:player_skip=webpage", "-J", url], 180)
    if rc == 0:
        d = json.loads(out)
        items = [{"id": e["id"], "url": f"https://www.youtube.com/watch?v={e['id']}", "title": e.get("title")} for e in d.get("entries") or [] if e.get("id")]
        if items:
            return items, None
        chan = d.get("channel_id")
    else:
        chan = handle if handle.startswith("UC") else None
    if chan:  # RSS fallback (works from datacenter IPs that are bot-checked on watch pages)
        try:
            x = urllib.request.urlopen(f"https://www.youtube.com/feeds/videos.xml?channel_id={chan}", timeout=30).read().decode()
            ids = re.findall(r"<yt:videoId>([\w-]{11})</yt:videoId>", x)[:limit]
            titles = re.findall(r"<media:title>(.*?)</media:title>", x)
            return [{"id": i, "url": f"https://www.youtube.com/watch?v={i}", "title": t} for i, t in zip(ids, titles)], None
        except Exception as e:
            return [], f"RSS failed: {e}"
    return [], wl_dl.classify(err)[1]


def x_api_list(h, limit, tok):
    """Optional: X API v2 (needs X_BEARER_TOKEN with credits). Returns (items, err)."""
    import requests
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"https://api.x.com/2/users/by/username/{h}", headers=H, timeout=30)
    if r.status_code != 200 or "data" not in r.json():
        return None, f"X API user lookup {r.status_code}"
    uid = r.json()["data"]["id"]
    r = requests.get(f"https://api.x.com/2/users/{uid}/tweets", headers=H, timeout=30, params={
        "max_results": max(5, min(100, limit * 4)), "exclude": "retweets,replies", "expansions": "attachments.media_keys",
        "media.fields": "type,duration_ms", "tweet.fields": "created_at"})
    if r.status_code != 200:
        return None, f"X API {r.status_code}"
    j = r.json(); media = {m["media_key"]: m for m in (j.get("includes") or {}).get("media", [])}
    items = []
    for t in j.get("data") or []:
        keys = (t.get("attachments") or {}).get("media_keys") or []
        if any(media.get(k, {}).get("type") in ("video", "animated_gif") for k in keys):
            items.append({"id": t["id"], "url": f"https://x.com/{h}/status/{t['id']}", "title": t.get("text", "")[:80],
                          "date": t.get("created_at")})
    return items[:limit], None


def x_list(handle, limit):
    """X listing chain: X API (only if X_BEARER_TOKEN set and WL_X_API!=0; 402/429/401 fall through)
    -> public syndication timeline (curl-cffi chrome, then safari). Each candidate is later downloaded with the
    syndication-first downloader, which skips non-video posts."""
    h = handle.lstrip("@").rstrip("/").split("/")[-1]
    errs = []
    tok = os.environ.get("X_BEARER_TOKEN")
    if tok and os.environ.get("WL_X_API", "1") != "0":
        try:
            items, e = x_api_list(h, limit, tok)
            if items is not None:
                return items, None
            errs.append(e)
        except Exception as e:
            errs.append(f"X API error {e}")
    try:
        from curl_cffi import requests as cr
        for imp in ("chrome", "safari"):
            r = cr.get(f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{h}", impersonate=imp, timeout=30)
            ids = list(dict.fromkeys(re.findall(r'"id_str":"(\d{10,})"', r.text)))
            if r.status_code == 200 and ids:
                vids = [i for i in ids if re.search(r'"id_str":"%s".{0,4000}?"type":"(?:video|animated_gif)"' % i, r.text, re.S)]
                use = vids or ids
                return [{"id": i, "url": f"https://x.com/{h}/status/{i}", "title": ""} for i in use[:limit * 3]], None
            errs.append(f"syndication({imp}) {r.status_code}")
    except Exception as e:
        errs.append(str(e))
    return [], ("X listing unavailable: " + "; ".join(errs) +
                ". Fallback: add explicit post URLs (x.com/<user>/status/<id>) to the 'x' list; they download via syndication without the API.")


def ytdlp_list(url, limit, plat):
    rc, out, err = wl_dl.run([wl_dl.ytdlp(), "--ignore-config", "--config-locations", wl_dl.config_file(), "--flat-playlist",
                              "--playlist-end", str(limit), "-J", url], 180)
    if rc != 0:
        return [], wl_dl.classify(err)[1]
    d = json.loads(out)
    return [{"id": str(e.get("id")), "url": e.get("url") or e.get("webpage_url"), "title": e.get("title")} for e in d.get("entries") or [] if e.get("id")], None


def ig_list(handle, limit):
    h = handle.lstrip("@").rstrip("/").split("/")[-1]
    try:
        from curl_cffi import requests as cr
        r = cr.get(f"https://www.instagram.com/api/v1/users/web_profile_info/?username={h}", impersonate="chrome",
                   headers={"x-ig-app-id": "936619743392459"}, timeout=30)
        if r.status_code == 200:
            edges = r.json()["data"]["user"]["edge_owner_to_timeline_media"]["edges"]
            items = [{"id": e["node"]["shortcode"], "url": f"https://www.instagram.com/p/{e['node']['shortcode']}/", "title": ""}
                     for e in edges if e["node"].get("is_video")]
            return items[:limit], None
        return [], f"Instagram profile listing blocked ({r.status_code}, login wall from this IP). Add post URLs to 'instagram' as full URLs instead."
    except Exception as e:
        return [], str(e)


def fb_list(h, limit):
    page = h.rstrip("/").split("facebook.com/")[-1].split("/")[0] if h.startswith("http") else h
    items, err = ytdlp_list(f"https://www.facebook.com/{page}/videos", limit, "facebook")
    if items:
        return items, None
    try:  # best effort: public page HTML usually embeds the latest video id(s)
        from curl_cffi import requests as cr
        ids = []
        for u in (f"https://www.facebook.com/{page}/videos", f"https://www.facebook.com/{page}"):
            t = cr.get(u, impersonate="chrome", timeout=30, headers={"Accept-Language": "en-US"}).text
            ids += re.findall(r'"video_id":"(\d{9,})"', t)
        ids = list(dict.fromkeys(ids))[:limit]
        if ids:
            return [{"id": i, "url": f"https://www.facebook.com/{page}/videos/{i}", "title": ""} for i in ids], None
    except Exception as e:
        err = str(e)
    return [], f"Facebook page listing unavailable without login ({err}); add video URLs explicitly"


def list_creator(plat, h, limit):
    if h.startswith("http") and plat not in ("youtube",) and re.search(r"/(status|video|p|reel|watch|videos/\d)", h):
        return [{"id": re.sub(r"\W+", "_", h)[-60:], "url": h, "title": ""}], None  # explicit post URL
    if plat == "youtube":
        return yt_list(h, limit)
    if plat == "x":
        return x_list(h, limit)
    if plat == "tiktok":
        return ytdlp_list(h if h.startswith("http") else f"https://www.tiktok.com/@{h.lstrip('@')}", limit, plat)
    if plat == "instagram":
        return ig_list(h, limit)
    if plat == "facebook":
        return fb_list(h, limit)
    return ytdlp_list(h, limit, plat)


def sync(a):
    c = wl_library.db(); conf = cfg(); report = []
    for plat, handles in conf.items():
        if plat.startswith("_") or (a.platform and plat != a.platform):
            continue
        for h in handles:
            items, err = list_creator(plat, h, a.limit)
            if err and not items:
                log("sync", f"{plat}:{h} listing failed: {err}"); report.append({"creator": f"{plat}:{h}", "error": err}); continue
            new = 0
            for it in items:
                row = c.execute("SELECT status, tries FROM seen WHERE platform=? AND item_id=?", (plat, it["id"])).fetchone()
                if row and (row["status"] in ("done", "skipped", "downloaded") or row["tries"] >= 3):
                    continue
                if c.execute("SELECT 1 FROM videos WHERE url=? OR id=?", (it["url"], f"{plat}:{it['id']}")).fetchone():
                    continue
                if a.dry_run:
                    report.append({"creator": f"{plat}:{h}", "new": it["url"]}); continue
                status, verr, vid = "failed", None, None
                r = wl_dl.download(it["url"], "audio" if a.audio_only else "video")
                if r.get("ok"):
                    f = r["files"][0]
                    if a.since and r.get("info_json"):
                        ud = json.load(open(r["info_json"])).get("upload_date") or ""
                        if ud and ud < a.since:
                            status = "skipped"
                    if status != "skipped":
                        try:
                            if a.no_transcribe:
                                status = "downloaded"
                            else:
                                ns = argparse.Namespace(out=None, speakers=None, engine="auto", lang=None, no_summary=False,
                                                        no_highlights=False, no_diarize=False, keyterms=None, whisper_model="small")
                                tj = wl_transcribe.transcribe(f, ns)
                                vid = wl_library.ingest(tj, f); status = "done"
                        except SystemExit as e:
                            verr = str(e)
                        except Exception as e:
                            verr = str(e)
                else:
                    verr = f"[{r.get('error_code')}] {r.get('error')}"
                c.execute("""INSERT INTO seen(platform,item_id,url,creator,status,tries,last_error,video_id,updated_at)
                             VALUES(?,?,?,?,?,1,?,?,datetime('now')) ON CONFLICT(platform,item_id) DO UPDATE SET
                             status=excluded.status, tries=seen.tries+1, last_error=excluded.last_error,
                             video_id=coalesce(excluded.video_id, seen.video_id), updated_at=excluded.updated_at""",
                          (plat, it["id"], it["url"], h, status, verr, vid))
                c.commit(); new += 1
                report.append({"creator": f"{plat}:{h}", "url": it["url"], "status": status, "error": verr, "video_id": vid})
            log("sync", f"{plat}:{h}: {len(items)} listed, {new} processed")
    return report


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "track":
        conf = cfg() or {"youtube": [], "x": [], "tiktok": [], "instagram": [], "facebook": [], "other": []}
        if len(sys.argv) >= 5 and sys.argv[2] in ("add", "rm"):
            p, h = sys.argv[3], sys.argv[4]; conf.setdefault(p, [])
            if sys.argv[2] == "add" and h not in conf[p]:
                conf[p].append(h)
            if sys.argv[2] == "rm" and h in conf[p]:
                conf[p].remove(h)
            save(conf)
        print(json.dumps({k: v for k, v in conf.items() if not k.startswith("_")}, indent=1)); return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=5); ap.add_argument("--platform"); ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--no-transcribe", action="store_true"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--since")
    a = ap.parse_args()
    rep = sync(a)
    print(json.dumps(rep, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
