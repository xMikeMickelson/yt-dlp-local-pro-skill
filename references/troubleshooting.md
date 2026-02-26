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
- glob for `<title>-<id>.*` after download
- pick most recent matching file

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
