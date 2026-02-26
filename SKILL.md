---
name: yt-dlp-local-pro
description: Build, harden, and operate a production-grade local yt-dlp API server for multi-platform downloading (YouTube, Instagram, TikTok, X/Twitter, Facebook) with per-platform proxies, cookie auth, retries, and OpenClaw integration. Use when setting up a self-hosted downloader service, debugging auth/rate-limit failures, or standardizing agent workflows to call a local download API instead of direct yt-dlp CLI.
---

# yt-dlp-local-pro

Implement and run a local HTTP wrapper around yt-dlp with production patterns:
- API endpoints for extract/download/audio/formats/serve
- per-platform sticky proxy routing
- cookie-based auth for gated content
- retry + backoff on transient network failures
- platform-specific fallback logic (especially Instagram)

## Read These References As Needed

- Architecture and request flow: `references/architecture.md`
- Endpoint contract + payloads: `references/api-contract.md`
- Proxy + cookies strategy: `references/proxy-cookie-strategy.md`
- Hardening + ops + monitoring: `references/hardening-ops.md`
- Failure triage: `references/troubleshooting.md`
- Exact implementation parity checklist: `references/local-parity-checklist.md`

## Standard Build Plan (Exact Replica Path)

1. Create service directory and Python venv.
2. Copy **reference implementation files** from `assets/service-template/`:
   - `app.py`
   - `config.py`
   - `requirements.txt`
   - `.env.example` -> `.env`
   - `yt-dlp-local.service.template` -> rendered systemd unit
3. Install dependencies from `requirements.txt`.
4. Add cookie files under `cookies/` and wire env paths.
5. Add proxy env and per-platform sticky ports.
6. Install/start systemd unit.
7. Run smoke tests and parity checklist (`references/local-parity-checklist.md`).
8. Integrate OpenClaw workflows to call local API, not direct CLI.

## Directory Layout

Use this layout:

```text
yt-dlp-local/
├── app.py
├── config.py
├── .env
├── requirements.txt
├── yt-dlp-local.service
├── cookies/
│   ├── youtube.txt
│   ├── instagram.txt
│   ├── instagram_master.txt
│   └── tiktok.txt
├── downloads/
│   ├── youtube/
│   ├── instagram/
│   ├── tiktok/
│   ├── twitter/
│   └── facebook/
└── logs/
```

## Minimal Requirements

- Python 3.11+
- `ffmpeg` installed (for merges/audio extraction)
- writable download/log directories
- valid cookie exports for gated platforms
- proxy provider (optional but recommended for reliability)

## `.env` Template (Sanitized)

Use placeholders only (do not publish personal paths, host IPs, usernames, or keys):

```bash
HOST=127.0.0.1
PORT=5000

DOWNLOAD_DIR=<SERVICE_DIR>/downloads
LOG_DIR=<SERVICE_DIR>/logs

YOUTUBE_COOKIES=cookies/youtube.txt
INSTAGRAM_COOKIES=cookies/instagram.txt
TIKTOK_COOKIES=cookies/tiktok.txt

# Optional proxy
PROXY_HOST=proxy-provider.example.com
PROXY_USER=YOUR_PROXY_USERNAME
PROXY_PASS=YOUR_PROXY_PASSWORD

# Sticky per-platform sessions
PROXY_PORT_YOUTUBE=20501
PROXY_PORT_INSTAGRAM=20502
PROXY_PORT_TIKTOK=20503
PROXY_PORT_TWITTER=20504
PROXY_PORT_FACEBOOK=20505
PROXY_PORT_DEFAULT=20506
```

## Service Management (systemd)

Render/install unit from template and enable:

```bash
# Option 1: helper script
sudo scripts/install-systemd.sh <SERVICE_DIR> <SERVICE_USER>

# Option 2: manual render + install
# 1) replace <SERVICE_DIR> and <SERVICE_USER> in assets/service-template/yt-dlp-local.service.template
# 2) copy to /etc/systemd/system/yt-dlp-local.service
# 3) daemon-reload + enable --now
```

## API Contract (Core)

- `GET /health` → service status + cookie/proxy readiness
- `POST /api/extract` → metadata only
- `POST /api/download` → full video download
- `POST /api/audio` → audio-only extraction
- `POST /api/formats` → available formats
- `POST /api/instagram/private` → Instagram private/auth fallback path
- `GET /api/serve/<path>` → file serving (optional)

See exact examples: `references/api-contract.md`.

## Multi-Platform Techniques

### 1) Platform detection
Route by URL domain to platform-specific options.

### 2) Per-platform sticky proxies
Assign stable proxy ports by platform to reduce anti-bot churn while keeping isolation.

### 3) Cookie-aware option builder
Attach cookie files by platform only when available.

### 4) Retry transient failures
Retry network/SSL/proxy transport errors with exponential backoff.

### 5) Platform-specific extractor tweaks
Use custom headers/extractor args where needed (notably Instagram).

### 6) Fallback strategy
On hard failures, trigger platform-specific fallback paths instead of immediate fail.

## Instagram Playbook (Critical)

1. First attempt normal yt-dlp path with cookies + proxy.
2. Preserve a master cookie file (`instagram_master.txt`).
3. Use a temporary copy for requests so session cookies are not corrupted.
4. For gated failures (`login required`, `private`, `rate-limit`), fallback to private API path when authorized cookies exist.
5. Return structured error with both primary and fallback failure details if both paths fail.

## OpenClaw Integration Rules

Prefer local API call from agents:

```bash
curl -s -X POST http://127.0.0.1:5000/api/download \
  -H "Content-Type: application/json" \
  -d '{"url":"VIDEO_URL"}'
```

Then copy result to allowed media path before sending in chat.

Do not default to direct `yt-dlp` CLI in agent flows unless explicitly required for a documented exception.

## Security Baseline

- Bind to loopback (`127.0.0.1`) by default.
- Never commit real `.env` or cookie files.
- Keep cookie files permissioned (`chmod 600`).
- Treat `/api/serve` as optional; disable if not needed.
- Add allowlist/reverse proxy auth if exposed beyond localhost.

## Operations Checklist

- Health: `curl -s http://127.0.0.1:5000/health`
- Logs: `journalctl -u yt-dlp-local -f`
- Restart: `sudo systemctl restart yt-dlp-local`
- Verify cookies and proxy state via `/health`
- Run endpoint smoke tests after every deploy

## Troubleshooting Workflow

1. Confirm service is running.
2. Confirm cookie files exist and are readable.
3. Confirm proxy credentials/ports.
4. Reproduce with `/api/extract` first.
5. Retry with `/api/download` and inspect returned error payload.
6. For Instagram: verify session cookie validity and fallback behavior.

Use `references/troubleshooting.md` for symptom-driven fixes.

## Deliverables for a Production Setup

- Working systemd-managed API service
- Stable downloads to platform subfolders
- Cookie/proxy-aware success across target platforms
- Deterministic JSON responses for automation
- Documented fallback paths for anti-bot/auth failures
