---
name: watch-later
description: >-
  Watch Later: video research + repurposing toolkit. Download public videos/audio from YouTube, X, TikTok,
  Instagram, Facebook, Reddit, Vimeo (fallback chain, no cookies); transcribe with speaker labels, word
  timestamps, chapters and key phrases (AssemblyAI; local Whisper/platform-captions fallback); find best
  moments; cut clips, mp3, silence trim, vertical 9:16 (face-tracked) with burned captions; searchable
  SQLite/FTS5 library with timestamped links; creator tracking + sync routine. Use when the user shares a
  video link, asks to summarize/transcribe/clip a video, make Shorts/Reels/TikToks, extract audio, track a
  creator, or search what someone said in a video.
---
# Watch Later

Everything is reproducible from this file on a fresh Linux box: run **Install** once (idempotent, re-run any
time to upgrade yt-dlp/EJS/plugins), then use `wl ...`. All state lives in `$WL_HOME` (default
`/workspace/watch-later`, else `~/watch-later`): `data/downloads`, `data/transcripts`, `data/clips`,
`data/library.db`, `config/creators.json`.

## Ground rules (say these when relevant, never lecture)
- Public content only. No DRM circumvention, no private/members-only/paywalled media, no account logins.
- For the user's personal research/notes, or content they own or have rights to repurpose. If the user wants
  to republish someone else's clips, remind them once that they need the rights/permission (or a fair-use
  basis such as commentary), and keep attribution (creator + link) in captions/posts.
- No cookies by default. Only if the user explicitly supplies *their own* cookies file: `--cookies FILE`.
  Never ask for passwords; never export browser cookies yourself.
- Keys: never print `ASSEMBLYAI_API_KEY` / `X_BEARER_TOKEN`; only report set/missing (`wl doctor`).
- Prefer short sections for heavy media (`--section 0-120`, `--max-height 720`) unless the user wants the full file.

## Menu (what to offer the user)
| Ask | Command |
|---|---|
| Download video / just audio (mp3) | `wl dl URL` / `wl dl URL --audio` (add `--section 1:00-2:30`, `--max-height 720`) |
| Metadata only (title, duration, uploader) | `wl dl URL --meta` |
| Transcript with speakers + timestamps | `wl transcribe URL_or_file [--speakers 2]` -> `.md`, `.srt`, `.transcript.json` |
| Summary / chapters / key points | transcribe, then read `.md` (Chapters + Key phrases) and write the summary yourself |
| Best moments for Shorts | `wl moments T.transcript.json` (heuristic) or `--prompt` -> you pick -> `--snap picks.json` |
| Vertical clip with captions | `wl clip make VIDEO --start S --end E --transcript T.json [--vertical face/center/blur] [--style bold/karaoke/clean/boxed] [--trim-silence]` |
| Plain cut / mp3 / remove silences | `wl clip cut V --start S --end E` / `wl clip mp3 V` / `wl clip silence V` |
| Repurpose into posts/threads | transcribe -> use chapters + moments + quotes to draft posts (cite timestamps + link) |
| Track creators | `wl track add youtube @handle` (x, tiktok, instagram, facebook, other) then `wl sync` |
| Search everything saved | `wl lib ingest T.json` then `wl search "phrase" [--author x --platform youtube]` |
| Weekly digest of new videos | `wl lib digest --days 7 [--platform youtube --author example]` (markdown; `--json` for raw) |
| Health check | `wl doctor` |

Typical flows:
1. "Summarize this": `wl transcribe URL` -> read the .md -> reply with summary, chapters (m:ss), notable quotes
   (speaker + timestamp), and offer clips. Ingest into the library (`wl lib ingest`).
2. "Make Shorts from this": `wl dl URL` (video) + `wl transcribe <downloaded file>` -> `wl moments T.json --n 5`
   (or do the `--prompt` LLM pass yourself, then `--snap`) -> for each pick `wl clip make ...` -> send files +
   a hook title + caption per clip. Default: `--vertical face --style bold`.
3. "What did X say about Y?": `wl search "Y" --author X` -> answer with snippets and timestamped links.
4. Clip from a long video without downloading all of it: `wl moments T.json` -> `wl dl URL --section 418-477`
   -> `wl clip make SECTION.mp4 --transcript T.json --offset 418` (offset = source time at the section start).

## Suggested routines (for the bot's scheduler)
- **Creator sync (daily, e.g. 7:00 local):** `wl sync --limit 3 --audio-only`, then post a short report: new items
  (title, creator, link, 1-line summary from the transcript), failures, blocked platforms. Idempotent: re-runs skip
  done items (state in `library.db` table `seen`; failed items retry up to 3 times).
- **Weekly digest (e.g. Monday 8:00):** `wl lib digest --days 7` -> turn it into a readable digest: per creator,
  2-3 bullet summary per video, best quote with speaker + timestamped link, and 1-2 suggested clips (`wl moments`).
- **Monthly upkeep:** `wl update` (upgrades yt-dlp nightly / EJS / PO-token plugin) then `wl doctor`.

## Install (one time; idempotent; ~2-4 min; no sudo needed if ffmpeg/python3/git exist)
From the public repository, `README.md` has a one-line `curl | bash` install. The block below writes the same files when you already have this document and no checkout.
Needs: python3 >= 3.10 with venv, git, curl, internet. Installs into `$WL_HOME`: venv with yt-dlp (nightly via `--pre`)
`[default,curl-cffi]` + yt-dlp-ejs, deno (PyPI wheel), bgutil-ytdlp-pot-provider (+ its server, run with deno),
opencv-python-headless<5 (face crop), requests; ffmpeg via apt if root/sudo, else a static build.
Copy-paste this whole block into a shell (it writes every file, then runs the installer):

```bash
export WL_HOME="${WL_HOME:-$( [ -w /workspace ] && echo /workspace/watch-later || echo "$HOME/watch-later")}"
mkdir -p "$WL_HOME/scripts" "$WL_HOME/tests"
cat > "$WL_HOME/install.sh" <<'WL_EOF_INSTALL_SH'
#!/usr/bin/env bash
# Watch Later toolkit installer. Idempotent; safe to re-run (also upgrades yt-dlp/EJS/plugins).
# Usage: bash install.sh [--no-pot] [--whisper] [--face]
#   --no-pot   skip the bgutil PO-token provider (YouTube)    --whisper  add local faster-whisper fallback
#   --face     add OpenCV for face-tracked vertical crops (on by default; ~60MB)
# Env: WL_HOME (default /workspace/watch-later, or ~/watch-later if /workspace is not writable)
set -uo pipefail
POT=1; WHISPER=0; FACE=1
for a in "$@"; do case "$a" in --no-pot) POT=0;; --whisper) WHISPER=1;; --no-face) FACE=0;; --face) FACE=1;; esac; done
if [[ -z "${WL_HOME:-}" ]]; then
  if [[ -w /workspace ]]; then WL_HOME=/workspace/watch-later; else WL_HOME="$HOME/watch-later"; fi
fi
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$WL_HOME"/{bin,scripts,data/{downloads,transcripts,clips},config,tmp,logs}
log(){ printf '\033[1;36m[install]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[install WARN]\033[0m %s\n' "$*" >&2; }
SUDO=""; if [[ $EUID -ne 0 ]] && command -v sudo >/dev/null && sudo -n true 2>/dev/null; then SUDO="sudo -n"; fi

# 1) ffmpeg/ffprobe: system pkg if possible, else static build into $WL_HOME/bin
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  if command -v apt-get >/dev/null && { [[ $EUID -eq 0 ]] || [[ -n $SUDO ]]; }; then
    log "installing ffmpeg via apt"; $SUDO apt-get update -qq && $SUDO apt-get install -y -qq ffmpeg >/dev/null || true
  fi
  if ! command -v ffmpeg >/dev/null && [[ ! -x "$WL_HOME/bin/ffmpeg" ]]; then
    log "downloading static ffmpeg (no root)"; arch=$(uname -m); [[ $arch == aarch64 ]] && fa=arm64 || fa=amd64
    curl -fsSL "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-$fa-static.tar.xz" -o "$WL_HOME/tmp/ff.tar.xz" &&
      tar -xJf "$WL_HOME/tmp/ff.tar.xz" -C "$WL_HOME/tmp" && cp "$WL_HOME"/tmp/ffmpeg-*-static/{ffmpeg,ffprobe} "$WL_HOME/bin/" &&
      rm -rf "$WL_HOME"/tmp/ff.tar.xz "$WL_HOME"/tmp/ffmpeg-*-static || warn "static ffmpeg download failed"
  fi
fi
# fonts for burned captions (best effort)
if ! fc-list 2>/dev/null | grep -qiE 'dejavu|liberation|noto'; then
  [[ -n $SUDO || $EUID -eq 0 ]] && command -v apt-get >/dev/null && $SUDO apt-get install -y -qq fonts-dejavu-core fontconfig >/dev/null 2>&1 || warn "no fonts found; captions use ffmpeg default"
fi

# 2) Python venv (python3 >= 3.10). Prefer uv if present (fast), else venv+pip.
PY=$(command -v python3); [[ -z $PY ]] && { warn "python3 missing"; exit 1; }
if [[ ! -x "$WL_HOME/venv/bin/python" ]]; then
  log "creating venv"; if command -v uv >/dev/null; then uv venv -q "$WL_HOME/venv" -p "$PY"; else "$PY" -m venv "$WL_HOME/venv" || { warn "python3-venv missing; trying --without-pip"; "$PY" -m venv --without-pip "$WL_HOME/venv" && curl -fsSL https://bootstrap.pypa.io/get-pip.py | "$WL_HOME/venv/bin/python"; }; fi
fi
VPY="$WL_HOME/venv/bin/python"
pipi(){ if command -v uv >/dev/null; then uv pip install -q -p "$VPY" "$@"; else "$VPY" -m pip install -q -U "$@"; fi; }
[[ -x "$WL_HOME/venv/bin/pip" ]] || "$VPY" -m ensurepip -q 2>/dev/null || true
log "installing/upgrading yt-dlp (nightly/pre-release) + EJS + curl-cffi + deno"
# --pre pulls yt-dlp nightly from PyPI (same as `yt-dlp --update-to nightly`); [default] includes yt-dlp-ejs
pipi -U "yt-dlp[default,curl-cffi]" "deno>=2.3" requests || warn "pip deps partially failed"
# then only yt-dlp itself to the nightly pre-release (deps stay on stable releases); EJS must match yt-dlp
pipi -U --pre --no-deps yt-dlp || warn "nightly yt-dlp unavailable; staying on stable"
pipi -U yt-dlp-ejs || true
# deno binary from the PyPI wheel -> $WL_HOME/bin/deno (yt-dlp's recommended JS runtime for EJS)
DENO=$("$VPY" -c 'import deno,os;print(deno.find_deno_bin())' 2>/dev/null || true)
[[ -n $DENO && -x $DENO ]] && ln -sf "$DENO" "$WL_HOME/bin/deno" || warn "deno wheel missing; will fall back to node/bun"
[[ $FACE == 1 ]] && { pipi -U "opencv-python-headless<5" numpy || warn "opencv install failed; face-tracked crop disabled"; }
[[ $WHISPER == 1 ]] && { pipi -U faster-whisper || warn "faster-whisper install failed"; }

# 3) PO-token provider (bgutil): plugin + local HTTP server on 127.0.0.1:4416 (runs with deno; no Docker needed)
if [[ $POT == 1 ]]; then
  pipi -U bgutil-ytdlp-pot-provider || warn "bgutil plugin install failed"
  PV=$("$VPY" -c 'import importlib.metadata as m;print(m.version("bgutil-ytdlp-pot-provider"))' 2>/dev/null || echo "")
  if [[ -n $PV ]] && command -v git >/dev/null; then
    if [[ ! -f "$WL_HOME/pot/.version" || "$(cat "$WL_HOME/pot/.version")" != "$PV" ]]; then
      log "setting up bgutil POT server $PV"; rm -rf "$WL_HOME/pot.new"
      if git clone -q --depth 1 --single-branch --branch "$PV" https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git "$WL_HOME/pot.new" 2>/dev/null; then
        ( cd "$WL_HOME/pot.new/server" && "$WL_HOME/bin/deno" install --allow-scripts=npm:canvas --frozen >/dev/null 2>&1 ) &&
          { rm -rf "$WL_HOME/pot"; mv "$WL_HOME/pot.new" "$WL_HOME/pot"; echo "$PV" > "$WL_HOME/pot/.version"; } || warn "bgutil server deps failed (YouTube still works via fallback clients)"
      else warn "git clone of bgutil failed"; fi
    fi
  fi
fi

# 4) Scripts + config
if [[ -d "$SRC/scripts" && "$SRC" != "$WL_HOME" ]]; then cp -f "$SRC"/scripts/*.py "$WL_HOME/scripts/" 2>/dev/null; cp -f "$SRC"/scripts/wl "$WL_HOME/scripts/" 2>/dev/null; fi
chmod +x "$WL_HOME"/scripts/* 2>/dev/null
ln -sf "$WL_HOME/scripts/wl" "$WL_HOME/bin/wl"
[[ -f "$WL_HOME/config/creators.json" ]] || cat > "$WL_HOME/config/creators.json" <<'JSON'
{"_comment": "Handles/channels to track. Public accounts only. Run: wl sync [--limit N] [--no-transcribe]",
 "youtube": [], "x": [], "tiktok": [], "instagram": [], "facebook": [], "other": []}
JSON
# yt-dlp config: absolute deno path under $WL_HOME (repo template keeps a WL_HOME token)
cat > "$WL_HOME/config/yt-dlp.conf" <<CONF
--js-runtimes deno:$WL_HOME/bin/deno
--js-runtimes node
--remote-components ejs:github
--no-cookies-from-browser
CONF
log "doctor:"; PATH="$WL_HOME/bin:$PATH" "$VPY" "$WL_HOME/scripts/wl_dl.py" --doctor || true
log "done. Add to PATH:  export PATH=\"$WL_HOME/bin:\$PATH\"   then run: wl help"
WL_EOF_INSTALL_SH
cat > "$WL_HOME/scripts/wl" <<'WL_EOF_SCRIPTS_WL'
#!/usr/bin/env bash
# Watch Later CLI dispatcher.  wl <dl|transcribe|clip|moments|lib|sync|track|doctor|help> ...
H="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"; export WL_HOME="${WL_HOME:-$H}"
PY="$WL_HOME/venv/bin/python"; S="$WL_HOME/scripts"; export PATH="$WL_HOME/bin:$WL_HOME/venv/bin:$PATH"
cmd="${1:-help}"; shift || true
case "$cmd" in
  dl|download) exec "$PY" "$S/wl_dl.py" "$@";;
  doctor) exec "$PY" "$S/wl_dl.py" --doctor;;
  transcribe|tx) exec "$PY" "$S/wl_transcribe.py" "$@";;
  clip) exec "$PY" "$S/wl_clip.py" "$@";;
  moments|best) exec "$PY" "$S/wl_moments.py" "$@";;
  lib|library|search) [[ $cmd == search ]] && set -- search "$@"; exec "$PY" "$S/wl_library.py" "$@";;
  sync) exec "$PY" "$S/wl_sync.py" "$@";;
  track) exec "$PY" "$S/wl_sync.py" track "$@";;
  update) exec bash "$WL_HOME/install.sh" "$@";;
  help|*) cat <<'H'
Watch Later  (public content only; no DRM; no cookies unless the user supplies their own file)
  wl dl <url> [--audio|--subs-only|--meta] [--max-height 720] [--cookies FILE]   download with fallback chain
  wl transcribe <url|file> [--speakers N] [--engine auto|assemblyai|whisper|captions]
  wl moments <T.transcript.json> [--n 8] [--prompt | --snap picks.json]         best-moment candidates
  wl clip make <video> --start S --end E [--transcript T.json] [--vertical face|center|blur|none] [--style bold|clean|karaoke|boxed] [--trim-silence]
  wl clip cut|mp3|silence|vertical|captions <file> ...                             single ffmpeg ops
  wl lib ingest <T.json> | wl search "query" [--platform youtube --author example] | wl lib list|show|stats|digest [--days 7]
  wl track add <youtube|x|tiktok|instagram|facebook|other> <handle|url> | wl track list
  wl sync [--limit 5] [--audio-only] [--dry-run]                                    new videos -> transcribe -> library
  wl doctor | wl update
H
  ;;
esac
WL_EOF_SCRIPTS_WL
cat > "$WL_HOME/scripts/wl_common.py" <<'WL_EOF_SCRIPTS_WL_COMMON_PY'
"""Shared helpers for Watch Later scripts (paths, time formatting, transcript I/O, SRT/ASS)."""
import json, os, pathlib, re, subprocess, sys

WL_HOME = pathlib.Path(os.environ.get("WL_HOME") or pathlib.Path(__file__).resolve().parent.parent)
DATA = pathlib.Path(os.environ.get("WL_DATA") or WL_HOME / "data")
os.environ["PATH"] = f"{WL_HOME/'bin'}:{WL_HOME/'venv'/'bin'}:" + os.environ.get("PATH", "")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def log(tag, *a):
    print(f"[wl {tag}]", *a, file=sys.stderr, flush=True)


def hms(ms, srt=False, sep=","):
    ms = max(0, int(ms))
    h, r = divmod(ms, 3600000); m, r = divmod(r, 60000); s, x = divmod(r, 1000)
    if srt:
        return f"{h:02d}:{m:02d}:{s:02d}{sep}{x:03d}"
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_ts(t):
    """'1:02:03.5' | '62.5' | '1:02' -> milliseconds."""
    t = str(t).strip()
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return int(float(t) * 1000)
    parts = [float(p.replace(",", ".")) for p in t.split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return int(sec * 1000)


def ffprobe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def video_size(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0:s=x", str(path)], capture_output=True, text=True)
    try:
        w, h = r.stdout.strip().split("\n")[0].split("x")[:2]
        return int(w), int(h)
    except Exception:
        return 0, 0


def load_transcript(path):
    p = pathlib.Path(path)
    if p.suffix == ".srt":
        return srt_to_transcript(p)
    d = json.loads(p.read_text())
    if "utterances" not in d and "words" not in d:
        raise SystemExit(f"{p} is not a Watch Later transcript json")
    return d


def srt_to_transcript(p):
    txt = pathlib.Path(p).read_text(errors="ignore")
    utts, prev = [], []
    for block in re.split(r"\n\s*\n", txt.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        tl = next((l for l in lines if "-->" in l), None)
        if not tl:
            continue
        a, b = [parse_ts(x.strip().split(" ")[0]) for x in tl.split("-->")]
        tlines = [re.sub(r"<[^>]+>", "", l).strip() for l in lines[lines.index(tl) + 1:]]
        body = " ".join(l for l in tlines if l and l not in prev).strip()  # drop YouTube auto-caption roll-up repeats
        prev = tlines
        if body and (not utts or utts[-1]["text"] != body):
            utts.append({"speaker": "A", "start": a, "end": b, "text": body})
    words = []
    for u in utts:  # approximate word timings by linear interpolation
        ws = u["text"].split(); n = max(1, len(ws)); d = (u["end"] - u["start"]) / n
        words += [{"text": w, "start": int(u["start"] + i * d), "end": int(u["start"] + (i + 1) * d), "speaker": "A"} for i, w in enumerate(ws)]
    return {"engine": "platform-captions", "utterances": utts, "words": words, "chapters": [], "highlights": [],
            "text": " ".join(u["text"] for u in utts), "duration": (utts[-1]["end"] / 1000 if utts else 0)}


def caption_cues(words, max_chars=32, max_ms=2500, gap_ms=600):
    """Group word timings into short caption cues (Shorts-style)."""
    cues, cur = [], []
    for w in words:
        if cur and (len(" ".join(x["text"] for x in cur + [w])) > max_chars or w["start"] - cur[0]["start"] > max_ms
                    or w["start"] - cur[-1]["end"] > gap_ms or cur[-1]["text"][-1:] in ".?!"):
            cues.append(cur); cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    return [{"start": c[0]["start"], "end": c[-1]["end"], "text": " ".join(x["text"] for x in c), "words": c,
             "speaker": c[0].get("speaker")} for c in cues]


def write_srt(cues, path, offset_ms=0):
    out = []
    for i, c in enumerate(cues, 1):
        out += [str(i), f"{hms(c['start'] - offset_ms, True)} --> {hms(c['end'] - offset_ms, True)}", c["text"], ""]
    pathlib.Path(path).write_text("\n".join(out))
    return path


ASS_STYLES = {
    # name: (font size as fraction of height, primary, outline, back, bold, alignment, margin_v fraction, uppercase)
    "bold": (0.055, "&H00FFFFFF", "&H00000000", "&H80000000", 1, 2, 0.22, True),
    "clean": (0.042, "&H00FFFFFF", "&H00202020", "&H64000000", 0, 2, 0.08, False),
    "karaoke": (0.055, "&H0000FFFF", "&H00000000", "&H80000000", 1, 2, 0.22, True),
    "boxed": (0.045, "&H00FFFFFF", "&H00000000", "&HA0000000", 1, 2, 0.12, False),
}


def ass_time(ms):
    ms = max(0, int(ms)); h, r = divmod(ms, 3600000); m, r = divmod(r, 60000); s, x = divmod(r, 1000)
    return f"{h}:{m:02d}:{s:02d}.{x // 10:02d}"


def write_ass(cues, path, w, h, style="bold", offset_ms=0, font="DejaVu Sans"):
    fs, prim, outl, back, bold, align, mv, upper = ASS_STYLES.get(style, ASS_STYLES["bold"])
    border = 3 if style == "boxed" else 1
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{int(h*fs)},{prim},&H00FFFFFF,{outl},{back},{bold},0,0,0,100,100,0,0,{border},{max(2,int(h*0.004))},1,{align},{int(w*0.06)},{int(w*0.06)},{int(h*mv)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for c in cues:
        if style == "karaoke" and c.get("words"):
            parts = []
            for wd in c["words"]:
                k = max(1, int((wd["end"] - wd["start"]) / 10))
                t = wd["text"].upper() if upper else wd["text"]
                parts.append(f"{{\\k{k}}}{t}")
            text = " ".join(parts).replace("{\\k", "{\\kf")  # fills Secondary(white) -> Primary(yellow)
        else:
            text = c["text"].upper() if upper else c["text"]
        text = text.replace("\n", "\\N")
        ev.append(f"Dialogue: 0,{ass_time(c['start']-offset_ms)},{ass_time(c['end']-offset_ms)},Default,,0,0,0,,{text}")
    pathlib.Path(path).write_text(hdr + "\n".join(ev) + "\n")
    return path


def slug(s, n=60):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "").strip("_")[:n] or "item"
WL_EOF_SCRIPTS_WL_COMMON_PY
cat > "$WL_HOME/scripts/wl_dl.py" <<'WL_EOF_SCRIPTS_WL_DL_PY'
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
WL_EOF_SCRIPTS_WL_DL_PY
cat > "$WL_HOME/scripts/wl_transcribe.py" <<'WL_EOF_SCRIPTS_WL_TRANSCRIBE_PY'
#!/usr/bin/env python3
"""wl transcribe - speaker-labelled transcript with word timestamps, chapters, highlights.

Usage: wl transcribe <url|media file|.srt> [--out DIR] [--speakers N] [--engine auto|assemblyai|whisper|captions]
                     [--lang en] [--no-summary] [--no-highlights] [--keyterms "a,b"] [--whisper-model small]
Engines: assemblyai (default when ASSEMBLYAI_API_KEY is set; universal-3-5-pro -> universal-2, speaker_labels,
         word timestamps, auto_highlights, Speech-Understanding summarization = chapters with headlines),
         whisper (local faster-whisper, no diarization; `bash install.sh --whisper`),
         captions (platform subtitles via wl dl --subs-only; no diarization).
auto = assemblyai -> whisper -> captions.
Outputs in --out (default data/transcripts/): <stem>.transcript.json (normalized), <stem>.md, <stem>.srt, <stem>.raw.json
Prints the .transcript.json path on stdout. Never prints the API key.
"""
import argparse, json, os, pathlib, subprocess, sys, time
from wl_common import DATA, log, hms, caption_cues, write_srt, slug, srt_to_transcript, ffprobe_duration
import wl_dl

API = "https://api.assemblyai.com"


def key():
    return os.environ.get("ASSEMBLYAI_API_KEY") or os.environ.get("ASSEMBLY_AI_KEY") or os.environ.get("AAI_API_KEY")


def to_audio(src, work):
    """Return (audio_path, info dict) for a URL or local media."""
    info = {}
    if os.path.exists(src):
        p = pathlib.Path(src).resolve()
        ij = p.with_suffix(".info.json")
        if ij.exists():
            info = json.loads(ij.read_text())
        if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus"):
            return str(p), info
        out = pathlib.Path(work) / (p.stem + ".mp3")
        if not out.exists():
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(p), "-vn", "-ac", "1", "-b:a", "64k", str(out)], check=True)
        return str(out), info
    r = wl_dl.download(src, "audio", work)
    if not r.get("ok"):
        raise RuntimeError(f"download failed [{r.get('error_code')}]: {r.get('error')}")
    if r.get("info_json") and os.path.exists(r["info_json"]):
        info = json.loads(open(r["info_json"]).read())
    return r["files"][0], info


def aai(audio, a):
    import requests
    H = {"authorization": key()}
    with open(audio, "rb") as f:
        up = requests.post(API + "/v2/upload", headers=H, data=f, timeout=1800)
    up.raise_for_status()
    body = {"audio_url": up.json()["upload_url"], "speech_models": ["universal-3-5-pro", "universal-2"],
            "punctuate": True, "format_text": True}
    if a.lang:
        body["language_code"] = a.lang
    else:
        body["language_detection"] = True
    if not a.no_diarize:
        body["speaker_labels"] = True
        if a.speakers:
            body["speakers_expected"] = a.speakers
    if not a.no_highlights:
        body["auto_highlights"] = True
    if not a.no_summary:  # chapters (auto_chapters was removed 2026-09-15 -> Speech Understanding summarization)
        body["speech_understanding"] = {"request": {"summarization": {"summary_type": "paragraph"}}}
    if a.keyterms:
        body["keyterms_prompt"] = [k.strip() for k in a.keyterms.split(",") if k.strip()]
    for attempt in range(4):
        r = requests.post(API + "/v2/transcript", headers=H, json=body, timeout=60)
        if r.status_code == 200:
            break
        msg = r.text[:300]
        log("transcribe", f"submit {r.status_code}: {msg}")
        # drop optional features the account/model rejects, then retry
        for k in ("speech_understanding", "auto_highlights", "keyterms_prompt"):
            if k in body and (k.split("_")[0] in msg.lower() or attempt >= 1):
                body.pop(k); break
        else:
            if r.status_code < 500:
                raise RuntimeError(f"AssemblyAI submit failed {r.status_code}: {msg}")
            time.sleep(5)
    else:
        raise RuntimeError("AssemblyAI submit failed")
    tid = r.json()["id"]
    log("transcribe", f"AssemblyAI job {tid}")
    t0 = time.time()
    while True:
        j = requests.get(f"{API}/v2/transcript/{tid}", headers=H, timeout=60).json()
        if j["status"] == "completed":
            return j
        if j["status"] == "error":
            raise RuntimeError("AssemblyAI error: " + str(j.get("error")))
        if time.time() - t0 > 3600:
            raise RuntimeError("AssemblyAI timeout")
        time.sleep(3)


def normalize_aai(j):
    words = [{"text": w["text"], "start": w["start"], "end": w["end"], "speaker": w.get("speaker"),
              "confidence": w.get("confidence")} for w in (j.get("words") or [])]
    utts = [{"speaker": u.get("speaker"), "start": u["start"], "end": u["end"], "text": u["text"]} for u in (j.get("utterances") or [])]
    if not utts and words:
        utts = [{"speaker": "A", "start": words[0]["start"], "end": words[-1]["end"], "text": j.get("text", "")}]
    chapters = []
    su = ((j.get("speech_understanding") or {}).get("response") or {}).get("summarization") or {}
    for c in su.get("summary") or []:
        if isinstance(c, dict):
            chapters.append({"start": c.get("start"), "end": c.get("end"), "headline": c.get("headline"), "summary": c.get("text")})
    for c in j.get("chapters") or []:  # legacy
        chapters.append({"start": c["start"], "end": c["end"], "headline": c.get("headline"), "summary": c.get("summary")})
    hl = []
    for h in ((j.get("auto_highlights_result") or {}).get("results") or []):
        hl.append({"text": h["text"], "count": h.get("count"), "rank": h.get("rank"),
                   "timestamps": [[t["start"], t["end"]] for t in h.get("timestamps", [])]})
    return {"engine": "assemblyai:" + str(j.get("speech_model_used") or j.get("speech_model") or "universal"),
            "aai_id": j["id"], "language": j.get("language_code"), "duration": j.get("audio_duration"),
            "text": j.get("text"), "utterances": utts, "words": words, "chapters": chapters, "highlights": hl}


def whisper(audio, a):
    from faster_whisper import WhisperModel
    m = WhisperModel(a.whisper_model, device="auto", compute_type="int8")
    segs, info = m.transcribe(audio, word_timestamps=True, vad_filter=True, language=a.lang)
    words, utts = [], []
    for s in segs:
        utts.append({"speaker": "A", "start": int(s.start * 1000), "end": int(s.end * 1000), "text": s.text.strip()})
        words += [{"text": w.word.strip(), "start": int(w.start * 1000), "end": int(w.end * 1000), "speaker": "A",
                   "confidence": w.probability} for w in (s.words or [])]
    return {"engine": f"faster-whisper:{a.whisper_model}", "language": info.language, "duration": info.duration,
            "text": " ".join(u["text"] for u in utts), "utterances": utts, "words": words, "chapters": [], "highlights": []}


def render_md(t, title, src):
    L = [f"# {title}", "", f"- Source: {src}", f"- Engine: {t['engine']} | language: {t.get('language')} | duration: {hms((t.get('duration') or 0)*1000)}", ""]
    if t.get("chapters"):
        L += ["## Chapters", ""] + [f"- [{hms(c['start'])}] **{c.get('headline')}** - {c.get('summary') or ''}" for c in t["chapters"]] + [""]
    if t.get("highlights"):
        L += ["## Key phrases", "", ", ".join(h["text"] for h in sorted(t["highlights"], key=lambda h: -(h.get("rank") or 0))[:20]), ""]
    L += ["## Transcript", ""]
    for u in t["utterances"]:
        L.append(f"**Speaker {u['speaker']}** [{hms(u['start'])}]: {u['text']}\n")
    return "\n".join(L)


def transcribe(src, a):
    out = pathlib.Path(a.out or DATA / "transcripts").resolve(); out.mkdir(parents=True, exist_ok=True)
    work = DATA / "downloads" / "audio"; work.mkdir(parents=True, exist_ok=True)
    info, t, audio = {}, None, None
    if str(src).endswith(".srt") and os.path.exists(src):
        t = srt_to_transcript(src)
    engines = [a.engine] if a.engine != "auto" else ["assemblyai", "whisper", "captions"]
    errors = []
    for eng in engines:
        if t:
            break
        try:
            if eng in ("assemblyai", "whisper") and audio is None:
                audio, info = to_audio(src, work)
            if eng == "assemblyai":
                if not key():
                    errors.append("assemblyai: ASSEMBLYAI_API_KEY not set"); continue
                j = aai(audio, a); t = normalize_aai(j); t["_raw"] = j
            elif eng == "whisper":
                try:
                    import faster_whisper  # noqa
                except ImportError:
                    errors.append("whisper: faster-whisper not installed (bash install.sh --whisper)"); continue
                t = whisper(audio, a)
            elif eng == "captions":
                if os.path.exists(src):
                    cands = sorted(pathlib.Path(src).parent.glob(pathlib.Path(src).stem + "*.srt"))
                    srt = str(cands[0]) if cands else None
                else:
                    r = wl_dl.download(src, "subs", work)
                    srt = next((f for f in r.get("files", []) if f.endswith(".srt")), None)
                    if r.get("info_json"):
                        info = json.loads(open(r["info_json"]).read())
                if srt:
                    t = srt_to_transcript(srt)
                else:
                    errors.append("captions: none available")
        except Exception as e:
            errors.append(f"{eng}: {e}")
            log("transcribe", f"{eng} failed: {e}")
            if "download failed" in str(e) and eng == "assemblyai":
                audio = None
                engines = [x for x in engines if x == "captions"] or engines
    if not t:
        raise SystemExit("transcription failed: " + " | ".join(errors))
    raw = t.pop("_raw", None)
    title = info.get("title") or (pathlib.Path(src).stem if os.path.exists(src) else src)
    t.update({"source": info.get("webpage_url") or src, "title": title, "media": audio if audio and os.path.exists(src) is False else (str(pathlib.Path(src).resolve()) if os.path.exists(src) else audio),
              "info": {k: info.get(k) for k in ("id", "extractor_key", "uploader", "uploader_id", "channel", "upload_date", "duration", "webpage_url", "timestamp")}})
    stem = slug(f"{info.get('id') or ''}_{title}", 80)
    base = out / stem
    if raw:
        (base.with_suffix(".raw.json")).write_text(json.dumps(raw))
    tj = pathlib.Path(str(base) + ".transcript.json"); tj.write_text(json.dumps(t, ensure_ascii=False, indent=1))
    pathlib.Path(str(base) + ".md").write_text(render_md(t, title, t["source"]))
    if t.get("words"):
        write_srt(caption_cues(t["words"], 42, 4000), str(base) + ".srt")
    log("transcribe", f"OK {t['engine']}: {len(t['utterances'])} utterances, {len(t['words'])} words, "
        f"{len(set(u['speaker'] for u in t['utterances']))} speakers, {len(t['chapters'])} chapters, {len(t['highlights'])} highlights")
    return str(tj)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source"); ap.add_argument("--out"); ap.add_argument("--speakers", type=int)
    ap.add_argument("--engine", default="auto", choices=["auto", "assemblyai", "whisper", "captions"])
    ap.add_argument("--lang"); ap.add_argument("--no-summary", action="store_true"); ap.add_argument("--no-highlights", action="store_true")
    ap.add_argument("--no-diarize", action="store_true"); ap.add_argument("--keyterms"); ap.add_argument("--whisper-model", default="small")
    a = ap.parse_args()
    print(transcribe(a.source, a))


if __name__ == "__main__":
    main()
WL_EOF_SCRIPTS_WL_TRANSCRIBE_PY
cat > "$WL_HOME/scripts/wl_clip.py" <<'WL_EOF_SCRIPTS_WL_CLIP_PY'
#!/usr/bin/env python3
"""wl clip - ffmpeg clipping toolkit: cut, mp3, silence trim, vertical 9:16 (center/face/blur), burned captions.

Usage:
  wl clip cut      <media> --start 1:02 --end 1:30 [--copy] [--out F]
  wl clip mp3      <media> [--start S --end E] [--out F]
  wl clip silence  <media> [--db -35] [--min 0.6] [--pad 0.15] [--out F]          # remove dead air
  wl clip vertical <media> [--mode center|face|blur] [--start S --end E] [--out F]
  wl clip captions <media> --transcript T.json [--style bold|clean|karaoke|boxed] [--offset S] [--out F]
  wl clip make     <media> --start S --end E [--transcript T.json] [--vertical face|center|blur|none]
                   [--style bold] [--trim-silence] [--offset S] [--out F]            # one-shot Short/Reel/TikTok
                   (--offset = source time at media 0, for clips downloaded with `wl dl --section`)
Times accept 75, 75.5, 1:15, 0:01:15.5. Output defaults to data/clips/. Prints output path.
Face mode uses OpenCV Haar cascades (no GPU/model download); falls back to center crop if no faces found.
"""
import argparse, json, os, pathlib, shutil, subprocess, sys, tempfile, statistics
from wl_common import DATA, log, parse_ts, ffprobe_duration, video_size, caption_cues, write_ass, write_srt, slug, load_transcript

OUT = DATA / "clips"


def ff(args):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("ffmpeg failed: " + r.stderr[-800:])


def outpath(src, tag, ext=".mp4", out=None):
    if out:
        pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True); return str(out)
    OUT.mkdir(parents=True, exist_ok=True)
    return str(OUT / f"{slug(pathlib.Path(src).stem, 50)}.{tag}{ext}")


ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"]


def cut(src, start, end, out=None, copy=False):
    s, e = parse_ts(start) / 1000, parse_ts(end) / 1000
    o = outpath(src, f"cut_{int(s)}-{int(e)}", out=out)
    if copy:
        ff(["-ss", f"{s}", "-to", f"{e}", "-i", src, "-c", "copy", "-avoid_negative_ts", "make_zero", o])
    else:
        ff(["-ss", f"{s}", "-i", src, "-t", f"{e - s}"] + ENC + [o])
    return o


def mp3(src, start=None, end=None, out=None):
    o = outpath(src, "audio", ".mp3", out)
    a = []
    if start is not None:
        a += ["-ss", str(parse_ts(start) / 1000)]
    a += ["-i", src]
    if end is not None:
        a += ["-t", str((parse_ts(end) - parse_ts(start or 0)) / 1000)]
    ff(a + ["-vn", "-c:a", "libmp3lame", "-q:a", "2", o])
    return o


def detect_silence(src, db=-35, min_s=0.6):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", f"silencedetect=noise={db}dB:d={min_s}", "-f", "null", "-"],
                       capture_output=True, text=True)
    sil, st = [], None
    for line in r.stderr.splitlines():
        if "silence_start:" in line:
            st = float(line.split("silence_start:")[1].split()[0])
        elif "silence_end:" in line and st is not None:
            sil.append((max(0, st), float(line.split("silence_end:")[1].split()[0]))); st = None
    if st is not None:
        sil.append((st, ffprobe_duration(src)))
    return sil


def keep_segments(src, db=-35, min_s=0.6, pad=0.15):
    dur = ffprobe_duration(src); keep, cur = [], 0.0
    for a, b in detect_silence(src, db, min_s):
        a2, b2 = a + pad, b - pad
        if a2 > cur:
            keep.append((cur, a2))
        cur = max(cur, b2)
    if cur < dur:
        keep.append((cur, dur))
    return [(a, b) for a, b in keep if b - a > 0.05]


def has_video(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=index", "-of", "csv=p=0", src], capture_output=True, text=True)
    return bool(r.stdout.strip())


def silence(src, db=-35, min_s=0.6, pad=0.15, out=None):
    segs = keep_segments(src, db, min_s, pad)
    vid = has_video(src)
    o = outpath(src, "nosilence", ".mp4" if vid else ".mp3", out)
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in segs)
    af = f"aselect='{sel}',asetpts=N/SR/TB"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fs:
        if vid:
            fs.write(f"[0:v]select='{sel}',setpts=N/FRAME_RATE/TB[v];[0:a]{af}[a]")
        else:
            fs.write(f"[0:a]{af}[a]")
    args = ["-i", src, "-filter_complex_script", fs.name, "-map", "[a]"] + (["-map", "[v]"] if vid else [])
    ff(args + (ENC if vid else ["-c:a", "libmp3lame", "-q:a", "2"]) + [o])
    os.unlink(fs.name)
    removed = ffprobe_duration(src) - sum(b - a for a, b in segs)
    log("clip", f"silence trim: kept {len(segs)} segments, removed {removed:.1f}s")
    json.dump({"segments": segs}, open(o + ".segments.json", "w"))
    return o, segs


def remap_words(words, segs, base_ms=0):
    """Map original word times (ms, absolute) through kept segments (seconds, relative to base)."""
    out, acc = [], 0.0
    bounds = []
    for a, b in segs:
        bounds.append((a, b, acc)); acc += b - a
    for w in words:
        t0 = (w["start"] - base_ms) / 1000; t1 = (w["end"] - base_ms) / 1000
        for a, b, off in bounds:
            if a - 0.05 <= t0 <= b:
                nw = dict(w); nw["start"] = int((off + t0 - a) * 1000); nw["end"] = int((off + min(t1, b) - a) * 1000)
                out.append(nw); break
    return out


def face_track(src, start_s=0, dur_s=None, step=0.5):
    """Return list of (t, cx_norm) keyframes of the dominant face center; [] if none."""
    try:
        import cv2
    except ImportError:
        log("clip", "opencv not installed -> center crop"); return []
    if not hasattr(cv2, "CascadeClassifier"):
        log("clip", "this OpenCV build lacks Haar cascades (install opencv-python-headless<5) -> center crop"); return []
    cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    end = min(total, start_s + dur_s) if dur_s else total
    keys, t = [], start_s
    while t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY); H, W = g.shape
        sc = 480 / max(W, 1); small = cv2.resize(g, (int(W * sc), int(H * sc))) if sc < 1 else g
        faces = cas.detectMultiScale(small, 1.1, 5, minSize=(int(24), int(24)))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            keys.append((t - start_s, (x + w / 2) / small.shape[1]))
        t += step
    cap.release()
    if len(keys) < 2:
        return []
    # smooth: rolling median then hold small moves (avoid jitter)
    xs = [k[1] for k in keys]; sm = []
    for i in range(len(xs)):
        win = xs[max(0, i - 3): i + 4]; sm.append(statistics.median(win))
    held = [sm[0]]
    for v in sm[1:]:
        held.append(v if abs(v - held[-1]) > 0.06 else held[-1])
    return [(keys[i][0], held[i]) for i in range(len(keys))]


def crop_x_expr(keys, W, cw):
    """Piecewise-linear ffmpeg expression for crop x (eased between keyframes)."""
    def px(c):
        return max(0, min(W - cw, int(c * W - cw / 2)))
    pts = [(keys[0][0], px(keys[0][1]))]
    for t, c in keys[1:]:
        if px(c) != pts[-1][1]:
            pts.append((t, px(c)))
    if len(pts) == 1:
        return str(pts[0][1])
    expr = str(pts[-1][1])
    for i in range(len(pts) - 2, -1, -1):
        t0, x0 = pts[i]; t1, x1 = pts[i + 1]; tr = min(0.4, t1 - t0)  # 0.4s pan into the new position
        seg = f"if(lt(t,{t1 - tr:.2f}),{x0},if(lt(t,{t1:.2f}),{x0}+({x1}-{x0})*(t-{t1 - tr:.2f})/{tr:.2f},{expr}))"
        expr = seg
    return expr


def vertical_filter(src, mode, start_s, dur_s, W, H, outW=1080, outH=1920):
    tw = int(H * 9 / 16) // 2 * 2
    if W <= tw:  # already vertical/narrow
        return f"scale={outW}:{outH}:force_original_aspect_ratio=decrease,pad={outW}:{outH}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    if mode == "blur":
        return (f"split[a][b];[a]scale={outW}:{outH}:force_original_aspect_ratio=increase,crop={outW}:{outH},boxblur=20:2[bg];"
                f"[b]scale={outW}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    x = f"{(W - tw) // 2}"
    if mode == "face":
        keys = face_track(src, start_s, dur_s)
        if keys:
            x = crop_x_expr(keys, W, tw); log("clip", f"face-tracked crop: {len(keys)} keyframes")
        else:
            log("clip", "no faces found -> center crop")
    return f"crop={tw}:{H}:'{x}':0,scale={outW}:{outH},setsar=1"


def esc_path(p):
    return p.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")


def make(src, start=None, end=None, transcript=None, vertical="face", style="bold", trim_silence=False, out=None, words_override=None, src_offset=0):
    """src_offset (ms): source/transcript time at media 0, e.g. for a `wl dl --section 418-477` download use 418000."""
    s_ms = parse_ts(start) if start is not None else 0
    e_ms = parse_ts(end) if end is not None else int(ffprobe_duration(src) * 1000)
    tag = f"short_{s_ms//1000}-{e_ms//1000}" if vertical != "none" else f"clip_{s_ms//1000}-{e_ms//1000}"
    o = outpath(src, tag, out=out)
    work = tempfile.mkdtemp(prefix="wlclip_", dir=str(DATA))
    try:
        seg = os.path.join(work, "seg.mp4")
        ff(["-ss", f"{s_ms/1000}", "-i", src, "-t", f"{(e_ms - s_ms)/1000}"] + ENC + [seg])
        words = None
        if transcript:
            t = load_transcript(transcript)
            o_ms = s_ms + src_offset; oe_ms = e_ms + src_offset
            words = [dict(w, start=w["start"] - o_ms, end=w["end"] - o_ms) for w in t.get("words", []) if w["start"] >= o_ms - 50 and w["end"] <= oe_ms + 50]
        if trim_silence:
            seg2, segs = silence(seg, out=os.path.join(work, "trim.mp4"))
            if words:
                words = remap_words(words, segs)
            seg = seg2
        W, H = video_size(seg)
        vf = []
        if vertical != "none" and W and H:
            vf.append(vertical_filter(seg, vertical, 0, None, W, H))
            oW, oH = 1080, 1920
        else:
            oW, oH = W, H
        if words:
            cues = caption_cues(words, 22 if vertical != "none" else 40, 2000)
            ass = write_ass(cues, os.path.join(work, "cap.ass"), oW, oH, style)
            write_srt(cues, o.rsplit(".", 1)[0] + ".srt")
            vf.append(f"subtitles='{esc_path(ass)}'")
        if vf:
            graph = ",".join(vf) if "split" not in vf[0] else vf[0] + ("," + ",".join(vf[1:]) if len(vf) > 1 else "")
            ff(["-i", seg, "-filter_complex", f"[0:v]{graph}[v]", "-map", "[v]", "-map", "0:a?"] + ENC + [o])
        else:
            os.replace(seg, o)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return o


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["cut", "mp3", "silence", "vertical", "captions", "make"])
    ap.add_argument("media"); ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--out")
    ap.add_argument("--copy", action="store_true"); ap.add_argument("--db", type=float, default=-35)
    ap.add_argument("--min", type=float, default=0.6); ap.add_argument("--pad", type=float, default=0.15)
    ap.add_argument("--mode", default="face", choices=["center", "face", "blur"])
    ap.add_argument("--vertical", default="face", choices=["face", "center", "blur", "none"])
    ap.add_argument("--transcript"); ap.add_argument("--style", default="bold", choices=["bold", "clean", "karaoke", "boxed"])
    ap.add_argument("--offset"); ap.add_argument("--trim-silence", action="store_true")
    a = ap.parse_args()
    m = a.media
    if not os.path.exists(m):
        raise SystemExit(f"no such file: {m}")
    if a.cmd == "cut":
        if a.start is None or a.end is None:
            raise SystemExit("--start and --end required")
        print(cut(m, a.start, a.end, a.out, a.copy))
    elif a.cmd == "mp3":
        print(mp3(m, a.start, a.end, a.out))
    elif a.cmd == "silence":
        print(silence(m, a.db, a.min, a.pad, a.out)[0])
    elif a.cmd == "vertical":
        print(make(m, a.start, a.end, None, a.mode, a.style, False, a.out))
    elif a.cmd == "captions":
        if not a.transcript:
            raise SystemExit("--transcript required")
        print(make(m, a.offset or a.start, a.end, a.transcript, "none", a.style, False, a.out))
    elif a.cmd == "make":
        print(make(m, a.start, a.end, a.transcript, a.vertical, a.style, a.trim_silence, a.out, src_offset=parse_ts(a.offset) if a.offset else 0))


if __name__ == "__main__":
    main()
WL_EOF_SCRIPTS_WL_CLIP_PY
cat > "$WL_HOME/scripts/wl_moments.py" <<'WL_EOF_SCRIPTS_WL_MOMENTS_PY'
#!/usr/bin/env python3
"""wl moments - rank candidate clips ("best moments") from a transcript.

Usage:
  wl moments <T.transcript.json> [--n 8] [--min 15] [--max 60] [--json]   # heuristic ranking (no LLM needed)
  wl moments <T.transcript.json> --prompt [--n 8]                         # print an LLM prompt (the bot answers it)
  wl moments <T.transcript.json> --snap picks.json                        # validate/snap LLM picks to word boundaries
Heuristic score = AssemblyAI key-phrase hits + hook/opener cues + questions/emphasis + numbers + speech density
                  + clean sentence boundaries + chapter alignment; non-overlapping top-N.
Output: ranked list with start/end (s and m:ss), duration, score, reason, text; JSON with --json.
"""
import argparse, json, re, sys
from wl_common import load_transcript, hms, log

HOOKS = r"\b(here'?s (why|how|the)|the (secret|truth|key|problem|reason|trick)|most people|nobody|never|always|stop|imagine|what if|the biggest|the first|the only|you need|you should|i (learned|realized|discovered)|turns out|in fact|actually|the best|worst|mistake|lesson|surprising|crazy|insane|wild|game.?changer)\b"
EMPH = r"\b(amazing|incredible|unbelievable|huge|massive|important|critical|breakthrough|historic|first time|record|love|hate|fear|excited|wow)\b"
FILLER = r"\b(um+|uh+|you know|like,|sort of|kind of)\b"


def sentences(t):
    """Split words into sentence units with times."""
    out, cur = [], []
    for w in t.get("words") or []:
        if cur and w.get("speaker") != cur[-1].get("speaker"):  # never merge across a speaker change
            out.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.?!]$", w["text"]) and len(cur) >= 3:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    if not out:  # captions-only transcripts without words
        for u in t.get("utterances") or []:
            out.append([{"text": u["text"], "start": u["start"], "end": u["end"], "speaker": u.get("speaker")}])
    return [{"start": s[0]["start"], "end": s[-1]["end"], "text": " ".join(w["text"] for w in s),
             "speaker": s[0].get("speaker"), "nw": len(s)} for s in out]


def score_window(sents, hl, chapters):
    text = " ".join(s["text"] for s in sents); low = text.lower()
    dur = (sents[-1]["end"] - sents[0]["start"]) / 1000
    reasons, sc = [], 0.0
    hits = [h for h in hl if h["text"].lower() in low]
    if hits:
        v = sum(1 + (h.get("rank") or 0) * 3 for h in hits); sc += v
        reasons.append("key phrases: " + ", ".join(h["text"] for h in hits[:4]))
    first = sents[0]["text"].lower()
    if re.search(HOOKS, first):
        sc += 3; reasons.append("strong hook opener")
    elif re.search(HOOKS, low):
        sc += 1.5; reasons.append("hook language")
    q = text.count("?")
    if q:
        sc += min(q, 3) * 1.0; reasons.append(f"{q} question(s)")
    e = len(re.findall(EMPH, low))
    if e:
        sc += min(e, 4) * 0.8; reasons.append("emphasis/emotion")
    nums = len(re.findall(r"\b\d[\d,.%]*\b", text))
    if nums:
        sc += min(nums, 4) * 0.5; reasons.append("concrete numbers")
    nw = sum(s["nw"] for s in sents); wps = nw / max(dur, 1)
    if 2.2 <= wps <= 4.2:
        sc += 1.0
    elif wps < 1.2:
        sc -= 2; reasons.append("sparse speech")
    fill = len(re.findall(FILLER, low))
    sc -= fill * 0.3
    if text.rstrip()[-1:] in ".?!":
        sc += 0.8
    spk = len({s["speaker"] for s in sents})
    if spk >= 2:
        sc += 0.7; reasons.append(f"{spk}-speaker exchange")
    for c in chapters or []:
        if c.get("start") is not None and abs(c["start"] - sents[0]["start"]) < 3000:
            sc += 1.0; reasons.append(f"starts chapter '{c.get('headline')}'"); break
    return sc, reasons or ["coherent self-contained segment"], text


def rank(t, n=8, mn=15, mx=60):
    ss = sentences(t); hl = t.get("highlights") or []; ch = t.get("chapters") or []
    cands = []
    for i in range(len(ss)):
        for j in range(i, len(ss)):
            dur = (ss[j]["end"] - ss[i]["start"]) / 1000
            if dur > mx:
                break
            if dur >= mn or (j == len(ss) - 1 and i == 0):
                sc, why, text = score_window(ss[i:j + 1], hl, ch)
                sc += min(dur, 45) / 45  # mild preference for fuller clips
                cands.append({"start_ms": ss[i]["start"], "end_ms": ss[j]["end"], "score": round(sc, 2), "reasons": why, "text": text})
    cands.sort(key=lambda c: -c["score"])
    picked = []
    for c in cands:
        if all(c["end_ms"] <= p["start_ms"] or c["start_ms"] >= p["end_ms"] for p in picked):
            picked.append(c)
        if len(picked) >= n:
            break
    for k, p in enumerate(picked, 1):
        p.update({"rank": k, "start": round(p["start_ms"] / 1000, 2), "end": round(p["end_ms"] / 1000 + 0.25, 2),
                  "duration": round((p["end_ms"] - p["start_ms"]) / 1000, 1), "reason": "; ".join(p.pop("reasons"))})
    return picked


PROMPT = """You are a short-form video editor. From the timestamped, speaker-labelled transcript below, pick the {n} best
self-contained moments for Shorts/Reels/TikTok ({mn}-{mx}s each). Favour: a strong hook in the first 3 seconds,
a complete thought/payoff, surprising or quotable lines, concrete numbers/stories, emotion, clear stakes. Avoid clips
that need prior context, start mid-sentence, or end before the payoff. Do not invent text; quote only what is said.
Return ONLY JSON: [{{"rank":1,"start":<seconds>,"end":<seconds>,"title":"<=60 chars hook title",
"hook":"first line as said","reason":"why it works","caption":"post caption (no hashtags spam)"}}]

Title: {title}
Source: {source}
Chapters: {chapters}
Key phrases: {keyphrases}

Transcript (start seconds | speaker | text):
{lines}
"""


def prompt(t, n=8, mn=15, mx=60):
    lines = "\n".join(f"{s['start']/1000:.1f} | {s['speaker'] or 'A'} | {s['text']}" for s in sentences(t))
    return PROMPT.format(n=n, mn=mn, mx=mx, title=t.get("title"), source=t.get("source"),
                         chapters="; ".join(f"{c['start']/1000:.0f}s {c.get('headline')}" for c in t.get("chapters") or []) or "n/a",
                         keyphrases=", ".join(h["text"] for h in (t.get("highlights") or [])[:25]) or "n/a", lines=lines)


def snap(t, picks):
    ws = t.get("words") or []
    out = []
    for p in picks:
        s, e = float(p["start"]) * 1000, float(p["end"]) * 1000
        if ws:
            s = min(ws, key=lambda w: abs(w["start"] - s))["start"]
            e = min(ws, key=lambda w: abs(w["end"] - e))["end"]
        q = dict(p, start=round(s / 1000, 2), end=round(e / 1000 + 0.25, 2), duration=round((e - s) / 1000 + 0.25, 1),
                 text=" ".join(w["text"] for w in ws if s <= w["start"] <= e))
        out.append(q)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript"); ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--min", type=float, default=15); ap.add_argument("--max", type=float, default=60)
    ap.add_argument("--json", action="store_true"); ap.add_argument("--prompt", action="store_true"); ap.add_argument("--snap")
    a = ap.parse_args()
    t = load_transcript(a.transcript)
    if a.prompt:
        print(prompt(t, a.n, a.min, a.max)); return
    if a.snap:
        print(json.dumps(snap(t, json.load(open(a.snap))), indent=1)); return
    dur = (t.get("duration") or 0)
    mn = min(a.min, max(3, dur * 0.3)) if dur and dur < a.min * 2 else a.min
    res = rank(t, a.n, mn, a.max)
    if a.json:
        print(json.dumps(res, indent=1, ensure_ascii=False)); return
    for r in res:
        print(f"#{r['rank']}  {hms(r['start_ms'])}-{hms(r['end_ms'])} ({r['duration']}s) score {r['score']}\n    why: {r['reason']}\n    \"{r['text'][:220]}\"")


if __name__ == "__main__":
    main()
WL_EOF_SCRIPTS_WL_MOMENTS_PY
cat > "$WL_HOME/scripts/wl_library.py" <<'WL_EOF_SCRIPTS_WL_LIBRARY_PY'
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
WL_EOF_SCRIPTS_WL_LIBRARY_PY
cat > "$WL_HOME/scripts/wl_sync.py" <<'WL_EOF_SCRIPTS_WL_SYNC_PY'
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
WL_EOF_SCRIPTS_WL_SYNC_PY
cat > "$WL_HOME/tests/run_tests.py" <<'WL_EOF_TESTS_RUN_TESTS_PY'
#!/usr/bin/env python3
"""Real end-to-end tests per platform. Writes TEST_RESULTS.md + tests/results.json.
Steps per platform: download(video) -> mp3 -> transcribe(AssemblyAI) -> moments -> clip make (vertical+captions) -> ingest -> search.
Run: WL_DATA=$WL_HOME/tmp/testdata venv/bin/python tests/run_tests.py [platform ...]
"""
import json, os, pathlib, subprocess, sys, time, argparse
HERE = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("WL_DATA", str(HERE / "tmp" / "testdata"))
sys.path.insert(0, str(HERE / "scripts"))
import wl_dl, wl_transcribe, wl_moments, wl_clip, wl_library  # noqa
from wl_common import load_transcript, ffprobe_duration

CASES = {  # short, public, official/CC content
    "youtube": ("https://www.youtube.com/watch?v=jNQXAC9IVRw", None, "Me at the zoo (YouTube's first video, 19s, official YouTube co-founder upload)"),
    "x": ("https://x.com/NASA/status/2106061652617568263", None, "@NASA flight-director applications (40s)"),
    "tiktok": ("https://www.tiktok.com/@nasa/video/7692161454694206733", "0-60", "@nasa 'big week in low Earth orbit' (first 60s)"),
    "instagram": ("https://www.instagram.com/reel/DW2mVfojTkV/", None, "@nasa Artemis II Earthset reel"),
    "facebook": ("https://www.facebook.com/NASA/videos/artemis-ii-splashdown-promo/1211632377548396/", None, "NASA Artemis II splashdown promo"),
    "reddit": ("https://www.reddit.com/r/nasa/comments/1samd8p/artemis_ii_launches_around_the_moon_official_nasa/", "0-60", "r/nasa official Artemis II recap (first 60s)"),
    "vimeo": ("https://vimeo.com/1084537", "0-45", "Big Buck Bunny (Blender Foundation, CC-BY; first 45s)"),
}


def step(res, name, fn):
    t0 = time.time()
    try:
        out = fn(); ok = bool(out)
        res["steps"][name] = {"ok": ok, "secs": round(time.time() - t0, 1), "detail": out if isinstance(out, (str, int, float, dict)) else str(out)[:300]}
        return out
    except BaseException as e:
        res["steps"][name] = {"ok": False, "secs": round(time.time() - t0, 1), "detail": f"{type(e).__name__}: {str(e)[:300]}"}
        return None


def run_case(plat, url, section, desc):
    res = {"platform": plat, "url": url, "desc": desc, "steps": {}}
    data = pathlib.Path(os.environ["WL_DATA"]); out = data / "downloads" / plat
    extra = ["--download-sections", "*" + section, "--force-keyframes-at-cuts"] if section else []
    r = step(res, "download_video", lambda: (lambda d: (res.__setitem__("dl", d), d["files"][0] if d.get("ok") else None)[1])(
        wl_dl.download(url, "video", out, 480, None, extra)))
    if res.get("dl"):
        res["steps"]["download_video"]["strategy"] = res["dl"].get("strategy"); res["steps"]["download_video"]["attempts"] = res["dl"].get("attempts")
        if not res["dl"].get("ok"):
            res["steps"]["download_video"]["detail"] = f"[{res['dl'].get('error_code')}] {res['dl'].get('error')}"
    video = r
    step(res, "mp3", lambda: wl_clip.mp3(video, out=str(data / "clips" / f"{plat}.mp3")) if video else None)
    ns = argparse.Namespace(out=str(data / "transcripts"), speakers=None, engine="assemblyai", lang=None, no_summary=False,
                            no_highlights=False, no_diarize=False, keyterms=None, whisper_model="small")
    tj = step(res, "transcribe", lambda: wl_transcribe.transcribe(video, ns) if video else None)
    if tj:
        t = load_transcript(tj)
        res["steps"]["transcribe"]["detail"] = {"engine": t["engine"], "words": len(t["words"]), "utterances": len(t["utterances"]),
                                                "speakers": len({u["speaker"] for u in t["utterances"]}), "chapters": len(t["chapters"]),
                                                "highlights": len(t["highlights"])}
    mom = step(res, "moments", lambda: (lambda m: {"n": len(m), "top": (m[0]["start"], m[0]["end"], m[0]["reason"]) if m else None})(
        wl_moments.rank(load_transcript(tj), 3, min(15, max(3, ffprobe_duration(video) * 0.3)), 60)) if tj else None)
    def mk():
        m = wl_moments.rank(load_transcript(tj), 1, min(15, max(3, ffprobe_duration(video) * 0.3)), 60) if tj else []
        s, e = (m[0]["start"], m[0]["end"]) if m else (0, min(15, ffprobe_duration(video)))
        o = wl_clip.make(video, s, e, tj if tj and load_transcript(tj)["words"] else None, "face", "bold", False,
                         str(data / "clips" / f"{plat}.short.mp4"))
        from wl_common import video_size
        return {"path": o, "size": video_size(o), "secs": round(ffprobe_duration(o), 1)}
    step(res, "vertical_clip_captions", lambda: mk() if video else None)
    vid = step(res, "library_ingest", lambda: wl_library.ingest(tj, video) if tj else None)
    def srch():
        t = load_transcript(tj); words = [w["text"].strip(".,!?").lower() for w in t["words"] if len(w["text"]) > 5]
        if not words:
            h, v = wl_library.search(t.get("title", "video").split()[0])
            return {"query": "(title)", "hits": len(h) + len(v)} if (h or v) else None
        q = words[len(words) // 2]; h, _ = wl_library.search(q)
        h = [x for x in h if x["id"] == vid]
        return {"query": q, "hits": len(h), "link": h[0]["link"]} if h else None
    step(res, "library_search", lambda: srch() if vid else None)
    return res


def main():
    plats = sys.argv[1:] or list(CASES)
    resf = HERE / "tests" / "results.json"
    allres = json.loads(resf.read_text()) if resf.exists() else {}
    for p in plats:
        print(f"=== {p}", flush=True)
        r = run_case(p, *CASES[p]); r["ran_at"] = time.strftime("%Y-%m-%d %H:%M %Z")
        allres[p] = r
        for k, v in r["steps"].items():
            print(f"  {'PASS' if v['ok'] else 'FAIL'} {k} ({v['secs']}s) {str(v['detail'])[:160]}", flush=True)
        resf.write_text(json.dumps(allres, indent=1, default=str))


if __name__ == "__main__":
    main()
WL_EOF_TESTS_RUN_TESTS_PY
chmod +x "$WL_HOME/install.sh" "$WL_HOME"/scripts/*
bash "$WL_HOME/install.sh"            # add --whisper for local transcription fallback, --no-pot to skip PO tokens
export PATH="$WL_HOME/bin:$PATH"; wl doctor
```
Optional self-test (downloads ~40 MB of short public NASA/CC clips, uses AssemblyAI credits for ~5 min audio):
`WL_DATA=$WL_HOME/tmp/testdata $WL_HOME/venv/bin/python $WL_HOME/tests/run_tests.py youtube x tiktok`
Env: `ASSEMBLYAI_API_KEY` (transcription), optional `X_BEARER_TOKEN` (X creator listing), optional `WL_DATA`, `WL_DB`, `WL_CREATORS`.

## How the downloader avoids the usual failures (2026)
`wl dl` tries strategies in order and stops at the first success; each failure is classified
(`YOUTUBE_BOT_CHECK`, `RATE_LIMITED`, `LOGIN_WALL`, `DRM`, `PRIVATE`, `GEO_BLOCKED`, `TIKTOK_IP_BLOCK`, `NO_FORMATS`, ...)
and the final message says what happened and what would fix it.
- **YouTube**: yt-dlp nightly + `yt-dlp-ejs` + **deno** (yt-dlp's recommended JS runtime; bun support is deprecated
  after 1.3.14) solves the n/sig challenges; **bgutil PO-token provider** (plugin + local HTTP server on 127.0.0.1:4416,
  auto-started) supplies GVS PO tokens. Chain: `mweb + player_skip=webpage` (skipping the watch page avoids the 429/
  "Sign in to confirm you're not a bot" that datacenter IPs get) -> `web_embedded + skip webpage` -> default ->
  `tv,web_safari` -> `android_vr` -> impersonated mweb -> **captions-only fallback** (exit code 3, `partial: captions_only`).
  Channel listing uses `player_skip=webpage`, falling back to the public RSS feed.
- **X/Twitter**: `twitter:api=syndication` -> graphql -> syndication + Chrome impersonation -> legacy. Downloads never need the
  X API. Creator listing: X API v2 only if `X_BEARER_TOKEN` is set *and* has credits (402/429/401 fall through; set
  `WL_X_API=0` to skip it) -> public syndication timeline (often 429 from datacenter IPs) -> explicit post URLs.
- **TikTok**: plain -> impersonate chrome -> safari -> `app_info` API variant.
- **Instagram / Facebook**: plain -> curl-cffi impersonate chrome -> safari -> page scrape for a direct MP4
  (`video_url`, `playable_url`, `browser_native_*_url`, `og:video`, incl. JSON-escaped page data), validated with ffprobe.
- **Reddit**: plain -> impersonate -> `v.redd.it/<id>` direct (v.redd.it links also work as input).
- **Vimeo**: logged-out web API now needs login, so the chain retries via the `player.vimeo.com/video/ID` embed with a
  vimeo.com referer. Videos whose HLS is FairPlay/Widevine-encrypted are reported as `DRM` and skipped (by design).
- Not used: Invidious/Piped (unreliable in 2026), browser-cookie extraction, account logins.
- Last-resort options to offer the user (never automatic): run later (IP cool-down), a residential proxy
  (`wl dl URL -- --proxy http://...`), or their own cookies file (`--cookies cookies.txt`).

## Transcription details
- AssemblyAI `/v2/transcript`: `speech_models: ["universal-3-5-pro","universal-2"]`, `speaker_labels`, word timestamps,
  `language_detection`, `auto_highlights` (key phrases), and chapters via **Speech Understanding summarization**
  (`speech_understanding.request.summarization`, because `auto_chapters` was removed on 2026-09-15). If the account
  rejects an optional feature, the request is retried without it. Long files: upload is streamed; polling up to 1 h.
- `--engine whisper` (install with `bash install.sh --whisper`) = local faster-whisper (no diarization).
  `--engine captions` = platform subtitles (no diarization; YouTube roll-up duplicates removed).
- Normalized `*.transcript.json`: `{title, source, engine, language, duration, utterances[{speaker,start,end,text}],
  words[{text,start,end,speaker,confidence}], chapters[{start,end,headline,summary}], highlights[{text,rank,count,timestamps}], info{...}}`
  (times in ms). Every other command consumes this file (or any `.srt`).

## Best moments: LLM pass (preferred when you have time)
1. `wl moments T.json --prompt --n 6 > /tmp/prompt.txt` and answer that prompt yourself (JSON list of picks).
2. Save your JSON to `picks.json`; `wl moments T.json --snap picks.json` snaps start/end to word boundaries and adds text.
3. Cut each: `wl clip make VIDEO --start <start> --end <end> --transcript T.json --vertical face`.
Heuristic fallback (`wl moments T.json`) scores key phrases, hook openers, questions, emphasis, numbers, speech
density, clean sentence ends, multi-speaker exchanges and chapter starts, and returns non-overlapping windows.

## Library
`data/library.db` (SQLite + FTS5, porter stemming). Tables: `videos` (platform, author, handle, url, title,
upload_date, duration, media/transcript paths, engine, chapters, highlights), `segments` (~20 s speaker turns with
start/end ms), `segments_fts`, `videos_fts`, `seen` (sync state). `wl search` supports FTS syntax: `"exact phrase"`,
`a OR b`, `prefix*`, `NEAR(a b, 5)`; results include deep links (`&t=123s` for YouTube, `#t=` for Vimeo, else `url @m:ss`).

## Creator tracking
`config/creators.json` lists handles per platform (`youtube`: `@handle` or `UC...` id; `x`: handle; `tiktok`: handle;
`instagram`: handle or post URLs; `facebook`: page name or video URLs; `other`: playlist/channel URLs).
`wl sync [--limit N] [--audio-only] [--no-transcribe] [--since YYYYMMDD] [--platform P] [--dry-run]` lists new public
videos, downloads, transcribes, ingests. Items already done are skipped; failed items retry up to 3 times.
Instagram profile listing is usually login-walled from datacenter IPs: tell the user and offer to process reel
URLs they paste (or that you find via web search) instead. Facebook page listing is best effort (latest video).
X profile listing without API credits is usually 429: find recent post URLs with web search (`site:x.com/<handle>/status`)
or the X connector if it has credits, then `wl track add x https://x.com/<handle>/status/<id>` (or `wl dl` them directly).

## Platform status (tested 2026-10-05 from a datacenter IP, no cookies)
| Platform | Single video | Strategy that worked | Creator listing |
|---|---|---|---|
| YouTube | OK (watch, youtu.be, Shorts, subs-only) | mweb + PO token + skip-webpage | OK (yt-dlp, RSS fallback) |
| X | OK (x.com + twitter.com, multi-video posts) | syndication | X API if credits, else explicit URLs |
| TikTok | OK | default | OK |
| Instagram | OK (reels, posts) | default (page-scrape fallback verified) | blocked (login wall) -> explicit URLs |
| Facebook | OK (page videos) | default (page-scrape fallback verified) | latest video via page scrape |
| Reddit | OK (v.redd.it with audio) | default | n/a (use URLs) |
| Vimeo | OK (non-DRM) | player embed / default | yt-dlp channel/showcase URLs via `other` |

## Troubleshooting
- `wl doctor` shows versions, JS runtime, PO-token server, keys (set/missing only).
- `wl update` (= re-run install.sh) when a platform breaks: it upgrades yt-dlp nightly, yt-dlp-ejs, plugins.
- YouTube `YOUTUBE_BOT_CHECK`/`RATE_LIMITED` on every strategy = this IP is flagged right now. Use the saved captions
  (exit code 3), wait 15-60 min, or ask the user for a proxy/cookies file. Don't hammer: one retry later.
- `LOGIN_WALL` on Instagram/Facebook = platform demands login for this IP; report it, don't log in.
- Captions font: install `fonts-dejavu-core` if text renders as boxes.
