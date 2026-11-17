# Vox Collage (Dark Society Edition) — Google Antigravity Agent Guide

This repository is built **specifically for Google Antigravity**, using Antigravity's built-in **Nano Banana (`image-generator` subagent)** to generate Vox-style paper-collage posters and `scripts/vox_animator.py` (OpenCV + Pillow + FFmpeg) to animate the objects inside those posters.

## Mandatory Agent Rules (Read Before Running Anything)

1. **Two Audio / Script Modes (Ask the User First):**
   - **Mode A — Generate Voice via API (DarkPlanner TTS or Google Gemini TTS):**
     - Requires either `DARKPLANNER_API_KEY` or `GEMINI_API_KEY` in `.env`.
     - **MANDATORY QUESTION:** Whenever the user asks to create a script or video without providing a pre-recorded audio file, **you MUST ask the user which TTS provider (`DarkPlanner` or `Google TTS`) and which VOICE (`voice_id` / voice name) will be used** before running `scripts/audio.py`!
   - **Mode B — User Provides Ready Script + Ready Audio (`--from-audio`):**
     - The user can send a ready script along with a pre-recorded `.mp3`/`.wav` file (or place `master.mp3` / `narr_<id>.mp3` in `out/<project>/audio/`).
     - Run `python scripts/audio.py out/<project> --from-audio <path_to_audio.mp3>` — this slices the user's audio per beat, applies broadcast leveling, generates word-level `_palavra.srt`, and computes exact shot durations **without needing any TTS API key**.

2. **Built-in Antigravity Nano Banana for Keyframes:**
   - Run `python scripts/keyframes.py out/<project>` to compose the 5-layer Vox collage prompts into `beats.json`.
   - Then invoke Antigravity's built-in `image-generator` subagent to generate each `kf_<shot>.jpg` and save it to `out/<project>/keyframes/`.

3. **Fast Shot Cadence (3.5s–5s per take) & Real Object Animation:**
   - Never leave a single static shot on screen for 10–20 seconds. Split every beat into multiple fast shots (`3.5s–5.0s` each) alternating wide establishing shots (`"title": true`) with tight detail cut-ins (`"title": false`).
   - Animate the **actual objects inside the collage images** using `scripts/vox_animator.py` (OpenCV `cv2.inpaint` + cutout layer physics + 10fps stop-motion + procedural 2D VFX), and assemble with `scripts/assemble.py`.
