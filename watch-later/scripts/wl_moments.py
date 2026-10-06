#!/usr/bin/env python3
"""wl moments - rank candidate clips ("best moments") from a transcript.

Usage:
  wl moments <T.transcript.json> [--n 8] [--min 15] [--max 60] [--json]   # heuristic ranking (no LLM needed)
  wl moments <T.transcript.json> --prompt [--n 8]                         # print an LLM prompt (the bot answers it)
  wl moments <T.transcript.json> --snap picks.json                        # validate/snap LLM picks to word boundaries
Heuristic score = AssemblyAI key-phrase hits + hook/opener cues + questions/emphasis + numbers + speech density
                  + clean sentence boundaries + chapter alignment; non-overlapping top-N.
Output: ranked list with start/end (s and m:ss), duration, score, reason, text; JSON with --json.
"""
import argparse, json, re, sys
from wl_common import load_transcript, hms, log

HOOKS = r"\b(here'?s (why|how|the)|the (secret|truth|key|problem|reason|trick)|most people|nobody|never|always|stop|imagine|what if|the biggest|the first|the only|you need|you should|i (learned|realized|discovered)|turns out|in fact|actually|the best|worst|mistake|lesson|surprising|crazy|insane|wild|game.?changer)\b"
EMPH = r"\b(amazing|incredible|unbelievable|huge|massive|important|critical|breakthrough|historic|first time|record|love|hate|fear|excited|wow)\b"
FILLER = r"\b(um+|uh+|you know|like,|sort of|kind of)\b"


def sentences(t):
    """Split words into sentence units with times."""
    out, cur = [], []
    for w in t.get("words") or []:
        if cur and w.get("speaker") != cur[-1].get("speaker"):  # never merge across a speaker change
            out.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.?!]$", w["text"]) and len(cur) >= 3:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    if not out:  # captions-only transcripts without words
        for u in t.get("utterances") or []:
            out.append([{"text": u["text"], "start": u["start"], "end": u["end"], "speaker": u.get("speaker")}])
    return [{"start": s[0]["start"], "end": s[-1]["end"], "text": " ".join(w["text"] for w in s),
             "speaker": s[0].get("speaker"), "nw": len(s)} for s in out]


def score_window(sents, hl, chapters):
    text = " ".join(s["text"] for s in sents); low = text.lower()
    dur = (sents[-1]["end"] - sents[0]["start"]) / 1000
    reasons, sc = [], 0.0
    hits = [h for h in hl if h["text"].lower() in low]
    if hits:
        v = sum(1 + (h.get("rank") or 0) * 3 for h in hits); sc += v
        reasons.append("key phrases: " + ", ".join(h["text"] for h in hits[:4]))
    first = sents[0]["text"].lower()
    if re.search(HOOKS, first):
        sc += 3; reasons.append("strong hook opener")
    elif re.search(HOOKS, low):
        sc += 1.5; reasons.append("hook language")
    q = text.count("?")
    if q:
        sc += min(q, 3) * 1.0; reasons.append(f"{q} question(s)")
    e = len(re.findall(EMPH, low))
    if e:
        sc += min(e, 4) * 0.8; reasons.append("emphasis/emotion")
    nums = len(re.findall(r"\b\d[\d,.%]*\b", text))
    if nums:
        sc += min(nums, 4) * 0.5; reasons.append("concrete numbers")
    nw = sum(s["nw"] for s in sents); wps = nw / max(dur, 1)
    if 2.2 <= wps <= 4.2:
        sc += 1.0
    elif wps < 1.2:
        sc -= 2; reasons.append("sparse speech")
    fill = len(re.findall(FILLER, low))
    sc -= fill * 0.3
    if text.rstrip()[-1:] in ".?!":
        sc += 0.8
    spk = len({s["speaker"] for s in sents})
    if spk >= 2:
        sc += 0.7; reasons.append(f"{spk}-speaker exchange")
    for c in chapters or []:
        if c.get("start") is not None and abs(c["start"] - sents[0]["start"]) < 3000:
            sc += 1.0; reasons.append(f"starts chapter '{c.get('headline')}'"); break
    return sc, reasons or ["coherent self-contained segment"], text


def rank(t, n=8, mn=15, mx=60):
    ss = sentences(t); hl = t.get("highlights") or []; ch = t.get("chapters") or []
    cands = []
    for i in range(len(ss)):
        for j in range(i, len(ss)):
            dur = (ss[j]["end"] - ss[i]["start"]) / 1000
            if dur > mx:
                break
            if dur >= mn or (j == len(ss) - 1 and i == 0):
                sc, why, text = score_window(ss[i:j + 1], hl, ch)
                sc += min(dur, 45) / 45  # mild preference for fuller clips
                cands.append({"start_ms": ss[i]["start"], "end_ms": ss[j]["end"], "score": round(sc, 2), "reasons": why, "text": text})
    cands.sort(key=lambda c: -c["score"])
    picked = []
    for c in cands:
        if all(c["end_ms"] <= p["start_ms"] or c["start_ms"] >= p["end_ms"] for p in picked):
            picked.append(c)
        if len(picked) >= n:
            break
    for k, p in enumerate(picked, 1):
        p.update({"rank": k, "start": round(p["start_ms"] / 1000, 2), "end": round(p["end_ms"] / 1000 + 0.25, 2),
                  "duration": round((p["end_ms"] - p["start_ms"]) / 1000, 1), "reason": "; ".join(p.pop("reasons"))})
    return picked


PROMPT = """You are a short-form video editor. From the timestamped, speaker-labelled transcript below, pick the {n} best
self-contained moments for Shorts/Reels/TikTok ({mn}-{mx}s each). Favour: a strong hook in the first 3 seconds,
a complete thought/payoff, surprising or quotable lines, concrete numbers/stories, emotion, clear stakes. Avoid clips
that need prior context, start mid-sentence, or end before the payoff. Do not invent text; quote only what is said.
Return ONLY JSON: [{{"rank":1,"start":<seconds>,"end":<seconds>,"title":"<=60 chars hook title",
"hook":"first line as said","reason":"why it works","caption":"post caption (no hashtags spam)"}}]

Title: {title}
Source: {source}
Chapters: {chapters}
Key phrases: {keyphrases}

Transcript (start seconds | speaker | text):
{lines}
"""


def prompt(t, n=8, mn=15, mx=60):
    lines = "\n".join(f"{s['start']/1000:.1f} | {s['speaker'] or 'A'} | {s['text']}" for s in sentences(t))
    return PROMPT.format(n=n, mn=mn, mx=mx, title=t.get("title"), source=t.get("source"),
                         chapters="; ".join(f"{c['start']/1000:.0f}s {c.get('headline')}" for c in t.get("chapters") or []) or "n/a",
                         keyphrases=", ".join(h["text"] for h in (t.get("highlights") or [])[:25]) or "n/a", lines=lines)


def snap(t, picks):
    ws = t.get("words") or []
    out = []
    for p in picks:
        s, e = float(p["start"]) * 1000, float(p["end"]) * 1000
        if ws:
            s = min(ws, key=lambda w: abs(w["start"] - s))["start"]
            e = min(ws, key=lambda w: abs(w["end"] - e))["end"]
        q = dict(p, start=round(s / 1000, 2), end=round(e / 1000 + 0.25, 2), duration=round((e - s) / 1000 + 0.25, 1),
                 text=" ".join(w["text"] for w in ws if s <= w["start"] <= e))
        out.append(q)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript"); ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--min", type=float, default=15); ap.add_argument("--max", type=float, default=60)
    ap.add_argument("--json", action="store_true"); ap.add_argument("--prompt", action="store_true"); ap.add_argument("--snap")
    a = ap.parse_args()
    t = load_transcript(a.transcript)
    if a.prompt:
        print(prompt(t, a.n, a.min, a.max)); return
    if a.snap:
        print(json.dumps(snap(t, json.load(open(a.snap))), indent=1)); return
    dur = (t.get("duration") or 0)
    mn = min(a.min, max(3, dur * 0.3)) if dur and dur < a.min * 2 else a.min
    res = rank(t, a.n, mn, a.max)
    if a.json:
        print(json.dumps(res, indent=1, ensure_ascii=False)); return
    for r in res:
        print(f"#{r['rank']}  {hms(r['start_ms'])}-{hms(r['end_ms'])} ({r['duration']}s) score {r['score']}\n    why: {r['reason']}\n    \"{r['text'][:220]}\"")


if __name__ == "__main__":
    main()
