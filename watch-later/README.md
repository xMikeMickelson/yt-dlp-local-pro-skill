# Watch Later

Watch Later downloads public videos, transcribes them, cuts 9:16 captioned Shorts, and keeps a SQLite full-text library.

## Install

On a fresh Linux machine, run:

```bash
curl -fsSL https://raw.githubusercontent.com/xMikeMickelson/yt-dlp-local-pro-skill/main/watch-later/bootstrap.sh | bash
```

Running it again refreshes the toolkit and upgrades yt-dlp. Downloads, the library, and `config/creators.json` stay in place.

Files land in `WL_HOME`. When `/workspace` is writable, that default is `/workspace/watch-later`. Otherwise it is `~/watch-later`. Set `WL_HOME` before the command to pick another directory.

```bash
export PATH="$WL_HOME/bin:$PATH"
wl doctor
```

## Keys

Transcription calls AssemblyAI. Set the key before `wl transcribe`.

```bash
export ASSEMBLYAI_API_KEY=your_key_here
```

`wl doctor` reports that variable as set or missing. It does not print the value. Downloads and mp3 export work without it. For offline transcription, re-run `bash "$WL_HOME/install.sh" --whisper`.

`X_BEARER_TOKEN` is optional and pay-per-use. Set it only when `wl sync` should list new posts from X accounts. Downloading one public post does not need that token.

## Platforms

| Platform | Public video | Listing new posts |
|---|---|---|
| YouTube | yes | yes |
| X | yes | needs `X_BEARER_TOKEN`, or paste post URLs |
| TikTok | yes | yes |
| Instagram | yes | usually login-walled, so paste reel URLs |
| Facebook | yes | latest video is best effort |
| Reddit | yes | paste post URLs |
| Vimeo | yes for non-DRM titles | channel URLs go in `other` |

## Ground rules

Public content only. Do not download private, members-only, or paywalled media. DRM titles are reported and skipped. Cookies stay off unless you pass your own Netscape cookies file with `--cookies`.

`wl help` lists commands. `wl dl URL` saves a video. `wl dl URL --audio` writes an mp3.
