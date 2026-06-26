from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.lyrics_service import format_lyrics

router = APIRouter(prefix="/api", tags=["lyrics"])


class FormatLyricsRequest(BaseModel):
    lyrics: str = Field(min_length=1, max_length=10000)
    structure: Literal["auto", "verse_chorus", "intro_verse_chorus", "hook_loop", "club_build", "ambient_loop"] = "verse_chorus"


class FormatLyricsResponse(BaseModel):
    formatted: str
    line_count: int
    section_count: int


@router.post("/format-lyrics", response_model=FormatLyricsResponse)
def format_lyrics_endpoint(request: FormatLyricsRequest):
    formatted = format_lyrics(request.lyrics, request.structure)
    lines = [line for line in formatted.splitlines() if line.strip()]
    sections = sum(1 for line in lines if line.rstrip().endswith(":"))
    return FormatLyricsResponse(formatted=formatted, line_count=len(lines), section_count=sections)
