from __future__ import annotations

import math
import random
import wave
from pathlib import Path

from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo
from app.generators.lyrics_timeline import build_lyric_timeline, event_at
from app.generators.quality_profile import quality_for

SAMPLE_RATE = 44_100
NYQUIST = SAMPLE_RATE / 2

# Per-formant bandwidth constants (Hz) — narrower = more resonant peak
F1_BW = 85.0
F2_BW = 72.0
F3_BW = 155.0
F4_BW = 250.0  # "singing formant" cluster ~3.2kHz adds brilliance


class StyleProfile:
    __slots__ = (
        "name", "default_bpm", "scale", "drum_pattern", "has_drums",
        "bass_amp", "pad_amp", "lead_amp", "vocal_amp", "noise_amp",
        "swing", "pluck_kind", "chorus_lift", "lowpass",
    )

    def __init__(
        self, name: str, default_bpm: int, scale: list[int], drum_pattern: str,
        has_drums: bool = True, bass_amp: float = 0.22, pad_amp: float = 0.10,
        lead_amp: float = 0.08, vocal_amp: float = 0.065, noise_amp: float = 0.02,
        swing: float = 0.0, pluck_kind: str = "sine", chorus_lift: float = 1.12,
        lowpass: float = 1.0,
    ) -> None:
        self.name = name
        self.default_bpm = default_bpm
        self.scale = scale
        self.drum_pattern = drum_pattern
        self.has_drums = has_drums
        self.bass_amp = bass_amp
        self.pad_amp = pad_amp
        self.lead_amp = lead_amp
        self.vocal_amp = vocal_amp
        self.noise_amp = noise_amp
        self.swing = swing
        self.pluck_kind = pluck_kind
        self.chorus_lift = chorus_lift
        self.lowpass = lowpass


class VoiceProfile:
    __slots__ = ("name", "base_multiplier", "vibrato_rate", "vibrato_depth", "breath", "brightness", "formants", "blend_count", "quantized")

    def __init__(
        self, name: str, base_multiplier: float, vibrato_rate: float,
        vibrato_depth: float, breath: float, brightness: float,
        formants: tuple[float, float, float, float],
        blend_count: int = 1, quantized: bool = False,
    ) -> None:
        self.name = name
        self.base_multiplier = base_multiplier
        self.vibrato_rate = vibrato_rate
        self.vibrato_depth = vibrato_depth
        self.breath = breath
        self.brightness = brightness
        self.formants = formants
        self.blend_count = blend_count
        self.quantized = quantized


MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
PENTATONIC_MINOR = [0, 3, 5, 7, 10]
DORIAN = [0, 2, 3, 5, 7, 9, 10]

PROFILES: dict[str, StyleProfile] = {
    "disco": StyleProfile(
        "disco", 116, DORIAN, "four_floor",
        bass_amp=0.30, pad_amp=0.12, lead_amp=0.06, vocal_amp=0.068,
        noise_amp=0.035, pluck_kind="pluck", chorus_lift=1.25,
    ),
    "club": StyleProfile(
        "club", 124, MINOR, "four_floor",
        bass_amp=0.34, pad_amp=0.09, lead_amp=0.10, vocal_amp=0.055,
        noise_amp=0.04, pluck_kind="saw", chorus_lift=1.30,
    ),
    "rap": StyleProfile(
        "rap", 82, PENTATONIC_MINOR, "half_time",
        bass_amp=0.42, pad_amp=0.045, lead_amp=0.045, vocal_amp=0.048,
        noise_amp=0.025, swing=0.08, pluck_kind="square", chorus_lift=1.10, lowpass=0.92,
    ),
    "ambient": StyleProfile(
        "ambient", 70, MINOR, "none",
        has_drums=False, bass_amp=0.05, pad_amp=0.24, lead_amp=0.025,
        vocal_amp=0.035, noise_amp=0.012, pluck_kind="sine", chorus_lift=1.05, lowpass=0.75,
    ),
    "acoustic": StyleProfile(
        "acoustic", 98, MAJOR, "soft_backbeat",
        bass_amp=0.15, pad_amp=0.06, lead_amp=0.16, vocal_amp=0.078,
        noise_amp=0.012, swing=0.04, pluck_kind="pluck", chorus_lift=1.18, lowpass=0.90,
    ),
    "lofi": StyleProfile(
        "lofi", 86, DORIAN, "soft_backbeat",
        bass_amp=0.18, pad_amp=0.14, lead_amp=0.08, vocal_amp=0.040,
        noise_amp=0.018, swing=0.06, pluck_kind="pluck", chorus_lift=1.08, lowpass=0.62,
    ),
    "cinematic": StyleProfile(
        "cinematic", 92, MINOR, "pulse",
        bass_amp=0.24, pad_amp=0.20, lead_amp=0.055, vocal_amp=0.040,
        noise_amp=0.018, pluck_kind="sine", chorus_lift=1.35,
    ),
    "pop": StyleProfile(
        "pop", 108, MAJOR, "pop",
        bass_amp=0.22, pad_amp=0.12, lead_amp=0.095, vocal_amp=0.095,
        noise_amp=0.025, pluck_kind="sine", chorus_lift=1.28,
    ),
    "default": StyleProfile(
        "default", 96, MINOR, "soft_backbeat",
        bass_amp=0.20, pad_amp=0.12, lead_amp=0.08, vocal_amp=0.060,
        noise_amp=0.018, pluck_kind="sine",
    ),
}

VOICE_PROFILES: dict[str, VoiceProfile] = {
    "female": VoiceProfile(
        "female", 1.95, 5.6, 0.018, 0.016, 0.88,
        (780.0, 1_250.0, 2_700.0, 3_280.0),
    ),
    "male": VoiceProfile(
        "male", 1.00, 4.7, 0.012, 0.010, 0.62,
        (620.0, 1_050.0, 2_400.0, 3_180.0),
    ),
    "choir": VoiceProfile(
        "choir", 1.55, 4.2, 0.010, 0.025, 0.72,
        (700.0, 1_150.0, 2_550.0, 3_220.0),
        blend_count=3,
    ),
    "robot": VoiceProfile(
        "robot", 1.28, 0.0, 0.000, 0.003, 0.95,
        (650.0, 1_300.0, 2_800.0, 3_500.0),
        quantized=True,
    ),
    "whisper": VoiceProfile(
        "whisper", 1.70, 5.0, 0.008, 0.110, 0.45,
        (760.0, 1_180.0, 2_500.0, 3_100.0),
    ),
}

VOWEL_FORMANT_SHIFTS: dict[str, tuple[float, float, float, float]] = {
    "a": (1.18, 1.10, 1.00, 1.00),
    "e": (0.76, 1.58, 1.06, 1.02),
    "i": (0.50, 1.88, 1.10, 1.04),
    "o": (0.80, 0.86, 0.90, 0.96),
    "u": (0.46, 0.70, 0.84, 0.92),
}

# Chord progressions per profile/section — indices into the scale list
CHORD_PROGRESSIONS: dict[str, dict[str, list[int]]] = {
    "disco": {
        "verse": [0, 3, 6, 2],
        "chorus": [0, 5, 3, 4],
        "build": [3, 5, 0, 4],
        "intro": [0, 0, 5, 4],
        "hook": [0, 3, 5, 4],
        "outro": [0, 5, 3, 0],
    },
    "club": {
        "verse": [0, 6, 4, 3],
        "chorus": [0, 3, 6, 4],
        "build": [0, 0, 6, 4],
        "intro": [0, 0, 0, 6],
        "hook": [0, 6, 3, 4],
        "outro": [0, 6, 3, 0],
    },
    "rap": {
        "verse": [0, 0, 2, 1],
        "chorus": [0, 2, 4, 3],
        "build": [0, 2, 4, 2],
        "intro": [0, 0, 0, 2],
        "hook": [0, 0, 2, 4],
        "outro": [0, 2, 0, 0],
    },
    "ambient": {
        "verse": [0, 2, 4, 5],
        "chorus": [0, 4, 2, 5],
        "build": [2, 4, 5, 4],
        "intro": [0, 0, 2, 0],
        "hook": [0, 2, 4, 0],
        "outro": [4, 2, 0, 0],
    },
    "acoustic": {
        "verse": [0, 4, 5, 3],
        "chorus": [0, 3, 4, 5],
        "build": [3, 4, 5, 4],
        "intro": [0, 4, 3, 4],
        "hook": [0, 3, 5, 4],
        "outro": [5, 3, 4, 0],
    },
    "lofi": {
        "verse": [0, 5, 3, 4],
        "chorus": [0, 3, 5, 4],
        "build": [0, 5, 3, 4],
        "intro": [0, 0, 5, 3],
        "hook": [0, 3, 5, 4],
        "outro": [5, 3, 0, 0],
    },
    "cinematic": {
        "verse": [0, 6, 3, 4],
        "chorus": [0, 3, 6, 4],
        "build": [3, 6, 0, 4],
        "intro": [0, 0, 6, 6],
        "hook": [0, 6, 3, 0],
        "outro": [0, 3, 6, 0],
    },
    "pop": {
        "verse": [0, 5, 3, 4],
        "chorus": [0, 5, 3, 4],
        "build": [3, 4, 5, 4],
        "intro": [0, 4, 5, 3],
        "hook": [0, 3, 5, 4],
        "outro": [5, 3, 4, 0],
    },
    "default": {
        "verse": [0, 5, 3, 4],
        "chorus": [0, 3, 5, 4],
        "build": [3, 5, 0, 4],
        "intro": [0, 0, 5, 4],
        "hook": [0, 3, 5, 4],
        "outro": [0, 5, 3, 0],
    },
}

# Melodic contour: scale-degree offsets from chord root (for lead + vocal)
MELODIC_CONTOURS: dict[str, list[int]] = {
    "verse":   [0, 1, 2, 1, 3, 2, 1, 0],
    "chorus":  [2, 3, 4, 3, 4, 5, 4, 3],
    "build":   [0, 2, 3, 4, 5, 4, 5, 6],
    "hook":    [4, 3, 2, 1, 2, 3, 4, 3],
    "intro":   [0, 1, 0, 1, 2, 1, 0, 1],
    "outro":   [3, 2, 1, 0, 1, 0, 0, 0],
}


def _osc(freq: float, t: float, kind: str = "sine") -> float:
    phase = 2 * math.pi * freq * t
    if kind == "square":
        return 1.0 if math.sin(phase) >= 0 else -1.0
    if kind == "saw":
        return 2.0 * ((freq * t) % 1.0) - 1.0
    if kind == "pluck":
        local = t % 0.75
        return math.sin(phase) * math.exp(-8.0 * local) + 0.35 * math.sin(phase * 2.01) * math.exp(-11.0 * local)
    return math.sin(phase)


def _env(x: float, attack: float = 0.02, release: float = 0.12) -> float:
    if x < attack:
        return x / max(attack, 0.0001)
    if x > 1.0 - release:
        return max(0.0, (1.0 - x) / max(release, 0.0001))
    return 1.0


def _chord_degree_idx(profile: StyleProfile, bar: int, section: str) -> int:
    progressions = CHORD_PROGRESSIONS.get(profile.name, CHORD_PROGRESSIONS["default"])
    prog = progressions.get(section, progressions.get("verse", [0, 5, 3, 4]))
    return prog[bar % len(prog)] % len(profile.scale)


def _chord_freq(profile: StyleProfile, root: float, bar: int, section: str) -> float:
    idx = _chord_degree_idx(profile, bar, section)
    degree = profile.scale[idx]
    return root * (2 ** (degree / 12))


def _melody_freq(profile: StyleProfile, root: float, bar: int, section: str, phrase_step: int, octave_mult: float = 2.0) -> float:
    chord_idx = _chord_degree_idx(profile, bar, section)
    contour = MELODIC_CONTOURS.get(section, MELODIC_CONTOURS["verse"])
    offset = contour[phrase_step % len(contour)]
    note_idx = (chord_idx + offset) % len(profile.scale)
    degree = profile.scale[note_idx]
    return root * octave_mult * (2 ** (degree / 12))


class ProceduralGenerator:
    name = "procedural-v3"
    label = "Procedural V3.4 Fallback"
    supports_lyrics = True
    supports_seed = True
    supports_duration = True
    description = "CPU-only stereo sketch with formant singing, harmonic chord progressions, and melodic contours."

    def info(self) -> GeneratorInfo:
        return GeneratorInfo(
            name=self.name,
            label=self.label,
            supports_lyrics=True,
            supports_seed=True,
            supports_duration=True,
            description=self.description,
            backend_type="fallback",
            status="ready",
        )

    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        positive_text = " ".join([
            request.prompt,
            " ".join(request.genre_tags),
            " ".join(request.mood_tags),
            request.vocal_style or "",
            request.mode,
            request.structure,
        ]).lower()
        negative_text = request.negative_prompt.lower()
        profile = self._profile(positive_text, request.mode, negative_text)
        quality = quality_for(request)
        rng = random.Random(request.seed if request.seed is not None else sum(ord(c) for c in request.prompt) % 2_147_483_647)
        duration = request.duration_seconds
        bpm = request.bpm or self._infer_bpm(positive_text, request.mode, profile)
        beat = 60.0 / bpm
        root = self._root_freq(request.key, request.prompt)
        sections = self._sections(duration, request.structure, profile.name)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        duration_beats = duration / beat
        lyric_events = build_lyric_timeline(request.lyrics, duration_beats)

        drums_enabled = profile.has_drums and request.mode != "instrumental"
        if profile.name in ("ambient",) or request.structure == "ambient_loop":
            drums_enabled = False
        if "no drums" in positive_text or "without drums" in positive_text:
            drums_enabled = False

        frames = bytearray()
        vocal_frames = bytearray() if quality.export_vocal_stem and lyric_events else None
        prev_l = prev_r = 0.0
        low_l = low_r = 0.0
        total_samples = int(SAMPLE_RATE * duration)
        motif_shift = rng.randrange(0, 2)

        for i in range(total_samples):
            t = i / SAMPLE_RATE
            beat_pos = t / beat
            bar = int(beat_pos // 4) + motif_shift
            section = self._section_at(t, sections)
            section_gain = profile.chorus_lift if section in ("chorus", "hook", "build") else 1.0
            if section == "intro":
                section_gain *= min(1.0, 0.35 + t / max(1.0, duration * 0.16))

            chord_freq = _chord_freq(profile, root, bar, section)

            bass = self._bass(profile, chord_freq, t, beat_pos, section_gain)
            pad = self._pad(profile, chord_freq, t, section_gain)
            lead = self._lead(profile, root, t, beat_pos, bar, section, section_gain)
            vocal = self._sung_voice(profile, request, lyric_events, root, t, beat_pos, bar, section)
            kick = hat = snare = perc = 0.0
            if drums_enabled:
                kick, hat, snare, perc = self._drums(profile, rng, t, beat_pos)

            sample = bass + pad + lead + vocal + kick + hat + snare + perc

            if profile.name == "lofi":
                wobble = 0.92 + 0.05 * math.sin(2 * math.pi * 0.38 * t) + 0.02 * math.sin(2 * math.pi * 0.13 * t)
                sample *= wobble
            if profile.name == "ambient":
                sample *= 0.82 + 0.18 * math.sin(2 * math.pi * 0.035 * t)
            if section == "outro":
                sample *= max(0.0, 1.0 - (t - sections[-1][0]) / max(1.0, duration - sections[-1][0]))

            sample = math.tanh(sample * quality.mix_drive) * 0.84
            pan = 0.16 * math.sin(2 * math.pi * (0.045 if profile.name == "ambient" else 0.07) * t)
            if profile.name in ("club", "disco") and section in ("chorus", "hook", "build"):
                pan += 0.08
            left = sample * (1 - pan * 0.42)
            right = sample * (1 + pan * 0.42)

            prev_l = 0.90 * prev_l + 0.10 * left
            prev_r = 0.90 * prev_r + 0.10 * right
            left = 0.86 * left + 0.14 * prev_l
            right = 0.86 * right + 0.14 * prev_r
            if profile.lowpass < 0.99:
                low_l = profile.lowpass * low_l + (1 - profile.lowpass) * left
                low_r = profile.lowpass * low_r + (1 - profile.lowpass) * right
                left = 0.65 * low_l + 0.35 * left
                right = 0.65 * low_r + 0.35 * right

            frames += int(max(-1, min(1, left)) * 32767).to_bytes(2, "little", signed=True)
            frames += int(max(-1, min(1, right)) * 32767).to_bytes(2, "little", signed=True)

            if vocal_frames is not None:
                v = math.tanh(vocal * 1.5) * 0.9
                vocal_frames += int(max(-1, min(1, v)) * 32767).to_bytes(2, "little", signed=True)
                vocal_frames += int(max(-1, min(1, v)) * 32767).to_bytes(2, "little", signed=True)

        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(bytes(frames))

        vocal_stem_name: str | None = None
        if vocal_frames is not None:
            stem_path = output_path.with_name(output_path.stem + "_vocal.wav")
            with wave.open(str(stem_path), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(SAMPLE_RATE)
                wav.writeframes(bytes(vocal_frames))
            vocal_stem_name = stem_path.name

        voice = self._voice(request, positive_text)
        metadata: dict = {
            "engine": "procedural-v3.4",
            "style_profile": profile.name,
            "lyrics_behavior": "formant_singing" if request.mode in ("song", "vocal_demo") and lyric_events else "none",
            "singing_voice": voice.name,
            "vocal_intensity": request.vocal_intensity,
            "bpm": bpm,
            "root_hz": round(root, 2),
            "channels": 2,
            "sections": sections,
            "drums_enabled": drums_enabled,
            "chord_system": "harmonic_progressions_v3.4",
            "lyric_events": len(lyric_events),
        }
        if vocal_stem_name:
            metadata["vocal_stem_file"] = vocal_stem_name
        return GenerationResult(
            file_name=output_path.name,
            duration_seconds=duration,
            sample_rate=SAMPLE_RATE,
            generator_name=self.name,
            metadata=metadata,
        )

    def _profile(self, text: str, mode: str, negative_text: str) -> StyleProfile:
        if "ambient" in text or (mode == "instrumental" and not any(k in text for k in ["cinematic", "trailer", "epic"])):
            return PROFILES["ambient"]
        if any(k in text for k in ["rap", "trap", "mixtape", "808", "hip hop", "hiphop"]):
            return PROFILES["rap"]
        if any(k in text for k in ["lofi", "lo-fi", "lo fi", "dusty", "tape wobble", "chillhop"]):
            return PROFILES["lofi"]
        if any(k in text for k in ["acoustic", "guitar", "indie", "folk", "singer-songwriter"]):
            return PROFILES["acoustic"]
        if any(k in text for k in ["club", "warehouse", "rave", "techno", "house", "edm"]):
            return PROFILES["club"]
        if any(k in text for k in ["disco", "dance", "french", "funky", "funk"]):
            return PROFILES["disco"]
        if any(k in text for k in ["cinematic", "trailer", "epic", "dramatic", "orchestral", "score"]):
            return PROFILES["cinematic"]
        if any(k in text for k in ["pop", "hook", "radio", "chart", "mainstream"]):
            return PROFILES["pop"]
        return PROFILES["default"]

    def _infer_bpm(self, text: str, mode: str, profile: StyleProfile) -> int:
        if any(k in text for k in ["slow", "ballad", "lullaby", "meditation"]):
            return min(profile.default_bpm, 78)
        if any(k in text for k in ["fast", "punk", "energetic", "upbeat"]):
            return max(profile.default_bpm, 138)
        if mode == "loop" and profile.name == "lofi":
            return 86
        return profile.default_bpm

    def _root_freq(self, key: str | None, prompt: str) -> float:
        notes = {
            "c": 261.63, "c#": 277.18, "db": 277.18, "d": 293.66,
            "eb": 311.13, "d#": 311.13, "e": 329.63, "f": 349.23,
            "f#": 369.99, "gb": 369.99, "g": 392.0, "g#": 415.3,
            "ab": 415.3, "a": 440.0, "bb": 466.16, "a#": 466.16, "b": 493.88,
        }
        if key:
            normalized = key.lower().replace("minor", "").replace("major", "").strip()
            if normalized in notes:
                return notes[normalized]
        base = [261.63, 293.66, 329.63, 349.23, 392.0, 440.0]
        return base[sum(ord(c) for c in prompt.lower()) % len(base)]

    def _sections(self, duration: int, structure: str, profile_name: str) -> list[tuple[float, str]]:
        if structure in ("hook_loop", "ambient_loop"):
            return [(0, "hook"), (duration * 0.78, "outro")]
        if structure == "intro_verse_chorus":
            return [(0, "intro"), (duration * 0.18, "verse"), (duration * 0.55, "chorus"), (duration * 0.86, "outro")]
        if structure == "club_build" or profile_name == "club":
            return [(0, "intro"), (duration * 0.30, "build"), (duration * 0.66, "chorus"), (duration * 0.9, "outro")]
        if profile_name == "ambient":
            return [(0, "intro"), (duration * 0.38, "build"), (duration * 0.82, "outro")]
        return [(0, "verse"), (duration * 0.50, "chorus"), (duration * 0.85, "outro")]

    def _section_at(self, t: float, sections: list[tuple[float, str]]) -> str:
        active = sections[0][1]
        for start, name in sections:
            if t >= start:
                active = name
        return active

    def _bass(self, profile: StyleProfile, chord_freq: float, t: float, beat_pos: float, section_gain: float) -> float:
        if profile.name == "rap":
            beat_gate = 1.0 if int(beat_pos * 2) % 4 in (0, 3) else 0.35
            pitch = chord_freq / 2 * (0.5 if int(beat_pos // 8) % 2 else 1.0)
            return profile.bass_amp * math.sin(2 * math.pi * pitch * t) * beat_gate
        if profile.name in ("disco", "club"):
            octave = 1.0 if int(beat_pos * 2) % 2 == 0 else 2.0
            pulse = 0.72 + 0.28 * math.sin(2 * math.pi * beat_pos)
            fifth = 1.0 if (int(beat_pos * 4) % 4 != 3) else 1.5
            return profile.bass_amp * math.sin(2 * math.pi * (chord_freq / 2) * octave * fifth * t) * pulse * section_gain
        if profile.name == "ambient":
            return profile.bass_amp * math.sin(2 * math.pi * (chord_freq / 4) * t)
        # Walking bass: root on beat 1, 5th on beat 3
        fifth_hit = int(beat_pos) % 4 == 2
        pitch = chord_freq / 2 * (1.5 if fifth_hit else 1.0)
        return profile.bass_amp * math.sin(2 * math.pi * pitch * t) * (0.75 + 0.25 * math.sin(2 * math.pi * beat_pos))

    def _pad(self, profile: StyleProfile, chord_freq: float, t: float, section_gain: float) -> float:
        slow = 0.7 + 0.3 * math.sin(2 * math.pi * 0.06 * t)
        if profile.name == "ambient":
            return profile.pad_amp * (
                _osc(chord_freq / 2, t, "sine") + 0.6 * _osc(chord_freq * 0.75, t, "sine") + 0.4 * _osc(chord_freq, t, "sine")
            ) * slow
        fifth_freq = chord_freq * 1.5
        return profile.pad_amp * (
            _osc(chord_freq, t, "sine") + _osc(fifth_freq, t, "sine") * 0.35 + _osc(chord_freq * 2, t, "sine") * 0.18
        ) * section_gain

    def _lead(self, profile: StyleProfile, root: float, t: float, beat_pos: float, bar: int, section: str, section_gain: float) -> float:
        if profile.name == "ambient":
            phrase_speed = 0.5
        elif profile.name == "rap":
            phrase_speed = 1.0
        elif profile.name in ("disco", "club"):
            phrase_speed = 4.0
        else:
            phrase_speed = 2.0
        phrase_step = int(beat_pos * phrase_speed)
        octave = 1.0 if profile.name in ("rap", "ambient") else 2.0
        freq = _melody_freq(profile, root, bar, section, phrase_step, octave)
        frac = (beat_pos * max(1.0, phrase_speed)) % 1
        if profile.name == "rap":
            return profile.lead_amp * _osc(freq * 0.5, t, "square") * _env(frac, 0.01, 0.42) * 0.55
        if profile.name == "ambient":
            return profile.lead_amp * _osc(freq, t, "sine") * (0.5 + 0.5 * math.sin(2 * math.pi * 0.04 * t))
        return profile.lead_amp * _osc(freq, t, profile.pluck_kind) * _env(frac, 0.01, 0.28) * section_gain

    def _voice(self, request: GenerationRequest, text: str) -> VoiceProfile:
        requested = request.singing_voice
        if requested == "auto":
            style = (request.vocal_style or "").lower() + " " + text
            if any(term in style for term in ["choir", "gang vocal", "group vocal", "harmony", "choral"]):
                requested = "choir"
            elif any(term in style for term in ["robot", "vocoder", "synth vocal", "talkbox", "autotune"]):
                requested = "robot"
            elif any(term in style for term in ["whisper", "breathy", "hushed", "airy"]):
                requested = "whisper"
            elif any(term in style for term in ["male", "baritone", "tenor", "bass voice"]):
                requested = "male"
            elif any(term in style for term in ["female", "soprano", "alto", "woman", "girl"]):
                requested = "female"
            else:
                requested = "female"
        return VOICE_PROFILES.get(requested, VOICE_PROFILES["female"])

    def _sung_voice(self, profile: StyleProfile, request: GenerationRequest, lyric_events: list, root: float, t: float, beat_pos: float, bar: int, section: str) -> float:
        if request.mode not in ("song", "vocal_demo") or not lyric_events or profile.vocal_amp <= 0 or request.vocal_intensity <= 0:
            return 0.0
        voice = self._voice(request, " ".join([request.prompt, request.vocal_style or ""]).lower())

        phrase_speed = 1.65 if profile.name != "rap" else 2.6
        phrase_pos = beat_pos * phrase_speed

        # Use lyric timeline for accurate word timing
        event = event_at(lyric_events, phrase_pos)
        if event is None:
            return 0.0
        word = event.word.lower()
        syllable_x = min(1.0, (phrase_pos - event.beat_start) / max(event.beat_duration, 0.001))
        word_idx = lyric_events.index(event)

        # Vocal melody: chord-aware contour, one step higher than lead
        contour = MELODIC_CONTOURS.get(section, MELODIC_CONTOURS["verse"])
        contour_step = int(phrase_pos * 2) % len(contour)
        chord_idx = _chord_degree_idx(profile, bar, section)
        note_idx = (chord_idx + contour[contour_step] + 2) % len(profile.scale)
        degree = profile.scale[note_idx]
        pitch = root * voice.base_multiplier * (2 ** (degree / 12))

        if voice.quantized:
            pitch = round(pitch / 18.0) * 18.0

        envelope = _env(syllable_x, 0.08 if voice.name != "whisper" else 0.16, 0.34)
        vowel = self._dominant_vowel(word)
        vowel_shift = VOWEL_FORMANT_SHIFTS[vowel]

        # Vibrato with natural onset delay
        vibrato_onset = min(1.0, syllable_x / 0.20)
        vibrato = voice.vibrato_depth * math.sin(2 * math.pi * voice.vibrato_rate * t) * vibrato_onset

        # Jitter: slow quasi-random pitch micro-variation for naturalness
        jitter = 0.0035 * math.sin(2 * math.pi * 8.3 * t + 0.31 * math.sin(2 * math.pi * 2.7 * t))

        voiced = 0.0
        for singer in range(voice.blend_count):
            detune = (singer - (voice.blend_count - 1) / 2) * 0.011
            singer_pitch = pitch * (1.0 + detune + vibrato + jitter)
            shimmer = 1.0 + 0.04 * math.sin(2 * math.pi * 6.1 * t + singer * 1.2)
            voiced += self._formant_tone(singer_pitch, t + singer * 0.003, voice, vowel_shift) * shimmer
        voiced /= voice.blend_count

        consonant = self._consonant_noise(word, syllable_x, t)
        breath_noise = voice.breath * (
            math.sin(2 * math.pi * 2_900 * t) * 0.5
            + math.sin(2 * math.pi * 4_100 * t) * 0.3
            + 0.2 * math.sin(2 * math.pi * 130 * t * math.sin(t * 3.1))
        )

        level = profile.vocal_amp * (0.40 + 1.20 * request.vocal_intensity)
        if request.mode == "vocal_demo":
            level *= 1.40
        if section in ("chorus", "hook"):
            level *= 1.22
        return level * envelope * (0.80 * voiced + breath_noise + consonant)

    def _dominant_vowel(self, word: str) -> str:
        for char in word:
            if char in VOWEL_FORMANT_SHIFTS:
                return char
        return "a"

    def _formant_tone(self, pitch: float, t: float, voice: VoiceProfile, vowel_shift: tuple[float, float, float, float]) -> float:
        tone = 0.0
        max_harmonics = min(22, int(NYQUIST / max(pitch, 1.0)))
        bandwidths = (F1_BW, F2_BW, F3_BW, F4_BW)

        for harmonic in range(1, max_harmonics + 1):
            freq = pitch * harmonic
            if freq >= NYQUIST:
                break

            # Sum of 4 Gaussian formant peaks
            formant_gain = 0.0
            for i, (formant, shift) in enumerate(zip(voice.formants, vowel_shift)):
                center = formant * shift
                bw = bandwidths[i]
                distance = (freq - center) / bw
                weight = 0.75 if i == 3 else 1.0  # F4 adds brilliance at lower weight
                formant_gain += weight * math.exp(-distance * distance * 0.5)

            # Spectral tilt: brightness controls harmonic rolloff
            tilt = 1.0 / (harmonic ** (1.1 - voice.brightness * 0.4))

            # Glottal source: odd harmonics stronger (modal/chest voice)
            source = 1.0 if harmonic % 2 == 1 else (0.55 + 0.45 * voice.brightness)

            tone += math.sin(2 * math.pi * freq * t) * tilt * source * (0.28 + formant_gain * 0.72)

        return math.tanh(tone * 0.48)

    def _consonant_noise(self, word: str, syllable_x: float, t: float) -> float:
        if syllable_x > 0.18 or not word:
            return 0.0
        c = word[0]
        if c not in "bcdfghjklmnpqrstvwxyz":
            return 0.0
        burst = math.exp(-syllable_x * 26.0)
        if c in "sfhzv":
            freq = 5_800 + (ord(c) % 1_200)
            return 0.018 * burst * math.sin(2 * math.pi * freq * t) * math.sin(2 * math.pi * freq * 1.37 * t)
        if c in "ptk":
            return 0.022 * burst * (math.sin(2 * math.pi * 2_800 * t) + 0.5 * math.sin(2 * math.pi * 4_200 * t))
        if c in "bdg":
            return 0.018 * burst * math.sin(2 * math.pi * (2_200 + ord(c) * 30) * t)
        if c in "mn":
            return 0.012 * burst * math.sin(2 * math.pi * (820 + ord(c) * 18) * t)
        return 0.014 * burst * math.sin(2 * math.pi * (4_000 + ord(c) % 1_000) * t)

    def _drums(self, profile: StyleProfile, rng: random.Random, t: float, beat_pos: float) -> tuple[float, float, float, float]:
        beat_frac = beat_pos % 1
        kick = hat = snare = perc = 0.0
        pat = profile.drum_pattern
        bar_beat = int(beat_pos) % 4
        velocity = 1.0 if bar_beat == 0 else (0.82 if bar_beat == 2 else 0.68)

        if pat == "four_floor":
            if beat_frac < 0.12:
                kick_body = math.sin(2 * math.pi * (52 + 90 * math.exp(-beat_frac * 24)) * t) * math.exp(-beat_frac * 14)
                kick_click = math.sin(2 * math.pi * 2_200 * t) * math.exp(-beat_frac * 80)
                kick = (0.55 * kick_body + 0.08 * kick_click) * velocity
            hat_step = int(beat_pos * 2) % 2
            if hat_step == 1:
                hat_vel = 0.90 if int(beat_pos * 4) % 4 == 2 else 0.60
                hat = (rng.random() * 2 - 1) * profile.noise_amp * hat_vel
            if int(beat_pos) % 4 in (1, 3) and beat_frac < 0.10:
                snare_body = (rng.random() * 2 - 1) * 0.06 * math.exp(-beat_frac * 22)
                snare_tone = math.sin(2 * math.pi * 280 * t) * math.exp(-beat_frac * 18) * 0.025
                snare = (snare_body + snare_tone) * velocity
            if int(beat_pos * 8) % 8 == 6 and beat_frac > 0.85:
                hat += (rng.random() * 2 - 1) * profile.noise_amp * 0.30

        elif pat == "half_time":
            half = int(beat_pos * 2) % 8
            if half in (0, 6) and beat_frac < 0.18:
                kick_body = math.sin(2 * math.pi * (44 + 68 * math.exp(-beat_frac * 20)) * t) * math.exp(-beat_frac * 9)
                kick = 0.62 * kick_body * velocity
            if int(beat_pos * 8) % 3 == 0:
                hat = (rng.random() * 2 - 1) * profile.noise_amp * 0.82
            if int(beat_pos) % 4 == 2 and beat_frac < 0.20:
                snare_noise = (rng.random() * 2 - 1) * 0.12 * math.exp(-beat_frac * 12)
                snare_crack = math.sin(2 * math.pi * 320 * t) * math.exp(-beat_frac * 25) * 0.035
                snare = (snare_noise + snare_crack) * velocity

        elif pat == "pulse":
            if int(beat_pos * 2) % 2 == 0 and beat_frac < 0.16:
                kick = 0.34 * math.sin(2 * math.pi * (50 + 55 * math.exp(-beat_frac * 10)) * t) * math.exp(-beat_frac * 7)
            if int(beat_pos * 4) % 8 == 7:
                perc = (rng.random() * 2 - 1) * profile.noise_amp * 0.55

        elif pat == "pop":
            if beat_frac < 0.11:
                kick_body = math.sin(2 * math.pi * (56 + 78 * math.exp(-beat_frac * 20)) * t) * math.exp(-beat_frac * 12)
                kick = 0.42 * kick_body * velocity
            if int(beat_pos) % 4 in (1, 3) and beat_frac < 0.16:
                snare = (rng.random() * 2 - 1) * 0.11 * math.exp(-beat_frac * 17) * velocity
                snare += math.sin(2 * math.pi * 300 * t) * math.exp(-beat_frac * 22) * 0.028
            hat_vel = 0.75 if int(beat_pos * 4) % 4 % 2 == 1 else 0.45
            if int(beat_pos * 4) % 2 == 1:
                hat = (rng.random() * 2 - 1) * profile.noise_amp * hat_vel

        elif pat == "soft_backbeat":
            if int(beat_pos) % 4 in (0, 2) and beat_frac < 0.10:
                kick = 0.25 * math.sin(2 * math.pi * (60 + 45 * math.exp(-beat_frac * 16)) * t) * math.exp(-beat_frac * 11)
            if int(beat_pos) % 4 in (1, 3) and beat_frac < 0.12:
                snare = (rng.random() * 2 - 1) * 0.055 * math.exp(-beat_frac * 15)
            if int(beat_pos * 2) % 2 == 1:
                hat = (rng.random() * 2 - 1) * profile.noise_amp * 0.42

        return kick, hat, snare, perc
