import asyncio
import json
import os
import shutil
import sqlite3
import ssl
import subprocess
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, Tuple
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
VIDEO_DIR = STATIC_DIR / "videos"
AUDIO_DIR = STATIC_DIR / "audio"
DB_PATH = BASE_DIR / "app.db"

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from pydub import AudioSegment

try:
    import edge_tts
except ImportError:
    edge_tts = None  # type: ignore[assignment, misc]

from story_arc import TWO_MINUTE_TRIANGLE_REV

load_dotenv(BASE_DIR / ".env")

PORTRAITS_DIR = STATIC_DIR / "portraits"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")


def _looks_like_gemini_api_key(value: str) -> bool:
    v = value.strip()
    # Browser / Gemini Developer keys typically start with "AIza".
    return v.startswith("AIza") and 20 < len(v) < 256


GEMINI_API_KEY_ENV = (
    (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
)
# Legacy misconfiguration support: Gemini key pasted into GOOGLE_CLOUD_PROJECT.
_raw_project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()

GEMINI_API_KEY = GEMINI_API_KEY_ENV
VERTEX_PROJECT_ID = _raw_project
if not GEMINI_API_KEY and _looks_like_gemini_api_key(VERTEX_PROJECT_ID):
    GEMINI_API_KEY = VERTEX_PROJECT_ID
    VERTEX_PROJECT_ID = ""

GENAI_CLOUD_CONFIGURED = bool(GEMINI_API_KEY or VERTEX_PROJECT_ID)

VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.1-generate-preview")
VEO_DURATION_SECONDS = int(os.getenv("VEO_DURATION_SECONDS", "8"))
VEO_DURATION_MAX = int(os.getenv("VEO_DURATION_MAX", "60"))
# Gemini Developer API (AI Studio key) Veo previews accept durationSeconds only in [4, 8]. Vertex routes may allow longer.
_VEO_CLIP_CANDIDATE = min(max(4, VEO_DURATION_SECONDS), VEO_DURATION_MAX)
VEO_CLIP_SECONDS = (
    min(_VEO_CLIP_CANDIDATE, 8) if GEMINI_API_KEY else _VEO_CLIP_CANDIDATE
)
VEO_ASPECT_RATIO = os.getenv("VEO_ASPECT_RATIO", "16:9")
VEO_POLL_SECONDS = int(os.getenv("VEO_POLL_SECONDS", "10"))
IMAGEN_MODEL = os.getenv(
    "IMAGEN_MODEL",
    "imagen-4.0-generate-001" if GEMINI_API_KEY else "imagen-3.0-generate-002",
)
VEO_GENERATE_NATIVE_AUDIO = os.getenv("VEO_GENERATE_NATIVE_AUDIO", "false").lower() in ("1", "true", "yes")
DIALOGUE_PAUSE_MS = int(os.getenv("DIALOGUE_PAUSE_MS", "280"))
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3")
# elevenlabs | edge | auto — auto uses ElevenLabs when API key + per-speaker voice id exist.
TTS_BACKEND = os.getenv("TTS_BACKEND", "auto").strip().lower()

EDGE_VOICE_MAP = {
    "Aryan": os.getenv("EDGE_VOICE_ARYAN", "en-IN-PrabhatNeural"),
    "Sara": os.getenv("EDGE_VOICE_SARA", "en-IN-NeerjaNeural"),
    "Rohan": os.getenv("EDGE_VOICE_ROHAN", "en-US-GuyNeural"),
}
EDGE_VOICE_DEFAULT = os.getenv("EDGE_VOICE_DEFAULT", "en-US-JennyNeural")

# Dev-only slate when Vertex credentials are unavailable (local pipeline smoke test).
ALLOW_PLACEHOLDER_VIDEO = os.getenv("ALLOW_PLACEHOLDER_VIDEO", "false").lower() in ("1", "true", "yes")

VOICE_ID_MAP = {
    "Aryan": os.getenv("ELEVENLABS_VOICE_ARYAN_ID", ""),
    "Sara": os.getenv("ELEVENLABS_VOICE_SARA_ID", ""),
    "Rohan": os.getenv("ELEVENLABS_VOICE_ROHAN_ID", ""),
}

VOICE_LABELS = {
    "Aryan": "Antoni or Adam",
    "Sara": "Rachel or Bella",
    "Rohan": "Josh or Arnold",
}

SAMPLE_LINES = {
    "Aryan": "I don't hate you. I hate that I can't.",
    "Sara": "Love was never the problem. I had too much of it.",
    "Rohan": "Choose, Sara. Choose before someone gets destroyed.",
}

SEED_CHARACTERS = [
    {
        "name": "Aryan",
        "age": 27,
        "role": "The loyal lover, soft and devoted",
        "personality": "Calm, quiet, emotionally restrained",
        "appearance": "Indian male, wheatish skin, sharp jawline, soft dark eyes, short hair",
        "voice_style": "Deep & calm",
        "color_hex": "#4A90D9",
    },
    {
        "name": "Sara",
        "age": 25,
        "role": "The torn woman, loves two, chooses none",
        "personality": "Emotional, conflicted, breathless",
        "appearance": "Indian female, long dark hair, expressive eyes, natural look",
        "voice_style": "Soft & emotional",
        "color_hex": "#D4638A",
    },
    {
        "name": "Rohan",
        "age": 28,
        "role": "The new flame, sincere and dangerous in equal measure",
        "personality": "Confident, bold, quietly vulnerable",
        "appearance": "Indian male, olive-brown skin, textured dark hair, thoughtful intense gaze",
        "voice_style": "Bold & confident",
        "color_hex": "#5BA85A",
    },
]

SEED_SCENES = [
    {
        "scene_number": 1,
        "title": "A Quiet Morning",
        "location": "INT. Cafe",
        "time_of_day": "Golden hour",
        "action_text": "Aryan sits alone at a small table. Coffee untouched. He stares at his phone — Sara's unread messages. He opens the phone. A photo of Sara — laughing. With someone else.",
        "dialogue_json": [
            {
                "speaker": "Aryan",
                "line": "Three years. Three years, and I still don't know where I stand with you.",
                "note": "Quietly heartbroken, underplayed.",
            }
        ],
        "emotion_tags": ["Longing", "Doubt", "Stillness"],
        "veo3_prompt": "Photorealistic Indian man, 27, soft eyes, sitting alone in a warmly-lit cafe, golden morning sunlight, untouched coffee cup, staring at phone with quietly heartbroken expression, shallow depth of field, 85mm cinematic lens, slow push-in camera movement, no dialogue, 8 seconds.",
    },
    {
        "scene_number": 2,
        "title": "The Confrontation",
        "location": "EXT. Rooftop",
        "time_of_day": "Night",
        "action_text": "Sara stands at the edge, city lights behind her. Aryan approaches. Aryan turns away. His jaw tightens. He doesn't cry — he just breathes.",
        "dialogue_json": [
            {"speaker": "Aryan", "line": "Who is he, Sara?", "note": "Controlled pain."},
            {"speaker": "Sara", "line": "Someone I didn't plan for.", "note": "Quiet confession."},
            {"speaker": "Aryan", "line": "Do you love him?", "note": "Barely holding composure."},
            {
                "speaker": "Sara",
                "line": "I love you too, Aryan. That's what makes this so hard.",
                "note": "Breathless and ashamed.",
            },
        ],
        "emotion_tags": ["Heartbreak", "Confession", "Tension"],
        "veo3_prompt": "Photorealistic Indian man and woman, late 20s, standing on a rooftop at night, city lights softly blurred behind, both facing forward not at each other, cool blue ambient light, tears forming in woman's eyes, wind moving her hair, static wide shot, cinematic, emotional, 8 seconds.",
    },
    {
        "scene_number": 3,
        "title": "Rohan's Truth",
        "location": "INT. Rohan's apartment",
        "time_of_day": "Late night",
        "action_text": "Rohan kneels in front of Sara. She hugs her knees on the couch. He pulls her into a hug. She cries silently.",
        "dialogue_json": [
            {
                "speaker": "Rohan",
                "line": "I knew you had someone. I still fell for you. Does that make me the villain?",
                "note": "Raw but steady.",
            },
            {"speaker": "Sara", "line": "It makes you human.", "note": "Softly consoling."},
            {
                "speaker": "Rohan",
                "line": "Then choose, Sara. Choose before someone gets destroyed.",
                "note": "Direct, pained, urgent.",
            },
            {
                "speaker": "Sara",
                "line": "What if choosing means I lose a part of myself either way?",
                "note": "Cracking voice.",
            },
        ],
        "emotion_tags": ["Guilt", "Vulnerability", "Urgency"],
        "veo3_prompt": "Photorealistic Indian man kneeling in front of seated woman on couch, late night apartment, warm low lamp light, he gently holds her face, her eyes red from crying, emotional intimate close-up, slow zoom into faces, cinematic, 8 seconds.",
    },
    {
        "scene_number": 4,
        "title": "The Meeting",
        "location": "EXT. Park bench",
        "time_of_day": "Raining",
        "action_text": "Aryan and Rohan sit apart on a bench in the rain. Neither planned this. Silence. Rain falls harder.",
        "dialogue_json": [
            {"speaker": "Aryan", "line": "You know she still texts me every morning.", "note": "Dry, resigned."},
            {"speaker": "Rohan", "line": "And she falls asleep talking to me every night.", "note": "Defensive honesty."},
            {"speaker": "Aryan", "line": "I don't hate you. I hate that I can't.", "note": "Quiet truth."},
            {
                "speaker": "Rohan",
                "line": "If she chooses you... I'll let her go. No drama, no fight.",
                "note": "Respectful restraint.",
            },
            {
                "speaker": "Aryan",
                "line": "And if she chooses you... tell her I said she deserves that happiness. Even if it's not with me.",
                "note": "Pain without bitterness.",
            },
        ],
        "emotion_tags": ["Restraint", "Respect", "Sadness"],
        "veo3_prompt": "Two photorealistic Indian men, late 20s, sitting far apart on a rain-soaked park bench in silence, heavy rain, overcast grey sky, one slowly stands and walks away into the rain, slow camera push-in, quiet sadness not anger, cinematic, 8 seconds.",
    },
    {
        "scene_number": 5,
        "title": "Sara's Choice",
        "location": "INT. Sara's room",
        "time_of_day": "Sunset",
        "action_text": "Sara sits at a window. Two phones in hand — one showing Aryan, one Rohan. She sets both down. Picks up a pen and writes a letter. We never see who it's for. She walks out. Camera holds on empty room. Both phones light up — unanswered. Fade to black.",
        "dialogue_json": [
            {
                "speaker": "Sara",
                "line": "Love was never the problem. I had too much of it — and not enough courage to be honest about it. You both deserved better. And so did I.",
                "note": "Voice-over, reflective and final.",
            }
        ],
        "emotion_tags": ["Release", "Ambiguity", "Self-Truth"],
        "veo3_prompt": "Photorealistic Indian woman sitting at a window, golden sunset light on her face, writing a letter, two phones beside her lighting up with notifications she ignores, she folds letter and walks to door, camera holds on empty room, two phones glowing, fade to black, cinematic, 8 seconds.",
    },
]


class CharacterUpdate(BaseModel):
    name: str
    age: int
    role: str
    personality: str
    appearance: str
    voice_style: str
    color_hex: str


class SceneUpdate(BaseModel):
    title: str
    location: str
    time_of_day: str
    action_text: str
    dialogue_json: list[dict[str, Any]]
    emotion_tags: list[str]
    veo3_prompt: str


class VoiceGenerationRequest(BaseModel):
    text: str = Field(..., min_length=1)


class SceneAudioGenerationRequest(BaseModel):
    character_name: str | None = None
    text: str | None = None


app = FastAPI(title="Between Two Hearts API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_character(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "age": row["age"],
        "role": row["role"],
        "personality": row["personality"],
        "appearance": row["appearance"],
        "voice_style": row["voice_style"],
        "color_hex": row["color_hex"],
        "recommended_voice_label": VOICE_LABELS.get(row["name"], ""),
        "sample_line": SAMPLE_LINES.get(row["name"], ""),
        "configured_voice_id": bool(VOICE_ID_MAP.get(row["name"], "")),
        "portrait_url": row["portrait_url"] if "portrait_url" in row.keys() else None,
    }


def row_to_scene(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "scene_number": row["scene_number"],
        "title": row["title"],
        "location": row["location"],
        "time_of_day": row["time_of_day"],
        "action_text": row["action_text"],
        "dialogue_json": json.loads(row["dialogue_json"]),
        "emotion_tags": json.loads(row["emotion_tags"]),
        "veo3_prompt": row["veo3_prompt"],
        "video_url": row["video_url"],
        "audio_url": row["audio_url"],
        "final_video_url": row["final_video_url"] if "final_video_url" in row.keys() else None,
    }


def migrate_schema(conn: sqlite3.Connection) -> None:
    char_cols = {row[1] for row in conn.execute("PRAGMA table_info(characters)")}
    if char_cols and "portrait_url" not in char_cols:
        conn.execute("ALTER TABLE characters ADD COLUMN portrait_url TEXT")
    scene_cols = {row[1] for row in conn.execute("PRAGMA table_info(scenes)")}
    if scene_cols and "final_video_url" not in scene_cols:
        conn.execute("ALTER TABLE scenes ADD COLUMN final_video_url TEXT")


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                role TEXT NOT NULL,
                personality TEXT NOT NULL,
                appearance TEXT NOT NULL,
                voice_style TEXT NOT NULL,
                color_hex TEXT NOT NULL,
                portrait_url TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scenes (
                id INTEGER PRIMARY KEY,
                scene_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                location TEXT NOT NULL,
                time_of_day TEXT NOT NULL,
                action_text TEXT NOT NULL,
                dialogue_json TEXT NOT NULL,
                emotion_tags TEXT NOT NULL,
                veo3_prompt TEXT NOT NULL,
                video_url TEXT,
                audio_url TEXT,
                final_video_url TEXT
            )
            """
        )

        migrate_schema(conn)

        character_count = conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
        if character_count == 0:
            conn.executemany(
                """
                INSERT INTO characters (name, age, role, personality, appearance, voice_style, color_hex, portrait_url)
                VALUES (:name, :age, :role, :personality, :appearance, :voice_style, :color_hex, NULL)
                """,
                SEED_CHARACTERS,
            )

        scene_count = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
        if scene_count == 0:
            conn.executemany(
                """
                INSERT INTO scenes (
                    scene_number, title, location, time_of_day, action_text,
                    dialogue_json, emotion_tags, veo3_prompt, video_url, audio_url, final_video_url
                )
                VALUES (
                    :scene_number, :title, :location, :time_of_day, :action_text,
                    :dialogue_json, :emotion_tags, :veo3_prompt, NULL, NULL, NULL
                )
                """,
                [
                    {
                        **scene,
                        "dialogue_json": json.dumps(scene["dialogue_json"]),
                        "emotion_tags": json.dumps(scene["emotion_tags"]),
                    }
                    for scene in SEED_SCENES
                ],
            )


def get_google_genai_client() -> genai.Client:
    if GEMINI_API_KEY:
        return genai.Client(api_key=GEMINI_API_KEY)
    if VERTEX_PROJECT_ID:
        return genai.Client(
            vertexai=True,
            project=VERTEX_PROJECT_ID,
            location=GOOGLE_CLOUD_LOCATION,
        )
    raise HTTPException(
        status_code=400,
        detail=(
            "Set GEMINI_API_KEY (or GOOGLE_API_KEY) for Gemini API, "
            "or GOOGLE_CLOUD_PROJECT + Application Default Credentials for Vertex AI."
        ),
    )


def get_elevenlabs_client() -> ElevenLabs:
    if not ELEVENLABS_API_KEY:
        raise HTTPException(status_code=400, detail="ELEVENLABS_API_KEY is not configured.")
    return ElevenLabs(api_key=ELEVENLABS_API_KEY)


def get_character_or_404(character_id: int) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Character not found.")
        return row_to_character(row)


def get_scene_row_or_404(scene_id: int) -> sqlite3.Row:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Scene not found.")
        return row


def scene_to_audio_script(scene: dict[str, Any]) -> str:
    chunks = [f"{scene['title']}. {scene['action_text']}"]
    for item in scene["dialogue_json"]:
        chunks.append(f"{item['speaker']} says: {item['line']}")
    return " ".join(chunks)


def fetch_uri_binary(uri: str) -> bytes:
    headers: dict[str, str] = {}
    parsed = urllib.parse.urlparse(uri)
    host = parsed.netloc.lower()
    # Gemini Developer media URLs require an API key; public GCS / signed URLs do not.
    if GEMINI_API_KEY and "storage.googleapis.com" not in host and "googleapis.com" in host:
        headers["x-goog-api-key"] = GEMINI_API_KEY

    req = urllib.request.Request(uri, headers=headers)

    ssl_ctx: ssl.SSLContext | None = None
    try:
        import certifi

        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    open_kw: dict[str, Any] = {"timeout": 600}
    if ssl_ctx is not None:
        open_kw["context"] = ssl_ctx
    with urllib.request.urlopen(req, **open_kw) as resp:
        return resp.read()


def save_video_file(video_obj: Any, destination: Path) -> None:
    if hasattr(video_obj, "video_bytes") and video_obj.video_bytes:
        destination.write_bytes(video_obj.video_bytes)
        return

    inline_data = getattr(video_obj, "inline_data", None)
    if inline_data and getattr(inline_data, "data", None):
        destination.write_bytes(inline_data.data)
        return

    uri = getattr(video_obj, "uri", None)
    if uri:
        destination.write_bytes(fetch_uri_binary(uri))
        return

    if hasattr(video_obj, "save") and callable(video_obj.save):
        video_obj.save(str(destination))
        return

    raise RuntimeError("Unable to persist generated video from GenAI response.")


def save_audio_stream(audio_iterable: Any, destination: Path) -> None:
    with destination.open("wb") as handle:
        for chunk in audio_iterable:
            if isinstance(chunk, bytes):
                handle.write(chunk)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def ffprobe_duration_seconds(media_path: Path) -> float | None:
    bin_path = shutil.which("ffprobe")
    if not bin_path:
        return None
    try:
        raw = subprocess.check_output(
            [
                bin_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media_path),
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return float(raw)
    except (subprocess.CalledProcessError, ValueError, OSError):
        return None


def apply_two_minute_triangle_script_to_db() -> list[int]:
    updated_ids: list[int] = []
    with get_db() as conn:
        for block in TWO_MINUTE_TRIANGLE_REV:
            sn = block["scene_number"]
            row = conn.execute("SELECT id FROM scenes WHERE scene_number = ?", (sn,)).fetchone()
            if not row:
                raise HTTPException(
                    status_code=500,
                    detail=f"Story sync failed: scene_number {sn} missing from SQLite.",
                )
            conn.execute(
                """
                UPDATE scenes
                SET title = ?, location = ?, time_of_day = ?, action_text = ?,
                    dialogue_json = ?, emotion_tags = ?, veo3_prompt = ?,
                    video_url = NULL, audio_url = NULL, final_video_url = NULL
                WHERE scene_number = ?
                """,
                (
                    block["title"],
                    block["location"],
                    block["time_of_day"],
                    block["action_text"],
                    json.dumps(block["dialogue_json"]),
                    json.dumps(block["emotion_tags"]),
                    block["veo3_prompt"],
                    sn,
                ),
            )
            updated_ids.append(int(row["id"]))
    updated_ids.sort()
    return updated_ids


def concat_scene_final_mp4s(paths: list[Path]) -> str:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise HTTPException(status_code=400, detail="ffmpeg executable not found on PATH.")
    uid = uuid4().hex
    list_file = VIDEO_DIR / f"story-concat-{uid}.ffconcat.txt"
    out_file = VIDEO_DIR / f"story-master-{uid}.mp4"
    chunks = ["ffconcat version 1.0\n"]
    for p in paths:
        escaped = str(p.resolve()).replace("'", "\\'")
        chunks.append(f"file '{escaped}'\n")
    list_file.write_text("".join(chunks))
    proc = subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        proc = subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "21",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(out_file),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        stderr = proc.stderr[-2400:] if proc.stderr else proc.stdout[-2400:] if proc.stdout else ""
        raise HTTPException(status_code=500, detail=f"Story stitch ffmpeg failed: {stderr}")
    return f"/static/videos/{out_file.name}"


def static_url_to_path(url: str) -> Path:
    if not url.startswith("/static/"):
        raise HTTPException(status_code=400, detail=f"Unsupported asset URL: {url}")
    return STATIC_DIR / url[len("/static/") :]


def load_characters_by_name() -> dict[str, dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM characters").fetchall()
    return {row_to_character(row)["name"]: row_to_character(row) for row in rows}


def gender_hint(character_name: str) -> str:
    if character_name.strip().lower() == "sara":
        return "woman"
    return "man"


def character_portrait_prompt(character: dict[str, Any]) -> str:
    g = gender_hint(character["name"])
    return (
        f"Ultra-photoreal cinematic close-up portrait of {character['name']}, "
        f"a {character['age']}-year-old Indian {g}, {character['appearance']}; "
        f"mood rooted in personality: {character['personality']}; role vibe: {character['role']}. "
        "Professional film lighting, 85mm lens, shallow depth of field, publicity still, "
        "neutral soft background, high detail eyes and skin texture, realistic color grade."
    )


def augment_veo_drama_prompt(scene: dict[str, Any], *, has_refs: bool) -> str:
    base = scene["veo3_prompt"].strip().rstrip(".")
    fragments: list[str] = []
    for entry in scene["dialogue_json"][:10]:
        note = entry.get("note", "").strip()
        frag = entry["speaker"]
        if note:
            frag += f" ({note})"
        frag += f': "{entry["line"]}"'
        fragments.append(frag)
    beats = "; ".join(fragments)
    identity = (
        "Use the supplied reference portraits as facial identity anchors (structure and likeness). "
        if has_refs
        else ""
    )
    continuity = (
        f"{scene['location']}, {scene['time_of_day']}. Blocking: {scene['action_text'].strip()}. "
        f"Perform emotional beats ({', '.join(scene['emotion_tags'])})."
    )
    tail = (
        f"{identity}{continuity} "
        "Natural on-camera conversational performance — subtle lips, jaw, and breath alive during spoken lines "
        '(unless the beat is expressly voice-over or silent). Scripted dialogue to inform timing and reactions: '
        f"{beats}."
    )
    return f"{base}. {tail}"


def portrait_reference_pack(
    scene: dict[str, Any], by_name: dict[str, dict[str, Any]]
) -> list[types.VideoGenerationReferenceImage]:
    refs: list[types.VideoGenerationReferenceImage] = []
    seen: list[str] = []
    for entry in scene["dialogue_json"]:
        name = entry["speaker"]
        if name in seen:
            continue
        seen.append(name)
        ch = by_name.get(name) or {}
        url = ch.get("portrait_url")
        if not url:
            continue
        path = static_url_to_path(url)
        if not path.exists():
            continue
        refs.append(
            types.VideoGenerationReferenceImage(
                image=types.Image.from_file(location=str(path)),
                reference_type=types.VideoGenerationReferenceType.ASSET,
            )
        )
        if len(refs) >= 3:
            break
    return refs


def persist_vertex_png(image: types.Image, destination: Path) -> None:
    if image.image_bytes:
        destination.write_bytes(image.image_bytes)
        return
    raise HTTPException(
        status_code=500,
        detail="Portrait generation returned no inline image bytes (GCS URIs require extra setup). ",
    )


def elevenlabs_to_mp3_bytes(client: ElevenLabs, voice_id: str, text: str) -> bytes:
    bio = BytesIO()
    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=ELEVENLABS_MODEL_ID,
        output_format="mp3_44100_128",
    )
    for chunk in audio:
        if isinstance(chunk, bytes):
            bio.write(chunk)
    return bio.getvalue()


def edge_tts_installed() -> bool:
    return edge_tts is not None




def edge_tts_bytes(text: str, voice: str) -> bytes:
    if edge_tts is None:
        raise HTTPException(
            status_code=500,
            detail="Install the edge-tts package for free TTS: pip install edge-tts",
        )

    async def _collect() -> bytes:
        bio = BytesIO()
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                bio.write(chunk["data"])
        return bio.getvalue()

    return asyncio.run(_collect())


def resolve_tts_route(speaker: str) -> Tuple[Literal["elevenlabs", "edge"], str]:
    """Return backend key and identifier (ElevenLabs voice_id or Edge voice short name)."""
    name = speaker.strip()
    eleven_id = (VOICE_ID_MAP.get(name) or "").strip()

    if TTS_BACKEND == "elevenlabs":
        if not ELEVENLABS_API_KEY.strip():
            raise HTTPException(
                status_code=400,
                detail="TTS_BACKEND=elevenlabs but ELEVENLABS_API_KEY is missing.",
            )
        if not eleven_id:
            raise HTTPException(
                status_code=400,
                detail=f"No ElevenLabs voice id configured for '{name}'. Set ELEVENLABS_VOICE_{name.upper().replace(' ', '_')}_ID.",
            )
        return ("elevenlabs", eleven_id)

    if TTS_BACKEND == "edge":
        if edge_tts is None:
            raise HTTPException(status_code=500, detail="edge-tts not installed.")
        vid = EDGE_VOICE_MAP.get(name, EDGE_VOICE_DEFAULT)
        return ("edge", vid)

    # auto — prefer ElevenLabs when credentials exist for this speaker.
    if ELEVENLABS_API_KEY.strip() and eleven_id:
        return ("elevenlabs", eleven_id)
    if edge_tts is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No speech backend for '{name}': ElevenLabs key or voice IDs missing, and edge-tts is not installed. "
                "Run `pip install edge-tts` or set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_*_ID."
            ),
        )
    return ("edge", EDGE_VOICE_MAP.get(name, EDGE_VOICE_DEFAULT))


def synthesize_line_to_mp3_bytes(speaker: str, text: str) -> Tuple[bytes, str]:
    route, vid = resolve_tts_route(speaker)
    if route == "elevenlabs":
        client = get_elevenlabs_client()
        raw = elevenlabs_to_mp3_bytes(client, vid, text)
        return raw, "elevenlabs"
    raw = edge_tts_bytes(text, vid)
    return raw, f"edge:{vid}"


def summarize_tts_for_health() -> dict[str, Any]:
    return {
        "tts_backend_env": TTS_BACKEND,
        "edge_tts_installed": edge_tts_installed(),
        "elevenlabs_key_present": bool(ELEVENLABS_API_KEY.strip()),
        "elevenlabs_voice_ids_present": (
            all((VOICE_ID_MAP.get(k) or "").strip() for k in VOICE_ID_MAP)
            if VOICE_ID_MAP
            else False
        ),
    }


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def healthcheck() -> dict[str, Any]:
    return {
        "status": "ok",
        "project_configured": GENAI_CLOUD_CONFIGURED,
        "gemini_api_configured": bool(GEMINI_API_KEY),
        "vertex_project_configured": bool(VERTEX_PROJECT_ID),
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "veo_model": VEO_MODEL,
        "google_cloud_location": GOOGLE_CLOUD_LOCATION,
        "imagen_model": IMAGEN_MODEL,
        "veo_clip_target_seconds": VEO_CLIP_SECONDS,
        "ffmpeg_available": ffmpeg_available(),
        "ffprobe_available": ffprobe_available(),
        **summarize_tts_for_health(),
        "tts_note": (
            "TTS_BACKEND=auto uses ElevenLabs when API key + voice ids exist per speaker (free signup quota at elevenlabs.io); "
            "otherwise Microsoft Edge neural TTS via edge-tts (no API key)."
        ),
        "placeholder_video_enabled": ALLOW_PLACEHOLDER_VIDEO,
    }


@app.get("/api/characters")
def list_characters() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM characters ORDER BY id ASC").fetchall()
        return [row_to_character(row) for row in rows]


@app.put("/api/characters/{character_id}")
def update_character(character_id: int, payload: CharacterUpdate) -> dict[str, Any]:
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE characters
            SET name = ?, age = ?, role = ?, personality = ?, appearance = ?, voice_style = ?, color_hex = ?
            WHERE id = ?
            """,
            (
                payload.name,
                payload.age,
                payload.role,
                payload.personality,
                payload.appearance,
                payload.voice_style,
                payload.color_hex,
                character_id,
            ),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Character not found.")

    return get_character_or_404(character_id)


@app.post("/api/characters/{character_id}/generate-portrait")
def generate_character_portrait(character_id: int) -> dict[str, Any]:
    character = get_character_or_404(character_id)
    client = get_google_genai_client()
    file_name = f"{character['name'].lower().replace(' ', '-')}-{uuid4().hex}.png"
    destination = PORTRAITS_DIR / file_name

    try:
        img_cfg: dict[str, Any] = {
            "number_of_images": 1,
            "aspect_ratio": "3:4",
            "person_generation": types.PersonGeneration.ALLOW_ADULT,
            "output_mime_type": "image/png",
        }
        if not GEMINI_API_KEY:
            img_cfg["enhance_prompt"] = True
        response = client.models.generate_images(
            model=IMAGEN_MODEL,
            prompt=character_portrait_prompt(character),
            config=types.GenerateImagesConfig(**img_cfg),
        )
    except Exception as exc:  # pragma: no cover - networked SDK call
        raise HTTPException(status_code=500, detail=f"Portrait generation failed: {exc}") from exc

    if not response.generated_images:
        attrs = response.positive_prompt_safety_attributes
        filtered = attrs.model_dump() if attrs else "No metadata"
        raise HTTPException(
            status_code=400,
            detail=f"No portrait images returned; prompt may have been filtered. Detail: {filtered}",
        )

    first = response.generated_images[0]
    if first.rai_filtered_reason:
        raise HTTPException(status_code=400, detail=f"Image filtered: {first.rai_filtered_reason}")
    if not first.image:
        raise HTTPException(status_code=500, detail="Imagen returned no raster image payload.")

    try:
        persist_vertex_png(first.image, destination)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Could not persist portrait file: {exc}") from exc

    public_url = f"/static/portraits/{file_name}"
    with get_db() as conn:
        conn.execute("UPDATE characters SET portrait_url = ? WHERE id = ?", (public_url, character_id))

    return get_character_or_404(character_id)


@app.post("/api/characters/{character_id}/generate-voice")
def generate_character_voice(character_id: int, payload: VoiceGenerationRequest) -> dict[str, Any]:
    character = get_character_or_404(character_id)
    file_name = f"{character['name'].lower()}-{uuid4().hex}.mp3"
    destination = AUDIO_DIR / file_name

    try:
        raw, backend_used = synthesize_line_to_mp3_bytes(character["name"], payload.text)
        destination.write_bytes(raw)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - network / pydub paths
        raise HTTPException(status_code=500, detail=f"Voice generation failed: {exc}") from exc

    return {
        "character_id": character_id,
        "character_name": character["name"],
        "audio_url": f"/static/audio/{file_name}",
        "tts_route": backend_used,
    }


@app.get("/api/scenes")
def list_scenes() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM scenes ORDER BY scene_number ASC").fetchall()
        return [row_to_scene(row) for row in rows]


@app.get("/api/scenes/{scene_id}")
def get_scene(scene_id: int) -> dict[str, Any]:
    row = get_scene_row_or_404(scene_id)
    return row_to_scene(row)


@app.put("/api/scenes/{scene_id}")
def update_scene(scene_id: int, payload: SceneUpdate) -> dict[str, Any]:
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE scenes
            SET title = ?, location = ?, time_of_day = ?, action_text = ?, dialogue_json = ?, emotion_tags = ?, veo3_prompt = ?
            WHERE id = ?
            """,
            (
                payload.title,
                payload.location,
                payload.time_of_day,
                payload.action_text,
                json.dumps(payload.dialogue_json),
                json.dumps(payload.emotion_tags),
                payload.veo3_prompt,
                scene_id,
            ),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Scene not found.")
    return get_scene(scene_id)


@app.post("/api/scenes/{scene_id}/generate-video")
def generate_scene_video(scene_id: int) -> dict[str, Any]:
    scene = get_scene(scene_id)
    client = get_google_genai_client()
    by_name = load_characters_by_name()
    ref_pack = portrait_reference_pack(scene, by_name)
    full_prompt = augment_veo_drama_prompt(scene, has_refs=len(ref_pack) > 0)
    file_name = f"scene-{scene['scene_number']}-{uuid4().hex}.mp4"
    destination = VIDEO_DIR / file_name

    config_kw: dict[str, Any] = {
        "number_of_videos": 1,
        "duration_seconds": VEO_CLIP_SECONDS,
        "aspect_ratio": VEO_ASPECT_RATIO,
    }
    if not GEMINI_API_KEY:
        config_kw["enhance_prompt"] = True
        config_kw["generate_audio"] = VEO_GENERATE_NATIVE_AUDIO
    if ref_pack:
        config_kw["reference_images"] = ref_pack

    try:
        operation = client.models.generate_videos(
            model=VEO_MODEL,
            source=types.GenerateVideosSource(prompt=full_prompt),
            config=types.GenerateVideosConfig(**config_kw),
        )

        while not operation.done:
            time.sleep(VEO_POLL_SECONDS)
            operation = client.operations.get(operation)

        generated_video = operation.response.generated_videos[0].video
        save_video_file(generated_video, destination)
    except Exception as exc:  # pragma: no cover - networked SDK call
        raise HTTPException(status_code=500, detail=f"Veo generation failed: {exc}") from exc

    public_url = f"/static/videos/{file_name}"
    with get_db() as conn:
        conn.execute(
            "UPDATE scenes SET video_url = ?, final_video_url = NULL WHERE id = ?",
            (public_url, scene_id),
        )

    out = get_scene(scene_id)
    out["generation_meta"] = {
        "prompt_used_preview": full_prompt[:800],
        "reference_portrait_count": len(ref_pack),
        "references_used_when_available": bool(ref_pack),
        "clip_target_seconds": VEO_CLIP_SECONDS,
        "lip_sync_note": (
            "Mouth motion is modeled by Veo from references + prompt; stitched TTS (ElevenLabs or free Edge neural"
            ") is muxed in ffmpeg—phoneme-perfect sync needs a specialized lip-sync pass."
        ),
    }
    return out


@app.post("/api/scenes/{scene_id}/generate-audio")
def generate_scene_audio(scene_id: int, payload: SceneAudioGenerationRequest) -> dict[str, Any]:
    scene = get_scene(scene_id)
    chosen_name = payload.character_name or (
        scene["dialogue_json"][0]["speaker"] if scene["dialogue_json"] else "Sara"
    )
    text = payload.text or scene_to_audio_script(scene)
    file_name = f"scene-{scene['scene_number']}-{chosen_name.lower().replace(' ', '-')}-{uuid4().hex}.mp3"
    destination = AUDIO_DIR / file_name

    try:
        raw, _backend_used = synthesize_line_to_mp3_bytes(chosen_name, text)
        destination.write_bytes(raw)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Scene narration failed: {exc}") from exc

    public_url = f"/static/audio/{file_name}"
    with get_db() as conn:
        conn.execute(
            "UPDATE scenes SET audio_url = ?, final_video_url = NULL WHERE id = ?",
            (public_url, scene_id),
        )

    return get_scene(scene_id)


@app.post("/api/scenes/{scene_id}/generate-dialogue-audio")
def generate_scene_dialogue_audio(scene_id: int) -> dict[str, Any]:
    scene = get_scene(scene_id)
    lines = scene["dialogue_json"]
    if not lines:
        raise HTTPException(status_code=400, detail="Scene has no dialogue.")
    ffmpeg_bin = ffmpeg_available()
    if not ffmpeg_bin:
        raise HTTPException(
            status_code=400,
            detail="ffmpeg is required on the PATH to splice MP3 clips (pydub).",
        )

    pause = AudioSegment.silent(duration=DIALOGUE_PAUSE_MS)
    combined = AudioSegment.empty()
    appended = False
    backends_used: list[str] = []
    try:
        for entry in lines:
            speaker = entry.get("speaker") or ""
            line = (entry.get("line") or "").strip()
            if not line:
                continue
            raw, tag = synthesize_line_to_mp3_bytes(speaker, line)
            backends_used.append(tag)
            seg = AudioSegment.from_file(BytesIO(raw), format="mp3")
            if not appended:
                combined += seg
                appended = True
            else:
                combined += pause + seg

        if combined.duration_seconds <= 0 or not appended:
            raise HTTPException(status_code=400, detail="No dialogue lines synthesized.")

        file_name = f"scene-{scene['scene_number']}-dialogue-{uuid4().hex}.mp3"
        destination = AUDIO_DIR / file_name
        combined.export(str(destination), format="mp3", bitrate="128k")
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - ffmpeg / pydub / network
        raise HTTPException(status_code=500, detail=f"Mixed dialogue synthesis failed: {exc}") from exc

    public_url = f"/static/audio/{file_name}"
    with get_db() as conn:
        conn.execute(
            "UPDATE scenes SET audio_url = ?, final_video_url = NULL WHERE id = ?",
            (public_url, scene_id),
        )

    out = get_scene(scene_id)
    out["dialogue_tts_backends"] = backends_used
    return out


@app.post("/api/scenes/{scene_id}/generate-placeholder-video")
def generate_placeholder_scene_video(scene_id: int) -> dict[str, Any]:
    if not ALLOW_PLACEHOLDER_VIDEO:
        raise HTTPException(
            status_code=403,
            detail="Disabled: set ALLOW_PLACEHOLDER_VIDEO=true in backend/.env for offline pipeline smoke tests.",
        )

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise HTTPException(status_code=400, detail="ffmpeg executable not found on PATH.")

    scene = get_scene(scene_id)
    secs = max(4, min(int(VEO_CLIP_SECONDS), 120))
    w, h = "1920", "1080"
    if VEO_ASPECT_RATIO.strip() == "9:16":
        w, h = "1080", "1920"

    file_name = f"scene-{scene['scene_number']}-placeholder-{uuid4().hex}.mp4"
    destination = VIDEO_DIR / file_name

    proc = subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0d0f14:s={w}x{h}:d={secs}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"ffmpeg placeholder failed: {proc.stderr[-2000:] if proc.stderr else proc.stdout}",
        )

    public_url = f"/static/videos/{file_name}"
    with get_db() as conn:
        conn.execute(
            "UPDATE scenes SET video_url = ?, final_video_url = NULL WHERE id = ?",
            (public_url, scene_id),
        )

    out = get_scene(scene_id)
    out["generation_meta"] = {
        "kind": "placeholder_slate",
        "seconds": secs,
        "note": "Replace with Vertex Veo when Application Default Credentials are configured.",
    }
    return out


@app.post("/api/scenes/{scene_id}/compose-final")
def compose_scene_final_video(scene_id: int) -> dict[str, Any]:
    scene = get_scene(scene_id)
    if not scene.get("video_url"):
        raise HTTPException(status_code=400, detail="Generate the scene video first.")
    if not scene.get("audio_url"):
        raise HTTPException(status_code=400, detail="Generate dialogue (or narrator) audio first.")

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise HTTPException(status_code=400, detail="ffmpeg executable not found on PATH.")

    video_path = static_url_to_path(scene["video_url"])
    audio_path = static_url_to_path(scene["audio_url"])
    if not video_path.exists() or not audio_path.exists():
        raise HTTPException(status_code=400, detail="Video or audio file missing on disk; regenerate assets.")

    out_name = f"scene-{scene['scene_number']}-final-{uuid4().hex}.mp4"
    out_path = VIDEO_DIR / out_name

    dur_s = ffprobe_duration_seconds(video_path)

    if dur_s is not None:
        dfs = f"{dur_s:.5f}"
        filter_chain = (
            f"[1:a]atrim=end={dfs},asetpts=PTS-STARTPTS[a0];[a0]apad=whole_dur={dfs}[aout]"
        )
        proc = subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-filter_complex",
                filter_chain,
                "-map",
                "0:v:0",
                "-map",
                "[aout]",
                "-t",
                dfs,
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(out_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        proc = subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(out_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    if proc.returncode != 0:
        msg = proc.stderr[-2000:] if proc.stderr else proc.stdout[-2000:] if proc.stdout else ""
        raise HTTPException(status_code=500, detail=f"ffmpeg failed: {msg}")

    final_url = f"/static/videos/{out_name}"
    with get_db() as conn:
        conn.execute("UPDATE scenes SET final_video_url = ? WHERE id = ?", (final_url, scene_id))

    return get_scene(scene_id)


@app.post("/api/story/sync-two-minute-triangle-script")
def api_story_sync_triangle_script() -> dict[str, Any]:
    ids = apply_two_minute_triangle_script_to_db()
    n = len(ids)
    return {
        "scene_ids": ids,
        "per_clip_target_seconds": VEO_CLIP_SECONDS,
        "scene_count": n,
        "approx_story_seconds_cap": VEO_CLIP_SECONDS * n,
        "note": "Clears per-scene video/audio/final URLs so the next run regenerates fresh clips.",
    }


@app.post("/api/story/run-full-pipeline")
def api_story_run_full_pipeline(
    sync_script: bool = Query(True, description="Overwrite scenes 1–5 with triangle arc for all three leads."),
    regenerate_portraits: bool = Query(False, description="POST Imagen portraits for every character (costly)."),
    stitch: bool = Query(True, description="Concatenate per-scene finals into one story-master MP4."),
) -> dict[str, Any]:
    if sync_script:
        apply_two_minute_triangle_script_to_db()
    if regenerate_portraits:
        with get_db() as conn:
            characters = conn.execute("SELECT id FROM characters ORDER BY id ASC").fetchall()
        for row in characters:
            generate_character_portrait(int(row["id"]))

    with get_db() as conn:
        ordered = conn.execute("SELECT id FROM scenes ORDER BY scene_number ASC").fetchall()
        scene_ids = [int(r["id"]) for r in ordered]

    clip_payload: list[dict[str, Any]] = []
    for sid in scene_ids:
        generate_scene_video(sid)
        generate_scene_dialogue_audio(sid)
        compose_scene_final_video(sid)
        clip_payload.append(get_scene(sid))

    master_url = None
    if stitch:
        paths: list[Path] = []
        for clip in clip_payload:
            fu = clip.get("final_video_url")
            if not fu:
                raise HTTPException(status_code=500, detail="Missing final_video_url after compose.")
            paths.append(static_url_to_path(fu))
        master_url = concat_scene_final_mp4s(paths)

    return {
        "story_master_url": master_url,
        "per_clip_target_seconds": VEO_CLIP_SECONDS,
        "approx_story_seconds_cap": VEO_CLIP_SECONDS * len(scene_ids),
        "clips": clip_payload,
    }


@app.exception_handler(sqlite3.Error)
def sqlite_exception_handler(_: Any, exc: sqlite3.Error) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": f"Database error: {exc}"})
