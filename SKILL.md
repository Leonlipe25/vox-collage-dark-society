---
name: vox-collage-dark-society
description: >
  Turn a topic — or a ready script with pre-recorded audio — into a finished Vox-style
  paper-collage documentary / explainer video inside Google Antigravity, automated end to end
  using Antigravity's built-in Nano Banana (`image-generator`), local OpenCV + Pillow + FFmpeg
  object-level collage animation (`scripts/vox_animator.py`), and DarkPlanner TTS / Google Gemini TTS
  / custom MP3 voiceover (`scripts/audio.py`).
  Triggers: "vox video", "collage video", "motion collage", "paper collage explainer",
  "documentário estilo vox", "colagem animada".
---

# Vox Collage — Dark Society Edition (Google Antigravity)

Turn a topic — or a ready script + voiceover — into a finished **Vox-style paper-collage documentary**:
a high-retention editorial explainer where each beat is a torn-paper collage poster whose internal
objects come alive in 10fps stop-motion, synchronized with broadcast-leveled narration and paper-cutout captions.

Built specifically for **Google Antigravity**:
- **Images (Keyframes):** Generated directly via Antigravity's built-in **Nano Banana (`image-generator` subagent)** — no paid external image API required.
- **Object-Level Motion (`scripts/vox_animator.py`):** Driven 100% locally via **OpenCV (`cv2.inpaint`) + NumPy + Pillow + FFmpeg** — cuts out objects inside the collage posters, reconstructs the paper/grid background behind them, and animates the cutouts with spring/slap physics, rotating needles/gears, growing chart arrows, and 2D procedural VFX.
- **Audio (`scripts/audio.py`):** Supports **DarkPlanner TTS API** (`DARKPLANNER_API_KEY`), **Google Gemini TTS API** (`GEMINI_API_KEY`), or **Ready Script + Pre-recorded Audio** (`--from-audio`).

---

## Mandatory Prerequisites & Voice Selection Gate (Check First, Never Skip)

1. **Local Dependencies:**
   - `ffmpeg` and `ffprobe` installed in PATH.
   - Python 3.10+ with `pillow`, `numpy`, and `opencv-python-headless` (`pip install pillow numpy opencv-python-headless`).

2. **Mandatory Audio / Voice Selection Gate (ALWAYS ask when creating a script):**
   Before running `scripts/audio.py`, check whether the user is providing their own recorded audio or wants the agent to generate the narration:
   - **Mode A — User sends Ready Script + Ready Audio (No API Key needed):**
     If the user provides an `.mp3`/`.wav` file along with their script, run:
     `python scripts/audio.py out/<project> --from-audio <path/to/audio.mp3>`
   - **Mode B — Generate Narration via API (`DARKPLANNER_API_KEY` or `GEMINI_API_KEY`):**
     - Verify that `.env` (or environment) has either `DARKPLANNER_API_KEY` or `GEMINI_API_KEY`. If neither is set, instruct the user to copy `.env.example` to `.env` and add their key.
     - **MANDATORY QUESTION:** You **MUST ALWAYS ASK the user** which TTS provider (**DarkPlanner** or **Google TTS**) and **which voice (`voice_id` / voice name)** they want to use before generating the audio!
     - Available Google Gemini TTS voices: `Charon`, `Orus`, `Fenrir`, `Puck`, `Kore`, `Aoede`.
     - Available DarkPlanner voices: run `python scripts/audio.py --list-voices [lang]` (e.g., `"A Top Narrator VO PRO"` `b5a75ce4-a73b-4268-9ed2-dc85f2d71c7c`, `"Norbert"` `3b1b6ce2-a4d9-4bf2-a87c-e36012c5f4e1`).

---

## Standard 6-Stage Workflow (Topic or Script → `final.mp4`)

All stages are driven by a single `out/<project>/beats.json`:

### 1. Topic / Script → Beat Map (`beats.json`) + Voice Confirmation
- Read `references/beat-layer.md` and `references/prompt-guide.md`.
- **Ask the user which TTS provider (`DarkPlanner` or `Google TTS`) and which voice they want** (unless they provided a ready `.mp3` file).
- Draft `out/<project>/beats.json` following the **Fast Retention Cadence** rules below.

### 2. Audio & Word-Level SRT (`scripts/audio.py`)
- Run `python scripts/audio.py out/<project>` (or `python scripts/audio.py out/<project> --from-audio <audio.mp3>`).
- Generates per-beat leveled `narr_<id>.mp3` (with broadcast EQ/compression: `highpass + acompressor + dynaudnorm + alimiter`), downloads/builds word-level `narr_<id>_palavra.srt`, and automatically distributes spoken duration across each beat's shots.

### 3. Collage Keyframe Prompts & Antigravity Nano Banana (`scripts/keyframes.py`)
- Run `python scripts/keyframes.py out/<project>`.
- Composes the 5-layer Vox collage prompt (`scripts/styles.py`) for every shot into `beats.json`.
- Invoke Antigravity's built-in **`image-generator` subagent** for each keyframe poster and save to `out/<project>/keyframes/kf_<shot>.jpg`.
- Re-run `python scripts/keyframes.py out/<project>` to link all local `.jpg` files into `beats.json`.

### 4. Object-Level Collage Animation (`scripts/vox_animator.py`)
- Run `python scripts/vox_animator.py out/<project>`.
- Uses OpenCV (`cv2.inpaint`) + NumPy + Pillow + FFmpeg to extract real cutouts/elements from inside each collage poster, reconstruct the paper/grid backdrop behind them so there is no ghosting, and animate the actual objects in 10fps stop-motion + smooth camera moves (`push_in`, `pull_out`, `pan`, `static`).
- *(Fallback)* For simple camera-only moves without object decomposition, `python scripts/kenburns.py out/<project>` is also available.

### 5. Final Assembly & Paper Captions (`scripts/assemble.py`)
- Run `python scripts/assemble.py out/<project>`.
- Concatenates all animated shot clips, parses each beat's `_palavra.srt` to burn dynamic phrase-by-phrase paper-cutout captions (`scripts/text_overlay.py` with automatic keyframe accent color extraction), mixes the leveled voice-over (and optional `audio/bgm.mp3` with sidechain ducking), and outputs `out/<project>/final.mp4`.

### 6. Visual Verification
- Extract sample frames with `ffmpeg` and inspect them via `read_file` to verify clean inpainting, object motion, and caption legibility:
  `ffmpeg -y -loglevel error -ss <t> -i out/<project>/final.mp4 -vf "scale=960:-1,format=yuvj420p" -frames:v 1 check.jpg`

---

## Cadence — How Long Shots Should Be (Critical Rule)

Never leave a single static shot on screen for 10–20 seconds:
- **Target 3.5–5.0 seconds per shot; never let a single shot exceed ~6s.**
- Split each beat into multiple fast shots alternating a **wide establishing shot** (`"title": true`, showing the torn-paper headline banner once) with **tight detail cut-ins** (`"title": false`, focusing on specific animated objects inside the collage as the narrator speaks).

---

## `beats.json` Schema

```json
{
  "title": "Why Did Singapore Get So Much Richer Than Malaysia?",
  "aspect": "16:9",
  "style": "collage",
  "theme": "swiss-modern",
  "collage_style": "swiss-modern",
  "caption_style": "paper",
  "captions": true,
  "language": "en",
  "voice": {
    "provider": "darkplanner",
    "voice_id": "b5a75ce4-a73b-4268-9ed2-dc85f2d71c7c",
    "language": "en",
    "speed": 1.0,
    "volume": 1.0
  },
  "beats": [
    {
      "id": 1,
      "chapter": "01. HOOK — The 1965 Paradox",
      "title_cn": "",
      "title_en": "EXPELLED IN 1965",
      "narration": "In August nineteen sixty-five, Singapore became the only country in modern history forced into independence against its own will...",
      "bg": "aged cream archival map paper with Swiss editorial grid lines",
      "feel": "dramatic historical paradox",
      "shots": [
        {
          "id": "a",
          "title": true,
          "dur": 4.5,
          "camera_move": "push_in",
          "anim_mode": "1a_wide",
          "scene": "Wide editorial paper collage poster..."
        },
        {
          "id": "b",
          "title": false,
          "dur": 4.5,
          "camera_move": "pan",
          "anim_mode": "1a_close_strait",
          "scene": "Close cut-in detail..."
        }
      ]
    }
  ]
}
```
