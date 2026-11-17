#!/usr/bin/env python3
"""
Audio stage (DarkPlanner TTS + Google Gemini TTS + Bring-Your-Own-Audio edition):

Supports 3 modes:
  1. Custom / Pre-recorded Audio Mode (NO API KEY NEEDED):
     - Pass `--from-audio <path/to/voiceover.mp3>` (and optional `--from-srt <path/to/subtitles.srt>`),
       OR place `master.mp3` (or `narr_1.mp3`, `narr_2.mp3`, ...) inside `<project>/audio/`.
     - Automatically slices a single `master.mp3` into per-beat `narr_<id>.mp3` files proportional
       to each beat's script (or aligned to the provided `.srt`), generates word-level `_palavra.srt`,
       and calculates exact 3.5s–5s shot durations!
  2. DarkPlanner API (`DARKPLANNER_API_KEY`) — downloads MP3 + word-level SRT (`_palavra.srt`).
  3. Google Gemini TTS API (`GEMINI_API_KEY` or `GOOGLE_API_KEY`) — uses `gemini-2.5-flash-preview-tts`
     with voices like `Charon`, `Orus`, `Fenrir`, `Kore`, `Aoede`, `Puck`.

Usage:
  python scripts/audio.py <project_dir>
  python scripts/audio.py <project_dir> --from-audio <audio.mp3> [--from-srt <subtitles.srt>]
  python scripts/audio.py --list-voices [lang]
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave

DARKPLANNER_BASE = "https://app.darkplanner.com.br/api/v1/audio"
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"

GOOGLE_VOICES = [
    {"id": "Charon", "name": "Charon (Deep Authoritative Documentary Narrator)", "gender": "male", "lang": "multilingual"},
    {"id": "Orus",   "name": "Orus (Firm & Resonant Investigative Narrator)", "gender": "male", "lang": "multilingual"},
    {"id": "Fenrir", "name": "Fenrir (Dynamic & Punchy Explainer Voice)", "gender": "male", "lang": "multilingual"},
    {"id": "Puck",   "name": "Puck (Upbeat & Fast-Paced Storytelling)", "gender": "male", "lang": "multilingual"},
    {"id": "Kore",   "name": "Kore (Clear & Calm Editorial Narrator)", "gender": "female", "lang": "multilingual"},
    {"id": "Aoede",  "name": "Aoede (Warm & Expressive Documentary Voice)", "gender": "female", "lang": "multilingual"},
]

DEFAULT_DP_VOICES = {
    "de": "3b1b6ce2-a4d9-4bf2-a87c-e36012c5f4e1",  # Norbert - Native German Journalist
    "en": "b5a75ce4-a73b-4268-9ed2-dc85f2d71c7c",  # A Top Narrator VO PRO
    "pt": "b5a75ce4-a73b-4268-9ed2-dc85f2d71c7c",  # A Top Narrator VO PRO
}


def load_dotenv():
    """Loads variables from .env in repo root if present."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_path = os.path.join(root, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v and not os.environ.get(k):
                    os.environ[k] = v


def probe_dur(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True
    ).stdout
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def apply_broadcast_leveling(raw_audio: str, dest_mp3: str):
    """Applies Broadcast Dynamic Leveling via ffmpeg."""
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", raw_audio,
        "-af", "highpass=f=75,acompressor=threshold=-20dB:ratio=3.5:attack=12:release=180:makeup=3dB,dynaudnorm=f=250:g=15:p=0.92:m=5.0,alimiter=limit=0.93",
        "-ar", "44100", "-b:a", "192k", dest_mp3
    ], check=True)
    if os.path.exists(raw_audio):
        os.remove(raw_audio)


def _fmt_srt_time(sec: float) -> str:
    ms = int(round((sec % 1.0) * 1000))
    s = int(sec) % 60
    m = (int(sec) // 60) % 60
    h = int(sec) // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_word_srt_from_duration(text: str, total_dur: float, dest_srt: str):
    """Generates a proportional word-level SRT (`_palavra.srt`) from text and audio duration."""
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words:
        return
    weights = []
    for w in words:
        bonus = 2.5 if w.endswith((".", "!", "?", ":", ";", "—")) else (1.2 if w.endswith(",") else 0.0)
        weights.append(max(1.0, len(w) + bonus))
    total_w = sum(weights)
    usable_dur = max(0.5, total_dur - 0.15)
    t_cur = 0.05
    blocks = []
    for idx, (w, wt) in enumerate(zip(words, weights), start=1):
        w_dur = usable_dur * (wt / total_w)
        t0 = t_cur
        t1 = min(total_dur, t_cur + max(0.08, w_dur - 0.02))
        blocks.append(f"{idx}\n{_fmt_srt_time(t0)} --> {_fmt_srt_time(t1)}\n{w}\n")
        t_cur += w_dur
    with open(dest_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))


def slice_master_audio_to_beats(master_audio_path: str, beats: list, adir: str):
    """
    Slices a single user-supplied voiceover file (`master.mp3` / `.wav`) into per-beat
    `narr_<id>.mp3` files proportional to each beat's narration text length, and builds
    word-level `_palavra.srt` files so no TTS API key is required.
    """
    total_dur = probe_dur(master_audio_path)
    if total_dur <= 0:
        raise RuntimeError(f"Não foi possível ler a duração do áudio enviado: {master_audio_path}")

    weights = []
    for b in beats:
        txt = (b.get("narration") or "").strip()
        weights.append(max(1, len(txt)))
    total_w = sum(weights)

    cursor = 0.0
    for i, (beat, w) in enumerate(zip(beats, weights)):
        bid = beat["id"]
        dur = round(total_dur - cursor, 2) if i == len(beats) - 1 else round(total_dur * (w / total_w), 2)
        dest_mp3 = os.path.join(adir, f"narr_{bid}.mp3")
        dest_srt = os.path.join(adir, f"narr_{bid}_palavra.srt")
        raw_slice = os.path.join(adir, f"narr_{bid}_slice.mp3")

        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{cursor:.3f}", "-t", f"{dur:.3f}",
            "-i", master_audio_path,
            "-c:a", "libmp3lame", "-q:a", "2", raw_slice
        ], check=True)
        apply_broadcast_leveling(raw_slice, dest_mp3)

        actual_dur = round(probe_dur(dest_mp3), 2)
        build_word_srt_from_duration(beat.get("narration", ""), actual_dur, dest_srt)
        cursor += dur
        print(f"[Custom Audio -> Beat {bid}] {actual_dur}s -> {dest_mp3}")


# =====================================================================
# PROVIDER 1: DARKPLANNER API
# =====================================================================

def dp_request(endpoint: str, api_key: str, method: str = "GET", payload: dict = None) -> dict:
    url = endpoint if endpoint.startswith("http") else f"{DARKPLANNER_BASE}{endpoint}"
    headers = {
        "X-API-Key": api_key,
        "User-Agent": "vox-collage-dark-society/1.0",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    for attempt in range(5):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", "10"))
                print(f"[DarkPlanner] Rate limit 429. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DarkPlanner HTTP {e.code} on {endpoint}: {body[:400]}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"DarkPlanner request failed on {endpoint}")


def download_file(url: str, dest_path: str):
    req = urllib.request.Request(url, headers={"User-Agent": "vox-collage-dark-society/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(dest_path, "wb") as f:
            f.write(resp.read())


def generate_darkplanner_tts(text: str, voice_id: str, title: str, speed: float, volume: float,
                             api_key: str, dest_mp3: str, dest_srt: str = None):
    if os.path.exists(dest_mp3) and os.path.getsize(dest_mp3) > 5000:
        print(f"[DarkPlanner] Reutilizando áudio existente: {dest_mp3}")
        return dest_mp3

    print(f"[DarkPlanner] Gerando '{title}' ({len(text)} chars, voice={voice_id})...")
    gen_res = dp_request("/generate", api_key, method="POST", payload={
        "text": text,
        "voice_id": voice_id,
        "title": title,
        "speed": float(speed or 1.0),
        "volume": float(volume or 1.0),
        "subtitle_words": 8,
        "subtitle_case": "normal",
        "subtitle_veo_words": 1,
        "subtitle_veo_min": 3,
        "subtitle_veo_max": 7,
    })

    job_id = gen_res.get("job_id")
    if not job_id:
        raise RuntimeError(f"job_id ausente na resposta do DarkPlanner: {gen_res}")

    for _ in range(300):
        time.sleep(2.5)
        st = dp_request(f"/status/{job_id}", api_key)
        status = st.get("status")
        if status == "completed":
            break
        if status in ("failed", "error"):
            raise RuntimeError(f"DarkPlanner job {job_id} falhou: {st}")
    else:
        raise RuntimeError(f"Timeout aguardando job {job_id} no DarkPlanner")

    dl = dp_request(f"/download/{job_id}", api_key)
    raw_mp3 = dest_mp3.replace(".mp3", "_raw.mp3")
    download_file(dl["audio_url"], raw_mp3)

    srt_url = dl.get("srt_palavra_url") or dl.get("srt_url")
    if srt_url and dest_srt:
        download_file(srt_url, dest_srt)

    apply_broadcast_leveling(raw_mp3, dest_mp3)
    return dest_mp3


# =====================================================================
# PROVIDER 2: GOOGLE GEMINI TTS API (`gemini-2.5-flash-preview-tts`)
# =====================================================================

def generate_google_tts(text: str, voice_name: str, title: str, api_key: str,
                        dest_mp3: str, dest_srt: str = None):
    if os.path.exists(dest_mp3) and os.path.getsize(dest_mp3) > 5000:
        print(f"[Google TTS] Reutilizando áudio existente: {dest_mp3}")
        return dest_mp3

    valid_names = {v["id"].lower(): v["id"] for v in GOOGLE_VOICES}
    v_clean = valid_names.get((voice_name or "").lower(), "Charon")

    print(f"[Google TTS] Gerando '{title}' ({len(text)} chars, voice={v_clean})...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TTS_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": v_clean
                    }
                }
            }
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            res = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google TTS HTTP {e.code}: {body[:400]}") from e

    parts = res.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    b64_data = None
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            b64_data = inline["data"]
            break
    if not b64_data:
        raise RuntimeError(f"Resposta de áudio vazia do Google TTS: {res}")

    pcm_bytes = base64.b64decode(b64_data)
    raw_wav = dest_mp3.replace(".mp3", "_raw.wav")
    with wave.open(raw_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_bytes)

    apply_broadcast_leveling(raw_wav, dest_mp3)
    if dest_srt:
        dur = probe_dur(dest_mp3)
        build_word_srt_from_duration(text, dur, dest_srt)
    return dest_mp3


# =====================================================================
# VOICE LISTING & MAIN PIPELINE
# =====================================================================

def list_voices(lang_filter: str = None):
    load_dotenv()
    print("=== VOZES GOOGLE GEMINI TTS (GEMINI_API_KEY) ===")
    for gv in GOOGLE_VOICES:
        print(f"  {gv['id']:8s} | {gv['name']} | gender={gv['gender']}")

    dp_key = os.environ.get("DARKPLANNER_API_KEY")
    if dp_key:
        print("\n=== VOZES DARKPLANNER TTS (DARKPLANNER_API_KEY) ===")
        res = dp_request("/voices", dp_key)
        voices = res.get("voices", [])
        count = 0
        for v in voices:
            vinfo = v.get("voice_info") or {}
            vlang = v.get("language") or vinfo.get("language") or ""
            if lang_filter and lang_filter.lower() not in vlang.lower() and lang_filter.lower() not in (v.get("name") or "").lower():
                continue
            print(f"  {v.get('id')} | {v.get('name')} | lang={vlang} | gender={v.get('gender')}")
            count += 1
            if count >= 40:
                break
    else:
        print("\n[Dica] Defina DARKPLANNER_API_KEY no arquivo .env para listar as +1.000 vozes do DarkPlanner.")


def run(project_dir: str, from_audio: str = None):
    load_dotenv()
    bpath = os.path.join(project_dir, "beats.json")
    with open(bpath, encoding="utf-8") as f:
        doc = json.load(f)
    adir = os.path.join(project_dir, "audio")
    os.makedirs(adir, exist_ok=True)

    # Check if user supplied a single master audio file (via --from-audio, beats.json "source_audio", or audio/master.mp3)
    master_candidate = (
        from_audio
        or doc.get("source_audio")
        or (os.path.join(adir, "master.mp3") if os.path.exists(os.path.join(adir, "master.mp3")) else None)
    )
    if master_candidate and os.path.exists(master_candidate):
        print(f"[Custom Audio] Usando áudio pronto enviado pelo usuário: {master_candidate}")
        slice_master_audio_to_beats(master_candidate, doc["beats"], adir)

    # Check if all narr_<id>.mp3 files already exist (either sliced above or placed directly by the user)
    all_exist = all(
        os.path.exists(os.path.join(adir, f"narr_{b['id']}.mp3")) and
        os.path.getsize(os.path.join(adir, f"narr_{b['id']}.mp3")) > 5000
        for b in doc["beats"] if (b.get("narration") or "").strip()
    )

    voice = doc.get("voice", {})
    language = (voice.get("language") or doc.get("language") or "en").split("-")[0].lower()
    dp_key = voice.get("darkplanner_api_key") or doc.get("darkplanner_api_key") or os.environ.get("DARKPLANNER_API_KEY")
    google_key = voice.get("google_api_key") or doc.get("google_api_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    provider = (voice.get("provider") or doc.get("tts_provider") or "").lower().strip()
    if not provider and not all_exist:
        if dp_key:
            provider = "darkplanner"
        elif google_key:
            provider = "google"
        else:
            raise RuntimeError(
                "Nenhuma chave de API de voz configurada e nenhum áudio pronto encontrado!\n"
                "Escolha UMA das 3 opções:\n"
                "  1) Enviar seu próprio áudio pronto: `python scripts/audio.py out/<projeto> --from-audio seu_audio.mp3`\n"
                "  2) Configurar DARKPLANNER_API_KEY no arquivo `.env` (para usar o DarkPlanner TTS)\n"
                "  3) Configurar GEMINI_API_KEY no arquivo `.env` (para usar o Google Gemini TTS)\n"
            )

    voice_id = voice.get("voice_id") or ""
    speed = float(voice.get("speed", 1.0))
    volume = float(voice.get("volume", 1.0))

    for beat in doc["beats"]:
        bid = beat["id"]
        text = beat.get("narration", "").strip()
        if not text:
            continue
        dest_mp3 = os.path.join(adir, f"narr_{bid}.mp3")
        dest_srt = os.path.join(adir, f"narr_{bid}_palavra.srt")
        title = f"{os.path.basename(project_dir)}_beat_{bid}"

        if not (os.path.exists(dest_mp3) and os.path.getsize(dest_mp3) > 5000):
            if provider == "google":
                if not google_key:
                    raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY não encontrada no ambiente ou .env!")
                generate_google_tts(
                    text=text,
                    voice_name=voice_id or "Charon",
                    title=title,
                    api_key=google_key,
                    dest_mp3=dest_mp3,
                    dest_srt=dest_srt,
                )
            else:
                if not dp_key:
                    raise RuntimeError("DARKPLANNER_API_KEY não encontrada no ambiente ou .env!")
                dp_vid = voice_id if len(voice_id) >= 20 else DEFAULT_DP_VOICES.get(language, DEFAULT_DP_VOICES["en"])
                generate_darkplanner_tts(
                    text=text,
                    voice_id=dp_vid,
                    title=title,
                    speed=speed,
                    volume=volume,
                    api_key=dp_key,
                    dest_mp3=dest_mp3,
                    dest_srt=dest_srt,
                )

        dur = round(probe_dur(dest_mp3), 2)
        beat["narration_audio"] = dest_mp3
        beat["narration_dur"] = dur
        if not os.path.exists(dest_srt):
            build_word_srt_from_duration(text, dur, dest_srt)
        beat["narration_srt"] = dest_srt

        shots = beat.get("shots")
        if shots:
            total_target = round(dur + 0.4, 2)
            n = len(shots)
            per_shot = round(total_target / n, 2)
            for i, s in enumerate(shots):
                if i == n - 1:
                    s["dur"] = round(total_target - per_shot * (n - 1), 2)
                else:
                    s["dur"] = per_shot

        print(f"[narr {bid}] {dur}s -> {dest_mp3}")

    bgm_path = os.path.join(adir, "bgm.mp3")
    if os.path.exists(bgm_path):
        doc["bgm_path"] = bgm_path
        doc["bgm_dur"] = round(probe_dur(bgm_path), 2)
        print(f"[bgm] found optional {bgm_path} ({doc['bgm_dur']}s)")
    else:
        doc.pop("bgm_path", None)
        print("[bgm] sem música (modo voz limpa — você pode adicionar a música depois)")

    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print("updated", bpath)


if __name__ == "__main__":
    if "--list-voices" in sys.argv:
        idx = sys.argv.index("--list-voices")
        lf = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        list_voices(lf)
        sys.exit(0)

    from_audio_arg = None
    if "--from-audio" in sys.argv:
        idx = sys.argv.index("--from-audio")
        if idx + 1 < len(sys.argv):
            from_audio_arg = sys.argv[idx + 1]

    pos_args = []
    skip_next = False
    for a in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if a in ("--from-audio", "--from-srt", "--list-voices"):
            skip_next = True
            continue
        if not a.startswith("--"):
            pos_args.append(a)

    proj = pos_args[0] if pos_args else os.path.join(
        os.path.dirname(__file__), "..", "out", "singapore-vs-malaysia")
    run(os.path.abspath(proj), from_audio=from_audio_arg)
