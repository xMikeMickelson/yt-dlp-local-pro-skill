"""Shared helpers for Watch Later scripts (paths, time formatting, transcript I/O, SRT/ASS)."""
import json, os, pathlib, re, subprocess, sys

WL_HOME = pathlib.Path(os.environ.get("WL_HOME") or pathlib.Path(__file__).resolve().parent.parent)
DATA = pathlib.Path(os.environ.get("WL_DATA") or WL_HOME / "data")
os.environ["PATH"] = f"{WL_HOME/'bin'}:{WL_HOME/'venv'/'bin'}:" + os.environ.get("PATH", "")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def log(tag, *a):
    print(f"[wl {tag}]", *a, file=sys.stderr, flush=True)


def hms(ms, srt=False, sep=","):
    ms = max(0, int(ms))
    h, r = divmod(ms, 3600000); m, r = divmod(r, 60000); s, x = divmod(r, 1000)
    if srt:
        return f"{h:02d}:{m:02d}:{s:02d}{sep}{x:03d}"
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_ts(t):
    """'1:02:03.5' | '62.5' | '1:02' -> milliseconds."""
    t = str(t).strip()
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return int(float(t) * 1000)
    parts = [float(p.replace(",", ".")) for p in t.split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return int(sec * 1000)


def ffprobe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def video_size(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0:s=x", str(path)], capture_output=True, text=True)
    try:
        w, h = r.stdout.strip().split("\n")[0].split("x")[:2]
        return int(w), int(h)
    except Exception:
        return 0, 0


def load_transcript(path):
    p = pathlib.Path(path)
    if p.suffix == ".srt":
        return srt_to_transcript(p)
    d = json.loads(p.read_text())
    if "utterances" not in d and "words" not in d:
        raise SystemExit(f"{p} is not a Watch Later transcript json")
    return d


def srt_to_transcript(p):
    txt = pathlib.Path(p).read_text(errors="ignore")
    utts, prev = [], []
    for block in re.split(r"\n\s*\n", txt.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        tl = next((l for l in lines if "-->" in l), None)
        if not tl:
            continue
        a, b = [parse_ts(x.strip().split(" ")[0]) for x in tl.split("-->")]
        tlines = [re.sub(r"<[^>]+>", "", l).strip() for l in lines[lines.index(tl) + 1:]]
        body = " ".join(l for l in tlines if l and l not in prev).strip()  # drop YouTube auto-caption roll-up repeats
        prev = tlines
        if body and (not utts or utts[-1]["text"] != body):
            utts.append({"speaker": "A", "start": a, "end": b, "text": body})
    words = []
    for u in utts:  # approximate word timings by linear interpolation
        ws = u["text"].split(); n = max(1, len(ws)); d = (u["end"] - u["start"]) / n
        words += [{"text": w, "start": int(u["start"] + i * d), "end": int(u["start"] + (i + 1) * d), "speaker": "A"} for i, w in enumerate(ws)]
    return {"engine": "platform-captions", "utterances": utts, "words": words, "chapters": [], "highlights": [],
            "text": " ".join(u["text"] for u in utts), "duration": (utts[-1]["end"] / 1000 if utts else 0)}


def caption_cues(words, max_chars=32, max_ms=2500, gap_ms=600):
    """Group word timings into short caption cues (Shorts-style)."""
    cues, cur = [], []
    for w in words:
        if cur and (len(" ".join(x["text"] for x in cur + [w])) > max_chars or w["start"] - cur[0]["start"] > max_ms
                    or w["start"] - cur[-1]["end"] > gap_ms or cur[-1]["text"][-1:] in ".?!"):
            cues.append(cur); cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    return [{"start": c[0]["start"], "end": c[-1]["end"], "text": " ".join(x["text"] for x in c), "words": c,
             "speaker": c[0].get("speaker")} for c in cues]


def write_srt(cues, path, offset_ms=0):
    out = []
    for i, c in enumerate(cues, 1):
        out += [str(i), f"{hms(c['start'] - offset_ms, True)} --> {hms(c['end'] - offset_ms, True)}", c["text"], ""]
    pathlib.Path(path).write_text("\n".join(out))
    return path


ASS_STYLES = {
    # name: (font size as fraction of height, primary, outline, back, bold, alignment, margin_v fraction, uppercase)
    "bold": (0.055, "&H00FFFFFF", "&H00000000", "&H80000000", 1, 2, 0.22, True),
    "clean": (0.042, "&H00FFFFFF", "&H00202020", "&H64000000", 0, 2, 0.08, False),
    "karaoke": (0.055, "&H0000FFFF", "&H00000000", "&H80000000", 1, 2, 0.22, True),
    "boxed": (0.045, "&H00FFFFFF", "&H00000000", "&HA0000000", 1, 2, 0.12, False),
}


def ass_time(ms):
    ms = max(0, int(ms)); h, r = divmod(ms, 3600000); m, r = divmod(r, 60000); s, x = divmod(r, 1000)
    return f"{h}:{m:02d}:{s:02d}.{x // 10:02d}"


def write_ass(cues, path, w, h, style="bold", offset_ms=0, font="DejaVu Sans"):
    fs, prim, outl, back, bold, align, mv, upper = ASS_STYLES.get(style, ASS_STYLES["bold"])
    border = 3 if style == "boxed" else 1
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{int(h*fs)},{prim},&H00FFFFFF,{outl},{back},{bold},0,0,0,100,100,0,0,{border},{max(2,int(h*0.004))},1,{align},{int(w*0.06)},{int(w*0.06)},{int(h*mv)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for c in cues:
        if style == "karaoke" and c.get("words"):
            parts = []
            for wd in c["words"]:
                k = max(1, int((wd["end"] - wd["start"]) / 10))
                t = wd["text"].upper() if upper else wd["text"]
                parts.append(f"{{\\k{k}}}{t}")
            text = " ".join(parts).replace("{\\k", "{\\kf")  # fills Secondary(white) -> Primary(yellow)
        else:
            text = c["text"].upper() if upper else c["text"]
        text = text.replace("\n", "\\N")
        ev.append(f"Dialogue: 0,{ass_time(c['start']-offset_ms)},{ass_time(c['end']-offset_ms)},Default,,0,0,0,,{text}")
    pathlib.Path(path).write_text(hdr + "\n".join(ev) + "\n")
    return path


def slug(s, n=60):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "").strip("_")[:n] or "item"
