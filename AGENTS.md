# Vox Collage (Dark Society Edition) — Agent Guide

This repository is an **agent skill**: a self-contained workflow that turns one
topic or script into a finished **Vox-style paper-collage video** (script → voice-over →
collage keyframes → object-level OpenCV animation → native paper captions → `final.mp4`).

## Mandatory Agent Rules (Read Before Running Anything)

1. **Check TTS API Key first:**
   - Narration requires **either** `DARKPLANNER_API_KEY` (DarkPlanner API) **or** `GEMINI_API_KEY` (Google Gemini TTS API) in `.env` or environment variables.
   - If neither is set, ask the user to provide their DarkPlanner API Key or Google Gemini API Key before running `scripts/audio.py`.
2. **ALWAYS Ask Which Voice to Use When Creating the Script:**
   - Whenever the user asks to create a script or video (`beats.json`), **you MUST ask the user which TTS provider (`DarkPlanner` or `Google TTS`) and which VOICE (`voice_id` / voice name) they want to use**!
   - You can list available voices at any time via `python scripts/audio.py --list-voices [lang]`.
3. **Fast Shot Cadence (3.5s–5s per take) & Real Object Animation:**
   - Never leave a single static shot on screen for 10–20 seconds. Split every beat into multiple fast shots (`3.5s–5.0s` each) alternating wide establishing shots (`"title": true`) with tight detail cut-ins (`"title": false`).
   - Animate the **actual objects inside the collage images** using `scripts/vox_animator.py` (OpenCV `cv2.inpaint` + cutout layer physics + 10fps stop-motion + procedural 2D VFX), and assemble with `scripts/assemble.py`.

## Workflow Order

1. Read **`SKILL.md`** and **`references/prompt-guide.md`**.
2. Ask the user for their **preferred voice** (DarkPlanner or Google TTS) and draft `out/<project>/beats.json`.
3. Run `python scripts/audio.py out/<project>` (generates leveled MP3 + word-level `_palavra.srt`).
4. Run `python scripts/keyframes.py out/<project>` and generate the collage posters with Antigravity's built-in Nano Banana (`image-generator`).
5. Run `python scripts/vox_animator.py out/<project>` (animates the objects inside each collage poster).
6. Run `python scripts/assemble.py out/<project>` (produces `out/<project>/final.mp4`).
