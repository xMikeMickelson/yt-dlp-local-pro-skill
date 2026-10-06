#!/usr/bin/env python3
"""wl clip - ffmpeg clipping toolkit: cut, mp3, silence trim, vertical 9:16 (center/face/blur), burned captions.

Usage:
  wl clip cut      <media> --start 1:02 --end 1:30 [--copy] [--out F]
  wl clip mp3      <media> [--start S --end E] [--out F]
  wl clip silence  <media> [--db -35] [--min 0.6] [--pad 0.15] [--out F]          # remove dead air
  wl clip vertical <media> [--mode center|face|blur] [--start S --end E] [--out F]
  wl clip captions <media> --transcript T.json [--style bold|clean|karaoke|boxed] [--offset S] [--out F]
  wl clip make     <media> --start S --end E [--transcript T.json] [--vertical face|center|blur|none]
                   [--style bold] [--trim-silence] [--offset S] [--out F]            # one-shot Short/Reel/TikTok
                   (--offset = source time at media 0, for clips downloaded with `wl dl --section`)
Times accept 75, 75.5, 1:15, 0:01:15.5. Output defaults to data/clips/. Prints output path.
Face mode uses OpenCV Haar cascades (no GPU/model download); falls back to center crop if no faces found.
"""
import argparse, json, os, pathlib, shutil, subprocess, sys, tempfile, statistics
from wl_common import DATA, log, parse_ts, ffprobe_duration, video_size, caption_cues, write_ass, write_srt, slug, load_transcript

OUT = DATA / "clips"


def ff(args):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("ffmpeg failed: " + r.stderr[-800:])


def outpath(src, tag, ext=".mp4", out=None):
    if out:
        pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True); return str(out)
    OUT.mkdir(parents=True, exist_ok=True)
    return str(OUT / f"{slug(pathlib.Path(src).stem, 50)}.{tag}{ext}")


ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"]


def cut(src, start, end, out=None, copy=False):
    s, e = parse_ts(start) / 1000, parse_ts(end) / 1000
    o = outpath(src, f"cut_{int(s)}-{int(e)}", out=out)
    if copy:
        ff(["-ss", f"{s}", "-to", f"{e}", "-i", src, "-c", "copy", "-avoid_negative_ts", "make_zero", o])
    else:
        ff(["-ss", f"{s}", "-i", src, "-t", f"{e - s}"] + ENC + [o])
    return o


def mp3(src, start=None, end=None, out=None):
    o = outpath(src, "audio", ".mp3", out)
    a = []
    if start is not None:
        a += ["-ss", str(parse_ts(start) / 1000)]
    a += ["-i", src]
    if end is not None:
        a += ["-t", str((parse_ts(end) - parse_ts(start or 0)) / 1000)]
    ff(a + ["-vn", "-c:a", "libmp3lame", "-q:a", "2", o])
    return o


def detect_silence(src, db=-35, min_s=0.6):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", f"silencedetect=noise={db}dB:d={min_s}", "-f", "null", "-"],
                       capture_output=True, text=True)
    sil, st = [], None
    for line in r.stderr.splitlines():
        if "silence_start:" in line:
            st = float(line.split("silence_start:")[1].split()[0])
        elif "silence_end:" in line and st is not None:
            sil.append((max(0, st), float(line.split("silence_end:")[1].split()[0]))); st = None
    if st is not None:
        sil.append((st, ffprobe_duration(src)))
    return sil


def keep_segments(src, db=-35, min_s=0.6, pad=0.15):
    dur = ffprobe_duration(src); keep, cur = [], 0.0
    for a, b in detect_silence(src, db, min_s):
        a2, b2 = a + pad, b - pad
        if a2 > cur:
            keep.append((cur, a2))
        cur = max(cur, b2)
    if cur < dur:
        keep.append((cur, dur))
    return [(a, b) for a, b in keep if b - a > 0.05]


def has_video(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=index", "-of", "csv=p=0", src], capture_output=True, text=True)
    return bool(r.stdout.strip())


def silence(src, db=-35, min_s=0.6, pad=0.15, out=None):
    segs = keep_segments(src, db, min_s, pad)
    vid = has_video(src)
    o = outpath(src, "nosilence", ".mp4" if vid else ".mp3", out)
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in segs)
    af = f"aselect='{sel}',asetpts=N/SR/TB"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fs:
        if vid:
            fs.write(f"[0:v]select='{sel}',setpts=N/FRAME_RATE/TB[v];[0:a]{af}[a]")
        else:
            fs.write(f"[0:a]{af}[a]")
    args = ["-i", src, "-filter_complex_script", fs.name, "-map", "[a]"] + (["-map", "[v]"] if vid else [])
    ff(args + (ENC if vid else ["-c:a", "libmp3lame", "-q:a", "2"]) + [o])
    os.unlink(fs.name)
    removed = ffprobe_duration(src) - sum(b - a for a, b in segs)
    log("clip", f"silence trim: kept {len(segs)} segments, removed {removed:.1f}s")
    json.dump({"segments": segs}, open(o + ".segments.json", "w"))
    return o, segs


def remap_words(words, segs, base_ms=0):
    """Map original word times (ms, absolute) through kept segments (seconds, relative to base)."""
    out, acc = [], 0.0
    bounds = []
    for a, b in segs:
        bounds.append((a, b, acc)); acc += b - a
    for w in words:
        t0 = (w["start"] - base_ms) / 1000; t1 = (w["end"] - base_ms) / 1000
        for a, b, off in bounds:
            if a - 0.05 <= t0 <= b:
                nw = dict(w); nw["start"] = int((off + t0 - a) * 1000); nw["end"] = int((off + min(t1, b) - a) * 1000)
                out.append(nw); break
    return out


def face_track(src, start_s=0, dur_s=None, step=0.5):
    """Return list of (t, cx_norm) keyframes of the dominant face center; [] if none."""
    try:
        import cv2
    except ImportError:
        log("clip", "opencv not installed -> center crop"); return []
    if not hasattr(cv2, "CascadeClassifier"):
        log("clip", "this OpenCV build lacks Haar cascades (install opencv-python-headless<5) -> center crop"); return []
    cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    end = min(total, start_s + dur_s) if dur_s else total
    keys, t = [], start_s
    while t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY); H, W = g.shape
        sc = 480 / max(W, 1); small = cv2.resize(g, (int(W * sc), int(H * sc))) if sc < 1 else g
        faces = cas.detectMultiScale(small, 1.1, 5, minSize=(int(24), int(24)))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            keys.append((t - start_s, (x + w / 2) / small.shape[1]))
        t += step
    cap.release()
    if len(keys) < 2:
        return []
    # smooth: rolling median then hold small moves (avoid jitter)
    xs = [k[1] for k in keys]; sm = []
    for i in range(len(xs)):
        win = xs[max(0, i - 3): i + 4]; sm.append(statistics.median(win))
    held = [sm[0]]
    for v in sm[1:]:
        held.append(v if abs(v - held[-1]) > 0.06 else held[-1])
    return [(keys[i][0], held[i]) for i in range(len(keys))]


def crop_x_expr(keys, W, cw):
    """Piecewise-linear ffmpeg expression for crop x (eased between keyframes)."""
    def px(c):
        return max(0, min(W - cw, int(c * W - cw / 2)))
    pts = [(keys[0][0], px(keys[0][1]))]
    for t, c in keys[1:]:
        if px(c) != pts[-1][1]:
            pts.append((t, px(c)))
    if len(pts) == 1:
        return str(pts[0][1])
    expr = str(pts[-1][1])
    for i in range(len(pts) - 2, -1, -1):
        t0, x0 = pts[i]; t1, x1 = pts[i + 1]; tr = min(0.4, t1 - t0)  # 0.4s pan into the new position
        seg = f"if(lt(t,{t1 - tr:.2f}),{x0},if(lt(t,{t1:.2f}),{x0}+({x1}-{x0})*(t-{t1 - tr:.2f})/{tr:.2f},{expr}))"
        expr = seg
    return expr


def vertical_filter(src, mode, start_s, dur_s, W, H, outW=1080, outH=1920):
    tw = int(H * 9 / 16) // 2 * 2
    if W <= tw:  # already vertical/narrow
        return f"scale={outW}:{outH}:force_original_aspect_ratio=decrease,pad={outW}:{outH}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    if mode == "blur":
        return (f"split[a][b];[a]scale={outW}:{outH}:force_original_aspect_ratio=increase,crop={outW}:{outH},boxblur=20:2[bg];"
                f"[b]scale={outW}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    x = f"{(W - tw) // 2}"
    if mode == "face":
        keys = face_track(src, start_s, dur_s)
        if keys:
            x = crop_x_expr(keys, W, tw); log("clip", f"face-tracked crop: {len(keys)} keyframes")
        else:
            log("clip", "no faces found -> center crop")
    return f"crop={tw}:{H}:'{x}':0,scale={outW}:{outH},setsar=1"


def esc_path(p):
    return p.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")


def make(src, start=None, end=None, transcript=None, vertical="face", style="bold", trim_silence=False, out=None, words_override=None, src_offset=0):
    """src_offset (ms): source/transcript time at media 0, e.g. for a `wl dl --section 418-477` download use 418000."""
    s_ms = parse_ts(start) if start is not None else 0
    e_ms = parse_ts(end) if end is not None else int(ffprobe_duration(src) * 1000)
    tag = f"short_{s_ms//1000}-{e_ms//1000}" if vertical != "none" else f"clip_{s_ms//1000}-{e_ms//1000}"
    o = outpath(src, tag, out=out)
    work = tempfile.mkdtemp(prefix="wlclip_", dir=str(DATA))
    try:
        seg = os.path.join(work, "seg.mp4")
        ff(["-ss", f"{s_ms/1000}", "-i", src, "-t", f"{(e_ms - s_ms)/1000}"] + ENC + [seg])
        words = None
        if transcript:
            t = load_transcript(transcript)
            o_ms = s_ms + src_offset; oe_ms = e_ms + src_offset
            words = [dict(w, start=w["start"] - o_ms, end=w["end"] - o_ms) for w in t.get("words", []) if w["start"] >= o_ms - 50 and w["end"] <= oe_ms + 50]
        if trim_silence:
            seg2, segs = silence(seg, out=os.path.join(work, "trim.mp4"))
            if words:
                words = remap_words(words, segs)
            seg = seg2
        W, H = video_size(seg)
        vf = []
        if vertical != "none" and W and H:
            vf.append(vertical_filter(seg, vertical, 0, None, W, H))
            oW, oH = 1080, 1920
        else:
            oW, oH = W, H
        if words:
            cues = caption_cues(words, 22 if vertical != "none" else 40, 2000)
            ass = write_ass(cues, os.path.join(work, "cap.ass"), oW, oH, style)
            write_srt(cues, o.rsplit(".", 1)[0] + ".srt")
            vf.append(f"subtitles='{esc_path(ass)}'")
        if vf:
            graph = ",".join(vf) if "split" not in vf[0] else vf[0] + ("," + ",".join(vf[1:]) if len(vf) > 1 else "")
            ff(["-i", seg, "-filter_complex", f"[0:v]{graph}[v]", "-map", "[v]", "-map", "0:a?"] + ENC + [o])
        else:
            os.replace(seg, o)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return o


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["cut", "mp3", "silence", "vertical", "captions", "make"])
    ap.add_argument("media"); ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--out")
    ap.add_argument("--copy", action="store_true"); ap.add_argument("--db", type=float, default=-35)
    ap.add_argument("--min", type=float, default=0.6); ap.add_argument("--pad", type=float, default=0.15)
    ap.add_argument("--mode", default="face", choices=["center", "face", "blur"])
    ap.add_argument("--vertical", default="face", choices=["face", "center", "blur", "none"])
    ap.add_argument("--transcript"); ap.add_argument("--style", default="bold", choices=["bold", "clean", "karaoke", "boxed"])
    ap.add_argument("--offset"); ap.add_argument("--trim-silence", action="store_true")
    a = ap.parse_args()
    m = a.media
    if not os.path.exists(m):
        raise SystemExit(f"no such file: {m}")
    if a.cmd == "cut":
        if a.start is None or a.end is None:
            raise SystemExit("--start and --end required")
        print(cut(m, a.start, a.end, a.out, a.copy))
    elif a.cmd == "mp3":
        print(mp3(m, a.start, a.end, a.out))
    elif a.cmd == "silence":
        print(silence(m, a.db, a.min, a.pad, a.out)[0])
    elif a.cmd == "vertical":
        print(make(m, a.start, a.end, None, a.mode, a.style, False, a.out))
    elif a.cmd == "captions":
        if not a.transcript:
            raise SystemExit("--transcript required")
        print(make(m, a.offset or a.start, a.end, a.transcript, "none", a.style, False, a.out))
    elif a.cmd == "make":
        print(make(m, a.start, a.end, a.transcript, a.vertical, a.style, a.trim_silence, a.out, src_offset=parse_ts(a.offset) if a.offset else 0))


if __name__ == "__main__":
    main()
