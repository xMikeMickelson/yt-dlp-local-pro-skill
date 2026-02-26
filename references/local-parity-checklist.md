# Local Parity Checklist (v1.1.0)

This checklist mirrors the reference implementation in `assets/service-template/`.
Use it to verify your deployed instance behaves the same way.

## 1) Config + Environment

- [ ] `HOST`, `PORT`, `DOWNLOAD_DIR`, `LOG_DIR` loaded from env/.env
- [ ] cookie vars present: `YOUTUBE_COOKIES`, `INSTAGRAM_COOKIES`, `TIKTOK_COOKIES`
- [ ] proxy vars present: `PROXY_HOST`, `PROXY_USER`, `PROXY_PASS`
- [ ] sticky ports present:
  - `PROXY_PORT_YOUTUBE`
  - `PROXY_PORT_INSTAGRAM`
  - `PROXY_PORT_TIKTOK`
  - `PROXY_PORT_TWITTER`
  - `PROXY_PORT_FACEBOOK`
  - `PROXY_PORT_DEFAULT`

## 2) Platform Detection

- [ ] Instagram: `instagram.com`, `instagr.am`
- [ ] TikTok: `tiktok.com`
- [ ] Twitter/X: `twitter.com`, `x.com`
- [ ] Facebook: `facebook.com`, `fb.com`, `fb.watch`
- [ ] fallback: YouTube

## 3) Endpoints

- [ ] `GET /`
- [ ] `GET /health`
- [ ] `POST /api/extract`
- [ ] `POST /api/download`
- [ ] `POST /api/audio`
- [ ] `POST /api/formats`
- [ ] `POST /api/instagram/private`
- [ ] `GET /api/serve/<path>` with path traversal protection

## 4) Retry Behavior

- [ ] transient retry wrapper enabled for extract/download paths
- [ ] max retries = 3
- [ ] exponential backoff base = 2
- [ ] transient patterns include SSL/network/proxy transport classes

## 5) Download Behavior

- [ ] sanitize filename and cap title length
- [ ] output path: `<download_dir>/<platform>/<title>-<id>.<ext>`
- [ ] if duplicate exists, append timestamp suffix
- [ ] return structured JSON (`success`, `file_path`, `file_size_mb`, etc.)

## 6) Format Rules

- [ ] YouTube `best` -> `bestvideo+bestaudio/best`
- [ ] non-YouTube `best` -> `best`
- [ ] numeric quality applies `height<=N` selector
- [ ] YouTube merge output format set to `mp4`
- [ ] audio-only extraction outputs `m4a` (preferredquality 192)

## 7) Instagram-Specific Logic

- [ ] extractor args set with web app id (`936619743392459`)
- [ ] browser-like headers present for request hardening
- [ ] uses `instagram_master.txt` copy to temp file when available
- [ ] fallback trigger on auth/gating keywords in `/api/download`
- [ ] `/api/instagram/private` fallback requires `sessionid` cookie
- [ ] shortcode -> media id conversion path present
- [ ] fallback returns structured `yt_dlp_error` + `api_error` on dual failure

## 8) Health Payload Parity

- [ ] reports cookie readiness booleans
- [ ] reports proxy enabled/host/ports fields
- [ ] reports version and download directory

## 9) Service Ops

- [ ] systemd unit restarts on failure
- [ ] logs to journal and file
- [ ] smoke test run passes (`/health`, `/api/extract`)

## 10) OpenClaw Usage Parity

- [ ] agents call local API (`/api/download`) instead of direct yt-dlp CLI by default
- [ ] downloaded files copied into allowed messaging directory before send
