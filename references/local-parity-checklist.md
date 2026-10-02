# Local Parity Checklist (v1.2.0)

This checklist mirrors the reference implementation in `assets/service-template/`.
Use it to verify your deployed instance behaves the same way.

## 1) Config + Environment

- [ ] `HOST`, `PORT`, `DOWNLOAD_DIR`, `LOG_DIR` loaded from env/.env
- [ ] cookie vars present: `YOUTUBE_COOKIES`, `INSTAGRAM_COOKIES`, `TIKTOK_COOKIES` (optional `TWITTER_COOKIES`, `COOKIES_FROM_BROWSER`, `USER_AGENT`)
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
- [ ] relative outtmpl under the platform dir (`paths.home`): `%(title).80S [%(id)s] %(playlist_index|)s.%(ext)s`
- [ ] playlist results (carousels, stories) return every media file in `files`, plus `sidecars`
- [ ] do not assume one `title-id.*` file
- [ ] `noplaylist` only when the request sets `noplaylist`, `single_slide`, or `single_frame`
- [ ] return structured JSON (`success`, `file_path`, `files`, `file_size_mb`, etc.)
- [ ] download options include writesubtitles, subtitleslangs `en.*` and `.*-orig`, writeinfojson, writedescription, retries 10, extractor_retries 3, fragment_retries 10, sleep_interval_requests 0.75, sleep_interval 5, max_sleep_interval 10
- [ ] impersonate is not set globally; dependency is `yt-dlp[default,curl-cffi]`

## 6) Format Rules

- [ ] YouTube `best` -> `bestvideo+bestaudio/best`
- [ ] non-YouTube `best` -> `best`
- [ ] numeric quality applies `height<=N` selector
- [ ] YouTube merge output format set to `mp4`
- [ ] audio-only extraction outputs `m4a` (preferredquality 192)

## 7) Instagram-Specific Logic

- [ ] extractor args default to web app id (`app_id=web`, `936619743392459`)
- [ ] login wall or empty media retries once with `app_id=ios`
- [ ] User-Agent comes from `USER_AGENT` and is documented as matching the cookie browser (default reduced Chrome 154)
- [ ] uses `instagram_master.txt` copy to temp file when available
- [ ] fallback trigger on auth/gating keywords in `/api/download`
- [ ] `/api/instagram/private` fallback requires `sessionid` cookie
- [ ] shortcode -> media id conversion path present for `/p/`, `/reel/`, `/reels/`, `/tv/`
- [ ] stories and highlights are accepted by the private API fallback
- [ ] `/share/` and `instagram:user` profile URLs are rejected with a clear error
- [ ] fallback returns structured `yt_dlp_error` + `api_error` on dual failure
- [ ] logged-out X sets `twitter:api=syndication`; cookies leave the default
- [ ] TikTok `/photo/` is rejected; status 10204 tells the caller to rotate proxy or source address

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
