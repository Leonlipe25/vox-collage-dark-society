# Technical Notes & FFmpeg / OpenCV Gotchas

Everything here was learned while building and refining the local Google Antigravity + OpenCV + FFmpeg pipeline.

## Stack Overview (100% Local Visuals + Dual TTS)

| Stage | Tool / Engine | Notes |
|---|---|---|
| **Keyframe Collage Posters** | Antigravity Built-in Nano Banana (`image-generator`) | 5-layer prompt composed by `scripts/keyframes.py` + `scripts/styles.py` |
| **Object-Level Animation** | `scripts/vox_animator.py` (OpenCV + NumPy + Pillow + FFmpeg) | Cuts out objects from the poster, reconstructs background via `cv2.inpaint` / feathered blur, animates in 10fps stop-motion |
| **Narration (Option 1)** | DarkPlanner TTS API (`DARKPLANNER_API_KEY`) | Downloads MP3 + native word-level `_palavra.srt` |
| **Narration (Option 2)** | Google Gemini TTS (`GEMINI_API_KEY`) | `gemini-2.5-flash-preview-tts` (`Charon`, `Orus`, `Fenrir`, `Puck`, `Kore`, `Aoede`) |
| **Narration (Option 3)** | Pre-recorded Audio (`--from-audio`) | Slices user-supplied `.mp3`/`.wav` per beat and builds word-level `_palavra.srt` |
| **Assembly & Captions** | `scripts/assemble.py` + `scripts/text_overlay.py` | SRT-synced paper-cutout captions + Broadcast EQ audio mix |

## OpenCV & Object Decomposition Gotchas (`vox_animator.py`)

- **Preventing Duplicate "Ghosts" Behind Moving Cutouts:**
  When extracting a cutout (a stamp, a needle, a headline banner, or a chart arrow) from a generated collage poster to animate it, the original pixels on the background must be cleaned:
  - For thin/high-contrast elements over textured paper (gauge needles, typewriter blocks, stamps), dilate the mask by 9–13px and run `cv2.inpaint(..., cv2.INPAINT_TELEA)`.
  - For elements over regular geometric grids (`kf_4a.jpg`), reconstruct the vertical and horizontal grid lines from unmasked rows/columns so the grid remains crisp behind progressive reveals.
  - For pop-settle elements that rest at their original home coordinates, a soft Gaussian placeholder blur (`45x45`) preserves local paper luminance and disappears once the sharp cutout settles into place.
- **Stop-Motion Cadence (`STOP_FPS = 10`):**
  Quantize cutout jitter/rotation time via `math.floor(t * 10) / 10` so paper elements move in authentic 10fps stop-motion while the camera zoom/pan runs smoothly at 24–25fps.

## FFmpeg & Pillow Assembly Gotchas (`assemble.py` / `text_overlay.py`)

- **Captions via Pillow PNG Overlays:**
  Standard `ffmpeg` builds often lack `libass`/`drawtext` or consistent cross-platform font configs. `text_overlay.py` renders transparent RGBA PNGs for each SRT phrase in the `"paper"` style (cream cutout letters with an accent-colored keyline sampled from each beat's keyframe) and composites them with `overlay=0:0:enable='between(t,s,e)'`.
- **Slow, Don't Freeze:**
  If a rendered shot clip is slightly shorter than its target narration duration, `assemble.py` stretches it smoothly with `setpts` rather than freezing early.
- **Sidechain Ducking Length:**
  When optional `audio/bgm.mp3` is present, `apad` the narration mix to the full video duration before `sidechaincompress`, otherwise `-shortest` will truncate the ending.
- **Frame Verification:**
  When extracting verification frames to `.jpg` with `ffmpeg`, always include `-vf "scale=960:-1,format=yuvj420p"` so `mjpeg` does not fail on full-range YUV pixel formats.
