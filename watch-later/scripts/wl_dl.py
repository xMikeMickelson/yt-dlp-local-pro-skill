#!/usr/bin/env python3
"""wl dl - bulletproof public-video downloader (yt-dlp + EJS/deno + PO tokens + impersonation + fallbacks).

Usage:
  wl dl <url> [--audio] [--subs-only] [--meta] [--max-height 1080] [--section 0-60] [--out DIR] [--cookies FILE] [--json] [-- extra yt-dlp args]
  wl dl --doctor
Modes: default = mp4 video (<=1080p) + info.json + subtitles; --audio = mp3; --subs-only = captions only (no media);
       --meta = print metadata JSON only.
Per-platform fallback chain (stops at first success): YouTube default clients+PO token -> mweb -> tv,web_safari ->
  android_vr -> web_embedded -> curl-cffi impersonation -> captions-only. X: syndication -> graphql -> impersonate.
  TikTok/Instagram/Facebook/Reddit/Vimeo: plain -> impersonate chrome -> impersonate safari -> page og:video scrape.
No cookies by default. --cookies FILE (Netscape cookies.txt that the USER provides for THEIR account) is opt-in.
Public content only; DRM content is never decrypted.
"""
import argparse, json, os, re, shutil, subprocess, sys, time, glob, pathlib, urllib.parse, socket

WL_HOME = pathlib.Path(os.environ.get("WL_HOME") or pathlib.Path(__file__).resolve().parent.parent)
VENV_BIN = WL_HOME / "venv" / "bin"
BIN = WL_HOME / "bin"
os.environ["PATH"] = f"{BIN}:{VENV_BIN}:" + os.environ.get("PATH", "")
DATA = pathlib.Path(os.environ.get("WL_DATA") or WL_HOME / "data")
CONF = WL_HOME / "config" / "yt-dlp.conf"
POT_DIR = WL_HOME / "pot" / "server"


def config_file():
    """yt-dlp config path. A literal WL_HOME token follows this install."""
    if not CONF.exists():
        return os.devnull
    text = CONF.read_text()
    if "WL_HOME" not in text:
        return str(CONF)
    dest = WL_HOME / "tmp" / "yt-dlp.conf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text.replace("WL_HOME", str(WL_HOME)))
    return str(dest)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"


def log(*a):
    print("[wl dl]", *a, file=sys.stderr, flush=True)


def platform_of(url):
    h = urllib.parse.urlparse(url).netloc.lower().split(":")[0]
    for key, pats in [("youtube", ["youtube.com", "youtu.be", "youtube-nocookie.com"]),
                      ("x", ["twitter.com", "x.com", "t.co"]), ("tiktok", ["tiktok.com"]),
                      ("instagram", ["instagram.com"]), ("facebook", ["facebook.com", "fb.watch", "fb.com"]),
                      ("reddit", ["reddit.com", "redd.it"]), ("vimeo", ["vimeo.com"])]:
        if any(h == p or h.endswith("." + p) for p in pats):
            return key
    return "other"


def normalize_url(url):
    """Canonicalize share links that commonly break extractors."""
    u = url.strip()
    u = re.sub(r"[?&](si|igsh|igshid|utm_[a-z]+|feature|s|t)=[^&#]*", "", u) if "youtu" not in u else re.sub(r"[?&]si=[^&#]*", "", u)
    u = u.replace("://mobile.twitter.com", "://x.com").replace("://twitter.com", "://x.com").replace("://m.facebook.com", "://www.facebook.com")
    u = re.sub(r"instagram\.com/reels/", "instagram.com/reel/", u)
    u = u.replace("://old.reddit.com", "://www.reddit.com")
    if "youtube.com/shorts/" in u:
        u = re.sub(r"youtube\.com/shorts/([\w-]{11}).*", r"youtube.com/watch?v=\1", u)
    return u


def ytdlp():
    p = VENV_BIN / "yt-dlp"
    return str(p) if p.exists() else (shutil.which("yt-dlp") or "yt-dlp")


def pot_alive(port=4416):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def ensure_pot_server():
    """Start the bgutil PO-token HTTP server (localhost only) if installed and not running."""
    if pot_alive():
        return True
    deno = BIN / "deno"
    if not (POT_DIR / "src" / "main.ts").exists() or not deno.exists():
        return False
    logf = open(WL_HOME / "logs" / "pot-server.log", "ab")
    subprocess.Popen([str(deno), "run", "--allow-env", "--allow-net", "--allow-ffi=.", "--allow-read=.", "../src/main.ts"],
                     cwd=str(POT_DIR / "node_modules"), stdout=logf, stderr=logf, start_new_session=True)
    for _ in range(30):
        time.sleep(0.5)
        if pot_alive():
            log("started bgutil PO-token server on 127.0.0.1:4416")
            return True
    log("PO-token server did not start (continuing without it)")
    return False


ERRORS = [
    (r"Sign in to confirm you.re not a bot|confirm you're not a bot", "YOUTUBE_BOT_CHECK",
     "YouTube flagged this IP (datacenter IPs are often blocked). Retried alternate clients + PO token. Options: retry later, use captions-only, run from a residential IP/proxy (--proxy), or pass a user-provided cookies file."),
    (r"HTTP Error 429|Too Many Requests", "RATE_LIMITED", "Rate limited (429). Wait a few minutes; lower request rate."),
    (r"Sign in to confirm your age|age-restricted|inappropriate for some users", "AGE_RESTRICTED", "Age-restricted: needs a logged-in cookies file from the user."),
    (r"Private video|This video is private|is private", "PRIVATE", "Private content - not downloadable (public content only)."),
    (r"members-only|Join this channel", "MEMBERS_ONLY", "Members-only content - not supported."),
    (r"DRM|drm protected|This video is DRM", "DRM", "DRM-protected - will not be downloaded."),
    (r"not available in your country|geo.?restrict", "GEO_BLOCKED", "Geo-blocked from this server's region."),
    (r"empty media response|login required|Requested content is not available, rate-limit reached or login required|Restricted Video|log in|logged-in", "LOGIN_WALL",
     "Platform login wall for this IP. Public post but the site demands login from datacenter IPs. Fallbacks tried; a user-provided cookies file would be required."),
    (r"status code 10204|10204", "TIKTOK_IP_BLOCK", "TikTok blocked this IP (10204). Try later or another network."),
    (r"Unsupported URL", "UNSUPPORTED_URL", "Unsupported URL - use the canonical post/video URL (not a profile/share/search page)."),
    (r"No video could be found in this tweet|No video", "NO_VIDEO", "This post has no video."),
    (r"HTTP Error 403|Forbidden", "HTTP_403", "403 Forbidden (often missing PO token / IP block)."),
    (r"Video unavailable|is unavailable|has been removed|does not exist|HTTP Error 404", "UNAVAILABLE", "Video unavailable/removed."),
    (r"Requested format is not available|Only images are available", "NO_FORMATS", "No downloadable formats (YouTube SABR/PO-token enforcement or JS challenge failed)."),
]


def classify(text):
    text = text or ""
    errs = "\n".join(l for l in text.splitlines() if "ERROR" in l)
    for chunk in (errs, text):  # prefer the ERROR line over earlier warnings
        for pat, code, msg in ERRORS:
            if chunk and re.search(pat, chunk, re.I):
                return code, msg
    return "UNKNOWN", (text or "").strip().splitlines()[-1][:300] if (text or "").strip() else "unknown error"


def strategies(plat, mode):
    """Ordered list of (name, extra_args). Impersonation uses curl-cffi."""
    imp = lambda t: ["--impersonate", t]
    if plat == "youtube":
        # player_skip=webpage avoids the watch-page fetch that datacenter IPs get 429/bot-checked on (tested 2026-10-05)
        s = [("mweb+pot,skip-webpage", ["--extractor-args", "youtube:player_client=mweb;player_skip=webpage"]),
             ("web_embedded,skip-webpage", ["--extractor-args", "youtube:player_client=web_embedded;player_skip=webpage"]),
             ("default+pot", []),
             ("tv,web_safari", ["--extractor-args", "youtube:player_client=tv,web_safari"]),
             ("android_vr", ["--extractor-args", "youtube:player_client=android_vr"]),
             ("mweb+impersonate", ["--extractor-args", "youtube:player_client=mweb;player_skip=webpage"] + imp("chrome"))]
    elif plat == "x":
        s = [("syndication", ["--extractor-args", "twitter:api=syndication"]),
             ("graphql", ["--extractor-args", "twitter:api=graphql"]),
             ("syndication+impersonate", ["--extractor-args", "twitter:api=syndication"] + imp("chrome")),
             ("legacy", ["--extractor-args", "twitter:api=legacy"])]
    elif plat == "tiktok":
        s = [("default", []), ("impersonate-chrome", imp("chrome")), ("impersonate-safari", imp("safari")),
             ("app-api", ["--extractor-args", "tiktok:app_info=7355728856979392262"])]
    elif plat == "vimeo":
        s = [("default", []), ("player-embed", ["--referer", "https://vimeo.com/", "@VIMEO_PLAYER"]),
             ("player-embed+impersonate", ["--referer", "https://vimeo.com/", "@VIMEO_PLAYER"] + imp("chrome"))]
    elif plat == "reddit":
        s = [("default", []), ("impersonate-chrome", imp("chrome")), ("v.redd.it-direct", ["@VREDDIT"])]
    elif plat in ("instagram", "facebook", "other"):
        s = [("default", []), ("impersonate-chrome", imp("chrome")), ("impersonate-safari", imp("safari"))]
    else:
        s = [("default", [])]
    return s


def base_args(mode, outdir, max_h, cookies, plat):
    a = [ytdlp(), "--ignore-config", "--config-locations", config_file(),
         "--no-playlist", "--retries", "5", "--extractor-retries", "2", "--fragment-retries", "10",
         "--retry-sleep", "http:exp=1:20", "--sleep-requests", "0.5", "--socket-timeout", "30",
         "--no-warnings", "--no-progress", "--restrict-filenames", "--windows-filenames",
         "-P", str(outdir), "-o", "%(title).60B__%(id)s.%(ext)s", "--write-info-json",
         "--print", "after_move:filepath"]
    if cookies:
        a += ["--cookies", cookies]
    else:
        a += ["--no-cookies"]
    subs = ["--write-subs", "--write-auto-subs", "--sub-langs", "en,en-orig,en-US,en-GB", "--sleep-subtitles", "1", "--convert-subs", "srt"]
    if mode == "audio":
        a += ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "4"]
    elif mode == "subs":
        a = [x for x in a if x != "after_move:filepath"]
        a[a.index("--print")] = "--no-simulate"
        a += ["--skip-download", "--print", "id"] + subs
    elif mode == "meta":
        a = [x for x in a if x not in ("--print", "after_move:filepath", "--write-info-json")]
        a += ["-J", "--skip-download"]
    else:
        # -S res:H = best quality not above H (falls back to the smallest above H); prefer h264/aac for mp4 compatibility
        a += ["-f", "bv*+ba/b", "-S", f"res:{max_h},vcodec:h264,acodec:aac", "--merge-output-format", "mp4"]
    return a


def run(cmd, timeout=900):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def vreddit(url):
    """Find the v.redd.it id on a public Reddit post page (Reddit's JSON API is 403 from many datacenter IPs)."""
    m = re.search(r"v\.redd\.it/(\w+)", url)
    if m:
        return f"https://v.redd.it/{m.group(1)}"
    try:
        from curl_cffi import requests as cr
        for u in (url, url.replace("www.reddit.com", "old.reddit.com")):
            t = cr.get(u, impersonate="chrome", timeout=30).text
            m = re.search(r"v\.redd\.it/(\w{8,})", t)
            if m:
                return f"https://v.redd.it/{m.group(1)}"
    except Exception:
        pass
    return None


def og_scrape(url, outdir, mode):
    """Last-resort for IG/FB/Reddit/other: fetch the public page with curl-cffi (Chrome TLS) and grab a direct MP4."""
    try:
        from curl_cffi import requests as cr
    except Exception:
        return None
    cands = []
    try:
        targets = [url]
        m = re.search(r"instagram\.com/(?:p|reel|tv)/([\w-]+)", url)
        if m:
            targets = [f"https://www.instagram.com/p/{m.group(1)}/embed/captioned/", url]
        if "reddit.com" in url:
            targets = [url.split("?")[0].rstrip("/") + ".json"] + targets
        for t in targets:
            r = cr.get(t, impersonate="chrome", timeout=30, headers={"Accept-Language": "en-US,en;q=0.9"})
            if r.status_code != 200:
                continue
            html = r.text
            keys = ["browser_native_hd_url", "playable_url_quality_hd", "hd_src", "browser_native_sd_url", "playable_url",
                    "sd_src", "video_url", "fallback_url", "contentUrl"]
            for k in keys:  # tolerate JSON embedded as escaped strings (\\"key\\":\\"https:\\/\\/...\\")
                for v in re.findall(r'\\*"' + k + r'\\*"\s*:\s*\\*"(https?:[^"]+?)\\*"', html):
                    v = re.sub(r"\\+u0026", "&", v); v = re.sub(r"\\+/", "/", v).replace("\\", "").replace("&amp;", "&")
                    cands.append(v)
            for v in re.findall(r'<meta[^>]+property="og:video(?::secure_url)?"[^>]+content="([^"]+)"', html):
                cands.append(v.replace("&amp;", "&"))
            if cands:
                break
    except Exception as e:
        log("og scrape error:", e)
    if not cands:
        return None
    vid = cands[0]
    stem = re.sub(r"[^\w.-]+", "_", urllib.parse.urlparse(url).path.strip("/"))[-60:] or "video"
    pathlib.Path(outdir).mkdir(parents=True, exist_ok=True)
    out = pathlib.Path(outdir) / f"{stem}.mp4"
    try:
        r = cr.get(vid, impersonate="chrome", timeout=120)
        if r.status_code == 200 and len(r.content) > 10000:
            out.write_bytes(r.content)
            if subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                              capture_output=True).returncode != 0:
                out.unlink(missing_ok=True)
                return None
            if "v.redd.it" in vid:  # reddit DASH: video-only; try to mux audio
                base = vid.split("DASH_")[0]
                for an in ("DASH_AUDIO_128.mp4", "DASH_audio.mp4", "DASH_AUDIO_64.mp4"):
                    ra = cr.get(base + an, impersonate="chrome", timeout=60)
                    if ra.status_code == 200 and len(ra.content) > 1000:
                        ap = out.with_suffix(".audio.mp4"); ap.write_bytes(ra.content)
                        mx = out.with_suffix(".mux.mp4")
                        if subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out), "-i", str(ap), "-c", "copy", str(mx)]).returncode == 0:
                            mx.replace(out)
                        ap.unlink(missing_ok=True)
                        break
            if mode == "audio":
                mp3 = out.with_suffix(".mp3")
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out), "-vn", "-q:a", "4", str(mp3)])
                out.unlink(missing_ok=True)
                out = mp3
            (out.with_suffix(".info.json")).write_text(json.dumps({"webpage_url": url, "id": stem, "title": stem,
                                                                   "extractor_key": "og_scrape", "direct_url": vid}))
            return str(out)
    except Exception as e:
        log("og download error:", e)
    return None


def download(url, mode="video", outdir=None, max_h=1080, cookies=None, extra=None, quiet=False):
    """Returns dict: ok, files, strategy, platform, error_code, error, attempts."""
    url = normalize_url(url)
    plat = platform_of(url)
    outdir = pathlib.Path(outdir or DATA / "downloads" / plat).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    if plat == "youtube":
        ensure_pot_server()
    attempts, last_err = [], ""
    for name, sargs in strategies(plat, mode):
        u = url
        if "@VIMEO_PLAYER" in sargs:
            sargs = [x for x in sargs if x != "@VIMEO_PLAYER"]
            m = re.search(r"vimeo\.com/(?:.*?/)?(\d+)(?:/([0-9a-f]{6,}))?", url)
            if not m:
                continue
            u = f"https://player.vimeo.com/video/{m.group(1)}" + (f"?h={m.group(2)}" if m.group(2) else "")
        if "@VREDDIT" in sargs:
            sargs = [x for x in sargs if x != "@VREDDIT"]
            u = vreddit(url)
            if not u:
                attempts.append({"strategy": name, "error": "NO_VREDDIT_ID"}); continue
        cmd = base_args(mode, outdir, max_h, cookies, plat) + sargs + (extra or []) + ["--", u]
        rc, out, err = run(cmd)
        if rc == 0 and mode == "meta":
            return {"ok": True, "platform": plat, "strategy": name, "meta": json.loads(out), "attempts": attempts}
        files = [l.strip() for l in out.splitlines() if l.strip() and os.path.exists(l.strip())]
        if mode == "subs":
            vid_id = (out.strip().splitlines() or [""])[-1].strip()
            files = sorted(glob.glob(str(outdir / f"*__{glob.escape(vid_id)}*.srt"))) if rc == 0 and vid_id else []
            ij = next(iter(glob.glob(str(outdir / f"*__{glob.escape(vid_id)}.info.json"))), None) if vid_id else None
        if rc == 0 and (files or mode == "subs"):
            if mode == "subs" and not files:
                attempts.append({"strategy": name, "error": "NO_SUBTITLES"}); last_err = "no subtitles"; continue
            if mode == "video" and plat in ("youtube", "vimeo", "tiktok"):
                # best effort: platform captions next to the media (non-fatal, same working strategy)
                run(base_args("subs", outdir, max_h, cookies, plat) + sargs + ["-o", "%(title).60B__%(id)s.%(ext)s", "--", u], 180)
                stem = pathlib.Path(files[0]).with_suffix("").name
                files += [f for f in glob.glob(str(outdir / (glob.escape(stem) + "*.srt")))]
            return {"ok": True, "platform": plat, "strategy": name, "files": files, "attempts": attempts,
                    "info_json": ij if mode == "subs" else next((str(pathlib.Path(f).with_suffix(".info.json")) for f in files
                                       if pathlib.Path(f).with_suffix(".info.json").exists()), None)}
        code, msg = classify(err)
        attempts.append({"strategy": name, "error": code})
        last_err = err
        if not quiet:
            log(f"strategy {name} failed: {code}")
        if code in ("PRIVATE", "MEMBERS_ONLY", "NO_VIDEO") or (code == "DRM" and plat != "vimeo"):
            break
        if code == "UNAVAILABLE" and sum(1 for x in attempts if x["error"] == "UNAVAILABLE") >= 2:
            break
        if code == "RATE_LIMITED":
            time.sleep(8)
    # non-yt-dlp fallbacks
    if mode in ("video", "audio") and plat in ("instagram", "facebook", "reddit", "other"):
        f = og_scrape(url, outdir, mode)
        if f:
            return {"ok": True, "platform": plat, "strategy": "og-scrape(curl-cffi)", "files": [f], "attempts": attempts,
                    "info_json": str(pathlib.Path(f).with_suffix(".info.json"))}
        attempts.append({"strategy": "og-scrape", "error": "NOT_FOUND"})
    if mode in ("video", "audio") and plat == "youtube":
        r = download(url, "subs", outdir, max_h, cookies, extra, quiet=True)
        if r.get("ok"):
            r.update({"ok": False, "partial": "captions_only", "attempts": attempts + r.get("attempts", []),
                      "error_code": classify(last_err)[0],
                      "error": "Media blocked; saved captions instead: " + classify(last_err)[1]})
            return r
    code, msg = classify(last_err)
    return {"ok": False, "platform": plat, "error_code": code, "error": msg, "attempts": attempts, "files": []}


def doctor():
    ok = True
    def chk(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'OK ' if cond else 'MISSING'} {name} {detail}")
    print("Watch Later doctor (WL_HOME=%s)" % WL_HOME)
    rc, out, _ = run([ytdlp(), "--version"], 30); chk("yt-dlp", rc == 0, out.strip())
    try:
        import importlib.metadata as m
        chk("yt-dlp-ejs", True, m.version("yt-dlp-ejs"))
    except Exception:
        chk("yt-dlp-ejs", False)
    d = shutil.which("deno"); chk("deno (JS runtime)", d, d or "")
    try:
        import curl_cffi; chk("curl-cffi (impersonation)", True, curl_cffi.__version__)
    except Exception:
        chk("curl-cffi", False)
    chk("ffmpeg", shutil.which("ffmpeg")); chk("ffprobe", shutil.which("ffprobe"))
    try:
        import importlib.metadata as m; v = m.version("bgutil-ytdlp-pot-provider")
        chk("bgutil PO-token plugin", True, v)
        chk("bgutil server", ensure_pot_server(), "127.0.0.1:4416")
    except Exception:
        print("  (optional) bgutil PO-token plugin not installed")
    try:
        import cv2; print("  OK  opencv (face crop)", cv2.__version__)
    except Exception:
        print("  (optional) opencv not installed -> vertical uses center crop")
    try:
        import faster_whisper; print("  OK  faster-whisper (local transcription fallback)")
    except Exception:
        print("  (optional) faster-whisper not installed")
    print("  %s ASSEMBLYAI_API_KEY" % ("OK " if os.environ.get("ASSEMBLYAI_API_KEY") else "MISSING (transcription needs it, or install --whisper)"))
    print("  %s X_BEARER_TOKEN (optional, for X creator sync)" % ("OK " if os.environ.get("X_BEARER_TOKEN") else "not set"))
    return ok


def main():
    argv = sys.argv[1:]
    extra = []
    if "--" in argv:
        i = argv.index("--"); extra = argv[i + 1:]; argv = argv[:i]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?")
    ap.add_argument("--audio", action="store_true"); ap.add_argument("--subs-only", action="store_true")
    ap.add_argument("--meta", action="store_true"); ap.add_argument("--max-height", type=int, default=1080)
    ap.add_argument("--out"); ap.add_argument("--cookies", help="opt-in Netscape cookies.txt supplied by the user")
    ap.add_argument("--json", action="store_true", help="print result JSON on stdout")
    ap.add_argument("--section", help="download only a time range, e.g. 0-60 or 1:30-2:15 (keeps files small)")
    ap.add_argument("--doctor", action="store_true")
    a = ap.parse_args(argv)
    if a.doctor:
        sys.exit(0 if doctor() else 1)
    if not a.url:
        ap.error("url required")
    mode = "audio" if a.audio else "subs" if a.subs_only else "meta" if a.meta else "video"
    if a.section:
        extra = ["--download-sections", "*" + a.section, "--force-keyframes-at-cuts"] + extra
    r = download(a.url, mode, a.out, a.max_height, a.cookies, extra)
    if a.json or mode == "meta":
        print(json.dumps(r if mode != "meta" or not r.get("ok") else r["meta"], ensure_ascii=False))
    else:
        for f in r.get("files", []):
            print(f)
        if r.get("ok"):
            log(f"OK via {r['strategy']} ({r['platform']})")
        else:
            log(f"FAILED [{r.get('error_code')}] {r.get('error')}" + (f" | partial: {r['partial']}" if r.get("partial") else ""))
    sys.exit(0 if r.get("ok") else (3 if r.get("partial") else 2))


if __name__ == "__main__":
    main()
