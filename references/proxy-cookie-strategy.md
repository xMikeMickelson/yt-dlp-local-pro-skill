# Proxy + Cookie Strategy

## Goals

- Keep platform sessions stable while reducing global bans.
- Preserve authenticated access for gated/private content.
- Avoid cookie corruption from downloader side effects.

## Proxy Model

Use **sticky sessions per platform**:

- YouTube -> port A
- Instagram -> port B
- TikTok -> port C
- X/Twitter -> port D
- Facebook -> port E
- Default -> fallback port

Why this works:
- Cross-platform failures are isolated.
- Reputation and challenge state stay platform-local.
- Easier debugging: failures map to one platform port.

## Cookie Model

Use dedicated cookie files per platform.

- `cookies/youtube.txt`
- `cookies/instagram.txt`
- `cookies/tiktok.txt`

### Instagram hardening pattern

Maintain a `instagram_master.txt` file and copy to temp for each run.

Reason: some flows rewrite cookie files and can strip critical session values over time.

Flow:
1. Read master cookie file.
2. Copy to temporary file.
3. Pass temp file to downloader.
4. Leave master untouched.

## Cookie Hygiene

- Export from a real logged-in browser session.
- Prefer fresh exports for unstable platforms.
- Set strict permissions (`chmod 600`).
- Never commit cookies to git.
- Rotate if repeated auth failures appear.

## Header + Extractor Tuning

For sensitive platforms (Instagram/TikTok), add realistic headers and extractor args where supported.

## Failure Policy

Classify errors:

- **Transient**: SSL reset, timeouts, DNS temp errors, proxy transport failures -> retry with backoff.
- **Auth/gating**: login required, private content, challenge/rate-limit -> trigger platform fallback or cookie refresh workflow.
- **Hard invalid**: bad URL, removed content -> fail fast with clear error.
