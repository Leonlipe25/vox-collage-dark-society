# Voice & Narration Guide (`scripts/audio.py`)

`scripts/audio.py` supports **3 narration modes**. Whenever the user creates a new script without providing a pre-recorded audio file, **the agent MUST ask the user which provider and which voice they want to use**.

---

## Mode 1: DarkPlanner TTS API (`DARKPLANNER_API_KEY`)

Set `DARKPLANNER_API_KEY="dpk_..."` in `.env`.
To list voices from your DarkPlanner catalog in the terminal:
```bash
python scripts/audio.py --list-voices
python scripts/audio.py --list-voices en
python scripts/audio.py --list-voices de
```

### Recommended Documentary Voices on DarkPlanner
| Voice Name | `voice_id` | Language | Best For |
|---|---|---|---|
| **A Top Narrator VO PRO** | `b5a75ce4-a73b-4268-9ed2-dc85f2d71c7c` | `en` / `pt` (Multilingual) | Economic documentaries, geopolitics, investigations |
| **Norbert - Native German Journalist** | `3b1b6ce2-a4d9-4bf2-a87c-e36012c5f4e1` | `de` | German DACH documentaries, engineering & history |

In `beats.json`:
```json
"voice": {
  "provider": "darkplanner",
  "voice_id": "b5a75ce4-a73b-4268-9ed2-dc85f2d71c7c",
  "language": "en",
  "speed": 1.0,
  "volume": 1.0
}
```

---

## Mode 2: Google Gemini TTS API (`GEMINI_API_KEY`)

Set `GEMINI_API_KEY="AIzaSy..."` in `.env` (free key from [Google AI Studio](https://aistudio.google.com/apikey)).
Uses `gemini-2.5-flash-preview-tts` and automatically generates broadcast-leveled `.mp3` + word-level `_palavra.srt`.

### Built-in Google Documentary Voices
| `voice_id` | Style & Tone | Gender | Languages |
|---|---|---|---|
| **`Charon`** | Deep, authoritative documentary narrator | Male | Multilingual (`en`, `pt`, `de`, `es`, ...) |
| **`Orus`** | Firm, resonant investigative narrator | Male | Multilingual |
| **`Fenrir`** | Dynamic, punchy explainer narrator | Male | Multilingual |
| **`Puck`** | Upbeat, fast-paced storytelling | Male | Multilingual |
| **`Kore`** | Clear, calm editorial narrator | Female | Multilingual |
| **`Aoede`** | Warm, expressive documentary narrator | Female | Multilingual |

In `beats.json`:
```json
"voice": {
  "provider": "google",
  "voice_id": "Charon",
  "language": "en",
  "speed": 1.0
}
```

---

## Mode 3: Bring Your Own Script + Pre-recorded Audio (`--from-audio`)

No API key required! If the user already has a recorded `.mp3` or `.wav` voiceover:
```bash
python scripts/audio.py out/<project> --from-audio path/to/my_voiceover.mp3
```
Or place `master.mp3` (or per-beat `narr_1.mp3`, `narr_2.mp3`, ...) directly inside `out/<project>/audio/`.
`scripts/audio.py` will automatically slice `master.mp3` across the beats, apply Broadcast Dynamic Leveling, generate word-level `_palavra.srt` files, and compute exact 3.5s–5s shot durations.
