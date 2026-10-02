# Architecture

## Core Components

1. **Flask API Layer**
   - Validates request payloads
   - Selects endpoint workflow (`extract`, `download`, `audio`, `formats`)
   - Returns stable JSON for agent tooling

2. **Config Loader (`config.py`)**
   - Loads env vars and optional `.env`
   - Resolves relative cookie paths
   - Builds per-platform proxy URLs

3. **yt-dlp Execution Layer**
   - Builds platform-specific yt-dlp options
   - Applies format policy (`best`, `worst`, capped height)
   - Handles merge/audio postprocessing

4. **Reliability Layer**
   - Transient error classifier
   - Retry decorator with exponential backoff

5. **Platform Fallback Layer**
   - Primary downloader path (yt-dlp extractor)
   - Optional platform-specific fallback path

6. **Storage + Logging Layer**
   - Platform-scoped downloads directory
   - Service logs (journal + file)

## Request Flow (Download)

1. Receive URL + options
2. Detect platform from domain and reject unsupported URLs (TikTok `/photo/`, Instagram profiles and `/share/`)
3. Build yt-dlp options (cookies, sticky proxy, format, subtitles/infojson/description, documented extractor args)
4. Download in one pass with a relative outtmpl under `paths.home` (Instagram web app_id retries once with ios on a login wall or empty media)
5. Collect every new media file and sidecar; do not assume a single `title-id` file
6. If a known Instagram auth/gating failure remains: run the private API fallback (posts, carousels, stories, highlights)

## Platform Strategy Matrix

| Platform | Cookies | Proxy | Special Handling |
|---|---:|---:|---|
| YouTube | Recommended | Recommended | Prefer split streams + merge mp4 |
| Instagram | Required for private/gated | Highly recommended | web app_id, one ios retry, temp cookie copy, stories/highlights fallback |
| TikTok | Recommended | Highly recommended | 10204 means rotate proxy or source address; `/photo/` is not a video |
| X/Twitter | Optional | Recommended | logged-out uses syndication; cookies keep the default API |
| Facebook | Optional | Recommended | extractor variability by post type |

## Why API Wrapper Instead of Raw CLI

- Deterministic JSON outputs for automation
- Centralized retries/cookies/proxy behavior
- Single control point for hardening + observability
- Easier integration with OpenClaw agents and cron jobs
