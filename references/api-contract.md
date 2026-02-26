# API Contract

## `GET /health`

### Purpose
Check service readiness and runtime config visibility.

### Response (example)
```json
{
  "status": "ok",
  "version": "1.1.0",
  "download_dir": "/opt/yt-dlp-local/downloads",
  "cookies": {
    "youtube": true,
    "instagram": true,
    "tiktok": true
  },
  "proxy": {
    "enabled": true,
    "host": "proxy-provider.example.com",
    "ports": {
      "youtube": 20501,
      "instagram": 20502,
      "tiktok": 20503,
      "twitter": 20504,
      "facebook": 20505,
      "default": 20506
    }
  }
}
```

---

## `POST /api/extract`

### Body
```json
{ "url": "https://example.com/video" }
```

### Success
Returns metadata and discovered format hints.

### Failure
`400` for bad URL/extractor error, `500` for internal errors.

---

## `POST /api/download`

### Body
```json
{
  "url": "https://example.com/video",
  "quality": "best",
  "audio_only": false
}
```

### Notes
- `quality`: `best`, `worst`, or numeric cap like `1080`, `720`
- `audio_only`: forces audio extraction path

### Success
```json
{
  "success": true,
  "platform": "instagram",
  "title": "Video title",
  "file_path": "/opt/yt-dlp-local/downloads/instagram/title-id.mp4",
  "file_name": "title-id.mp4",
  "file_size_mb": 12.34,
  "duration": 37,
  "ext": "mp4"
}
```

### Failure
```json
{
  "error": "Download error",
  "message": "...original downloader error..."
}
```

May include fallback diagnostics for platform-specific paths.

---

## `POST /api/audio`

### Body
```json
{ "url": "https://example.com/video" }
```

### Behavior
Equivalent to download with `audio_only=true`.

---

## `POST /api/formats`

### Body
```json
{ "url": "https://example.com/video" }
```

### Success
Returns list of formats (`format_id`, codecs, size hints, resolution, bitrate).

---

## `POST /api/instagram/private`

### Purpose
Explicit Instagram fallback endpoint for private/gated media where standard extraction fails.

### Body
```json
{ "url": "https://www.instagram.com/reel/SHORTCODE/", "quality": "best" }
```

### Notes
- Uses authenticated cookie path.
- Requires valid Instagram `sessionid` for private content.
- May return `method: yt-dlp-authenticated` or `method: instagram-private-api`.

---

## `GET /api/serve/<path>`

### Purpose
Serve previously downloaded files.

### Security
- Resolve and validate path is within download root.
- Prefer disabling externally unless required.

---

## Integration Pattern for Agents

1. Call `/api/download`
2. Parse JSON
3. Copy downloaded file into agent-allowed media dir
4. Send media via messaging tool
