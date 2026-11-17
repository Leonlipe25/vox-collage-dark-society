#!/usr/bin/env python3
"""
Keyframe stage: one styled keyframe per SHOT (Google Antigravity Built-in Nano Banana edition).

- Composes the 5-layer Vox collage prompt (`compose_collage_prompt`) for every shot
  and writes `keyframe_prompt` + expected `keyframe_path` into `beats.json`.
- If the image file (`kf_<key>.jpg` or `.png`) is already in `<project>/keyframes/`,
  links it automatically (converting PNG -> JPG if needed).

Usage:
  python scripts/keyframes.py <project_dir>
"""
import json
import os
import sys
from PIL import Image

from styles import compose_keyframe_prompt, compose_collage_prompt, resolve_theme


def shots_of(beat):
    """Yield (shot_dict, shot_key) for a beat; synthesize one shot if none."""
    if beat.get("shots"):
        for s in beat["shots"]:
            yield s, f"{beat['id']}{s.get('id','')}"
    else:
        yield beat, f"{beat['id']}"


def run(project_dir: str):
    bpath = os.path.join(project_dir, "beats.json")
    with open(bpath, encoding="utf-8") as f:
        doc = json.load(f)
    aspect = doc.get("aspect", "16:9")
    style = doc.get("style", "collage")
    theme = resolve_theme(doc.get("theme")) or {}
    collage_style = theme.get("idiom") or doc.get("collage_style", "swiss-modern")
    t_palette = theme.get("palette") or doc.get("palette")
    t_type = theme.get("type_style") or doc.get("type_style")
    t_finish = theme.get("finish") or doc.get("finish")
    era = doc.get("era")
    kf_dir = os.path.join(project_dir, "keyframes")
    os.makedirs(kf_dir, exist_ok=True)

    pending = []

    for beat in doc["beats"]:
        for shot, key in shots_of(beat):
            dest_jpg = os.path.join(kf_dir, f"kf_{key}.jpg")
            dest_png = os.path.join(kf_dir, f"kf_{key}.png")

            # Convert PNG -> JPG if Nano Banana saved a PNG
            if os.path.exists(dest_png) and not os.path.exists(dest_jpg):
                Image.open(dest_png).convert("RGB").save(dest_jpg, quality=95)

            scene = shot["scene"]
            t_cn = beat.get("title_cn", "")
            t_en = beat.get("title_en", "")
            if style == "collage":
                prompt = compose_collage_prompt(
                    scene, t_cn, t_en,
                    beat.get("bg", "warm ochre"), aspect,
                    with_title=shot.get("title", True),
                    style=collage_style, palette=t_palette,
                    type_style=t_type, finish=t_finish
                )
            else:
                prompt = compose_keyframe_prompt(era, scene, t_cn, t_en, aspect)

            shot["keyframe_prompt"] = prompt
            shot["keyframe_path"] = dest_jpg

            if os.path.exists(dest_jpg):
                print(f"[{key}] OK (local): {dest_jpg}")
            else:
                pending.append((key, dest_jpg, prompt))

    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print("updated", bpath)

    if pending:
        print(f"\n=== {len(pending)} KEYFRAME(S) READY FOR ANTIGRAVITY NANO BANANA ===")
        for key, dest_jpg, prompt in pending:
            print(f"\n--- SHOT [{key}] -> {dest_jpg} ---")
            print(prompt)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    proj = args[0] if args else os.path.join(
        os.path.dirname(__file__), "..", "out", "singapore-vs-malaysia")
    run(os.path.abspath(proj))
