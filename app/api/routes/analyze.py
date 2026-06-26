from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import get_settings
from app.core.config import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    prompt: str
    lyrics: str = ""


class AnalyzeResponse(BaseModel):
    bpm: int | None = None
    key: str | None = None
    mode: str | None = None
    structure: str | None = None
    quality: str | None = None
    singing_voice: str | None = None
    vocal_style: str | None = None
    genre_tags: list[str] = []
    mood_tags: list[str] = []
    negative_prompt: str = ""
    enhanced_prompt: str = ""
    ai_enhanced: bool = False


ANALYZE_SYSTEM = """You are a music production expert. Analyze the user's music generation prompt and extract precise musical parameters. Return ONLY valid JSON with these optional fields:

{
  "bpm": <integer 40-220 — infer from genre/mood>,
  "key": <string like "C", "F#", "Bb", "Eb" — omit if not clear>,
  "mode": <"song" | "instrumental" | "vocal_demo" | "loop">,
  "structure": <"auto" | "verse_chorus" | "intro_verse_chorus" | "hook_loop" | "club_build" | "ambient_loop">,
  "quality": <"draft" | "balanced" | "high">,
  "singing_voice": <"auto" | "female" | "male" | "choir" | "robot" | "whisper">,
  "vocal_style": <short string describing tone, technique, character — max 120 chars>,
  "genre_tags": [<up to 5 specific genre strings, lowercase>],
  "mood_tags": [<up to 5 mood/vibe strings, lowercase>],
  "negative_prompt": <what to avoid in production — max 200 chars>,
  "enhanced_prompt": <improved version of original prompt, 1-3 sentences, rich with production detail>
}

Be specific and production-aware. Infer missing parameters from genre conventions. Return ONLY the JSON object."""


def _local_analyze(prompt: str, lyrics: str) -> AnalyzeResponse:
    """Keyword-based fallback when no API key is configured."""
    text = (prompt + " " + lyrics).lower()

    # BPM inference
    bpm_map = [
        (["lullaby", "ambient", "meditation", "sleep"], 68),
        (["ballad", "slow", "melancholy", "sad"], 76),
        (["folk", "acoustic", "singer-songwriter"], 90),
        (["lofi", "lo-fi", "chill", "chillhop"], 86),
        (["hip hop", "hiphop", "rap", "trap"], 92),
        (["pop", "radio", "mainstream"], 120),
        (["disco", "funky", "funk"], 118),
        (["dance", "club", "house"], 128),
        (["techno", "trance"], 140),
        (["drum and bass", "dnb", "jungle"], 174),
        (["punk", "metal", "thrash"], 160),
    ]
    bpm = 120
    for kws, b in bpm_map:
        if any(k in text for k in kws):
            bpm = b
            break

    # Key detection from prompt text
    key = None
    import re
    m = re.search(r'\b(?:in\s+)?([A-G][b#]?)\s+(?:major|minor|maj|min)?\b', prompt, re.IGNORECASE)
    if m:
        key = m.group(1)

    # Mode
    mode = "song"
    if any(k in text for k in ["instrumental", "no vocals", "no voice", "without vocals"]):
        mode = "instrumental"
    elif any(k in text for k in ["vocal demo", "vocal only", "a cappella"]):
        mode = "vocal_demo"
    elif any(k in text for k in ["loop", "looping", "seamless"]):
        mode = "loop"

    # Structure
    structure = "auto"
    if any(k in text for k in ["club", "warehouse", "rave", "build-up", "buildup", "drop"]):
        structure = "club_build"
    elif any(k in text for k in ["hook loop", "hook"]):
        structure = "hook_loop"
    elif any(k in text for k in ["ambient", "drone", "meditation"]):
        structure = "ambient_loop"
    elif any(k in text for k in ["intro", "verse", "chorus"]):
        structure = "intro_verse_chorus"

    # Singing voice
    singing_voice = "auto"
    if any(k in text for k in ["female", "woman", "soprano", "alto", "girl"]):
        singing_voice = "female"
    elif any(k in text for k in ["male", "man", "tenor", "baritone", "bass voice"]):
        singing_voice = "male"
    elif any(k in text for k in ["choir", "choral", "group", "harmony vocals"]):
        singing_voice = "choir"
    elif any(k in text for k in ["robot", "vocoder", "autotune", "synth voice"]):
        singing_voice = "robot"
    elif any(k in text for k in ["whisper", "breathy", "hushed"]):
        singing_voice = "whisper"

    # Vocal style
    style_parts = []
    if any(k in text for k in ["powerful", "belting", "strong"]):
        style_parts.append("powerful belt")
    elif any(k in text for k in ["soft", "gentle", "tender"]):
        style_parts.append("soft and gentle")
    if any(k in text for k in ["soulful", "soul", "r&b", "gospel"]):
        style_parts.append("soulful")
    if any(k in text for k in ["electronic", "processed", "effect"]):
        style_parts.append("processed")
    vocal_style = ", ".join(style_parts) if style_parts else "natural"

    # Genre tags
    genre_kw = {
        "pop": ["pop", "radio", "mainstream", "chart"],
        "hip hop": ["hip hop", "hiphop", "rap", "trap"],
        "electronic": ["edm", "electronic", "synth", "electro"],
        "lo-fi": ["lofi", "lo-fi", "chillhop"],
        "disco": ["disco", "funky", "funk"],
        "acoustic": ["acoustic", "folk", "singer-songwriter", "guitar"],
        "ambient": ["ambient", "drone", "meditation", "atmospheric"],
        "club": ["club", "techno", "house", "warehouse", "rave"],
        "cinematic": ["cinematic", "epic", "orchestral", "trailer", "score"],
        "r&b": ["r&b", "rnb", "soul", "soulful"],
    }
    genre_tags = [g for g, kws in genre_kw.items() if any(k in text for k in kws)][:5]

    # Mood tags
    mood_kw = {
        "energetic": ["energetic", "upbeat", "exciting", "powerful", "pumping", "fast"],
        "groovy": ["funky", "funk", "groove", "groovy", "dance", "danceable"],
        "chill": ["chill", "relaxed", "laid-back", "mellow", "calm", "soothing"],
        "melancholy": ["melancholy", "sad", "emotional", "longing", "heartbreak", "bittersweet"],
        "euphoric": ["euphoric", "joyful", "happy", "uplifting", "feel-good", "positive"],
        "dark": ["dark", "gritty", "intense", "aggressive", "heavy", "ominous"],
        "dreamy": ["dreamy", "ethereal", "hypnotic", "spacey", "hazy", "floating"],
        "romantic": ["romantic", "love", "intimate", "tender", "sweet", "passionate"],
        "epic": ["epic", "cinematic", "dramatic", "grand", "powerful", "triumphant"],
    }
    mood_tags = [m for m, kws in mood_kw.items() if any(k in text for k in kws)][:5]

    enhanced_prompt = prompt.strip()
    if genre_tags:
        enhanced_prompt += f". Genre: {', '.join(genre_tags)}"
    if mood_tags:
        enhanced_prompt += f". Vibe: {', '.join(mood_tags)}"

    return AnalyzeResponse(
        bpm=bpm,
        key=key,
        mode=mode,
        structure=structure,
        quality="balanced",
        singing_voice=singing_voice,
        vocal_style=vocal_style,
        genre_tags=genre_tags,
        mood_tags=mood_tags,
        negative_prompt="",
        enhanced_prompt=enhanced_prompt,
    )


@router.post("/analyze-prompt", response_model=AnalyzeResponse)
async def analyze_prompt(request: AnalyzeRequest, settings: Settings = Depends(get_settings)):
    if not settings.anthropic_api_key:
        return _local_analyze(request.prompt, request.lyrics)
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        user_content = f"Prompt: {request.prompt}"
        if request.lyrics.strip():
            user_content += f"\n\nLyrics preview: {request.lyrics[:400]}"

        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=ANALYZE_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        text = message.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        return AnalyzeResponse(ai_enhanced=True, **{k: v for k, v in data.items() if k in AnalyzeResponse.model_fields and k != "ai_enhanced"})
    except json.JSONDecodeError as exc:
        logger.warning("analyze_prompt json decode failed: %s", exc)
        raise HTTPException(status_code=502, detail="AI response was not valid JSON")
    except Exception as exc:
        logger.error("analyze_prompt error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
