# Watch Later: Phase 1 research (compiled 2026-10-05, ET)

Sources: public X posts (metrics as of 2026-10-05), web search, the GitHub API (star counts fetched 2026-10-05),
and yt-dlp / AssemblyAI docs. The numbers below are copied from those sources. Nothing is estimated.

---

## 1. What people ask video bots/agents to do (ranked by demand)

Ranking method: number of distinct posts/products × engagement (likes, bookmarks, views), plus commercial proof.

| # | Job to be done | Evidence (engagement) |
|---|---|---|
| 1 | **Turn long videos into vertical Shorts/Reels/TikToks:** best moments, captions, 9:16 reframe | OpusClip says it has "16M+ creators and businesses" ([opus.pro](https://www.opus.pro/)), "over 229 million clips" at its 2-year mark ([blog](https://www.opus.pro/blog/celebrating-2-years-of-opusclip-from-the-best-ai-clipping-tool-to-the-best-ai-growth-tool-for-video-creators)), and ~$20M ARR ([MicroGaps](https://www.microgaps.com/gaps/2026-03-07-podcast-clip-repurposing-opus-clip-gap)). On X: OpenClaw "agent army" that turns a YouTube URL into content, 2,701 likes / 5,881 bookmarks / 311,537 views ([x.com/Jacobsklug/status/2029550513747112377](https://x.com/Jacobsklug/status/2029550513747112377)). OpenShorts (OpusClip alternative), 126 likes / 9,226 views ([x.com/JafarNajafov/status/2047628944346861899](https://x.com/JafarNajafov/status/2047628944346861899)). Higgsfield Personal Clipper (best moments + subtitles + resize), 55 likes / 6,684 views ([x.com/WesRoth/status/2057793598205141013](https://x.com/WesRoth/status/2057793598205141013)). An API turning a long YouTube video into 10+ clips with animated captions, timestamped summaries, searchable moments and a speaker-labelled transcript, 53 likes / 9,494 views ([x.com/Prathkum/status/2044051674873115096](https://x.com/Prathkum/status/2044051674873115096)). yt-dlp + Claude turning a 40-min interview into 5 clips + a thread, 39 likes / 1,703 views ([x.com/marcthecreatorr/status/2083549524664938760](https://x.com/marcthecreatorr/status/2083549524664938760)). Podcli (face tracking, caption burn-in, ranked picks) ([x.com/nikasiradze_/status/2056061654664708570](https://x.com/nikasiradze_/status/2056061654664708570)). Background agent that clips podcasts daily ([x.com/mfishbein/status/2091990962234929449](https://x.com/mfishbein/status/2091990962234929449)). |
| 2 | **"Watch this for me":** transcribe, summarize, chapters, notes into a second brain | /watch-video skill (transcript + frames + notes), 2,355 likes / 4,687 bookmarks / 223,897 views ([x.com/coreyhainesco/status/2083953532903059846](https://x.com/coreyhainesco/status/2083953532903059846)). "Claude Code can WATCH videos", 614 likes / 1,358 bookmarks / 51,915 views ([x.com/PrajwalTomar_/status/2073414555695477085](https://x.com/PrajwalTomar_/status/2073414555695477085)). Obsidian/second-brain integrations, 2,189 likes / 4,453 bookmarks / 290,486 views ([x.com/akshay_pachaar/status/2056356792494682385](https://x.com/akshay_pachaar/status/2056356792494682385)). vidlens article, 261 likes / 1,288,693 views ([x.com/cmd_alt_ecs/status/2091015777491259752](https://x.com/cmd_alt_ecs/status/2091015777491259752)). Transcript → cheatsheet, 292 likes / 371 bookmarks / 27,600 views ([x.com/rubenhassid/status/2043645374716670329](https://x.com/rubenhassid/status/2043645374716670329)). "ChatGPT refuses YouTube links, agents don't", 57 likes / 18,812 views ([x.com/qwenwork/status/2031234581702287423](https://x.com/qwenwork/status/2031234581702287423)). GitHub: bradautomates/claude-video, 18,090★. |
| 3 | **Auto-editing:** remove fillers and dead air, add subtitles, "edit while I sleep" | browser-use/video-use (fillers, silence, subtitles): 28,119★. On X: 362 likes / 565 bookmarks / 66,815 views ([x.com/exploraX_/status/2072277788967481683](https://x.com/exploraX_/status/2072277788967481683)) and 139 likes / 276 bookmarks / 15,917 views ([x.com/startupideaspod/status/2095550256905847147](https://x.com/startupideaspod/status/2095550256905847147)). "Claude edit your videos while you sleep", 239 likes / 369 bookmarks / 25,678 views ([x.com/mikenevermiss/status/2097014962098938258](https://x.com/mikenevermiss/status/2097014962098938258)). OpenMontage, 293 likes / 510 bookmarks / 75,506 views ([x.com/heynavtoor/status/2072730850899456441](https://x.com/heynavtoor/status/2072730850899456441)). "How I edit videos entirely with AI", 424 likes / 1,380 bookmarks / 68,412 views ([x.com/Emarky/status/2034995870035268034](https://x.com/Emarky/status/2034995870035268034)). |
| 4 | **Repurposing into posts/threads/newsletters** | Claude Repurpose skill, 3,026 views ([x.com/DanKornas/status/2073079048486465850](https://x.com/DanKornas/status/2073079048486465850)). marcthecreatorr's interview → clips + thread (above). coreyhaines31/marketingskills, 53,363★ (a marketing skill pack that includes repurposing). |
| 5 | **Searchable archives / channel monitoring** | ChannelScout (whole-channel searchable transcript DB) ([x.com/johncalvo/status/2073300591577817361](https://x.com/johncalvo/status/2073300591577817361), small). The Prathkum API above lists "searchable moments". Second-brain posts (#2). |
| 6 | **Reliable downloading** (yt-dlp blocked on servers) | Pain posts: every client blocked on a datacenter IP ([x.com/LexiAngelus/status/2060527563580277134](https://x.com/LexiAngelus/status/2060527563580277134)); Invidious 403 / Piped offline ([x.com/LOCALDEV_AI/status/2033448576706138394](https://x.com/LOCALDEV_AI/status/2033448576706138394)); a media-downloader skill hitting 403 that needs a JS runtime + PO token ([x.com/2024Echo/status/2015347907030110565](https://x.com/2024Echo/status/2015347907030110565)); Railway IP bot check ([x.com/nischayhq/status/2042966511036567977](https://x.com/nischayhq/status/2042966511036567977)); [x.com/yazzu709/status/2090031650013118648](https://x.com/yazzu709/status/2090031650013118648). yt-dlp itself: 195,770★. |
| 7 | **Speaker labels / diarization** (podcasts, interviews) | whisperX, 24,375★. MicroGaps names "no speaker diarization" as the gap in Vizard and says podcasters want tools that understand speaker dynamics ([link](https://www.microgaps.com/gaps/2026-03-07-podcast-clip-repurposing-opus-clip-gap)). |

Skill/catalog meta-signal: an article listing 1,116 Claude Code skills drew 901 likes / 3,824 bookmarks / 968,758 views
([x.com/polydao/status/2047644016632557700](https://x.com/polydao/status/2047644016632557700)), and an "AI video studio in Claude Code" post drew 181,920 views
([x.com/notEgoyard/status/2082787425579897196](https://x.com/notEgoyard/status/2082787425579897196)).

**What this means for Watch Later:** the most-requested pipeline is link → transcript (with speakers) → best
moments → 9:16 captioned clips → post copy. The next most valuable pieces are the "watch/summarize into my
notes" flow and a searchable library. Downloading reliability is the hidden dependency behind all of them.

---

## 2. Top video skills / repos people use with Claude, Claude Code and Codex

| Repo | Stars (2026-10-05) | What it does | Relevance |
|---|---|---|---|
| [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | 128,640 | Topic → generated short video (script, stock footage, TTS, subs) | generation, not clipping |
| [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) | 63,988 | Agentic video production pipeline | editing/assembly |
| [remotion-dev/remotion](https://github.com/remotion-dev/remotion) | 62,039 | Programmatic React video. Agent skills via `npx skills add remotion-dev/skills` ([remotion-dev/skills](https://github.com/remotion-dev/skills), 4,850★) | animated captions/titles |
| [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | 57,297 | HTML → video rendering for agents | motion graphics |
| [browser-use/video-use](https://github.com/browser-use/video-use) | 28,119 | Edit videos with coding agents: cut fillers/silence, subtitles | auto-edit |
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 25,718 | Fast local Whisper | our offline fallback |
| [m-bain/whisperX](https://github.com/m-bain/whisperX) | 24,375 | Whisper + word alignment + diarization | local diarization option |
| [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) | 20,470 | TikTok/Douyin download API | downloading |
| [jianchang512/pyvideotrans](https://github.com/jianchang512/pyvideotrans) | 19,223 | Translate/dub video, embed subtitles | localization |
| [bradautomates/claude-video](https://github.com/bradautomates/claude-video) | 18,090 | `/watch`: download, extract frames, transcribe, hand to Claude | "watch" flow |
| [palmier-io/palmier-pro](https://github.com/palmier-io/palmier-pro) | 14,513 | macOS AI video editor + MCP | editor |
| [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | 10,378 | Remotion-based video skill | |
| [mutonby/openshorts](https://github.com/mutonby/openshorts) | 6,143 | Long video → 9:16 shorts with AI moment detection, face tracking | clipping |
| [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) | 5,427 | Silence/motion-based auto cut | silence trim |
| [Anil-matcha/AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) | 5,251 | OpusClip-style: highlights + 9:16 crop | clipping |
| [jub0t/concat](https://github.com/jub0t/concat) | 4,118 | CapCut alternative with MCP | editor |
| [op7418/Youtube-clipper-skill](https://github.com/op7418/Youtube-clipper-skill) | 2,221 | Claude skill: chapters, clip, bilingual subs, burn-in | closest analogue |
| [digitalsamba/claude-code-video-toolkit](https://github.com/digitalsamba/claude-code-video-toolkit) | 2,169 | Claude Code video toolkit | |
| [0xsline/OpenChatCut](https://github.com/0xsline/OpenChatCut) | 2,128 | Chat-driven cutting | |
| [kajisho5/ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) | 1,853 | 42 ffmpeg tools: cut, silence, captions, vertical | ffmpeg recipes |
| [video-db/Director](https://github.com/video-db/Director) | 1,545 | AI video agents framework | |
| [jordanrendric/claude-video-vision](https://github.com/jordanrendric/claude-video-vision) | 1,344 | Frame-based video understanding for Claude | |
| [Brainicism/bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) | 828 | PO-token provider for yt-dlp | **used** |
| [zenstory-ai/video-recap-skills](https://github.com/zenstory-ai/video-recap-skills) | 549 | Recap skills | summaries |
| [yt-dlp/ejs](https://github.com/yt-dlp/ejs) | 458 | yt-dlp JS challenge solver | **used** |
| [zhuyansen/awesome-claude-video-skills](https://github.com/zhuyansen/awesome-claude-video-skills) | 420 | Curated list (~180 repos) | discovery |
| [kamilstanuch/Autocrop-vertical](https://github.com/kamilstanuch/Autocrop-vertical) | 415 | YOLOv8 person-tracked 9:16 crop | reframe |
| [kevinwatt/yt-dlp-mcp](https://github.com/kevinwatt/yt-dlp-mcp) | 286 | yt-dlp MCP server | downloading |
| [nmbrthirteen/podcli](https://github.com/nmbrthirteen/podcli) | 78 | Podcast clips: face tracking, captions, MCP | clipping |
| [coletdjnz/yt-dlp-getpot-wpc](https://github.com/coletdjnz/yt-dlp-getpot-wpc) | 71 | Browser-based PO-token provider | alternative |
| [AssemblyAI/assemblyai-skill](https://github.com/AssemblyAI/assemblyai-skill) | 15 | Official AssemblyAI agent skill | transcription |

Patterns that recur in the best repos, and that we adopted:
- **Transcript-first pipeline.** Every clipping tool works from word timestamps.
- **Ranked candidate clips with reasons**, then a human or LLM pick.
- **9:16 reframe** with face/person tracking and a center-crop fallback.
- **Burned, word-synced captions** in ASS styles (bold/karaoke/boxed).
- **Silence and filler trimming.**
- **A local library** for recall.

Heavy pieces we left out to keep it installable from text: YOLO/MediaPipe tracking (OpenCV Haar is used instead),
Remotion rendering (Node build), and whisperX (GPU-heavy).

---

## 3. yt-dlp failure modes in 2026 and fixes

| Failure | Symptom | Best current fix | Source |
|---|---|---|---|
| YouTube n/sig JS challenge | "n challenge solving failed", only images/storyboards, missing formats | Install a JS runtime + `yt-dlp-ejs` (`yt-dlp[default]`). **deno is recommended** (≥2.3), node ≥22 and quickjs also work, and **bun is deprecated (≤1.3.14 only)**. `--remote-components ejs:github` | [EJS wiki](https://github.com/yt-dlp/yt-dlp/wiki/EJS) |
| SABR-only streaming | "YouTube is forcing SABR streaming", "Only images are available" | Current nightly, a JS runtime, a PO-token client (mweb); SABR downloader work is in progress | [#15793](https://github.com/yt-dlp/yt-dlp/issues/15793), [#12482](https://github.com/yt-dlp/yt-dlp/issues/12482), [PR #13515](https://github.com/yt-dlp/yt-dlp/pull/13515) |
| PO tokens (GVS) | 403 on media, 360p only, missing formats | **bgutil-ytdlp-pot-provider** (HTTP server on 127.0.0.1:4416, run with deno/node, plus pip plugin) with `player_client=mweb`. Tokens are bound to IP/video. The guide's client table: tv is DRM'd without cookies, android_vr needs no token | [PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide), [bgutil](https://github.com/Brainicism/bgutil-ytdlp-pot-provider), [PyPI](https://pypi.org/project/bgutil-ytdlp-pot-provider/2.0.0/) |
| Datacenter-IP bot check | "Sign in to confirm you're not a bot", HTTP 429 on the watch page | A PO token alone does not lift an IP flag ([#11053](https://github.com/yt-dlp/yt-dlp/issues/11053), [#10128](https://github.com/yt-dlp/yt-dlp/issues/10128), [#14195](https://github.com/yt-dlp/yt-dlp/issues/14195)). **Our finding:** `--extractor-args "youtube:player_client=mweb;player_skip=webpage"` (+ bgutil) and `web_embedded;player_skip=webpage` worked from a flagged datacenter IP, where the original skill failed. Other options: a residential proxy, user cookies (opt-in), cooling off, IPv4 (`-4`) | [tunelio 403 guide](https://tunelio.dev/blog/yt-dlp-403-forbidden/) |
| Forced itags | 403 when using `-f 137+140` | Use `-S` sorting instead of fixed itags | tunelio (above) |
| X/Twitter guest API | "Bad guest token", 404, rate limits | `--extractor-args twitter:api=syndication` (works for single posts). Profile timelines via syndication return 429 from datacenter IPs. The X API v2 works but needs paid credits (it can return 402 after credits run out) | yt-dlp Twitter extractor; own tests |
| TikTok | "Your IP address is blocked", empty webpage data | Upgrade, then `--impersonate chrome` (curl-cffi), then the app_info variant. In our tests plain extraction worked | yt-dlp README (impersonation) |
| Instagram | "login required", rate-limit, empty media | Single reels/posts worked without login here. **Profile listing** (`web_profile_info`) returned 401 (login wall). Fallback: process explicit URLs. Page-scrape `video_url` from `/embed/captioned/` or the reel HTML (verified) | own tests |
| Facebook | Login wall, "Cannot parse data" | Single page videos worked. yt-dlp has no page listing, so we scrape the page HTML for `video_id` to get the latest video. Page-scrape `browser_native_*_url` fallback verified | own tests |
| Reddit | 403 from the JSON API / "Prove your humanity" on page HTML | yt-dlp default worked (v.redd.it DASH + audio mux). `v.redd.it/<id>` direct input also works | own tests |
| Vimeo | "logged-in" requirement for the web client, DRM | Retry via `player.vimeo.com/video/ID` with a vimeo.com referer (worked). Some titles are FairPlay/Widevine (e.g. 76979871): reported as DRM and skipped by design | own tests |
| Invidious/Piped | 403 / instances offline | **Not recommended** in 2026 | [x.com/LOCALDEV_AI/status/2033448576706138394](https://x.com/LOCALDEV_AI/status/2033448576706138394) |
| Everything blocked | | Captions-only fallback (`--subs-only`; our chain exits 3 with captions), or transcribe from the platform's subtitles | own design |

AssemblyAI changes that matter:
- `auto_chapters` was **removed on 2026-09-15**. Use Speech Understanding summarization instead
  ([migration guide](https://www.assemblyai.com/docs/speech-understanding/migration-guides/auto-chapters)).
- Current models: `universal-3-5-pro` and `universal-2` ([models](https://www.assemblyai.com/llms/models.md)).
- `speaker_labels`, word timestamps, `auto_highlights` and `language_detection` are still supported.

### Implications for the original skill
- `--js-runtimes bun` above the supported 1.3.14 line is outside yt-dlp's range. Switch to deno (pip wheel `deno`), or node 22 or newer.
- Add the bgutil PO-token provider and `player_skip=webpage` for YouTube on a flagged datacenter IP. The original skill got
  429 / bot check on that IP, while the Watch Later chain succeeded.
