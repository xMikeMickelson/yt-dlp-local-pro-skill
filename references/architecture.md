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
2. Detect platform from domain
3. Extract metadata first
4. Build safe filename and output template
5. Build yt-dlp options:
   - cookies (if configured)
   - proxy (if configured)
   - format strategy
   - headers/extractor args
6. Execute download with retry wrapper
7. Discover resulting file and return JSON payload
8. If known platform-specific auth/gating failure: run fallback path

## Platform Strategy Matrix

| Platform | Cookies | Proxy | Special Handling |
|---|---:|---:|---|
| YouTube | Recommended | Recommended | Prefer split streams + merge mp4 |
| Instagram | Required for private/gated | Highly recommended | temp cookie copy + fallback path |
| TikTok | Recommended | Highly recommended | anti-bot pressure is common |
| X/Twitter | Optional | Recommended | short-lived media URLs can expire |
| Facebook | Optional | Recommended | extractor variability by post type |

## Why API Wrapper Instead of Raw CLI

- Deterministic JSON outputs for automation
- Centralized retries/cookies/proxy behavior
- Single control point for hardening + observability
- Easier integration with OpenClaw agents and cron jobs
