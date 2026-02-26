# Hardening + Operations

## Security Baseline

1. Bind service to loopback unless explicitly needed externally.
2. Place service behind reverse proxy auth if exposed.
3. Keep `.env` and cookies out of git.
4. Restrict file permissions:
   - `.env`: 600
   - cookies: 600
   - service dir: least privilege
5. Validate file-serving paths (prevent traversal).

## Systemd Recommendations

- `Restart=always`
- `RestartSec=5`
- dedicated service user
- explicit venv path in `ExecStart`

Optional hardening options:
- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ProtectSystem=strict` (if compatible)
- `ProtectHome=read-only` (if compatible)

## Observability

- Structured-ish logs with timestamp + level
- Log endpoint calls, platform selection, and top-level failures
- Avoid logging secrets (cookies, proxy password)
- Keep log rotation policy in place

## Health and SLO Checks

- `/health` every 1-5 min
- synthetic download checks on key platforms
- alert when repeated failures exceed threshold

## Maintenance Routine

Daily:
- check service health
- scan recent failures by platform

Weekly:
- refresh stale cookies on unstable platforms
- validate proxy port health and ban rates
- update yt-dlp and retest critical flows

After updates:
- run endpoint smoke test matrix:
  - extract + download for each active platform
  - audio endpoint
  - formats endpoint
