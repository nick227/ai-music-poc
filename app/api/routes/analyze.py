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


@router.post("/analyze-prompt", response_model=AnalyzeResponse)
async def analyze_prompt(request: AnalyzeRequest, settings: Settings = Depends(get_settings)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured — add it to .env to enable AI prompt analysis")
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
        return AnalyzeResponse(**{k: v for k, v in data.items() if k in AnalyzeResponse.model_fields})
    except json.JSONDecodeError as exc:
        logger.warning("analyze_prompt json decode failed: %s", exc)
        raise HTTPException(status_code=502, detail="AI response was not valid JSON")
    except Exception as exc:
        logger.error("analyze_prompt error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
