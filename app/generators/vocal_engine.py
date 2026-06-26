from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.models import GenerationRequest
from app.generators.lyrics_timeline import LyricEvent, build_lyric_timeline, event_at
from app.generators.quality_profile import QualityProfile


@dataclass(frozen=True)
class VoiceProfile:
    name: str
    base_multiplier: float
    vibrato_rate: float
    vibrato_depth: float
    breath: float
    brightness: float
    formants: tuple[float, float, float]
    blend_count: int = 1
    quantized: bool = False


VOICE_PROFILES: dict[str, VoiceProfile] = {
    "female": VoiceProfile("female", 1.95, 5.6, 0.020, 0.020, 0.85, (780, 1_250, 2_700)),
    "male": VoiceProfile("male", 1.00, 4.7, 0.014, 0.012, 0.62, (620, 1_050, 2_400)),
    "choir": VoiceProfile("choir", 1.55, 4.2, 0.012, 0.030, 0.70, (700, 1_150, 2_550), blend_count=3),
    "robot": VoiceProfile("robot", 1.28, 0.0, 0.000, 0.004, 0.92, (650, 1_300, 2_800), quantized=True),
    "whisper": VoiceProfile("whisper", 1.70, 5.0, 0.010, 0.095, 0.45, (760, 1_180, 2_500)),
}

VOWEL_FORMANT_SHIFTS: dict[str, tuple[float, float, float]] = {
    "a": (1.16, 1.10, 1.00),
    "e": (0.78, 1.55, 1.06),
    "i": (0.52, 1.85, 1.10),
    "o": (0.82, 0.88, 0.92),
    "u": (0.48, 0.72, 0.86),
}


def _env(x: float, attack: float = 0.02, release: float = 0.12) -> float:
    if x < attack:
        return x / max(attack, 0.0001)
    if x > 1.0 - release:
        return max(0.0, (1.0 - x) / max(release, 0.0001))
    return 1.0


def resolve_voice(request: GenerationRequest, text: str) -> VoiceProfile:
    requested = request.singing_voice
    if requested == "auto":
        style = (request.vocal_style or "").lower() + " " + text
        if any(term in style for term in ["choir", "gang vocal", "group vocal", "harmony"]):
            requested = "choir"
        elif any(term in style for term in ["robot", "vocoder", "synth vocal", "talkbox"]):
            requested = "robot"
        elif any(term in style for term in ["whisper", "breathy", "hushed"]):
            requested = "whisper"
        elif any(term in style for term in ["male", "baritone", "tenor"]):
            requested = "male"
        else:
            requested = "female"
    return VOICE_PROFILES[requested]


class VocalEngine:
    def __init__(
        self,
        request: GenerationRequest,
        profile_name: str,
        scale: list[int],
        root: float,
        duration_beats: float,
        phrase_speed: float,
        vocal_amp: float,
        quality: QualityProfile,
        positive_text: str,
    ) -> None:
        self.request = request
        self.profile_name = profile_name
        self.scale = scale
        self.root = root
        self.phrase_speed = phrase_speed
        self.vocal_amp = vocal_amp
        self.quality = quality
        self.voice = resolve_voice(request, positive_text)
        self.events = build_lyric_timeline(request.lyrics, duration_beats)
        self._reverb_buf: list[float] = []
        self._delay_buf: list[float] = []

    def enabled(self) -> bool:
        return (
            self.request.mode in ("song", "vocal_demo")
            and bool(self.events)
            and self.vocal_amp > 0
            and self.request.vocal_intensity > 0
        )

    def sample(self, t: float, beat_pos: float, bar: int, section: str, motif_shift: int) -> float:
        if not self.enabled():
            return 0.0
        event = event_at(self.events, beat_pos * self.phrase_speed)
        if event is None:
            return 0.0

        word = event.word.lower()
        syllable_x = (beat_pos * self.phrase_speed - event.beat_start) / max(event.beat_duration, 0.001)
        word_idx = self.events.index(event)
        note = self.scale[(word_idx + bar + motif_shift + (2 if section in ("chorus", "hook") else 0)) % len(self.scale)]
        octave = self.voice.base_multiplier * (0.82 if self.profile_name == "rap" else 1.0)
        pitch = self.root * octave * (2 ** (note / 12))
        if self.voice.quantized:
            pitch = round(pitch / 18.0) * 18.0

        envelope = _env(syllable_x, 0.08 if self.voice.name != "whisper" else 0.16, 0.34)
        vowel = _dominant_vowel(word)
        vowel_shift = VOWEL_FORMANT_SHIFTS[vowel]
        vibrato = self.voice.vibrato_depth * math.sin(2 * math.pi * self.voice.vibrato_rate * t)
        if syllable_x < 0.18:
            vibrato *= syllable_x / 0.18

        dry = self._tone_at_pitch(pitch, t, vowel_shift, vibrato)
        if section in ("chorus", "hook"):
            dry += 0.42 * self._tone_at_pitch(pitch * (2 ** (4 / 12)), t + 0.004, vowel_shift, vibrato * 0.7)
            dry += 0.28 * self._tone_at_pitch(pitch * (2 ** (7 / 12)), t + 0.008, vowel_shift, vibrato * 0.5)

        consonant = _consonant_noise(word, syllable_x, t)
        breath = self.voice.breath * math.sin(2 * math.pi * (2_900 + 130 * math.sin(t * 3.1)) * t)
        level = self.vocal_amp * (0.35 + 1.25 * self.request.vocal_intensity)
        if self.request.mode == "vocal_demo":
            level *= 1.35
        if section in ("chorus", "hook"):
            level *= 1.20

        dry_sample = level * envelope * (0.82 * dry + breath + consonant)
        wet = self._apply_vocal_fx(dry_sample, t)
        return dry_sample * (1.0 - self.quality.vocal_reverb - self.quality.vocal_delay_mix) + wet

    def _tone_at_pitch(self, pitch: float, t: float, vowel_shift: tuple[float, float, float], vibrato: float) -> float:
        voiced = 0.0
        for singer in range(self.voice.blend_count):
            detune = (singer - (self.voice.blend_count - 1) / 2) * 0.012
            singer_pitch = pitch * (1.0 + detune + vibrato)
            voiced += _formant_tone(singer_pitch, t + singer * 0.003, self.voice, vowel_shift, self.quality.harmonics)
        return voiced / self.voice.blend_count

    def _apply_vocal_fx(self, sample: float, t: float) -> float:
        self._reverb_buf.append(sample)
        if len(self._reverb_buf) > 4_410:
            self._reverb_buf.pop(0)
        reverb = sum(self._reverb_buf[-800:]) / 800 * self.quality.vocal_reverb

        delay_t = t - 0.18
        delay = 0.0
        if delay_t > 0:
            delay = sample * 0.55 * self.quality.vocal_delay_mix * math.sin(2 * math.pi * 3.2 * delay_t)
        return reverb + delay


def _dominant_vowel(word: str) -> str:
    for char in word:
        if char in VOWEL_FORMANT_SHIFTS:
            return char
    return "a"


def _formant_tone(pitch: float, t: float, voice: VoiceProfile, vowel_shift: tuple[float, float, float], harmonics: int) -> float:
    tone = 0.0
    for harmonic in range(1, harmonics + 1):
        freq = pitch * harmonic
        formant_gain = 0.0
        for formant, shift in zip(voice.formants, vowel_shift):
            distance = (freq - formant * shift) / 360.0
            formant_gain += math.exp(-distance * distance)
        harmonic_gain = (1.0 / harmonic) * (0.55 + voice.brightness * 0.45)
        tone += math.sin(2 * math.pi * freq * t) * harmonic_gain * (0.34 + formant_gain)
    return math.tanh(tone * 0.62)


def _consonant_noise(word: str, syllable_x: float, t: float) -> float:
    if syllable_x > 0.16 or not word:
        return 0.0
    if word[0] not in "bcdfghjklmnpqrstvwxyz":
        return 0.0
    burst = math.exp(-syllable_x * 26.0)
    return 0.020 * burst * math.sin(2 * math.pi * (4_500 + (ord(word[0]) % 900)) * t)
