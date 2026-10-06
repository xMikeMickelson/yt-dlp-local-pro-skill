#!/usr/bin/env bash
# Fetch the Watch Later toolkit into WL_HOME and run install.sh.
# Safe to re-run: scripts and docs refresh, downloads and creators.json stay.
#
#   curl -fsSL https://raw.githubusercontent.com/xMikeMickelson/yt-dlp-local-pro-skill/main/watch-later/bootstrap.sh | bash
#
# Env:
#   WL_HOME      install directory. Default: /workspace/watch-later when /workspace
#                is writable, otherwise ~/watch-later. Same rule as install.sh.
#   WL_REPO      GitHub owner/name. Default is this public repository.
#   WL_REF       git ref to download. Default: main.
#   WL_SRC       local watch-later directory to copy instead of downloading.
#   WL_RAW_BASE  full raw URL prefix, overrides WL_REPO and WL_REF.
set -euo pipefail
# One compound command so a re-run can replace this file on disk after bash has read it.
{

WL_REPO="${WL_REPO:-xMikeMickelson/yt-dlp-local-pro-skill}"
WL_REF="${WL_REF:-main}"
if [[ -z "${WL_HOME:-}" ]]; then
  if [[ -w /workspace ]]; then WL_HOME=/workspace/watch-later; else WL_HOME="${HOME}/watch-later"; fi
fi
export WL_HOME

FILES=(
  bootstrap.sh
  install.sh
  README.md
  SKILL.md
  TEST_RESULTS.md
  RESEARCH.md
  config/yt-dlp.conf
  config/creators.json
  scripts/wl
  scripts/wl_clip.py
  scripts/wl_common.py
  scripts/wl_dl.py
  scripts/wl_library.py
  scripts/wl_moments.py
  scripts/wl_sync.py
  scripts/wl_transcribe.py
)

log() { printf '\033[1;36m[bootstrap]\033[0m %s\n' "$*"; }

fetch_one() {
  local rel="$1"
  local dest="$WL_HOME/$rel"
  local tmp
  mkdir -p "$(dirname "$dest")"
  tmp="$(mktemp)"
  if [[ -n "${WL_SRC:-}" ]]; then
    cp -f "$WL_SRC/$rel" "$tmp"
  else
    local base="${WL_RAW_BASE:-https://raw.githubusercontent.com/${WL_REPO}/${WL_REF}/watch-later}"
    curl -fsSL "${base}/${rel}" -o "$tmp"
  fi
  mv "$tmp" "$dest"
}

log "WL_HOME=$WL_HOME"
mkdir -p "$WL_HOME"/{bin,scripts,data/{downloads,transcripts,clips},config,tmp,logs}
for rel in "${FILES[@]}"; do
  if [[ "$rel" == "config/creators.json" && -f "$WL_HOME/config/creators.json" ]]; then
    log "keeping existing config/creators.json"
    continue
  fi
  log "fetch $rel"
  fetch_one "$rel"
done
chmod +x "$WL_HOME/install.sh" "$WL_HOME/bootstrap.sh" "$WL_HOME"/scripts/wl "$WL_HOME"/scripts/*.py
log "running install.sh"
bash "$WL_HOME/install.sh" "$@"
log "ready. export PATH=\"$WL_HOME/bin:\$PATH\" && wl doctor"
}
