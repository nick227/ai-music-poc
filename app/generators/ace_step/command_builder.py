from __future__ import annotations

from pathlib import Path

from app.core.command_template import render_command, safe_write_text
from app.core.config import Settings
from app.domain.models import GenerationRequest


class AceCommandBuilder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def prompt_with_voice(self, request: GenerationRequest) -> str:
        voice_parts = []
        if request.singing_voice != "auto":
            voice_parts.append(f"{request.singing_voice} singing voice")
        if request.vocal_style:
            voice_parts.append(request.vocal_style)
        if request.mode in ("song", "vocal_demo") and voice_parts:
            return f"{request.prompt}\n\nVocal direction: {', '.join(voice_parts)}. Vocal intensity {request.vocal_intensity:.2f}."
        return request.prompt

    def prepare_files(self, request: GenerationRequest, output_path: Path) -> dict[str, Path]:
        tmp_dir = self.settings.tmp_dir / output_path.stem
        tmp_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = tmp_dir / "prompt.txt"
        lyrics_file = tmp_dir / "lyrics.txt"
        negative_file = tmp_dir / "negative_prompt.txt"
        request_file = tmp_dir / "request.json"
        safe_write_text(prompt_file, self.prompt_with_voice(request))
        safe_write_text(lyrics_file, request.lyrics)
        safe_write_text(negative_file, request.negative_prompt)
        safe_write_text(request_file, request.model_dump_json(indent=2))
        return {"prompt_file": prompt_file, "lyrics_file": lyrics_file, "negative_file": negative_file, "request_file": request_file}

    def build(self, request: GenerationRequest, output_path: Path) -> list[str]:
        files = self.prepare_files(request, output_path)
        values = {
            "python": self.settings.ace_python,
            "script": self.settings.ace_script,
            "prompt": request.prompt,
            "lyrics": request.lyrics,
            "title": request.title,
            "duration_seconds": request.duration_seconds,
            "seed": "" if request.seed is None else request.seed,
            "bpm": "" if request.bpm is None else request.bpm,
            "key": request.key or "",
            "mode": request.mode,
            "structure": request.structure,
            "quality": request.quality,
            "guidance_scale": request.guidance_scale,
            "negative_prompt": request.negative_prompt,
            "vocal_style": request.vocal_style or "",
            "singing_voice": request.singing_voice,
            "vocal_intensity": request.vocal_intensity,
            "genre_tags": ",".join(request.genre_tags),
            "mood_tags": ",".join(request.mood_tags),
            "lora_path": request.lora_path or "__none__",
            "lora_scale": request.lora_scale,
            "use_lora": "true" if request.lora_path else "false",
            "output_path": output_path,
            "model_dir": self.settings.ace_model_dir,
            "device": self.settings.ace_device,
            **files,
        }
        return render_command(self.settings.ace_command_template, values)
