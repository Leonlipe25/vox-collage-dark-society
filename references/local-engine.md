# Local Object-Level Motion Collage Engine (`vox_animator.py` & `motion.py`)

Instead of relying on external video APIs or slow static Ken Burns zooms, this repository animates the **actual objects inside each generated collage poster** 100% locally using **OpenCV (`cv2.inpaint`) + NumPy + Pillow + FFmpeg**.

## How `scripts/vox_animator.py` Works

1. **Object Extraction & Background Reconstruction (`extract_feathered_patch` / `cv2.inpaint`):**
   - Extracts specific collage cutouts from the poster (stamps, headline banners, gauge needles, typewriter blocks, gavel, oil barrels, magnifying glass, dollar stacks, skylines, brain cutouts).
   - Reconstructs the paper or grid background behind the extracted object using OpenCV Telea Inpainting (`cv2.inpaint`), grid-line synthesis, or feathered placeholder blur so moving elements never leave a duplicate "ghost" on the backdrop.

2. **Tactile Paper Physics & 10fps Stop-Motion (`STOP_FPS = 10`):**
   - Extracted cutouts animate with `ease_out_back` (overshoot snap), `ease_out_cubic`, and quantized 10fps stop-motion jitter while the camera moves smoothly at 25fps.
   - Mechanical objects inside the collage move physically: gauge needles drop and rattle at `0%`, typewriter blocks pop in letter by letter, gavels swing down with camera impact shake, and ascending chart ribbons (`SINGAPORE $88,000`) grow progressively across the graph paper.

3. **Procedural 2D Paper VFX:**
   - Draws tactile 2D effects directly on the poster's geometry: jagged paper-cutout lightning bolts (`draw_paper_bolt`), water pulses flowing through pipelines, glowing trade packets shooting along map routes, silicon wafer holographic shimmers, and neural/circuit board pulses.

4. **Multi-Shot Fast Cadence (3.5s–5.0s per cut):**
   - From a single high-detail keyframe poster, `vox_animator.py` can render both a **wide establishing shot** (`1a_wide`) and **tight animated detail cut-ins** (`1a_close_strait`, `3a_english_typewriter`, `3a_gavel_strike`), keeping cuts every **3.5–5 seconds**.
