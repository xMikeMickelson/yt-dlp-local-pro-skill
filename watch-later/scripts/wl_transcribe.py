#!/usr/bin/env python3
"""wl transcribe - speaker-labelled transcript with word timestamps, chapters, highlights.

Usage: wl transcribe <url|media file|.srt> [--out DIR] [--speakers N] [--engine auto|assemblyai|whisper|captions]
                     [--lang en] [--no-summary] [--no-highlights] [--keyterms "a,b"] [--whisper-model small]
Engines: assemblyai (default when ASSEMBLYAI_API_KEY is set; universal-3-5-pro -> universal-2, speaker_labels,
         word timestamps, auto_highlights, Speech-Understanding summarization = chapters with headlines),
         whisper (local faster-whisper, no diarization; `bash install.sh --whisper`),
         captions (platform subtitles via wl dl --subs-only; no diarization).
auto = assemblyai -> whisper -> captions.
Outputs in --out (default data/transcripts/): <stem>.transcript.json (normalized), <stem>.md, <stem>.srt, <stem>.raw.json
Prints the .transcript.json path on stdout. Never prints the API key.
"""
import argparse, json, os, pathlib, subprocess, sys, time
from wl_common import DATA, log, hms, caption_cues, write_srt, slug, srt_to_transcript, ffprobe_duration
import wl_dl

API = "https://api.assemblyai.com"


def key():
    return os.environ.get("ASSEMBLYAI_API_KEY") or os.environ.get("ASSEMBLY_AI_KEY") or os.environ.get("AAI_API_KEY")


def to_audio(src, work):
    """Return (audio_path, info dict) for a URL or local media."""
    info = {}
    if os.path.exists(src):
        p = pathlib.Path(src).resolve()
        ij = p.with_suffix(".info.json")
        if ij.exists():
            info = json.loads(ij.read_text())
        if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus"):
            return str(p), info
        out = pathlib.Path(work) / (p.stem + ".mp3")
        if not out.exists():
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(p), "-vn", "-ac", "1", "-b:a", "64k", str(out)], check=True)
        return str(out), info
    r = wl_dl.download(src, "audio", work)
    if not r.get("ok"):
        raise RuntimeError(f"download failed [{r.get('error_code')}]: {r.get('error')}")
    if r.get("info_json") and os.path.exists(r["info_json"]):
        info = json.loads(open(r["info_json"]).read())
    return r["files"][0], info


def aai(audio, a):
    import requests
    H = {"authorization": key()}
    with open(audio, "rb") as f:
        up = requests.post(API + "/v2/upload", headers=H, data=f, timeout=1800)
    up.raise_for_status()
    body = {"audio_url": up.json()["upload_url"], "speech_models": ["universal-3-5-pro", "universal-2"],
            "punctuate": True, "format_text": True}
    if a.lang:
        body["language_code"] = a.lang
    else:
        body["language_detection"] = True
    if not a.no_diarize:
        body["speaker_labels"] = True
        if a.speakers:
            body["speakers_expected"] = a.speakers
    if not a.no_highlights:
        body["auto_highlights"] = True
    if not a.no_summary:  # chapters (auto_chapters was removed 2026-09-15 -> Speech Understanding summarization)
        body["speech_understanding"] = {"request": {"summarization": {"summary_type": "paragraph"}}}
    if a.keyterms:
        body["keyterms_prompt"] = [k.strip() for k in a.keyterms.split(",") if k.strip()]
    for attempt in range(4):
        r = requests.post(API + "/v2/transcript", headers=H, json=body, timeout=60)
        if r.status_code == 200:
            break
        msg = r.text[:300]
        log("transcribe", f"submit {r.status_code}: {msg}")
        # drop optional features the account/model rejects, then retry
        for k in ("speech_understanding", "auto_highlights", "keyterms_prompt"):
            if k in body and (k.split("_")[0] in msg.lower() or attempt >= 1):
                body.pop(k); break
        else:
            if r.status_code < 500:
                raise RuntimeError(f"AssemblyAI submit failed {r.status_code}: {msg}")
            time.sleep(5)
    else:
        raise RuntimeError("AssemblyAI submit failed")
    tid = r.json()["id"]
    log("transcribe", f"AssemblyAI job {tid}")
    t0 = time.time()
    while True:
        j = requests.get(f"{API}/v2/transcript/{tid}", headers=H, timeout=60).json()
        if j["status"] == "completed":
            return j
        if j["status"] == "error":
            raise RuntimeError("AssemblyAI error: " + str(j.get("error")))
        if time.time() - t0 > 3600:
            raise RuntimeError("AssemblyAI timeout")
        time.sleep(3)


def normalize_aai(j):
    words = [{"text": w["text"], "start": w["start"], "end": w["end"], "speaker": w.get("speaker"),
              "confidence": w.get("confidence")} for w in (j.get("words") or [])]
    utts = [{"speaker": u.get("speaker"), "start": u["start"], "end": u["end"], "text": u["text"]} for u in (j.get("utterances") or [])]
    if not utts and words:
        utts = [{"speaker": "A", "start": words[0]["start"], "end": words[-1]["end"], "text": j.get("text", "")}]
    chapters = []
    su = ((j.get("speech_understanding") or {}).get("response") or {}).get("summarization") or {}
    for c in su.get("summary") or []:
        if isinstance(c, dict):
            chapters.append({"start": c.get("start"), "end": c.get("end"), "headline": c.get("headline"), "summary": c.get("text")})
    for c in j.get("chapters") or []:  # legacy
        chapters.append({"start": c["start"], "end": c["end"], "headline": c.get("headline"), "summary": c.get("summary")})
    hl = []
    for h in ((j.get("auto_highlights_result") or {}).get("results") or []):
        hl.append({"text": h["text"], "count": h.get("count"), "rank": h.get("rank"),
                   "timestamps": [[t["start"], t["end"]] for t in h.get("timestamps", [])]})
    return {"engine": "assemblyai:" + str(j.get("speech_model_used") or j.get("speech_model") or "universal"),
            "aai_id": j["id"], "language": j.get("language_code"), "duration": j.get("audio_duration"),
            "text": j.get("text"), "utterances": utts, "words": words, "chapters": chapters, "highlights": hl}


def whisper(audio, a):
    from faster_whisper import WhisperModel
    m = WhisperModel(a.whisper_model, device="auto", compute_type="int8")
    segs, info = m.transcribe(audio, word_timestamps=True, vad_filter=True, language=a.lang)
    words, utts = [], []
    for s in segs:
        utts.append({"speaker": "A", "start": int(s.start * 1000), "end": int(s.end * 1000), "text": s.text.strip()})
        words += [{"text": w.word.strip(), "start": int(w.start * 1000), "end": int(w.end * 1000), "speaker": "A",
                   "confidence": w.probability} for w in (s.words or [])]
    return {"engine": f"faster-whisper:{a.whisper_model}", "language": info.language, "duration": info.duration,
            "text": " ".join(u["text"] for u in utts), "utterances": utts, "words": words, "chapters": [], "highlights": []}


def render_md(t, title, src):
    L = [f"# {title}", "", f"- Source: {src}", f"- Engine: {t['engine']} | language: {t.get('language')} | duration: {hms((t.get('duration') or 0)*1000)}", ""]
    if t.get("chapters"):
        L += ["## Chapters", ""] + [f"- [{hms(c['start'])}] **{c.get('headline')}** - {c.get('summary') or ''}" for c in t["chapters"]] + [""]
    if t.get("highlights"):
        L += ["## Key phrases", "", ", ".join(h["text"] for h in sorted(t["highlights"], key=lambda h: -(h.get("rank") or 0))[:20]), ""]
    L += ["## Transcript", ""]
    for u in t["utterances"]:
        L.append(f"**Speaker {u['speaker']}** [{hms(u['start'])}]: {u['text']}\n")
    return "\n".join(L)


def transcribe(src, a):
    out = pathlib.Path(a.out or DATA / "transcripts").resolve(); out.mkdir(parents=True, exist_ok=True)
    work = DATA / "downloads" / "audio"; work.mkdir(parents=True, exist_ok=True)
    info, t, audio = {}, None, None
    if str(src).endswith(".srt") and os.path.exists(src):
        t = srt_to_transcript(src)
    engines = [a.engine] if a.engine != "auto" else ["assemblyai", "whisper", "captions"]
    errors = []
    for eng in engines:
        if t:
            break
        try:
            if eng in ("assemblyai", "whisper") and audio is None:
                audio, info = to_audio(src, work)
            if eng == "assemblyai":
                if not key():
                    errors.append("assemblyai: ASSEMBLYAI_API_KEY not set"); continue
                j = aai(audio, a); t = normalize_aai(j); t["_raw"] = j
            elif eng == "whisper":
                try:
                    import faster_whisper  # noqa
                except ImportError:
                    errors.append("whisper: faster-whisper not installed (bash install.sh --whisper)"); continue
                t = whisper(audio, a)
            elif eng == "captions":
                if os.path.exists(src):
                    cands = sorted(pathlib.Path(src).parent.glob(pathlib.Path(src).stem + "*.srt"))
                    srt = str(cands[0]) if cands else None
                else:
                    r = wl_dl.download(src, "subs", work)
                    srt = next((f for f in r.get("files", []) if f.endswith(".srt")), None)
                    if r.get("info_json"):
                        info = json.loads(open(r["info_json"]).read())
                if srt:
                    t = srt_to_transcript(srt)
                else:
                    errors.append("captions: none available")
        except Exception as e:
            errors.append(f"{eng}: {e}")
            log("transcribe", f"{eng} failed: {e}")
            if "download failed" in str(e) and eng == "assemblyai":
                audio = None
                engines = [x for x in engines if x == "captions"] or engines
    if not t:
        raise SystemExit("transcription failed: " + " | ".join(errors))
    raw = t.pop("_raw", None)
    title = info.get("title") or (pathlib.Path(src).stem if os.path.exists(src) else src)
    t.update({"source": info.get("webpage_url") or src, "title": title, "media": audio if audio and os.path.exists(src) is False else (str(pathlib.Path(src).resolve()) if os.path.exists(src) else audio),
              "info": {k: info.get(k) for k in ("id", "extractor_key", "uploader", "uploader_id", "channel", "upload_date", "duration", "webpage_url", "timestamp")}})
    stem = slug(f"{info.get('id') or ''}_{title}", 80)
    base = out / stem
    if raw:
        (base.with_suffix(".raw.json")).write_text(json.dumps(raw))
    tj = pathlib.Path(str(base) + ".transcript.json"); tj.write_text(json.dumps(t, ensure_ascii=False, indent=1))
    pathlib.Path(str(base) + ".md").write_text(render_md(t, title, t["source"]))
    if t.get("words"):
        write_srt(caption_cues(t["words"], 42, 4000), str(base) + ".srt")
    log("transcribe", f"OK {t['engine']}: {len(t['utterances'])} utterances, {len(t['words'])} words, "
        f"{len(set(u['speaker'] for u in t['utterances']))} speakers, {len(t['chapters'])} chapters, {len(t['highlights'])} highlights")
    return str(tj)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source"); ap.add_argument("--out"); ap.add_argument("--speakers", type=int)
    ap.add_argument("--engine", default="auto", choices=["auto", "assemblyai", "whisper", "captions"])
    ap.add_argument("--lang"); ap.add_argument("--no-summary", action="store_true"); ap.add_argument("--no-highlights", action="store_true")
    ap.add_argument("--no-diarize", action="store_true"); ap.add_argument("--keyterms"); ap.add_argument("--whisper-model", default="small")
    a = ap.parse_args()
    print(transcribe(a.source, a))


if __name__ == "__main__":
    main()
