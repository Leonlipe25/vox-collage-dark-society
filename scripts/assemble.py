#!/usr/bin/env python3
"""
Assembly stage (ffmpeg): multi-shot clips + per-beat narration + optional music -> final.mp4

Model: beats -> shots. Each shot is one short clip (its own cut). Narration and
captions are per BEAT and span all the beat's shots, so the voice stays aligned
while the visuals cut. BGM is optional (if present, ducked under the narration;
if omitted, outputs clean voice-over so you can add music later).

Usage: python assemble.py <project_dir>
"""
import json
import os
import subprocess
import sys

import text_overlay

FPS, TAIL = 24, 0.4
WATERMARK = ""
RES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}


def ff(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def probe_dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def shots_of(beat):
    if beat.get("shots"):
        for s in beat["shots"]:
            yield s
    else:
        yield beat


def run(project_dir):
    with open(os.path.join(project_dir, "beats.json"), encoding="utf-8") as f:
        doc = json.load(f)
    beats = doc["beats"]
    W, H = RES.get(doc.get("aspect", "16:9"), (1920, 1080))
    wm_text = doc.get("watermark", WATERMARK)
    mix = doc.get("mix", {})
    music_vol = float(mix.get("music", 0.6))
    voice_vol = float(mix.get("voice", 1.15))
    cap_style = doc.get("caption_style", "paper")
    tmp = os.path.join(project_dir, "_seg")
    os.makedirs(tmp, exist_ok=True)

    # ---- flatten shots into timed segments; track each beat's span ----
    segs = []
    beat_spans = []
    t = 0.0
    for beat in beats:
        beat_start = t
        shot_list = list(shots_of(beat))
        durs = [float(s.get("dur", 5)) for s in shot_list]
        need = float(beat.get("narration_dur", sum(durs))) + TAIL
        if sum(durs) < need and shot_list[-1].get("kind") != "host":
            durs[-1] += need - sum(durs)
        for s, d in zip(shot_list, durs):
            segs.append({"clip": s["clip_path"], "dur": round(d, 2),
                         "host": s.get("kind") == "host"})
            t += d
        beat_spans.append({"start": beat_start, "dur": round(t - beat_start, 2), "beat": beat})
    total = round(t, 2)

    # ---- 1) normalise each shot to a silent segment of exactly its dur ----
    seg_files = []
    for i, s in enumerate(segs):
        out = os.path.join(tmp, f"seg_{i:02d}.mp4")
        cd = probe_dur(s["clip"])
        factor = s["dur"] / cd if cd > 0 else 1.0
        pre = f"setpts={factor:.4f}*PTS," if factor > 1.02 and not s["host"] else ""
        fc = (f"[0:v]{pre}split[s0][s1];"
              f"[s0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"boxblur=26:2,eq=brightness=-0.05[bg];"
              f"[s1]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS},"
              f"tpad=stop_mode=clone:stop_duration=1[v]")
        ff(["-i", s["clip"], "-an", "-filter_complex", fc, "-map", "[v]", "-t", f"{s['dur']}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", out])
        seg_files.append(out)

    # ---- 2) concat all shot segments (video only) ----
    listf = os.path.join(tmp, "list.txt")
    with open(listf, "w", encoding="utf-8") as f:
        for s in seg_files:
            safe_path = os.path.abspath(s).replace("\\", "/")
            f.write(f"file '{safe_path}'\n")
    body = os.path.join(tmp, "body_silent.mp4")
    ff(["-f", "concat", "-safe", "0", "-i", listf, "-c", "copy", body])

    # ---- 3) captions (per SRT phrase or per beat) + optional watermark PNGs ----
    captions_on = bool(doc.get("captions", True))
    cap_items = []
    if captions_on:
        import re
        def _parse_srt_chunks(srt_path, offset_s, max_words=9):
            raw = open(srt_path, encoding="utf-8").read().strip()
            words = []
            for blk in re.split(r"\n\s*\n", raw):
                lns = [l.strip() for l in blk.strip().splitlines() if l.strip()]
                if len(lns) >= 3 and "-->" in lns[1]:
                    t0_s, t1_s = [x.strip().replace(",", ".") for x in lns[1].split("-->")]
                    def _sec(ts):
                        h, m, s = ts.split(":")
                        return int(h) * 3600 + int(m) * 60 + float(s)
                    words.append((offset_s + _sec(t0_s), offset_s + _sec(t1_s), " ".join(lns[2:])))
            chunks, cur = [], []
            for w in words:
                cur.append(w)
                if len(cur) >= max_words or (len(cur) >= 5 and w[2].endswith((".", "?", "!", ":", ";", "—"))):
                    chunks.append((cur[0][0], cur[-1][1] + 0.12, " ".join(x[2] for x in cur)))
                    cur = []
            if cur:
                chunks.append((cur[0][0], cur[-1][1] + 0.15, " ".join(x[2] for x in cur)))
            return chunks

        for bs in beat_spans:
            beat = bs["beat"]
            acc = None
            if cap_style == "paper":
                kf = next((s["keyframe_path"] for s in (beat.get("shots") or [beat])
                           if s.get("keyframe_path") and os.path.exists(s["keyframe_path"])), None)
                acc = text_overlay.accent_color(kf) if kf else None
            srt_p = beat.get("narration_srt")
            if srt_p and os.path.exists(srt_p):
                for c_idx, (cs, ce, ctxt) in enumerate(_parse_srt_chunks(srt_p, bs["start"])):
                    p = os.path.join(tmp, f"cap_{beat['id']}_{c_idx:02d}.png")
                    text_overlay.render_caption(ctxt, p, W, H, accent=acc, style=cap_style)
                    cap_items.append({"png": p, "start": cs, "end": ce})
            else:
                p = os.path.join(tmp, f"cap_{beat['id']}.png")
                text_overlay.render_caption(beat["narration"], p, W, H, accent=acc, style=cap_style)
                cap_items.append({"png": p, "start": bs["start"] + 0.15, "end": bs["start"] + bs["dur"] - 0.1})

    has_wm = bool(wm_text and wm_text.strip())
    wm_png = text_overlay.render_watermark(wm_text, os.path.join(tmp, "wm.png"), W, H) if has_wm else None

    # ---- 4) one pass: overlay captions+wm, mix per-beat narration, optional BGM ----
    nb = len(beat_spans)
    ncap = len(cap_items)
    inputs = ["-i", body]                       # 0
    for item in cap_items:
        inputs += ["-i", item["png"]]           # 1..ncap
    if has_wm:
        inputs += ["-i", wm_png]                # ncap+1
        narr_base = ncap + 2
    else:
        narr_base = ncap + 1

    for bs in beat_spans:
        inputs += ["-i", bs["beat"]["narration_audio"]]

    bgm_path = doc.get("bgm_path")
    has_bgm = bool(bgm_path and os.path.exists(bgm_path))
    if has_bgm:
        bgm_idx = narr_base + nb
        inputs += ["-i", bgm_path]

    chain, prev = [], "[0:v]"
    for i, item in enumerate(cap_items):
        s, e = item["start"], item["end"]
        lbl = f"[v{i+1}]"
        chain.append(f"{prev}[{i+1}:v]overlay=0:0:enable='between(t,{s:.2f},{e:.2f})'{lbl}")
        prev = lbl
    if has_wm:
        chain.append(f"{prev}[{ncap+1}:v]overlay=0:0[v]")
    else:
        chain.append(f"{prev}null[v]")

    # per-beat narration delayed to its start, then mixed
    nlabels = []
    for i, bs in enumerate(beat_spans):
        ms = int(bs["start"] * 1000)
        chain.append(f"[{narr_base+i}:a]adelay={ms}:all=1[n{i}]")
        nlabels.append(f"[n{i}]")

    if has_bgm:
        chain.append(f"{''.join(nlabels)}amix=inputs={nb}:normalize=0:duration=longest,volume={voice_vol},apad,atrim=0:{total}[narrmix]")
        chain.append("[narrmix]asplit=2[narrA][narrB]")
        chain.append(f"[{bgm_idx}:a]atrim=0:{total},volume={music_vol},afade=t=out:st={max(total-2,0):.2f}:d=2[bgt]")
        chain.append("[bgt][narrA]sidechaincompress=threshold=0.02:ratio=12:attack=5:release=350[bgd]")
        chain.append(f"[narrB][bgd]amix=inputs=2:normalize=0:duration=longest,volume=1.4,atrim=0:{total}[a]")
    else:
        chain.append(f"{''.join(nlabels)}amix=inputs={nb}:normalize=0:duration=longest,volume={voice_vol},apad,atrim=0:{total}[a]")

    filt = ";".join(chain)

    final = os.path.join(project_dir, "final.mp4")
    ff([*inputs, "-filter_complex", filt, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", final])
    print("FINAL:", final, f"(~{total}s, {len(segs)} shots, bgm={'yes' if has_bgm else 'no'})")


if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "out", "tang-30s")
    run(os.path.abspath(proj))
