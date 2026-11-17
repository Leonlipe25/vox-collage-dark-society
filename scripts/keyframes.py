#!/usr/bin/env python3
"""
Keyframe stage: one styled keyframe per SHOT.

Adapted for Antigravity Built-in Nano Banana (`image-generator` subagent):
- Composes the full Vox collage prompt (`compose_collage_prompt`) for every shot
  and writes `keyframe_prompt` + expected `keyframe_path` into `beats.json`.
- If the image file (`kf_<key>.jpg` or `.png`) is already in `<project>/keyframes/`,
  links it automatically (converting PNG -> JPG if needed).
- Pass `--atlas` to use Atlas Cloud API instead of Antigravity built-in Nano Banana.

Usage:
  python keyframes.py <project_dir>            # Antigravity Nano Banana mode (default)
  python keyframes.py <project_dir> --atlas    # Atlas Cloud API mode
"""
import json
import os
import sys
from PIL import Image

from styles import compose_keyframe_prompt, compose_collage_prompt, resolve_theme, image_params

IMAGE_MODEL = "google/nano-banana-2/text-to-image"


def shots_of(beat):
    """Yield (shot_dict, shot_key) for a beat; synthesize one shot if none."""
    if beat.get("shots"):
        for s in beat["shots"]:
            yield s, f"{beat['id']}{s.get('id','')}"
    else:
        yield beat, f"{beat['id']}"


def run(project_dir, use_atlas=False):
    bpath = os.path.join(project_dir, "beats.json")
    with open(bpath, encoding="utf-8") as f:
        doc = json.load(f)
    aspect = doc.get("aspect", "16:9")
    img_model = doc.get("image_model", IMAGE_MODEL)
    img_res = doc.get("image_resolution", "1k")
    style = doc.get("style", "collage")
    theme = resolve_theme(doc.get("theme")) or {}
    collage_style = theme.get("idiom") or doc.get("collage_style", "american-retro")
    t_palette = theme.get("palette") or doc.get("palette")
    t_type = theme.get("type_style") or doc.get("type_style")
    t_finish = theme.get("finish") or doc.get("finish")
    era = doc.get("era")
    kf_dir = os.path.join(project_dir, "keyframes")
    os.makedirs(kf_dir, exist_ok=True)

    pending = []
    specs, by_key = {}, {}

    for beat in doc["beats"]:
        for shot, key in shots_of(beat):
            if shot.get("kind") == "host":
                continue
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

            if os.path.exists(dest_jpg):
                shot["keyframe_path"] = dest_jpg
                print(f"[{key}] OK (local): {dest_jpg}")
                continue

            if use_atlas:
                from provider import get_provider
                prov = get_provider(doc.get("provider"))
                specs[key] = (lambda p=prompt: prov.submit_image(
                    img_model, p, **image_params(img_model, aspect, img_res)))
                by_key[key] = shot
            else:
                shot["keyframe_path"] = dest_jpg
                pending.append((key, dest_jpg, prompt))

    if use_atlas and specs:
        from provider import get_provider, run_jobs
        prov = get_provider(doc.get("provider"))
        done = run_jobs(prov, specs, poll_s=3, stall_s=75, max_retries=2, deadline_s=300)
        for key, url in done.items():
            if not url:
                continue
            dest = os.path.join(kf_dir, f"kf_{key}.jpg")
            prov.download(url, dest)
            shot = by_key[key]
            shot["keyframe_url"] = url
            shot["keyframe_path"] = dest
            print(f"[{key}] saved {dest}")

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
    use_atlas = "--atlas" in sys.argv
    proj = args[0] if args else os.path.join(
        os.path.dirname(__file__), "..", "out", "tang-30s")
    run(os.path.abspath(proj), use_atlas=use_atlas)
