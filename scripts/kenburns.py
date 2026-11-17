#!/usr/bin/env python3
"""
Local Motion Stage (FFmpeg Camera Engine — NO AI video API needed):
Turns each beat's keyframe poster into a dynamic clip honoring `camera_move`
from `beats.json` (`push_in`, `pull_out`, `pan`, `tilt`, `static`), with a
blurred collage backdrop if the keyframe aspect ratio differs slightly.

Usage: python kenburns.py <project_dir> [shotkeys]
"""
import json
import os
import subprocess
import sys

FPS = 25
RES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "3:4": (1080, 1440)}


def shots_of(beat):
    if beat.get("shots"):
        for s in beat["shots"]:
            yield s, f"{beat['id']}{s.get('id','')}"
    else:
        yield beat, f"{beat['id']}"


def camera_expr(move: str, frames: int, idx: int):
    move = (move or "").lower().strip()
    if not move:
        move = "push_in" if (idx % 2 == 0) else "pull_out"

    if "static" in move:
        return "1.03", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)", "static"
    if "pull" in move or "out" in move:
        z = f"if(eq(on,1),1.18,max(zoom-{0.18/max(frames,1):.6f},1.0))"
        return z, "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)", "pull_out"
    if "pan" in move:
        z = "1.14"
        x = f"(iw-iw/zoom)*(on/{max(frames,1)})" if (idx % 2 == 0) else f"(iw-iw/zoom)*(1-on/{max(frames,1)})"
        y = "ih/2-(ih/zoom/2)"
        return z, x, y, "pan"
    if "tilt" in move:
        z = "1.14"
        x = "iw/2-(iw/zoom/2)"
        y = f"(ih-ih/zoom)*(on/{max(frames,1)})" if (idx % 2 == 0) else f"(ih-ih/zoom)*(1-on/{max(frames,1)})"
        return z, x, y, "tilt"
    # Default: push_in
    z = f"min(zoom+{0.18/max(frames,1):.6f},1.18)"
    return z, "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)", "push_in"


def run(project_dir, only=None):
    bpath = os.path.join(project_dir, "beats.json")
    with open(bpath, encoding="utf-8") as f:
        doc = json.load(f)
    W, H = RES.get(doc.get("aspect", "9:16"), (1080, 1920))
    clip_dir = os.path.join(project_dir, "clips")
    os.makedirs(clip_dir, exist_ok=True)

    idx = 0
    for beat in doc["beats"]:
        for shot, key in shots_of(beat):
            if only and key not in only:
                idx += 1
                continue
            img = shot.get("keyframe_path")
            if not img or not os.path.exists(img):
                print(f"[{key}] no keyframe_path ({img})")
                idx += 1
                continue
            dur = float(shot.get("dur", 5))
            frames = max(1, int(round(dur * FPS)))
            move = shot.get("camera_move") or beat.get("camera_move") or ""
            z, x_expr, y_expr, move_label = camera_expr(move, frames, idx)

            vf = (
                f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},boxblur=26:2,eq=brightness=-0.05[bg];"
                f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,scale={W*2}:{H*2},"
                f"zoompan=z='{z}':d={frames}:x='{x_expr}':y='{y_expr}':"
                f"s={W}x{H}:fps={FPS}[v]"
            )
            out = os.path.join(clip_dir, f"clip_{key}.mp4")
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img,
                "-filter_complex", vf, "-map", "[v]", "-t", f"{dur}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", out
            ], check=True)
            shot["clip_path"] = out
            shot.pop("clip_url", None)
            print(f"[{key}] local-motion -> {out} ({move_label}, {dur}s)")
            idx += 1

    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print("updated", bpath)


if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "out", "ronaldo")
    only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
    run(os.path.abspath(proj), only=only)
