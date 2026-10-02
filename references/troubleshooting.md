# Troubleshooting

## 1) `/health` says cookies=false

Cause:
- cookie path missing or unreadable

Fix:
- verify file exists
- verify path resolution (relative vs absolute)
- `chmod 600 cookies/*.txt`

---

## 2) Repeated `login required` / `private` on Instagram

Cause:
- stale/invalid session cookie
- cookie file corruption

Fix:
- export fresh logged-in cookie
- keep immutable master cookie and use temp copy pattern
- verify session key is present in cookie file

---

## 3) Frequent timeout/SSL/proxy errors

Cause:
- unhealthy proxy route
- intermittent upstream network failures

Fix:
- confirm proxy credentials and host
- test each sticky port
- enable retry-on-transient with backoff
- rotate problematic platform port mapping

---

## 4) Download succeeded but file not found

Cause:
- mismatch between expected ext and actual output
- output template mismatch

Fix:
- collect every file written in the platform directory during the run
- carousels and stories produce multiple media files plus `.info.json`, `.description`, and subtitles
- template is `%(title).80S [%(id)s] %(playlist_index|)s.%(ext)s` under `paths.home`
- do not assume one `<title>-<id>.*` file

---

## 5) TikTok/Instagram works manually but fails in agent

Cause:
- agent bypassing local API and calling direct CLI

Fix:
- enforce API-only workflow in skill/tooling docs
- add lint/check in task scripts if needed

---

## 6) YouTube returns 403 on some hosts

Cause:
- anti-bot challenge / extractor/runtime behavior

Fix:
- try runtime/header/cookie adjustments per host policy
- if a known documented workaround exists in your environment, apply that exception explicitly

---

## 7) Service flaps under load

Cause:
- no concurrency limits/backpressure

Fix:
- add request queue or worker model
- cap concurrent downloads
- tune system resources and systemd restart policy

---

## 8) TikTok status 10204

Cause:
- TikTok is blocking the source IP

Fix:
- rotate proxy or source address
- do not invent `app_info` or `device_id` extractor args

---

## 9) TikTok `/photo/` URL

Cause:
- the video extractor does not accept photo posts

Fix:
- pass a `/video/` URL
- `vm.tiktok.com` and `vt.tiktok.com` short links to videos still work

---

## 10) Instagram profile or `/share/` URL

Cause:
- `instagram:user` is broken (`_WORKING = False`)
- `/share/` is excluded from the post extractor

Fix:
- pass `/p/`, `/reel/`, `/tv/`, or `/stories/` (highlights included)
- open a share link in the browser and copy the canonical URL

---

## 11) Logged-out X/Twitter fails on the default API

Cause:
- graphql is a poor fit without cookies

Fix:
- with no Twitter cookie file and no `--cookies-from-browser`, the service sets `twitter:api=syndication`
- if cookies are configured, leave the default API and refresh the jar instead of forcing syndication
