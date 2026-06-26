from __future__ import annotations

from app.domain.models import GenerationRequest, Preset

PRESETS: list[Preset] = [
    Preset(
        id="french-disco-sad",
        label="French Disco Sad",
        description="Glossy dance pulse, melancholy vocal, analog bass, emotional night-drive energy.",
        prompt_suffix="French disco, glossy drums, analog bass, bittersweet vocal, cinematic night drive, elegant melancholy.",
        negative_prompt="novelty, parody, harsh treble, muddy mix, theatrical musical vocals",
        mode="song",
        structure="intro_verse_chorus",
        quality="balanced",
        duration_seconds=90,
        bpm=116,
        vocal_style="reserved male vocal, intimate, slightly breathy",
        singing_voice="male",
        vocal_intensity=0.72,
        genre_tags=["disco", "indie", "electronic"],
        mood_tags=["sad", "cinematic", "cool"],
    ),
    Preset(id="dark-club-demo", label="Dark Club Demo", description="Four-on-floor club sketch with stronger kick and minor scale tension.", prompt_suffix="dark club, four-on-floor, sub bass, tense synth stabs, late-night warehouse", negative_prompt="thin kick, happy pop, acoustic strumming", structure="club_build", quality="balanced", duration_seconds=75, bpm=124, genre_tags=["club", "electronic"], mood_tags=["dark", "driving"]),
    Preset(id="indie-acoustic-fx", label="Indie Acoustic FX", description="Plucked acoustic texture, FX haze, restrained post-indie feel.", prompt_suffix="heavy FX acoustic guitar, crisp urgency, restrained vocal, post-indie underground cool", negative_prompt="jam band, church rock, theatrical, whimsical", structure="verse_chorus", duration_seconds=90, bpm=102, vocal_style="quiet reserved vocal", genre_tags=["indie", "acoustic"], mood_tags=["urgent", "reserved"]),
    Preset(id="heavy-rap-mixtape", label="Heavy Rap Mixtape", description="Hard drums, low bass, aggressive mixtape energy.", prompt_suffix="heavy rap mixtape, hard drums, low 808, ominous sample, confident hook", negative_prompt="soft pop, cheerful ukulele, thin drums", structure="hook_loop", duration_seconds=60, bpm=82, vocal_style="forceful rap cadence", genre_tags=["rap", "trap"], mood_tags=["heavy", "aggressive"]),
    Preset(id="ambient-instrumental", label="Ambient Instrumental", description="No vocal focus, long pads, evolving texture.", prompt_suffix="ambient instrumental, long evolving pads, soft noise, cinematic texture", negative_prompt="busy drums, harsh lead, dense vocals", mode="instrumental", structure="ambient_loop", duration_seconds=120, bpm=70, genre_tags=["ambient"], mood_tags=["calm", "wide"]),
    Preset(id="pop-hook-draft", label="Pop Hook Draft", description="Quick vocal hook layout for songwriting drafts.", prompt_suffix="modern pop hook, clear chorus lift, simple memorable melody, polished demo", negative_prompt="muddy vocal, overcomplicated arrangement", mode="vocal_demo", structure="verse_chorus", duration_seconds=60, bpm=108, vocal_style="clear melodic demo vocal", singing_voice="female", vocal_intensity=0.85, quality="balanced", genre_tags=["pop"], mood_tags=["direct"]),
    Preset(id="lofi-loop", label="Lo-fi Loop", description="Soft loop for background beds and visualizer demos.", prompt_suffix="lo-fi loop, dusty texture, soft drums, warm keys, tape wobble", negative_prompt="bright EDM, aggressive lead, harsh cymbals", mode="loop", structure="hook_loop", duration_seconds=45, bpm=86, genre_tags=["lofi"], mood_tags=["warm", "relaxed"]),
    Preset(id="cinematic-trailer-cue", label="Cinematic Trailer Cue", description="Short dramatic cue with rising intensity.", prompt_suffix="cinematic trailer cue, rising tension, low pulses, dramatic hit, wide reverb", negative_prompt="comedy, small room, weak drums", mode="instrumental", structure="club_build", duration_seconds=60, bpm=96, genre_tags=["cinematic"], mood_tags=["dramatic", "epic"]),
]


def list_presets() -> list[Preset]:
    return PRESETS


def get_preset(preset_id: str) -> Preset | None:
    return next((preset for preset in PRESETS if preset.id == preset_id), None)


def apply_preset(request: GenerationRequest, preset: Preset) -> GenerationRequest:
    data = request.model_dump()
    data.update({
        "mode": preset.mode,
        "structure": preset.structure,
        "quality": preset.quality,
        "duration_seconds": preset.duration_seconds,
        "bpm": preset.bpm,
        "key": preset.key,
        "vocal_style": preset.vocal_style,
        "singing_voice": preset.singing_voice,
        "vocal_intensity": preset.vocal_intensity,
        "genre_tags": preset.genre_tags,
        "mood_tags": preset.mood_tags,
    })
    suffix = preset.prompt_suffix.strip()
    if suffix and suffix.lower() not in request.prompt.lower():
        data["prompt"] = f"{request.prompt.strip()}\n\nPreset direction: {suffix}"
    if preset.negative_prompt and not data.get("negative_prompt"):
        data["negative_prompt"] = preset.negative_prompt
    return GenerationRequest.model_validate(data)
