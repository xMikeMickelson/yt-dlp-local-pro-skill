# Watch Later: test results (2026-10-05, ET)

Environment: a Linux host on a **datacenter IP** (YouTube flags that class of address: the original skill got 429 / "Sign in
to confirm you're not a bot" on that run), no cookies, no logins.
Software: yt-dlp nightly 2026.09.27.232945, yt-dlp-ejs 0.8.0 + deno, curl-cffi 0.16.3, bgutil PO-token provider 2.0.1,
ffmpeg 7.1, AssemblyAI `universal-3-5-pro`.
Test clips are short, public, official uploads (NASA, Google, YouTube's first video, and Big Buck Bunny, which is CC-BY).
Harness: `tests/run_tests.py`; raw results in `tests/results.json` and `tests/results_fresh_install.json` (logs: `tests/fresh_install*.log`).

## Summary
| Suite | Result |
|---|---|
| Run A: full pipeline on the main install, 7 platforms × 7 steps | **49/49 PASS** |
| Run B: the same suite on a **fresh install built only from SKILL.md text** (`env -i`, clean dir, no X token, ~28 s install) | **49/49 PASS** |
| Earlier fresh install (before the latest edits; `tests/results_fresh_install_prev.json`) | 49/49 PASS |
| Extra download breadth (URL variants, Shorts, youtu.be, twitter.com, multi-video post, IG /p/ and /user/reel/, FB slug URLs, Vimeo channel) | **11/11 PASS** |
| Download regression after fallback changes (Reddit, IG, YouTube, v.redd.it direct) | 4/4 PASS |
| Page-scrape fallback, called directly (IG reel, FB video) | 2/2 PASS (video+audio streams, ffprobe-validated) |
| Creator sync, 3 runs (YouTube @Google, TikTok nasa, Facebook NASA, X via explicit post URL; no X API) | run1 3 new, run2 1 new (X URL), run3 0 new = **idempotent** |
| Long multi-speaker video (10.6 min NASA Space-to-Space Call, yfmG9qmZn6Y): transcribe → moments → clip | PASS: 8 speakers, 37 utterances, 1,807 words, 4 chapters, 15 key phrases; 5 ranked moments; 56 s 1080×1920 face-tracked karaoke-caption Short |
| Error handling: Vimeo DRM title (76979871) / nonexistent YouTube ID | correctly reported `DRM` / `UNAVAILABLE` |

\* Vimeo's Big Buck Bunny has **no speech**, so it produced 0 words and 0 moments. Those steps "pass" because they ran
without error, but transcript and moments quality are **N/A for Vimeo**, so treat it as 5/7 meaningful passes. Speech on Vimeo is
covered by the downloader breadth test only.

## Per platform, per step (with timings)
### Run A - main install (WL_HOME), 7:38-7:42 PM ET

| Platform | Download strategy | download_video | mp3 | transcribe | moments | vertical_clip_captions | library_ingest | library_search | Pass |
|---|---|---|---|---|---|---|---|---|---|
| youtube | mweb+pot,skip-webpage | PASS 14.6s | PASS 0.3s | PASS 8.2s (40w, 1 spk) | PASS 0.1s | PASS 7.2s | PASS 0.0s | PASS 0.0s | 7/7 |
| x | syndication | PASS 7.9s | PASS 0.6s | PASS 8.3s (16w, 1 spk) | PASS 0.1s | PASS 4.8s | PASS 0.0s | PASS 0.0s | 7/7 |
| tiktok | default | PASS 14.7s | PASS 0.8s | PASS 11.9s (159w, 1 spk) | PASS 0.1s | PASS 17.7s | PASS 0.0s | PASS 0.0s | 7/7 |
| instagram | default | PASS 5.1s | PASS 0.8s | PASS 8.5s (114w, 1 spk) | PASS 0.1s | PASS 11.2s | PASS 0.0s | PASS 0.0s | 7/7 |
| facebook | default | PASS 2.9s | PASS 0.6s | PASS 8.6s (80w, 3 spk) | PASS 0.1s | PASS 11.9s | PASS 0.0s | PASS 0.0s | 7/7 |
| reddit | default | PASS 12.8s | PASS 0.8s | PASS 12.0s (156w, 5 spk) | PASS 0.1s | PASS 21.6s | PASS 0.0s | PASS 0.0s | 7/7 |
| vimeo | player-embed | PASS 18.3s | PASS 0.7s | PASS 5.1s (0w, 0 spk) | PASS* (no speech) | PASS 5.0s | PASS 0.0s | PASS 0.0s | 7/7 |

**Total: 49/49**

### Run B - fresh install from SKILL.md text (env -i, clean dir, since removed, no X token), 8:08-8:12 PM ET

| Platform | Download strategy | download_video | mp3 | transcribe | moments | vertical_clip_captions | library_ingest | library_search | Pass |
|---|---|---|---|---|---|---|---|---|---|
| youtube | mweb+pot,skip-webpage | PASS 15.2s | PASS 0.2s | PASS 8.0s (40w, 1 spk) | PASS 0.1s | PASS 6.4s | PASS 0.0s | PASS 0.0s | 7/7 |
| x | syndication | PASS 2.9s | PASS 0.6s | PASS 14.9s (16w, 1 spk) | PASS 0.1s | PASS 5.1s | PASS 0.0s | PASS 0.0s | 7/7 |
| tiktok | default | PASS 14.5s | PASS 0.8s | PASS 8.4s (159w, 1 spk) | PASS 0.1s | PASS 14.6s | PASS 0.0s | PASS 0.0s | 7/7 |
| instagram | default | PASS 4.6s | PASS 0.8s | PASS 9.0s (114w, 1 spk) | PASS 0.1s | PASS 10.3s | PASS 0.0s | PASS 0.0s | 7/7 |
| facebook | default | PASS 2.9s | PASS 0.6s | PASS 8.3s (80w, 3 spk) | PASS 0.1s | PASS 14.5s | PASS 0.0s | PASS 0.0s | 7/7 |
| reddit | default | PASS 15.2s | PASS 0.9s | PASS 12.1s (156w, 5 spk) | PASS 0.1s | PASS 22.7s | PASS 0.0s | PASS 0.0s | 7/7 |
| vimeo | player-embed | PASS 18.3s | PASS 0.6s | PASS 5.0s (0w, 0 spk) | PASS* (no speech) | PASS 5.5s | PASS 0.0s | PASS 0.0s | 7/7 |

**Total: 49/49**

Test URLs: YouTube `jNQXAC9IVRw` ("Me at the zoo", 19 s); X `x.com/NASA/status/2106061652617568263`; TikTok
`@nasa/video/7692161454694206733` (first 60 s); Instagram `reel/DW2mVfojTkV`; Facebook
`NASA/videos/artemis-ii-splashdown-promo/1211632377548396`; Reddit `r/nasa/comments/1samd8p` (first 60 s); Vimeo `1084537`
(first 45 s).
Diarization check: Facebook promo 3 speakers, Reddit recap 5, long YouTube call 8.

## Download breadth (tmp/breadth.txt)
| Result | Strategy | Files | URL |
|---|---|---|---|
| PASS | mweb+pot,skip-webpage | 1 | https://www.youtube.com/shorts/-62C9R_41Sc |
| PASS | mweb+pot,skip-webpage | 3 | https://youtu.be/yfmG9qmZn6Y |
| PASS | syndication | 3 | https://x.com/SpaceX/status/2106089751837278533 |
| PASS | syndication | 1 | https://twitter.com/NASA/status/2107095768821576019 |
| PASS | default | 1 | https://www.instagram.com/reel/DW-IhhKjdrC/ |
| PASS | default | 1 | https://www.instagram.com/nasa/reel/DH_hyJbprmG/ |
| PASS | default | 1 | https://www.facebook.com/NASA/videos/930452829785006 |
| PASS | default | 1 | https://www.facebook.com/NASA/videos/nasas-artemis-iii-announcement-official-nasa-trailer/960710576782934/ |
| PASS | default | 1 | https://www.tiktok.com/@nasa/video/7691066504380452110 |
| PASS | default | 1 | https://www.reddit.com/r/ArtemisProgram/comments/1saqhh0/this_is_the_best_artemis_ii_launch_footage_ive/ |
| PASS | default | 1 | https://vimeo.com/channels/staffpicks/1231817291 |

Other download modes, all PASS:
- `--subs-only` on YouTube (via `web_embedded`).
- `--section` cuts with forced keyframes.
- `--audio` mp3.
- `--meta`.
- Captions transcription engine (1,836 words after removing roll-up duplicates).

## Creator sync (WL_DATA=tmp/sync2, `--limit 1 --audio-only`, X_BEARER_TOKEN unset)
| Run | youtube:@Google | tiktok:nasa | facebook:NASA | x:NASA (handle) | x: explicit post URL | Wall time |
|---|---|---|---|---|---|---|
| 1 | 1 new → done (ktdbUIZKeSE, 2:13) | 1 new → done | 1 new → done (latest video via page scrape) | listing failed: syndication 429 (clear message) | (added after run 1) | 74 s |
| 2 | 0 (skipped) | 0 | 0 | 429 | 1 new → done (2107095768821576019) | 23 s |
| 3 | 0 | 0 | 0 | 429 | 0 | ~15 s |
Earlier runs (while X API credits remained): X listing via API v2 worked; YouTube `UC…` id and @NASA, and TikTok `--limit 3`
(2 new) also worked. `wl lib digest --days 7` rendered a markdown digest of the synced videos.

## Feature checks (manual, frames inspected visually)
| Feature | Result |
|---|---|
| Vertical 9:16, center / face (Haar, piecewise-smoothed crop) / blur-background | PASS (face mode kept the speaker centered; 107 keyframes on the long clip) |
| Burned captions: bold / clean / karaoke (`\kf`) / boxed | PASS (text matches the transcript timing) |
| Silence trim with caption remapping (`--trim-silence`) | PASS (59 s → 56 s on the long clip; captions stayed in sync) |
| `make --offset` (clip from a `--section` download of a long video) | PASS |
| Moments: heuristic ranking, `--prompt` LLM template, `--snap` to word boundaries | PASS |
| Library: FTS5 search with deep links (YouTube `&t=`), title/chapter matches, list/show/stats/digest | PASS |

## Known limits and fallbacks
| Issue | Status | Fallback in place |
|---|---|---|
| **X creator listing without API credits.** The X API returned 402 (credits depleted); the syndication timeline returns 429 from a datacenter IP | FAILS (listing only) | X API is optional (used only if the token works; 402/429 fall through; `WL_X_API=0` disables it). Add explicit post URLs found by web search. **Single-post downloads never need the API** (syndication) |
| Instagram profile listing (`web_profile_info` 401, login wall) | FAILS (listing only) | Explicit reel/post URLs; single reels download fine (yt-dlp, then page-scrape fallback) |
| Facebook page listing (yt-dlp unsupported) | partial | Page-HTML scrape finds the latest video; explicit URLs otherwise |
| YouTube watch page blocked on this IP | worked around | mweb + PO token + `player_skip=webpage` → web_embedded → … → captions-only (exit 3). If all of these fail: wait, a user proxy, or a user cookies file (opt-in only) |
| Vimeo DRM titles (FairPlay/Widevine) | by design | Reported as `DRM`, not attempted |
| Reddit page HTML/JSON "Prove your humanity" from curl | n/a | yt-dlp default works; `v.redd.it/<id>` direct |
| bun as the JS runtime (the original skill) | deprecated upstream (>1.3.14 unsupported) | Watch Later uses deno (pip wheel) + node |
