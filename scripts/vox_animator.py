#!/usr/bin/env python3
"""
vox_animator.py — Element-level Vox Paper-Collage Animator (100% Local: OpenCV + NumPy + Pillow + FFmpeg)

Animates the ACTUAL objects inside each generated Vox collage keyframe poster by:
  1. Extracting real collage cutouts/regions from the poster and reconstructing the
     paper/grid backdrop behind them via OpenCV Telea Inpainting (`cv2.inpaint`) or
     soft-feathered placeholder blur (`references/local-engine.md`) so moving cutouts
     never leave a duplicate "ghost" behind.
  2. Driving extracted cutouts with authentic Vox paper physics (`ease_out_back`,
     `pop_settle`, `fly_in`, `bounce`, 10fps stop-motion jitter, rotating needles/wheels/gavels).
  3. Drawing scene-specific 2D tactile paper VFX directly on the poster's own geometry
     (flowing water inside the pipeline, glowing trade routes along the world map,
     progressive reveal of the emerald $88,000 ribbon, firing neural/circuit traces, etc.).

Usage:
  python scripts/vox_animator.py out/singapore-vs-malaysia
"""
import json
import math
import os
import random
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

FPS = 25
STOP_FPS = 10  # Classic 10fps stop-motion cadence for paper cutouts


def stop_t(t: float, rate: float = STOP_FPS) -> float:
    return math.floor(t * rate) / rate


def ease_out_back(p: float, s: float = 1.75) -> float:
    p = max(0.0, min(1.0, p)) - 1.0
    return 1.0 + (s + 1.0) * (p ** 3) + s * (p ** 2)


def ease_out_cubic(p: float) -> float:
    p = max(0.0, min(1.0, p))
    return 1.0 - (1.0 - p) ** 3


def ease_in_out(p: float) -> float:
    p = max(0.0, min(1.0, p))
    return p * p * (3.0 - 2.0 * p)


def _open_ffmpeg_pipe(out_path: str, W: int, H: int, fps: int):
    return subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out_path
    ], stdin=subprocess.PIPE)


def apply_camera(frame_rgb: np.ndarray, zoom: float, cx_norm: float = 0.5, cy_norm: float = 0.5,
                 dx_px: float = 0.0, dy_px: float = 0.0) -> np.ndarray:
    """Crops and scales frame_rgb around normalized focal center (cx_norm, cy_norm) + pixel shake."""
    H, W = frame_rgb.shape[:2]
    z = max(1.01, float(zoom))
    cw, ch = int(round(W / z)), int(round(H / z))
    cx = cx_norm * W + dx_px
    cy = cy_norm * H + dy_px
    x0 = int(round(max(0, min(W - cw, cx - cw / 2.0))))
    y0 = int(round(max(0, min(H - ch, cy - ch / 2.0))))
    crop = frame_rgb[y0:y0 + ch, x0:x0 + cw]
    return cv2.resize(crop, (W, H), interpolation=cv2.INTER_LINEAR)


def extract_feathered_patch(base_np: np.ndarray, bbox_norm, feather: int = 11, inpaint_bg: bool = False):
    """
    Extracts a rectangular/feathered RGBA cutout from base_np (x0, y0, x1, y1 in 0..1 coords)
    and returns (cutout_pil, cx_px, cy_px, modified_bg_np).
    Following `references/local-engine.md`: blurs or inpaints the home region on the backdrop
    so that while the cutout is flying/scaling/rotating in, there is no hard duplicate edge.
    """
    H, W = base_np.shape[:2]
    x0 = int(round(bbox_norm[0] * W))
    y0 = int(round(bbox_norm[1] * H))
    x1 = int(round(bbox_norm[2] * W))
    y1 = int(round(bbox_norm[3] * H))
    bw, bh = max(2, x1 - x0), max(2, y1 - y0)

    crop_rgb = base_np[y0:y1, x0:x1].copy()
    mask = np.zeros((bh, bw), dtype=np.uint8)
    pad = max(2, feather // 2)
    cv2.rectangle(mask, (pad, pad), (bw - pad, bh - pad), 255, -1)
    k = feather if feather % 2 == 1 else feather + 1
    alpha = cv2.GaussianBlur(mask, (k, k), 0)
    cutout_pil = Image.fromarray(np.dstack([crop_rgb, alpha]), "RGBA")

    bg_np = base_np.copy()
    if inpaint_bg:
        inp_mask = np.zeros((H, W), dtype=np.uint8)
        inp_mask[y0:y1, x0:x1] = 255
        bgr = cv2.cvtColor(bg_np, cv2.COLOR_RGB2BGR)
        bgr = cv2.inpaint(bgr, inp_mask, 9, cv2.INPAINT_TELEA)
        bg_np = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    else:
        # Local blurred placeholder (from references/local-engine.md)
        blurred_patch = cv2.GaussianBlur(bg_np[y0:y1, x0:x1], (45, 45), 0)
        a_norm = (alpha.astype(np.float32) / 255.0)[:, :, None]
        bg_np[y0:y1, x0:x1] = (blurred_patch * a_norm + bg_np[y0:y1, x0:x1] * (1.0 - a_norm)).astype(np.uint8)

    return cutout_pil, (x0 + x1) / 2.0, (y0 + y1) / 2.0, bg_np


def paste_animated_cutout(canvas: Image.Image, cutout_pil: Image.Image, cx: float, cy: float,
                          scale: float = 1.0, rot_deg: float = 0.0, dx: float = 0.0, dy: float = 0.0,
                          alpha_mult: float = 1.0, shadow_offset: int = 8):
    if alpha_mult <= 0.01:
        return
    nw = max(2, int(round(cutout_pil.width * scale)))
    nh = max(2, int(round(cutout_pil.height * scale)))
    im = cutout_pil.resize((nw, nh), Image.LANCZOS)
    if abs(rot_deg) > 0.05:
        im = im.rotate(rot_deg, expand=True, resample=Image.BICUBIC)
    if alpha_mult < 0.999:
        r, g, b, a = im.split()
        a = a.point(lambda v: int(v * alpha_mult))
        im = Image.merge("RGBA", (r, g, b, a))

    px = int(round(cx + dx - im.width / 2.0))
    py = int(round(cy + dy - im.height / 2.0))

    if shadow_offset > 0 and abs(scale - 1.0) + abs(rot_deg) + abs(dx) + abs(dy) > 0.01:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sh.paste((15, 12, 10, int(95 * alpha_mult)), (0, 0), im.split()[3])
        sh = sh.filter(ImageFilter.GaussianBlur(5))
        canvas.alpha_composite(sh, (px + shadow_offset, py + shadow_offset))

    canvas.alpha_composite(im, (px, py))


def draw_paper_bolt(draw: ImageDraw.ImageDraw, p0, p1, seed: int, width: int = 7,
                    fill=(235, 52, 36, 255), core=(255, 242, 165, 255), outline=(22, 18, 15, 235)):
    """Draws a 2D jagged paper-cutout lightning/fracture bolt between p0 and p1."""
    rng = random.Random(seed)
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist < 5:
        return
    ux, uy = dx / dist, dy / dist
    nx, ny = -uy, ux
    steps = max(4, int(dist / 34))
    pts_top, pts_bot, center_pts = [(x0, y0)], [(x0, y0)], [(x0, y0)]
    for i in range(1, steps):
        f = i / steps
        env = math.sin(f * math.pi)
        jitter = rng.uniform(-20, 20) * env
        cx = x0 + dx * f + nx * jitter
        cy = y0 + dy * f + ny * jitter
        w = width * (0.55 + 0.85 * env)
        pts_top.append((cx + nx * w, cy + ny * w))
        pts_bot.append((cx - nx * w, cy - ny * w))
        center_pts.append((cx, cy))
    pts_top.append((x1, y1))
    pts_bot.append((x1, y1))
    center_pts.append((x1, y1))
    poly = pts_top + list(reversed(pts_bot))
    draw.polygon([(x + 3, y + 4) for x, y in poly], fill=(0, 0, 0, 95))
    draw.polygon(poly, fill=fill, outline=outline)
    if len(center_pts) >= 2:
        draw.line(center_pts, fill=core, width=max(2, width // 2))


# =====================================================================
# SINGAPORE VS MALAYSIA — OBJECT-LEVEL COLLAGE ANIMATORS
# =====================================================================

def anim_1a(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_1a.jpg:
    - Extracts the red '1965' rubber stamp on the Johor Strait and the 'EXPELLED IN 1965'
      torn-paper banner + red paper triangle cutouts.
    - Animates the 'EXPELLED IN 1965' banner flying/popping in, the '1965' stamp slapping
      down with camera shake, and a glowing red separation line tracing the torn strait!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))

    # Extract actual objects from kf_1a.jpg
    stamp_pil, st_cx, st_cy, bg1 = extract_feathered_patch(base_np, (0.354, 0.502, 0.496, 0.642), feather=13, inpaint_bg=True)
    banner_pil, bn_cx, bn_cy, bg2 = extract_feathered_patch(bg1, (0.515, 0.395, 0.968, 0.625), feather=15, inpaint_bg=False)
    bg_pil = Image.fromarray(bg2).convert("RGBA")

    # Torn strait path points for animated red scissor-cut trace
    tear_pts = [
        (int(0.415 * W), int(0.065 * H)),
        (int(0.422 * W), int(0.220 * H)),
        (int(0.432 * W), int(0.380 * H)),
        (int(0.425 * W), int(0.540 * H)),
        (int(0.410 * W), int(0.695 * H)),
        (int(0.392 * W), int(0.865 * H)),
    ]

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 11)
        canvas = bg_pil.copy()

        # 1. Animate 'EXPELLED IN 1965' paper banner popping/settling in + stop-motion breathing
        p_bn = ease_out_back(min(1.0, t / 0.48), s=1.65)
        bn_scale = 1.28 - 0.28 * p_bn + (0.008 * math.sin(st * 7.0) if t > 0.5 else 0.0)
        bn_rot = (1.0 - ease_out_cubic(min(1.0, t / 0.48))) * -4.0 + rng.uniform(-0.4, 0.4)
        paste_animated_cutout(canvas, banner_pil, bn_cx, bn_cy, scale=bn_scale, rot_deg=bn_rot)

        # 2. Animate the red '1965' stamp from the image slapping onto the Johor Strait
        stamp_t0 = 0.55 if mode == "1a_wide" else 0.25
        if t >= stamp_t0:
            dt = t - stamp_t0
            p_st = ease_out_back(min(1.0, dt / 0.28), s=1.9)
            st_scale = 1.85 - 0.85 * p_st
            st_rot = (1.0 - ease_out_cubic(min(1.0, dt / 0.28))) * -14.0 + rng.uniform(-1.2, 1.2)
            paste_animated_cutout(canvas, stamp_pil, st_cx, st_cy, scale=st_scale, rot_deg=st_rot,
                                  dx=rng.uniform(-2, 2), dy=rng.uniform(-2, 2))

        # 3. Animated red separation trace & pulsing radar ring on Singapore island tip
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(fx)
        prog = min(1.0, t / 1.4)
        n_seg = len(tear_pts) - 1
        for i in range(n_seg):
            seg_p = max(0.0, min(1.0, prog * n_seg - i))
            if seg_p > 0:
                x0, y0 = tear_pts[i]
                x1, y1 = tear_pts[i + 1]
                xm = x0 + (x1 - x0) * seg_p
                ym = y0 + (y1 - y0) * seg_p
                draw.line([(x0, y0), (xm, ym)], fill=(228, 42, 32, 215), width=6)

        # Pulsing paper ring around Singapore island (0.435W, 0.725H)
        sg_x, sg_y = int(0.435 * W), int(0.725 * H)
        ring_p = (t * 1.2) % 1.0
        r_ring = int(20 + 68 * ring_p)
        draw.ellipse([sg_x - r_ring, sg_y - r_ring, sg_x + r_ring, sg_y + r_ring],
                     outline=(228, 42, 32, int(220 * (1.0 - ring_p))), width=4)

        canvas.alpha_composite(fx)

        # Camera framing (wide vs tight strait cut-in)
        sx = sy = 0.0
        if t >= stamp_t0 and (t - stamp_t0) < 0.45:
            d = t - stamp_t0
            amp = 15.0 * math.exp(-13.0 * d)
            sx, sy = amp * math.sin(d * 68), amp * math.cos(d * 55)

        if mode == "1a_wide":
            zoom = 1.03 + 0.11 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.50, 0.50, sx, sy)
        else:
            zoom = 1.38 + 0.12 * (t / dur)
            cx_n = 0.44 + 0.04 * (t / dur)
            cy_n = 0.62 - 0.04 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, cx_n, cy_n, sx, sy)

        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


def anim_1b(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_1b.jpg:
    - Mode '1b_pipeline': Focuses on the halftone water pipeline crossing the blue paper strait;
      animates bright cyan/white water pressure pulses flowing through the pipe + water droplets.
    - Mode '1b_skyline_dollars': Extracts the golden Singapore skyline silhouette and the
      towering emerald green dollar stack so the dollar stack rises up and the golden skyline
      pops in front of it with shimmering golden light rays!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))
    sky_pil, sky_cx, sky_cy, bg1 = extract_feathered_patch(base_np, (0.580, 0.395, 0.992, 0.728), feather=15)
    dlr_pil, dlr_cx, dlr_cy, bg2 = extract_feathered_patch(bg1, (0.505, 0.115, 0.802, 0.855), feather=17)

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    # Pipeline axis from bottom-left (0.02W, 0.66H) to top-right tip (0.45W, 0.275H)
    p_start = (0.02 * W, 0.665 * H)
    p_end = (0.448 * W, 0.275 * H)

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 23)

        if mode == "1b_pipeline":
            canvas = Image.fromarray(base_np).convert("RGBA")
            fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw = ImageDraw.Draw(fx)

            # Animated water flow packets travelling along the pipeline
            for k in range(5):
                prog = ((t * 0.65) + k * 0.20) % 1.0
                px = p_start[0] + (p_end[0] - p_start[0]) * prog
                py = p_start[1] + (p_end[1] - p_start[1]) * prog
                tx = p_start[0] + (p_end[0] - p_start[0]) * max(0.0, prog - 0.08)
                ty = p_start[1] + (p_end[1] - p_start[1]) * max(0.0, prog - 0.08)
                w_rad = int(18 * (1.0 - 0.55 * prog))
                draw.line([(tx, ty), (px, py)], fill=(70, 215, 255, 210), width=max(4, w_rad))
                draw.ellipse([px - w_rad, py - w_rad, px + w_rad, py + w_rad],
                             fill=(220, 250, 255, 235), outline=(20, 85, 140, 220), width=2)

            canvas.alpha_composite(fx)
            zoom = 1.34 + 0.10 * (t / dur)
            cx_n = 0.27 + 0.05 * (t / dur)
            cy_n = 0.50 - 0.04 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, cx_n, cy_n)
        else:
            canvas = Image.fromarray(bg2).convert("RGBA")
            # 1. Dollar stack rises with spring overshoot
            p_dlr = ease_out_back(min(1.0, t / 0.55), s=1.6)
            dlr_dy = (1.0 - p_dlr) * 140.0 + rng.uniform(-2, 2)
            dlr_sc = 0.88 + 0.12 * p_dlr
            paste_animated_cutout(canvas, dlr_pil, dlr_cx, dlr_cy, scale=dlr_sc, dy=dlr_dy)

            # 2. Golden Singapore skyline pops up right after (t > 0.25s)
            p_sky = ease_out_back(min(1.0, max(0.0, (t - 0.22) / 0.52)), s=1.8)
            sky_dy = (1.0 - p_sky) * 160.0 + rng.uniform(-1.5, 1.5)
            sky_sc = 0.85 + 0.15 * p_sky
            paste_animated_cutout(canvas, sky_pil, sky_cx, sky_cy, scale=sky_sc, dy=sky_dy)

            # 3. Stop-motion golden paper sparkles around the skyline & dollar stack
            fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw = ImageDraw.Draw(fx)
            for sp_x, sp_y in [(0.62, 0.22), (0.76, 0.18), (0.88, 0.34), (0.93, 0.42)]:
                if rng.random() < 0.75:
                    gx, gy = int(sp_x * W + rng.uniform(-10, 10)), int(sp_y * H + rng.uniform(-10, 10))
                    r = rng.randint(10, 22)
                    draw.line([(gx - r, gy), (gx + r, gy)], fill=(255, 205, 35, 235), width=4)
                    draw.line([(gx, gy - r), (gx, gy + r)], fill=(255, 205, 35, 235), width=4)
            canvas.alpha_composite(fx)

            zoom = 1.28 + 0.12 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.72, 0.49)

        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


def anim_1c(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_1c.jpg:
    - Inpaints the static red needle inside the 0% gauge (center: 0.808W, 0.485H) and
      animates the red gauge needle dropping down to 0% and rattling!
    - Extracts the two 'COLLAPSE?' paper stamps so they slap onto the poster.
    - Animates crackling red fracture lightning bolts inside the split Singapore island!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))
    H, W = base_np.shape[:2]
    r, g, b = base_np[:, :, 0].astype(int), base_np[:, :, 1].astype(int), base_np[:, :, 2].astype(int)
    yy, xx = np.mgrid[0:H, 0:W]

    # 1. Erase the red needle inside the right-hand gauge (cx=0.808W, cy=0.485H)
    gx, gy = int(0.808 * W), int(0.485 * H)
    dist_g = np.hypot(xx - gx, yy - gy)
    needle_mask = (
        (dist_g < int(0.115 * H)) &
        (yy < gy + int(0.055 * H)) &  # keep the '0%' text at the bottom of the dial!
        ~((yy > gy + int(0.035 * H)) & (np.abs(xx - gx) < int(0.035 * W))) &
        ((r - g) > 45) & (r > 130)
    ).astype(np.uint8) * 255
    needle_mask = cv2.dilate(needle_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)), iterations=1)
    clean_bgr = cv2.inpaint(cv2.cvtColor(base_np, cv2.COLOR_RGB2BGR), needle_mask, 9, cv2.INPAINT_TELEA)
    clean_np = cv2.cvtColor(clean_bgr, cv2.COLOR_BGR2RGB)

    # 2. Extract the top and bottom 'COLLAPSE?' paper strips
    col_top_pil, ct_cx, ct_cy, bg1 = extract_feathered_patch(clean_np, (0.535, 0.095, 0.755, 0.290), feather=13)
    col_bot_pil, cb_cx, cb_cy, bg2 = extract_feathered_patch(bg1, (0.580, 0.725, 0.785, 0.918), feather=13)
    bg_pil = Image.fromarray(bg2).convert("RGBA")

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    crack_top = (int(0.352 * W), int(0.215 * H))
    crack_mid = (int(0.348 * W), int(0.445 * H))
    crack_bot = (int(0.358 * W), int(0.655 * H))

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 37)
        canvas = bg_pil.copy()

        # Animate the two 'COLLAPSE?' paper strips slapping in
        p1 = ease_out_back(min(1.0, t / 0.38), s=1.8)
        paste_animated_cutout(canvas, col_top_pil, ct_cx, ct_cy,
                              scale=1.35 - 0.35 * p1, rot_deg=rng.uniform(-1.5, 1.5))
        if t >= 0.25:
            p2 = ease_out_back(min(1.0, (t - 0.25) / 0.38), s=1.8)
            paste_animated_cutout(canvas, col_bot_pil, cb_cx, cb_cy,
                                  scale=1.35 - 0.35 * p2, rot_deg=rng.uniform(-1.5, 1.5))

        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(fx)

        # Animate the red gauge needle dropping from +30 deg (70%) down to +140 deg (0% mark at bottom-left)
        drop_p = ease_out_back(min(1.0, t / 0.95), s=1.35)
        jitter = rng.uniform(-4.5, 4.5) if t > 0.7 else 0.0
        ang_deg = -45.0 - drop_p * 92.0 + jitter  # sweeps counter-clockwise to bottom-left (137 deg)
        # Wait: in screen coords (0 deg = right, 90 deg = down, 138 deg = bottom-left '0' mark, -42 deg = top-right)
        ang_rad = math.radians(-38.0 + drop_p * 176.0 + jitter)
        ux, uy = math.cos(ang_rad), math.sin(ang_rad)
        nx, ny = -uy, ux
        tip_l, tail_l = int(0.095 * H), int(0.042 * H)
        poly = [
            (gx - ux * tail_l + nx * 6, gy - uy * tail_l + ny * 6),
            (gx - ux * tail_l - nx * 6, gy - uy * tail_l - ny * 6),
            (gx + ux * tip_l - nx * 2.5, gy + uy * tip_l - ny * 2.5),
            (gx + ux * tip_l + nx * 2.5, gy + uy * tip_l + ny * 2.5),
        ]
        draw.polygon([(x + 3, y + 3) for x, y in poly], fill=(0, 0, 0, 110))
        draw.polygon(poly, fill=(218, 38, 32, 255), outline=(140, 18, 15, 255))
        draw.ellipse([gx - 11, gy - 11, gx + 11, gy + 11], fill=(218, 38, 32, 255), outline=(245, 240, 230, 255), width=3)

        # Animated red fracture energy crackling along the split island crack
        step_seed = int(st * 20)
        if step_seed % 2 == 0:
            draw_paper_bolt(draw, crack_top, crack_mid, seed=step_seed * 13, width=7)
        else:
            draw_paper_bolt(draw, crack_mid, crack_bot, seed=step_seed * 17, width=7)

        canvas.alpha_composite(fx)

        if mode == "1c_gauge_barrels":
            zoom = 1.32 + 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.68, 0.54)
        else:
            zoom = 1.15 - 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.45, 0.48)

        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


def anim_2a(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_2a.jpg ('450X LARGER'):
    - Extracts the '450X LARGER' headline banner, the golden oil barrels, the silver tin ingots,
      and the magnifying glass + 'SINGAPORE' label on the right.
    - Animates the oil barrels & tin ingots popping in sequentially, the magnifying glass
      zooming/pulsing over the tiny red Singapore dot, and golden oil droplets pumping!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))
    hdr_pil, hdr_cx, hdr_cy, bg1 = extract_feathered_patch(base_np, (0.235, 0.062, 0.655, 0.312), feather=15)
    brl_pil, brl_cx, brl_cy, bg2 = extract_feathered_patch(bg1, (0.162, 0.448, 0.345, 0.775), feather=15)
    tin_pil, tin_cx, tin_cy, bg3 = extract_feathered_patch(bg2, (0.378, 0.485, 0.542, 0.705), feather=15)
    mag_pil, mag_cx, mag_cy, bg4 = extract_feathered_patch(bg3, (0.718, 0.352, 0.916, 0.655), feather=15)
    bg_pil = Image.fromarray(bg4).convert("RGBA")

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 41)
        canvas = bg_pil.copy()

        # 1. Headline '450X LARGER'
        p_hdr = ease_out_back(min(1.0, t / 0.42), s=1.7)
        paste_animated_cutout(canvas, hdr_pil, hdr_cx, hdr_cy,
                              scale=1.22 - 0.22 * p_hdr, rot_deg=rng.uniform(-0.6, 0.6))

        # 2. Golden oil barrels bounce/pop in + pulse
        p_brl = ease_out_back(min(1.0, max(0.0, (t - 0.12) / 0.45)), s=1.85)
        brl_sc = (0.75 + 0.25 * p_brl) * (1.0 + 0.018 * math.sin(t * 7.0))
        paste_animated_cutout(canvas, brl_pil, brl_cx, brl_cy, scale=brl_sc, rot_deg=rng.uniform(-1.0, 1.0))

        # 3. Silver tin ingots pop in
        p_tin = ease_out_back(min(1.0, max(0.0, (t - 0.28) / 0.45)), s=1.85)
        tin_sc = (0.75 + 0.25 * p_tin) * (1.0 + 0.018 * math.cos(t * 6.5))
        paste_animated_cutout(canvas, tin_pil, tin_cx, tin_cy, scale=tin_sc, rot_deg=rng.uniform(-1.0, 1.0))

        # 4. Magnifying glass over tiny red Singapore dot zooms & hovers
        p_mag = ease_out_back(min(1.0, max(0.0, (t - 0.20) / 0.50)), s=1.9)
        mag_sc = (1.35 - 0.35 * p_mag) * (1.0 + 0.035 * math.sin(t * 5.5))
        mag_rot = math.sin(t * 3.5) * 2.5
        paste_animated_cutout(canvas, mag_pil, mag_cx, mag_cy, scale=mag_sc, rot_deg=mag_rot)

        # 5. Pulsing target rings around the microscopic red dot of Singapore (0.795W, 0.492H)
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(fx)
        dot_x, dot_y = int(0.795 * W), int(0.492 * H)
        for k in range(2):
            ph = (t * 1.3 + k * 0.5) % 1.0
            rad = int(12 + 52 * ph)
            draw.ellipse([dot_x - rad, dot_y - rad, dot_x + rad, dot_y + rad],
                         outline=(225, 40, 30, int(230 * (1.0 - ph))), width=4)
        canvas.alpha_composite(fx)

        if mode == "2a_wide":
            zoom = 1.03 + 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.50, 0.50)
        elif mode == "2a_resources_close":
            zoom = 1.35 + 0.08 * (t / dur)
            cx_n = 0.28 + 0.08 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, cx_n, 0.55)
        else:  # 2a_magnifier_close
            zoom = 1.42 + 0.14 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.78, 0.50)

        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


def anim_2b(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_2b.jpg ('2,000,000 PEOPLE' Harbor & Torn Blue Waves):
    - Extracts the '2,000,000 PEOPLE' card and bottom torn blue paper wave strips.
    - Animates the '2,000,000 PEOPLE' card slapping onto the harbor and the torn blue
      paper ocean waves rocking back and forth in 10fps stop-motion!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))
    card_pil, cd_cx, cd_cy, bg1 = extract_feathered_patch(base_np, (0.532, 0.445, 0.802, 0.758), feather=15)
    wave_l_pil, wl_cx, wl_cy, bg2 = extract_feathered_patch(bg1, (0.0, 0.405, 0.205, 0.695), feather=15)
    wave_r_pil, wr_cx, wr_cy, bg3 = extract_feathered_patch(bg2, (0.795, 0.365, 1.0, 0.725), feather=15)
    bg_pil = Image.fromarray(bg3).convert("RGBA")

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 53)
        canvas = bg_pil.copy()

        # Rocking torn-paper ocean waves in 10fps stop-motion
        wl_dx = math.sin(st * 4.5) * 14.0
        wl_dy = math.cos(st * 5.5) * 8.0
        paste_animated_cutout(canvas, wave_l_pil, wl_cx, wl_cy, scale=1.04,
                              rot_deg=math.sin(st * 3.5) * 2.2, dx=wl_dx, dy=wl_dy)

        wr_dx = -math.sin(st * 4.2) * 14.0
        wr_dy = math.sin(st * 5.0) * 9.0
        paste_animated_cutout(canvas, wave_r_pil, wr_cx, wr_cy, scale=1.04,
                              rot_deg=-math.cos(st * 3.8) * 2.2, dx=wr_dx, dy=wr_dy)

        # '2,000,000 PEOPLE' card slaps in
        p_cd = ease_out_back(min(1.0, t / 0.45), s=1.85)
        cd_sc = 1.38 - 0.38 * p_cd
        cd_rot = (1.0 - ease_out_cubic(min(1.0, t / 0.45))) * 9.0 + rng.uniform(-0.8, 0.8)
        paste_animated_cutout(canvas, card_pil, cd_cx, cd_cy, scale=cd_sc, rot_deg=cd_rot)

        if mode == "2b_harbor_wide":
            zoom = 1.04 + 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.50, 0.48)
        else:
            zoom = 1.30 - 0.12 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.54, 0.60)

        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


def anim_3a(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_3a.jpg ('THE 3 BIG BETS'):
    - Extracts the wooden Gavel cutout (x:0.675..0.958, y:0.352..0.665) and the
      7 'E-N-G-L-I-S-H' typewriter letter blocks (x:0.605..0.956, y:0.775..0.892).
    - Animates:
      * Each of the 7 E-N-G-L-I-S-H blocks popping in one by one like typewriter keys!
      * The wooden gavel swinging up and striking down onto the sound block with camera shake!
      * Glowing red & gold trade packets shooting from Singapore (0.508W, 0.592H) to
        New York (0.244W, 0.480H), London (0.368W, 0.435H), and Tokyo (0.563W, 0.486H)!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))

    # Extract Gavel
    gavel_pil, gv_cx, gv_cy, bg_cur = extract_feathered_patch(base_np, (0.675, 0.350, 0.960, 0.668), feather=15)

    # Extract each of the 7 E-N-G-L-I-S-H letter blocks individually!
    letters = []
    x_start, x_end = 0.606, 0.956
    step_w = (x_end - x_start) / 7.0
    for i in range(7):
        lx0 = x_start + i * step_w
        lx1 = lx0 + step_w
        lpil, lcx, lcy, bg_cur = extract_feathered_patch(bg_cur, (lx0, 0.774, lx1, 0.892), feather=9, inpaint_bg=True)
        letters.append((lpil, lcx, lcy))

    bg_pil = Image.fromarray(bg_cur).convert("RGBA")

    # Coordinates on the world map
    sg_pt = (int(0.508 * W), int(0.592 * H))
    ny_pt = (int(0.244 * W), int(0.480 * H))
    ln_pt = (int(0.368 * W), int(0.435 * H))
    tk_pt = (int(0.563 * W), int(0.486 * H))

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 67)
        canvas = bg_pil.copy()

        # 1. Typewriter E-N-G-L-I-S-H blocks pop in one by one
        for i, (lpil, lcx, lcy) in enumerate(letters):
            t0 = 0.08 + i * 0.14 if mode == "3a_english_typewriter" else 0.05 + i * 0.08
            if t < t0:
                continue
            dt = t - t0
            p_l = ease_out_back(min(1.0, dt / 0.22), s=2.1)
            sc = 1.42 - 0.42 * p_l
            dy = (1.0 - p_l) * -28.0 + rng.uniform(-1.5, 1.5)
            rot = rng.uniform(-1.8, 1.8)
            paste_animated_cutout(canvas, lpil, lcx, lcy, scale=sc, rot_deg=rot, dy=dy, shadow_offset=5)

        # 2. Gavel swings up (+18 deg) and slams down (0 deg) repeatedly or on impact
        strike_t = 0.45 if mode == "3a_gavel_strike" else 0.65
        if t < strike_t:
            gv_rot = -18.0 * math.sin((t / strike_t) * (math.pi / 2.0))
            gv_sc = 1.06
        else:
            dt_g = t - strike_t
            p_g = min(1.0, dt_g / 0.16)
            gv_rot = -18.0 * (1.0 - ease_out_cubic(p_g)) + (math.sin(dt_g * 28.0) * 3.0 * math.exp(-6.0 * dt_g))
            gv_sc = 1.0 + 0.05 * math.exp(-8.0 * dt_g)
        paste_animated_cutout(canvas, gavel_pil, gv_cx, gv_cy, scale=gv_sc, rot_deg=gv_rot)

        # 3. Animated glowing trade routes shooting from Singapore to NY, London, Tokyo
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(fx)
        routes = [
            (sg_pt, ny_pt, (235, 55, 42, 245)),
            (sg_pt, ln_pt, (250, 200, 45, 245)),
            (sg_pt, tk_pt, (235, 55, 42, 245)),
        ]
        for idx_r, (p0, p1, col) in enumerate(routes):
            for pkt in range(2):
                prog = ((t * 0.72) + idx_r * 0.28 + pkt * 0.5) % 1.0
                px = p0[0] + (p1[0] - p0[0]) * prog
                py = p0[1] + (p1[1] - p0[1]) * prog
                tx = p0[0] + (p1[0] - p0[0]) * max(0.0, prog - 0.14)
                ty = p0[1] + (p1[1] - p0[1]) * max(0.0, prog - 0.14)
                draw.line([(tx, ty), (px, py)], fill=col, width=7)
                draw.ellipse([px - 9, py - 9, px + 9, py + 9], fill=(255, 252, 220, 255), outline=col, width=3)

            # Pulsing city node ring at destination
            ph = (t * 1.4 + idx_r * 0.33) % 1.0
            rad = int(8 + 28 * ph)
            draw.ellipse([p1[0] - rad, p1[1] - rad, p1[0] + rad, p1[1] + rad],
                         outline=(col[0], col[1], col[2], int(225 * (1.0 - ph))), width=3)

        canvas.alpha_composite(fx)

        # Camera shake on gavel strike
        sx = sy = 0.0
        if t >= strike_t and (t - strike_t) < 0.45:
            d = t - strike_t
            amp = 18.0 * math.exp(-12.0 * d)
            sx, sy = amp * math.sin(d * 70), amp * math.cos(d * 58)

        if mode == "3a_wide":
            zoom = 1.03 + 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.50, 0.50, sx, sy)
        elif mode == "3a_english_typewriter":
            zoom = 1.42 + 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.74, 0.74, sx, sy)
        elif mode == "3a_gavel_strike":
            zoom = 1.40 + 0.12 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.78, 0.52, sx, sy)
        else:  # 3a_world_routes
            zoom = 1.32 - 0.12 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.38, 0.48, sx, sy)

        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


def anim_3b(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_3b.jpg (Silicon Wafer, Cargo Containers & International Banks):
    - Sweeps an iridescent holographic light sheen across the circular silicon wafer (cx=0.318W, cy=0.512H).
    - Extracts the cargo container stack and the two classical bank facades so they drop/pop in
      with elastic physics!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))
    cnt_pil, cnt_cx, cnt_cy, bg1 = extract_feathered_patch(base_np, (0.552, 0.172, 0.912, 0.495), feather=15)
    bnk_pil, bnk_cx, bnk_cy, bg2 = extract_feathered_patch(bg1, (0.575, 0.528, 0.958, 0.855), feather=15)

    yy, xx = np.mgrid[0:H, 0:W]
    w_cx, w_cy, w_r = int(0.318 * W), int(0.512 * H), int(0.345 * H)
    wafer_mask = (np.hypot(xx - w_cx, yy - w_cy) < w_r).astype(np.float32)
    wafer_mask = cv2.GaussianBlur(wafer_mask, (15, 15), 0)

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 73)

        # Diagonal iridescent shimmer wave sweeping across the silicon wafer
        diag = (xx - w_cx) * 0.7 + (yy - w_cy) * 0.7
        band_pos = -w_r + ((t * 360.0) % (2.2 * w_r))
        shimmer = np.exp(-((diag - band_pos) ** 2) / (2 * (55.0 ** 2))) * wafer_mask
        frame_np = bg2.copy().astype(np.float32)
        frame_np[:, :, 0] = np.clip(frame_np[:, :, 0] + shimmer * 65.0, 0, 255)
        frame_np[:, :, 1] = np.clip(frame_np[:, :, 1] + shimmer * 85.0, 0, 255)
        frame_np[:, :, 2] = np.clip(frame_np[:, :, 2] + shimmer * 95.0, 0, 255)

        canvas = Image.fromarray(frame_np.astype(np.uint8)).convert("RGBA")

        # Cargo containers drop/bounce in
        p_c = ease_out_back(min(1.0, t / 0.45), s=1.8)
        paste_animated_cutout(canvas, cnt_pil, cnt_cx, cnt_cy,
                              scale=0.82 + 0.18 * p_c, dy=(1.0 - p_c) * -90.0 + rng.uniform(-1.5, 1.5))

        # Classical bank cutouts pop up
        p_b = ease_out_back(min(1.0, max(0.0, (t - 0.25) / 0.48)), s=1.8)
        paste_animated_cutout(canvas, bnk_pil, bnk_cx, bnk_cy,
                              scale=0.82 + 0.18 * p_b, dy=(1.0 - p_b) * 90.0 + rng.uniform(-1.5, 1.5))

        zoom = 1.06 + 0.10 * (t / dur)
        cx_n = 0.46 + 0.08 * (t / dur)
        out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, cx_n, 0.50)
        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


def anim_4a(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_4a.jpg ('$88K VS $13K' Chart):
    - Inpaints the emerald-green 'SINGAPORE $88,000' ascending ribbon so we can progressively
      grow/wipe the green arrow from left (1965) to top-right (2025) as it shoots upward!
    - Extracts the '$88K VS $13K' headline banner, the walking figure cutout, and the gold coins
      so they animate independently!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))
    r, g, b = base_np[:, :, 0].astype(int), base_np[:, :, 1].astype(int), base_np[:, :, 2].astype(int)
    yy, xx = np.mgrid[0:H, 0:W]

    # Mask of the emerald green arrow ribbon (including the white text 'SINGAPORE $88,000' inside it)
    green_raw = ((g > 115) & ((g - r) > 35) & (xx > int(0.05 * W))).astype(np.uint8) * 255
    # Close holes so the white letters 'SINGAPORE $88,000' inside the green ribbon are included!
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (45, 45))
    green_closed = cv2.morphologyEx(green_raw, cv2.MORPH_CLOSE, kernel_close)
    green_dilated = cv2.dilate(green_closed, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)), iterations=1)

    # Reconstruct clean crisp graph-paper background (with vertical & horizontal grid lines!) behind the green arrow
    bg_no_green_np = base_np.copy()
    # Sample clean paper color and grid lines from rows/cols outside the green mask
    paper_rgb = np.array([247, 245, 239], dtype=np.uint8)
    grid_rgb = np.array([28, 28, 28], dtype=np.uint8)
    # Detect vertical grid columns from row y=int(0.40*H) or y=int(0.12*H) where not masked
    col_dark = np.zeros(W, dtype=bool)
    for check_y in (int(0.10 * H), int(0.42 * H), int(0.68 * H)):
        row_slice = base_np[check_y, :, :]
        row_mask = green_dilated[check_y, :] == 0
        is_grid_col = (row_slice[:, 0] < 90) & (row_slice[:, 1] < 90) & (row_slice[:, 2] < 90) & row_mask
        col_dark |= is_grid_col
    # Detect horizontal grid rows from col x=int(0.62*W) or x=int(0.32*W) where not masked
    row_dark = np.zeros(H, dtype=bool)
    for check_x in (int(0.32 * W), int(0.62 * W), int(0.85 * W)):
        col_slice = base_np[:, check_x, :]
        col_mask = green_dilated[:, check_x] == 0
        is_grid_row = (col_slice[:, 0] < 90) & (col_slice[:, 1] < 90) & (col_slice[:, 2] < 90) & col_mask
        row_dark |= is_grid_row

    synth_grid = np.full_like(base_np, paper_rgb)
    synth_grid[row_dark, :, :] = grid_rgb
    synth_grid[:, col_dark, :] = grid_rgb
    synth_grid = cv2.GaussianBlur(synth_grid, (3, 3), 0)
    mask_bool = green_dilated > 0
    bg_no_green_np[mask_bool] = synth_grid[mask_bool]

    # Also extract the '$88K VS $13K' banner
    hdr_pil, hdr_cx, hdr_cy, bg_clean = extract_feathered_patch(bg_no_green_np, (0.075, 0.055, 0.575, 0.355), feather=15)

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 83)

        # Progressive left-to-right growth of the emerald green arrow ribbon!
        if mode == "4a_chart_grow":
            grow_p = ease_in_out(min(1.0, t / (dur * 0.72)))
        else:
            grow_p = 1.0
        reveal_x = int((0.06 + 0.89 * grow_p) * W)

        reveal_mask = np.zeros((H, W), dtype=np.float32)
        reveal_mask[:, :reveal_x] = 1.0
        reveal_mask = cv2.GaussianBlur(reveal_mask, (21, 21), 0)
        arrow_alpha = (green_dilated.astype(np.float32) / 255.0) * reveal_mask

        # Traveling bright highlight wave along the green ribbon
        wave_x = (0.10 + ((t * 0.55) % 0.85)) * W
        wave_boost = np.exp(-((xx - wave_x) ** 2) / (2 * (70.0 ** 2))) * arrow_alpha

        comp_np = (bg_clean.astype(np.float32) * (1.0 - arrow_alpha[:, :, None]) +
                   base_np.astype(np.float32) * arrow_alpha[:, :, None])
        comp_np[:, :, 0] = np.clip(comp_np[:, :, 0] + wave_boost * 55.0, 0, 255)
        comp_np[:, :, 1] = np.clip(comp_np[:, :, 1] + wave_boost * 75.0, 0, 255)
        comp_np[:, :, 2] = np.clip(comp_np[:, :, 2] + wave_boost * 45.0, 0, 255)

        canvas = Image.fromarray(comp_np.astype(np.uint8)).convert("RGBA")

        # Animate '$88K VS $13K' headline banner
        p_h = ease_out_back(min(1.0, t / 0.42), s=1.75)
        paste_animated_cutout(canvas, hdr_pil, hdr_cx, hdr_cy,
                              scale=1.24 - 0.24 * p_h, rot_deg=rng.uniform(-0.6, 0.6))

        if mode == "4a_chart_grow":
            zoom = 1.03 + 0.09 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.50, 0.50)
        else:  # 4a_peak_close
            zoom = 1.32 + 0.10 * (t / dur)
            cx_n = 0.62 + 0.10 * (t / dur)
            cy_n = 0.48 - 0.08 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, cx_n, cy_n)

        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


def anim_4b(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_4b.jpg (Steel Bank Vault, Gold Bullion & '$1 TRILLION+ SOVEREIGN WEALTH'):
    - Extracts the '$1 TRILLION+' and 'SOVEREIGN WEALTH' paper banners so they slap in.
    - Sweeps golden gleams across the stacked gold bullion bars.
    - Animates glowing energy pulses racing along the red string polygon connecting the pushpins!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))
    t1_pil, t1_cx, t1_cy, bg1 = extract_feathered_patch(base_np, (0.455, 0.305, 0.838, 0.505), feather=15)
    t2_pil, t2_cx, t2_cy, bg2 = extract_feathered_patch(bg1, (0.412, 0.530, 0.916, 0.705), feather=15)
    bg_pil = Image.fromarray(bg2).convert("RGBA")

    # Pushpin coordinates of the red string polygon in kf_4b.jpg
    pins = [
        (int(0.468 * W), int(0.382 * H)),
        (int(0.822 * W), int(0.308 * H)),
        (int(0.915 * W), int(0.592 * H)),
        (int(0.715 * W), int(0.865 * H)),
        (int(0.355 * W), int(0.818 * H)),
        (int(0.418 * W), int(0.588 * H)),
    ]

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 91)
        canvas = bg_pil.copy()

        # 1. '$1 TRILLION+' and 'SOVEREIGN WEALTH' banners pop in
        p1 = ease_out_back(min(1.0, t / 0.42), s=1.8)
        paste_animated_cutout(canvas, t1_pil, t1_cx, t1_cy,
                              scale=1.28 - 0.28 * p1, rot_deg=rng.uniform(-0.8, 0.8))
        p2 = ease_out_back(min(1.0, max(0.0, (t - 0.18) / 0.42)), s=1.8)
        paste_animated_cutout(canvas, t2_pil, t2_cx, t2_cy,
                              scale=1.28 - 0.28 * p2, rot_deg=rng.uniform(-0.8, 0.8))

        # 2. Animated golden sparkles on bullion + glowing trace along the red pushpin string
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(fx)
        for i in range(len(pins)):
            p0 = pins[i]
            p1_pt = pins[(i + 1) % len(pins)]
            prog = (t * 1.1 + i * 0.17) % 1.0
            px = p0[0] + (p1_pt[0] - p0[0]) * prog
            py = p0[1] + (p1_pt[1] - p0[1]) * prog
            draw.ellipse([px - 7, py - 7, px + 7, py + 7],
                         fill=(255, 235, 110, 245), outline=(220, 35, 25, 255), width=2)

        # Gold bullion sparkles
        for gx_n, gy_n in [(0.43, 0.42), (0.48, 0.72), (0.58, 0.78), (0.64, 0.74)]:
            if rng.random() < 0.7:
                gx, gy = int(gx_n * W + rng.uniform(-8, 8)), int(gy_n * H + rng.uniform(-8, 8))
                r = rng.randint(10, 20)
                draw.line([(gx - r, gy), (gx + r, gy)], fill=(255, 248, 175, 245), width=4)
                draw.line([(gx, gy - r), (gx, gy + r)], fill=(255, 248, 175, 245), width=4)

        canvas.alpha_composite(fx)

        if mode == "4b_vault_wheel":
            zoom = 1.28 + 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.36, 0.52)
        else:
            zoom = 1.22 - 0.14 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.58, 0.52)

        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


def anim_5a(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_5a.jpg ('THE PARADOX' Split-Screen):
    - Extracts 'THE PARADOX' banner and the golden brain cutout on the top-right.
    - Left side (Underground): animates stop-motion rotation ticks on the buried gears
      and wobbling oil barrels.
    - Right side (Above ground): animates bright golden/blue electricity pulses shooting
      along the circuit board traces into Marina Bay Sands and the golden brain!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))
    hdr_pil, hdr_cx, hdr_cy, bg1 = extract_feathered_patch(base_np, (0.245, 0.115, 0.755, 0.385), feather=15)
    brn_pil, brn_cx, brn_cy, bg2 = extract_feathered_patch(bg1, (0.782, 0.158, 0.972, 0.435), feather=15)
    bg_pil = Image.fromarray(bg2).convert("RGBA")

    # Circuit trace paths on the right half of kf_5a.jpg
    circuits = [
        [(0.525, 0.475), (0.558, 0.475), (0.610, 0.535), (0.660, 0.535)],
        [(0.520, 0.695), (0.562, 0.640), (0.645, 0.640)],
        [(0.660, 0.925), (0.660, 0.765)],
        [(0.735, 0.955), (0.735, 0.765)],
        [(0.805, 0.895), (0.768, 0.835), (0.768, 0.765)],
        [(0.782, 0.325), (0.782, 0.465)],
        [(0.838, 0.395), (0.812, 0.435), (0.812, 0.475)],
        [(0.865, 0.555), (0.915, 0.555), (0.955, 0.510)],
    ]

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 101)
        canvas = bg_pil.copy()

        # 1. 'THE PARADOX' banner pops in
        p_h = ease_out_back(min(1.0, t / 0.45), s=1.75)
        paste_animated_cutout(canvas, hdr_pil, hdr_cx, hdr_cy,
                              scale=1.22 - 0.22 * p_h, rot_deg=rng.uniform(-0.6, 0.6))

        # 2. Golden brain breathes & hovers
        brn_sc = 1.0 + 0.04 * math.sin(t * 4.5)
        brn_rot = math.sin(t * 3.0) * 2.2
        paste_animated_cutout(canvas, brn_pil, brn_cx, brn_cy, scale=brn_sc, rot_deg=brn_rot)

        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(fx)

        # 3. Left underground gears ticking in stop-motion
        step_idx = int(st * 6)
        for gx_n, gy_n, gr in [(0.312, 0.785, 58), (0.395, 0.742, 76)]:
            gx, gy = int(gx_n * W), int(gy_n * H)
            for k in range(6):
                ang = math.radians(step_idx * 15 + k * 60)
                x0, y0 = gx + math.cos(ang) * (gr - 8), gy + math.sin(ang) * (gr - 8)
                x1, y1 = gx + math.cos(ang) * (gr + 12), gy + math.sin(ang) * (gr + 12)
                draw.line([(x0, y0), (x1, y1)], fill=(235, 95, 45, 220), width=5)

        # 4. Right circuit board data pulses
        for c_idx, pts in enumerate(circuits):
            prog = (t * 1.15 + c_idx * 0.21) % 1.0
            seg_cnt = len(pts) - 1
            seg_f = prog * seg_cnt
            s_i = min(seg_cnt - 1, int(seg_f))
            local_p = seg_f - s_i
            px = (pts[s_i][0] + (pts[s_i + 1][0] - pts[s_i][0]) * local_p) * W
            py = (pts[s_i][1] + (pts[s_i + 1][1] - pts[s_i][1]) * local_p) * H
            draw.ellipse([px - 8, py - 8, px + 8, py + 8],
                         fill=(255, 230, 85, 250), outline=(25, 95, 235, 240), width=3)

        canvas.alpha_composite(fx)

        if mode == "5a_wide_split":
            zoom = 1.03 + 0.09 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.50, 0.50)
        elif mode == "5a_underground_gears":
            zoom = 1.38 + 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.28, 0.65)
        else:  # 5a_skyline_circuits
            zoom = 1.34 + 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.72, 0.56)

        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


def anim_5b(img_path: str, out_path: str, dur: float, mode: str, W=1920, H=1080):
    """
    kf_5b.jpg ('HUMAN CAPITAL' — Golden Brain, Classical Columns, Microchip & Skyscrapers):
    - Extracts the 'HUMAN CAPITAL' stamp and the central golden brain cutout.
    - Animates golden neural synapses firing across the brain and glowing circuit pulses
      travelling between the microchip and the modern skyscrapers!
    """
    base_np = np.array(Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS))
    st_pil, st_cx, st_cy, bg1 = extract_feathered_patch(base_np, (0.595, 0.082, 0.758, 0.295), feather=13)
    brn_pil, brn_cx, brn_cy, bg2 = extract_feathered_patch(bg1, (0.305, 0.230, 0.692, 0.795), feather=19)
    bg_pil = Image.fromarray(bg2).convert("RGBA")

    # Neural synapse nodes across the golden brain
    synapses = [
        (0.385, 0.425), (0.445, 0.335), (0.525, 0.345), (0.595, 0.415),
        (0.425, 0.515), (0.510, 0.485), (0.585, 0.535), (0.485, 0.610),
    ]
    syn_edges = [(0, 1), (1, 2), (2, 3), (0, 4), (1, 5), (2, 5), (3, 6), (4, 5), (5, 6), (4, 7), (5, 7)]

    frames = int(round(dur * FPS))
    proc = _open_ffmpeg_pipe(out_path, W, H, FPS)

    for f in range(frames):
        t = f / FPS
        st = stop_t(t, STOP_FPS)
        rng = random.Random(int(st * 100) + 113)
        canvas = bg_pil.copy()

        # 1. Golden brain gently pulses
        brn_sc = 1.0 + 0.028 * math.sin(t * 4.2)
        paste_animated_cutout(canvas, brn_pil, brn_cx, brn_cy, scale=brn_sc,
                              rot_deg=math.sin(t * 2.5) * 1.0, shadow_offset=0)

        # 2. 'HUMAN CAPITAL' stamp pops in
        p_s = ease_out_back(min(1.0, t / 0.45), s=1.8)
        paste_animated_cutout(canvas, st_pil, st_cx, st_cy,
                              scale=1.30 - 0.30 * p_s, rot_deg=rng.uniform(-1.0, 1.0))

        # 3. Firing golden neural pulses & microchip signals
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(fx)
        for e_i, (u, v) in enumerate(syn_edges):
            p0 = (synapses[u][0] * W, synapses[u][1] * H)
            p1 = (synapses[v][0] * W, synapses[v][1] * H)
            prog = (t * 1.45 + e_i * 0.19) % 1.0
            px = p0[0] + (p1[0] - p0[0]) * prog
            py = p0[1] + (p1[1] - p0[1]) * prog
            draw.ellipse([px - 7, py - 7, px + 7, py + 7],
                         fill=(255, 245, 155, 235), outline=(235, 165, 20, 220), width=2)

        canvas.alpha_composite(fx)

        if mode == "5b_brain_synapses":
            zoom = 1.28 + 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.52, 0.48)
        else:  # 5b_institutions_wide
            zoom = 1.14 - 0.10 * (t / dur)
            out_rgb = apply_camera(np.array(canvas.convert("RGB")), zoom, 0.50, 0.50)

        proc.stdin.write(out_rgb.tobytes())

    proc.stdin.close()
    proc.wait()


# =====================================================================
# DISPATCHER
# =====================================================================

MODE_DISPATCH = {
    "1a_wide": anim_1a,
    "1a_close_strait": anim_1a,
    "1b_pipeline": anim_1b,
    "1b_skyline_dollars": anim_1b,
    "1c_gauge_barrels": anim_1c,
    "1c_crack_wide": anim_1c,
    "2a_wide": anim_2a,
    "2a_resources_close": anim_2a,
    "2a_magnifier_close": anim_2a,
    "2b_harbor_wide": anim_2b,
    "2b_waves_close": anim_2b,
    "3a_wide": anim_3a,
    "3a_english_typewriter": anim_3a,
    "3a_gavel_strike": anim_3a,
    "3a_world_routes": anim_3a,
    "3b_wafer_containers": anim_3b,
    "4a_chart_grow": anim_4a,
    "4a_peak_close": anim_4a,
    "4b_vault_wheel": anim_4b,
    "4b_trillion_strings": anim_4b,
    "5a_wide_split": anim_5a,
    "5a_underground_gears": anim_5a,
    "5a_skyline_circuits": anim_5a,
    "5b_brain_synapses": anim_5b,
    "5b_institutions_wide": anim_5b,
}


def run(project_dir: str):
    bpath = os.path.join(project_dir, "beats.json")
    with open(bpath, encoding="utf-8") as f:
        doc = json.load(f)
    clip_dir = os.path.join(project_dir, "clips")
    os.makedirs(clip_dir, exist_ok=True)

    for beat in doc["beats"]:
        for shot in beat.get("shots", []):
            key = f"{beat['id']}{shot.get('id', '')}"
            img = shot.get("keyframe_path")
            dur = float(shot.get("dur", 4.5))
            mode = shot.get("anim_mode", "")
            out = os.path.join(clip_dir, f"clip_{key}.mp4")
            fn = MODE_DISPATCH.get(mode)
            if fn and img and os.path.exists(img):
                print(f"[{key}] Animating collage objects ({mode}, {dur}s) -> {out} ...")
                fn(img, out, dur, mode)
                shot["clip_path"] = out
            else:
                print(f"[{key}] Missing renderer for mode={mode} or img={img}")

    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print("updated", bpath)


if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "out", "singapore-vs-malaysia")
    run(os.path.abspath(proj))
