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
- `cookies/twitter.txt` (optional; when absent, logged-out X uses `twitter:api=syndication`)

Files must be Netscape format. The first line is `# Netscape HTTP Cookie File`.
Instagram gated downloads need `sessionid`. TikTok needs `sid_tt`. Do not print those values.

`--cookies-from-browser` is optional and is used only when that platform has no cookie file.
On Linux, Chromium decryption needs the optional `secretstorage` extra (Gnome keyring). Do not require it on other platforms.

The request User-Agent must match the browser that exported the cookies. Set `USER_AGENT` when it does not. The default is reduced Chrome 154 (`Chrome/154.0.0.0`), matching stable `154.0.8037.97` verified 2026-10-01.

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
- After a login wall, or when yt-dlp reports the Instagram cookies are no longer valid, re-export. Do not keep using a jar yt-dlp invalidated. With curl-cffi the `sessionid` may remain in the file even after yt-dlp tried to clear it.

## Header + Extractor Tuning

For Instagram, pass documented `extractor_args` `app_id=web` (the default, `936619743392459`) and a User-Agent that matches the cookie export. If web returns a login wall or empty media, retry once with `app_id=ios`. Do not invent TikTok `app_info` or `device_id`. Do not force a global impersonate target; install the `curl-cffi` extra instead.

## Failure Policy

Classify errors:

- **Transient**: SSL reset, timeouts, DNS temp errors, proxy transport failures -> retry with backoff.
- **Auth/gating**: login required, private content, challenge/rate-limit -> trigger platform fallback or cookie refresh workflow.
- **Hard invalid**: bad URL, removed content -> fail fast with clear error.
