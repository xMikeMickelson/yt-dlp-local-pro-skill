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
