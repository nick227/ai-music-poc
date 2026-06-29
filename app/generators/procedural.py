from __future__ import annotations

import math
import random
import re
import struct
import wave
from pathlib import Path

from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo
from app.generators.quality_profile import quality_for
from app.generators.vocal_plan import VocalPlan, build_vocal_plan, midi_to_hz, save_vocal_plan, syllable_at

SAMPLE_RATE = 44_100
NYQUIST = SAMPLE_RATE / 2

# Per-formant bandwidth constants (Hz) — narrower = more resonant peak
F1_BW = 85.0
F2_BW = 72.0
F3_BW = 155.0
F4_BW = 250.0  # "singing formant" cluster ~3.2kHz adds brilliance

LEAD_PORTAMENTO_SECONDS = 0.015

class StyleProfile:
    __slots__ = (
        "name", "default_bpm", "scale", "drum_pattern", "has_drums",
        "bass_amp", "pad_amp", "lead_amp", "vocal_amp", "noise_amp",
        "swing", "lead_kind", "bass_kind", "pad_kind", "chorus_lift", "lowpass",
    )

    def __init__(
        self, name: str, default_bpm: int, scale: list[int], drum_pattern: str,
        has_drums: bool = True, bass_amp: float = 0.22, pad_amp: float = 0.10,
        lead_amp: float = 0.08, vocal_amp: float = 0.065, noise_amp: float = 0.02,
        swing: float = 0.0, lead_kind: str = "sine", bass_kind: str = "sine",
        pad_kind: str = "sine", chorus_lift: float = 1.12, lowpass: float = 1.0,
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
        self.lead_kind = lead_kind
        self.bass_kind = bass_kind
        self.pad_kind = pad_kind
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

# Precomputed semitone frequency ratios — avoids per-sample 2**(x/12) exponentiation
_R_MAJ2 = 2 ** (2 / 12)   # major 2nd (≈1.122) — used for 9th chord (chord_freq * 2 * _R_MAJ2)
_R_MAJ3 = 2 ** (4 / 12)   # major 3rd (≈1.260)
_R_PERF4 = 2 ** (5 / 12)  # perfect 4th (≈1.335)
_R_PERF5 = 2 ** (7 / 12)  # perfect 5th (≈1.498)
_R_MAJ6 = 2 ** (9 / 12)   # major 6th (≈1.587)
_R_MIN7 = 2 ** (10 / 12)  # minor 7th (≈1.782)
_R_DET_UP = 2 ** (4 / 1200)   # +4 cents detune (≈1.00231) — pad chorus doubler
_R_DET_DN = 2 ** (-4 / 1200)  # -4 cents detune (≈0.99769) — pad chorus doubler

PROFILES: dict[str, StyleProfile] = {
    # lead_kind: funky pluck melody; bass_kind: sine (disco octave jumps); pad_kind: sine (strings)
    "disco": StyleProfile(
        "disco", 116, DORIAN, "four_floor",
        bass_amp=0.28, pad_amp=0.10, lead_amp=0.06, vocal_amp=0.090,
        noise_amp=0.035, lead_kind="pluck", bass_kind="sine", pad_kind="sine", chorus_lift=1.25,
    ),
    # lead_kind: saw (synth lead); bass_kind: saw (acid bass); pad_kind: saw (synth pad)
    "club": StyleProfile(
        "club", 124, MINOR, "four_floor",
        bass_amp=0.30, pad_amp=0.08, lead_amp=0.09, vocal_amp=0.075,
        noise_amp=0.04, lead_kind="saw", bass_kind="saw", pad_kind="saw", chorus_lift=1.30,
    ),
    # lead_kind: square (808-style); bass_kind: saw (punchy 808); pad_kind: sine (hi-hat pad)
    "rap": StyleProfile(
        "rap", 82, PENTATONIC_MINOR, "half_time",
        bass_amp=0.38, pad_amp=0.04, lead_amp=0.04, vocal_amp=0.072,
        noise_amp=0.025, swing=0.08, lead_kind="square", bass_kind="saw", pad_kind="sine",
        chorus_lift=1.10, lowpass=0.92,
    ),
    # all sine: smooth ambient drones
    "ambient": StyleProfile(
        "ambient", 70, MINOR, "none",
        has_drums=False, bass_amp=0.05, pad_amp=0.22, lead_amp=0.025,
        vocal_amp=0.055, noise_amp=0.012, lead_kind="sine", bass_kind="sine", pad_kind="sine",
        chorus_lift=1.05, lowpass=0.75,
    ),
    # lead_kind: pluck (guitar); bass_kind: pluck (acoustic bass); pad_kind: sine (open chords)
    "acoustic": StyleProfile(
        "acoustic", 98, MAJOR, "soft_backbeat",
        bass_amp=0.14, pad_amp=0.06, lead_amp=0.14, vocal_amp=0.11,
        noise_amp=0.012, swing=0.04, lead_kind="pluck", bass_kind="pluck", pad_kind="sine",
        chorus_lift=1.18, lowpass=0.90,
    ),
    # lead_kind: pluck (tape-warped piano); bass_kind: sine (round sub); pad_kind: sine (mellow keys)
    "lofi": StyleProfile(
        "lofi", 86, DORIAN, "soft_backbeat",
        bass_amp=0.17, pad_amp=0.12, lead_amp=0.07, vocal_amp=0.062,
        noise_amp=0.018, swing=0.06, lead_kind="pluck", bass_kind="sine", pad_kind="sine",
        chorus_lift=1.08, lowpass=0.62,
    ),
    # lead_kind: pluck (piano/strings); bass_kind: sine (cello-like); pad_kind: sine (orchestra swell)
    "cinematic": StyleProfile(
        "cinematic", 92, MINOR, "pulse",
        bass_amp=0.22, pad_amp=0.16, lead_amp=0.068, vocal_amp=0.065,
        noise_amp=0.018, lead_kind="pluck", bass_kind="sine", pad_kind="sine", chorus_lift=1.35,
    ),
    # lead_kind: sine (smooth); bass_kind: sine (punchy); pad_kind: sine (warm synth)
    "pop": StyleProfile(
        "pop", 108, MAJOR, "pop",
        bass_amp=0.20, pad_amp=0.10, lead_amp=0.085, vocal_amp=0.125,
        noise_amp=0.025, lead_kind="sine", bass_kind="sine", pad_kind="sine", chorus_lift=1.28,
    ),
    # all sine: balanced starter timbre
    "default": StyleProfile(
        "default", 96, MINOR, "soft_backbeat",
        bass_amp=0.18, pad_amp=0.10, lead_amp=0.075, vocal_amp=0.085,
        noise_amp=0.018, lead_kind="sine", bass_kind="sine", pad_kind="sine",
    ),
    # lead_kind: KS guitar; bass_kind: KS (acoustic upright feel); pad_kind: sine (open strums)
    "folk": StyleProfile(
        "folk", 92, MAJOR, "soft_backbeat",
        bass_amp=0.13, pad_amp=0.08, lead_amp=0.15, vocal_amp=0.11,
        noise_amp=0.014, swing=0.03, lead_kind="karplusstrong", bass_kind="karplusstrong",
        pad_kind="sine", chorus_lift=1.15, lowpass=0.92,
    ),
    # lead_kind: pluck (piano/sax feel); bass_kind: pluck (walking upright); pad_kind: sine (comping)
    "jazz": StyleProfile(
        "jazz", 112, DORIAN, "jazz",
        bass_amp=0.16, pad_amp=0.14, lead_amp=0.10, vocal_amp=0.09,
        noise_amp=0.016, swing=0.10, lead_kind="pluck", bass_kind="pluck", pad_kind="sine",
        chorus_lift=1.10, lowpass=0.88,
    ),
    # lead_kind: sine (smooth melody); bass_kind: sine (warm round sub); pad_kind: sine (lush keys)
    "rnb": StyleProfile(
        "rnb", 88, MINOR, "half_time",
        bass_amp=0.22, pad_amp=0.14, lead_amp=0.07, vocal_amp=0.14,
        noise_amp=0.022, swing=0.06, lead_kind="sine", bass_kind="sine", pad_kind="sine",
        chorus_lift=1.28, lowpass=0.95,
    ),
    # lead_kind: pluck (guitar skank); bass_kind: sine (roots reggae sub-bass); pad_kind: sine (organ)
    "reggae": StyleProfile(
        "reggae", 80, MAJOR, "reggae",
        bass_amp=0.28, pad_amp=0.10, lead_amp=0.06, vocal_amp=0.10,
        noise_amp=0.020, lead_kind="pluck", bass_kind="sine", pad_kind="sine",
        chorus_lift=1.12, lowpass=0.90,
    ),
    # lead_kind: square (distorted guitar); bass_kind: saw (growling bass); pad_kind: square (power chord)
    "metal": StyleProfile(
        "metal", 148, MINOR, "four_floor",
        bass_amp=0.30, pad_amp=0.08, lead_amp=0.14, vocal_amp=0.08,
        noise_amp=0.038, lead_kind="square", bass_kind="saw", pad_kind="square", chorus_lift=1.35,
    ),
    # lead_kind: pluck (nylon guitar); bass_kind: pluck (thumb bass); pad_kind: sine (soft comping)
    "bossa": StyleProfile(
        "bossa", 116, MAJOR, "bossa",
        bass_amp=0.14, pad_amp=0.12, lead_amp=0.09, vocal_amp=0.09,
        noise_amp=0.014, swing=0.06, lead_kind="pluck", bass_kind="pluck", pad_kind="sine",
        chorus_lift=1.12, lowpass=0.90,
    ),
    # lead_kind: sine (organ/piano); bass_kind: sine (deep organ bass); pad_kind: sine (choir swell)
    "gospel": StyleProfile(
        "gospel", 78, MAJOR, "pop",
        bass_amp=0.18, pad_amp=0.18, lead_amp=0.08, vocal_amp=0.16,
        noise_amp=0.022, lead_kind="sine", bass_kind="sine", pad_kind="sine", chorus_lift=1.32,
    ),
    # lead_kind: KS (Telecaster twang); bass_kind: KS (acoustic bass); pad_kind: sine (pedal steel feel)
    "country": StyleProfile(
        "country", 106, MAJOR, "country",
        bass_amp=0.16, pad_amp=0.08, lead_amp=0.15, vocal_amp=0.11,
        noise_amp=0.016, swing=0.04, lead_kind="karplusstrong", bass_kind="karplusstrong",
        pad_kind="sine", chorus_lift=1.20, lowpass=0.92,
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
    # profile-matched voices
    "crooner": VoiceProfile(
        # jazz/bossa: warm baritone, wide slow vibrato, low breath, darker formants
        "crooner", 1.12, 4.2, 0.022, 0.020, 0.55,
        (640.0, 1_080.0, 2_350.0, 3_100.0),
    ),
    "soul": VoiceProfile(
        # rnb/gospel: chest-belt female, strong vibrato, pushed F1 for power
        "soul", 1.88, 6.5, 0.026, 0.022, 0.92,
        (820.0, 1_300.0, 2_800.0, 3_380.0),
        blend_count=2,
    ),
    "natural": VoiceProfile(
        # folk/country/acoustic: breathy female, earthier formants, gentle vibrato
        "natural", 1.82, 5.2, 0.014, 0.028, 0.70,
        (750.0, 1_200.0, 2_520.0, 3_150.0),
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
        "bridge": [2, 4, 5, 3],
        "breakdown": [0, 0, 5, 5],
        "outro": [0, 5, 3, 0],
    },
    "club": {
        "verse": [0, 6, 4, 3],
        "chorus": [0, 3, 6, 4],
        "build": [0, 0, 6, 4],
        "intro": [0, 0, 0, 6],
        "hook": [0, 6, 3, 4],
        "bridge": [5, 6, 4, 0],
        "breakdown": [0, 0, 6, 6],
        "outro": [0, 6, 3, 0],
    },
    "rap": {
        "verse": [0, 0, 2, 1],
        "chorus": [0, 2, 4, 3],
        "build": [0, 2, 4, 2],
        "intro": [0, 0, 0, 2],
        "hook": [0, 0, 2, 4],
        "bridge": [2, 3, 4, 2],
        "outro": [0, 2, 0, 0],
    },
    "ambient": {
        "verse": [0, 2, 4, 5],
        "chorus": [0, 4, 2, 5],
        "build": [2, 4, 5, 4],
        "intro": [0, 0, 2, 0],
        "hook": [0, 2, 4, 0],
        "bridge": [4, 2, 5, 0],
        "outro": [4, 2, 0, 0],
    },
    "acoustic": {
        "verse": [0, 4, 5, 3],
        "chorus": [0, 3, 4, 5],
        "build": [3, 4, 5, 4],
        "intro": [0, 4, 3, 4],
        "hook": [0, 3, 5, 4],
        "bridge": [5, 3, 4, 0],
        "outro": [5, 3, 4, 0],
    },
    "lofi": {
        "verse": [0, 5, 3, 4],
        "chorus": [0, 3, 5, 4],
        "build": [0, 5, 3, 4],
        "intro": [0, 0, 5, 3],
        "hook": [0, 3, 5, 4],
        "bridge": [2, 5, 3, 0],
        "outro": [5, 3, 0, 0],
    },
    "cinematic": {
        "verse": [0, 6, 3, 4],
        "chorus": [0, 3, 6, 4],
        "build": [3, 6, 0, 4],
        "intro": [0, 0, 6, 6],
        "hook": [0, 6, 3, 0],
        "bridge": [5, 6, 4, 0],
        "outro": [0, 3, 6, 0],
    },
    "pop": {
        "verse": [0, 5, 3, 4],   # I-V-iii-IV (classic pop verse)
        "chorus": [0, 3, 4, 5],  # I-iii-IV-V (lift: walks up to V for energy)
        "build": [3, 4, 5, 4],
        "intro": [0, 4, 5, 3],
        "hook": [0, 3, 5, 4],
        "bridge": [5, 3, 4, 0],  # vi-IV-V-I — the Suno bridge (Am-F-G-C in C major)
        "outro": [5, 3, 4, 0],
    },
    "default": {
        "verse": [0, 5, 3, 4],
        "chorus": [0, 3, 5, 4],
        "build": [3, 5, 0, 4],
        "intro": [0, 0, 5, 4],
        "hook": [0, 3, 5, 4],
        "bridge": [3, 5, 4, 0],
        "breakdown": [0, 0, 3, 3],
        "outro": [0, 5, 3, 0],
    },
    "folk": {
        "verse": [0, 4, 5, 3],
        "chorus": [0, 3, 0, 4],
        "build": [3, 4, 5, 4],
        "intro": [0, 4, 3, 4],
        "hook": [0, 3, 4, 0],
        "bridge": [5, 3, 4, 0],
        "breakdown": [0, 0, 3, 3],
        "outro": [5, 3, 0, 0],
    },
    "jazz": {
        "verse": [0, 3, 5, 1],
        "chorus": [0, 5, 1, 4],
        "build": [1, 4, 5, 4],
        "intro": [0, 0, 1, 4],
        "hook": [0, 5, 3, 4],
        "bridge": [1, 4, 0, 5],
        "breakdown": [0, 0, 1, 1],
        "outro": [0, 5, 0, 0],
    },
    "rnb": {
        "verse": [0, 5, 3, 6],
        "chorus": [0, 3, 5, 4],
        "build": [3, 5, 6, 5],
        "intro": [0, 0, 5, 6],
        "hook": [0, 5, 3, 4],
        "bridge": [5, 3, 6, 0],
        "breakdown": [0, 0, 5, 5],
        "outro": [5, 3, 0, 0],
    },
    "reggae": {
        "verse": [0, 4, 3, 4],
        "chorus": [0, 3, 4, 3],
        "build": [3, 4, 5, 4],
        "intro": [0, 0, 4, 3],
        "hook": [0, 3, 4, 0],
        "bridge": [5, 3, 4, 0],
        "breakdown": [0, 0, 0, 4],
        "outro": [3, 4, 0, 0],
    },
    "metal": {
        "verse": [0, 6, 5, 6],
        "chorus": [0, 5, 3, 6],
        "build": [0, 0, 6, 5],
        "intro": [0, 0, 0, 6],
        "hook": [0, 5, 6, 0],
        "bridge": [3, 5, 6, 0],
        "breakdown": [0, 0, 6, 6],
        "outro": [0, 6, 0, 0],
    },
    "bossa": {
        "verse": [0, 2, 5, 1],
        "chorus": [0, 5, 1, 4],
        "build": [1, 4, 5, 4],
        "intro": [0, 2, 1, 4],
        "hook": [0, 5, 3, 4],
        "bridge": [1, 4, 0, 5],
        "breakdown": [0, 0, 2, 2],
        "outro": [0, 2, 0, 0],
    },
    "gospel": {
        "verse": [0, 3, 4, 0],
        "chorus": [0, 4, 3, 0],
        "build": [3, 0, 4, 0],
        "intro": [0, 3, 0, 4],
        "hook": [0, 3, 4, 0],
        "bridge": [3, 0, 4, 0],
        "breakdown": [0, 0, 3, 0],
        "outro": [3, 4, 0, 0],
    },
    "country": {
        "verse": [0, 4, 3, 4],
        "chorus": [0, 3, 4, 0],
        "build": [3, 4, 5, 4],
        "intro": [0, 4, 0, 4],
        "hook": [0, 3, 4, 0],
        "bridge": [5, 3, 4, 0],
        "breakdown": [0, 0, 3, 4],
        "outro": [3, 4, 0, 0],
    },
}

# Melodic contour: scale-degree offsets from chord root (for lead + vocal)
MELODIC_CONTOURS: dict[str, list[int]] = {
    "verse":   [0, 1, 2, 1, 3, 2, 1, 0],
    "chorus":  [2, 3, 4, 3, 4, 5, 4, 3],
    "build":   [0, 2, 3, 4, 5, 4, 5, 6],
    "hook":    [4, 3, 2, 1, 2, 3, 4, 3],
    "intro":   [0, 1, 0, 1, 2, 1, 0, 1],
    "bridge":    [0, 2, 1, 3, 2, 1, 0, 1],
    "bridge_b":  [4, 5, 4, 3, 4, 5, 3, 2],  # B-phrase: high register, descends to build tension for final chorus
    "breakdown": [0, 0, 1, 0, 0, 1, 0, 0],
    "outro":     [3, 2, 1, 0, 1, 0, 0, 0],
}


def _osc(freq: float, t: float, kind: str = "sine", note_period: float = 0.5) -> float:
    phase = 2 * math.pi * freq * t
    if kind == "square":
        return 1.0 if math.sin(phase) >= 0 else -1.0
    if kind == "saw":
        return 2.0 * ((freq * t) % 1.0) - 1.0
    if kind == "pluck":
        local = t % 0.75
        return math.sin(phase) * math.exp(-8.0 * local) + 0.35 * math.sin(phase * 2.01) * math.exp(-11.0 * local)
    if kind == "karplusstrong":
        # Karplus-Strong approximation: per-cycle exponential decay, harmonics decay faster
        # Uses note_period so decay resets on each new melody note
        local = t % note_period
        n_cyc = local * freq
        d0 = math.exp(-n_cyc * 0.022)
        if d0 < 0.002:
            return 0.0
        d1 = math.exp(-n_cyc * 0.040)
        d2 = math.exp(-n_cyc * 0.072)
        d3 = math.exp(-n_cyc * 0.115)
        return (
            math.sin(phase) * d0
            + math.sin(phase * 2.001) * 0.50 * d1
            + math.sin(phase * 2.997) * 0.25 * d2
            + math.sin(phase * 4.003) * 0.12 * d3
        )
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
    label = "Procedural V3.32 Fallback"
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
        # Mood-based scale override: "sad/dark/minor" → MINOR, "happy/bright/major" → MAJOR
        if any(k in positive_text for k in ["sad", "melancholic", "dark", "gloomy", "somber", "depressing", "tragic", "heartbreak"]) or "minor" in positive_text:
            if profile.scale != MINOR:
                profile = StyleProfile(
                    profile.name, profile.default_bpm, MINOR, profile.drum_pattern,
                    profile.has_drums, profile.bass_amp, profile.pad_amp, profile.lead_amp,
                    profile.vocal_amp, profile.noise_amp, profile.swing,
                    profile.lead_kind, profile.bass_kind, profile.pad_kind,
                    profile.chorus_lift, profile.lowpass,
                )
        elif any(k in positive_text for k in ["happy", "joyful", "cheerful", "uplifting", "bright", "positive", "sunshine", "celebration"]) or "major" in positive_text:
            if profile.scale != MAJOR:
                profile = StyleProfile(
                    profile.name, profile.default_bpm, MAJOR, profile.drum_pattern,
                    profile.has_drums, profile.bass_amp, profile.pad_amp, profile.lead_amp,
                    profile.vocal_amp, profile.noise_amp, profile.swing,
                    profile.lead_kind, profile.bass_kind, profile.pad_kind,
                    profile.chorus_lift, profile.lowpass,
                )
        profile = self._apply_instrumentation_hints(profile, positive_text)
        quality = quality_for(request)
        rng = random.Random(request.seed if request.seed is not None else sum(ord(c) for c in request.prompt) % 2_147_483_647)
        duration = request.duration_seconds
        bpm = request.bpm or self._infer_bpm(positive_text, request.mode, profile)
        beat = 60.0 / bpm
        root = self._root_freq(request.key, request.prompt)
        sections = self._sections(duration, request.structure, profile.name)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        duration_beats = duration / beat
        vocal_plan: VocalPlan | None = None
        if request.mode in ("song", "vocal_demo") and request.lyrics.strip():
            vocal_plan = build_vocal_plan(
                request.lyrics,
                bpm=bpm,
                key=request.key,
                duration_beats=duration_beats,
                scale=profile.scale,
                root_hz=root,
                profile_name=profile.name,
                melodic_contours=MELODIC_CONTOURS,
            )

        vocal_frames = bytearray() if quality.export_vocal_stem and vocal_plan and vocal_plan.syllable_count() else None
        voice_profile = self._voice(request, positive_text, profile)

        drums_enabled = profile.has_drums and request.mode != "instrumental"
        if profile.name in ("ambient",) or request.structure == "ambient_loop":
            drums_enabled = False
        if "no drums" in positive_text or "without drums" in positive_text:
            drums_enabled = False

        raw_l: list[float] = []
        raw_r: list[float] = []
        prev_l = prev_r = 0.0
        low_l = low_r = 0.0
        total_samples = int(SAMPLE_RATE * duration)
        motif_shift = rng.randrange(0, 2)
        _verse_motif = self._motif_notes(profile, root)

        # Pre-compute section time boundaries for use in arrangement logic
        _sec_bounds: dict[str, tuple[float, float]] = {}
        for _si, (_st, _sn) in enumerate(sections):
            _se = sections[_si + 1][0] if _si + 1 < len(sections) else float(duration)
            _sec_bounds[_sn] = (_st, _se)
        _intro_end = sections[1][0] if len(sections) > 1 else duration * 0.25
        _outro_start = sections[-1][0]

        # Presence boost state for pop/acoustic (high-shelf ~3kHz)
        _pres_lp_l = _pres_lp_r = 0.0
        _do_presence = profile.name in ("pop", "acoustic", "default")

        # Vocal reverb ring buffers (O(1) per sample)
        _voc_rev_len = int(0.038 * SAMPLE_RATE)
        _voc_del_len = int(0.175 * SAMPLE_RATE)
        _voc_rev_buf = [0.0] * _voc_rev_len
        _voc_del_buf = [0.0] * _voc_del_len
        _voc_rev_ptr = 0
        _voc_del_ptr = 0

        # ADT (automatic double tracking) — 20ms delay, chorus-only
        _adt_len = int(0.020 * SAMPLE_RATE)
        _adt_buf = [0.0] * _adt_len
        _adt_ptr = 0

        # Section change tracking for crash cymbal at chorus entry
        _prev_section = ""
        _section_changed_t = -999.0

        # Sidechain compressor: kick-triggered bass ducking (pumping/groove effect)
        _sc_env = 0.0
        _sc_coeff = 0.9994  # ~80ms half-life release at 44100 Hz
        _sc_depth = {"club": 0.42, "disco": 0.38, "pop": 0.22}.get(profile.name, 0.0)

        # Snare room reverb: 25ms comb filter gives natural room ambience
        _sr_len = int(0.025 * SAMPLE_RATE)
        _sr_buf = [0.0] * _sr_len
        _sr_ptr = 0

        # Pre-chorus snare fill zones: 16th-note roll in last 1.5 beats before chorus/hook
        _fill_zones: list[tuple[float, float]] = []
        for _fz_si in range(len(sections) - 1):
            _, _fz_sn = sections[_fz_si]
            _fz_nxt, _fz_nn = sections[_fz_si + 1]
            if _fz_nn in ("chorus", "hook") and _fz_sn not in ("chorus", "hook", "build"):
                _fill_zones.append((max(0.0, _fz_nxt - 1.5 * beat), _fz_nxt))

        # Formant cache: maps (int_pitch, vowel_shift, harmonics) → (freqs, gains)
        # Avoids recomputing 4×exp per harmonic on every sample — gains are stable within a note
        _formant_cache: dict = {}

        # Lead plate reverb: 50ms comb gives air and depth to the melody
        _lead_rev_len = int(0.050 * SAMPLE_RATE)
        _lead_rev_buf = [0.0] * _lead_rev_len
        _lead_rev_ptr = 0

        # Pad room reverb: 75ms gives the harmonic bed warmth and width
        _pad_rev_len = int(0.075 * SAMPLE_RATE)
        _pad_rev_buf = [0.0] * _pad_rev_len
        _pad_rev_ptr = 0
        _do_pad_rev = profile.name not in ("lofi",)

        for i in range(total_samples):
            t = i / SAMPLE_RATE
            beat_pos = t / beat
            bar = int(beat_pos // 4) + motif_shift
            section = self._section_at(t, sections)
            if section != _prev_section:
                _section_changed_t = t
                _prev_section = section

            # Per-section mix automation
            if section in ("chorus", "hook"):
                section_gain = profile.chorus_lift
                _voc_sect = 1.0        # chorus boost already in _sung_voice (+22%)
                _kick_sect = 1.18
                _rev_mult = 1.30
                _pan_depth = 0.22
            elif section == "build":
                _bst, _bnd = _sec_bounds.get("build", (t, t + 1.0))
                _bp = (t - _bst) / max(1.0, _bnd - _bst)   # 0→1 through build
                section_gain = profile.chorus_lift * (0.62 + 0.38 * _bp)
                _voc_sect = 0.88 + 0.20 * _bp
                _kick_sect = 0.90 + 0.38 * _bp
                _rev_mult = 1.05 + 0.20 * _bp
                _pan_depth = 0.16 + 0.06 * _bp
            elif section == "verse":
                section_gain = 1.0
                _voc_sect = 0.841      # verse vocal -1.5dB
                _kick_sect = 0.88
                _rev_mult = 0.82
                _pan_depth = 0.15
            elif section == "intro":
                _ramp = min(1.0, 0.35 + t / max(1.0, duration * 0.16))
                section_gain = _ramp
                _voc_sect = 0.75 * _ramp
                _kick_sect = 0.72 * _ramp
                _rev_mult = 0.70
                _pan_depth = 0.14
            elif section == "outro":
                _fade = max(0.0, 1.0 - (t - _outro_start) / max(1.0, float(duration) - _outro_start))
                section_gain = _fade
                _voc_sect = _fade * 0.9
                _kick_sect = _fade
                _rev_mult = 0.85 + 0.15 * _fade
                _pan_depth = 0.14
            elif section == "bridge":
                # Bridge: stripped-back, more reverb — creates space before the final chorus payoff
                section_gain = profile.chorus_lift * 0.72
                _voc_sect = 0.95
                _kick_sect = 0.62
                _rev_mult = 1.45
                _pan_depth = 0.18
            elif section == "breakdown":
                # EDM breakdown: only pad + hihat survive; kick/bass/lead silenced below
                section_gain = 0.28
                _voc_sect = 0.0
                _kick_sect = 0.0
                _rev_mult = 1.90
                _pan_depth = 0.22
            else:  # hook or unrecognized
                section_gain = 1.0
                _voc_sect = 1.0
                _kick_sect = 1.0
                _rev_mult = 1.0
                _pan_depth = 0.16

            chord_freq = _chord_freq(profile, root, bar, section)

            bass = self._bass(profile, chord_freq, t, beat_pos, section_gain, beat)
            # Sub-bass layer in chorus for club/disco: deep sine at 2 octaves below root
            if profile.name in ("disco", "club") and section in ("chorus", "hook"):
                bass += profile.bass_amp * 0.32 * math.sin(2 * math.pi * (chord_freq / 4) * t) * section_gain
            pad = self._pad(profile, chord_freq, t, section_gain, section)
            if _do_pad_rev and pad != 0.0:
                _pr_out = _pad_rev_buf[_pad_rev_ptr]
                _pad_rev_buf[_pad_rev_ptr] = pad * 0.40 + _pr_out * 0.48
                _pad_rev_ptr = (_pad_rev_ptr + 1) % _pad_rev_len
                pad += _pr_out * 0.14
            lead = self._lead(profile, root, t, beat_pos, bar, section, section_gain, beat, _verse_motif)
            if lead != 0.0 and profile.name not in ("ambient", "lofi"):
                _lr_out = _lead_rev_buf[_lead_rev_ptr]
                _lead_rev_buf[_lead_rev_ptr] = lead * 0.45 + _lr_out * 0.35
                _lead_rev_ptr = (_lead_rev_ptr + 1) % _lead_rev_len
                lead += _lr_out * 0.22
            vocal = self._sung_voice(profile, request, vocal_plan, voice_profile, root, t, beat_pos, bar, section, quality.harmonics, _formant_cache)
            if vocal != 0.0:
                vocal *= _voc_sect
                if quality.vocal_reverb > 0:
                    _rev_out = _voc_rev_buf[_voc_rev_ptr]
                    _voc_rev_buf[_voc_rev_ptr] = vocal * 0.55 + _rev_out * 0.38
                    _voc_rev_ptr = (_voc_rev_ptr + 1) % _voc_rev_len
                    _del_out = _voc_del_buf[_voc_del_ptr]
                    _voc_del_buf[_voc_del_ptr] = vocal * 0.40 + _del_out * 0.32
                    _voc_del_ptr = (_voc_del_ptr + 1) % _voc_del_len
                    vocal = vocal + _rev_out * quality.vocal_reverb * _rev_mult + _del_out * quality.vocal_delay_mix
            _adt_out = _adt_buf[_adt_ptr]
            _adt_buf[_adt_ptr] = vocal
            _adt_ptr = (_adt_ptr + 1) % _adt_len
            if section in ("chorus", "hook") and _adt_out != 0.0:
                vocal += _adt_out * 0.48
            kick = hat = snare = perc = 0.0
            if drums_enabled:
                kick, hat, snare, perc = self._drums(profile, rng, t, beat_pos, section)
                kick *= _kick_sect
                if quality.drum_sub_layer and kick != 0.0:
                    _bf = beat_pos % 1
                    kick += 0.22 * math.sin(2 * math.pi * 50 * t) * math.exp(-_bf * 10) * _kick_sect

            # Intro: stagger instrument entry for dramatic buildup
            if section == "intro" and drums_enabled:
                _ip = t / max(1.0, _intro_end)
                if _ip < 0.20:
                    pad = lead = vocal = 0.0
                    hat *= 0.35; snare *= 0.25
                elif _ip < 0.46:
                    lead = vocal = 0.0
                    pad *= max(0.0, (_ip - 0.20) / 0.12)
                elif _ip < 0.70:
                    vocal = 0.0
                    lead *= max(0.0, (_ip - 0.46) / 0.24)
                elif _ip < 0.88:
                    vocal *= max(0.0, (_ip - 0.70) / 0.18)

            # EDM breakdown: kill kick/bass/lead; keep pad + hihat for tension
            elif section == "breakdown":
                bass = kick = lead = vocal = 0.0
                snare *= 0.12
                hat *= 0.60

            # Outro: mirror breakdown — instruments drop out in reverse order
            elif section == "outro":
                _op = (t - _outro_start) / max(1.0, float(duration) - _outro_start)
                if _op > 0.80:
                    lead = vocal = 0.0
                    hat *= max(0.0, 1.0 - (_op - 0.80) / 0.20)
                    snare *= max(0.0, 1.0 - (_op - 0.80) / 0.20)
                    pad *= max(0.0, 1.0 - (_op - 0.80) / 0.20)
                elif _op > 0.58:
                    vocal = 0.0
                    lead *= max(0.0, 1.0 - (_op - 0.58) / 0.22)
                elif _op > 0.38:
                    vocal *= max(0.0, 1.0 - (_op - 0.38) / 0.20)

            # Ghost notes: quiet snare on off-beats for funk/groove feel (verse/build only)
            if drums_enabled and section in ("verse", "build") and profile.name in ("pop", "disco", "club", "acoustic", "default"):
                _g16 = beat_pos * 4
                if int(_g16) % 4 not in (0,) and _g16 % 1 < 0.09 and int(beat_pos) % 4 not in (1, 3):
                    snare += (rng.random() * 2 - 1) * 0.016 * math.exp(-(_g16 % 1) * 22)

            # Sidechain: kick-triggered bass ducking for rhythmic groove
            if _sc_depth > 0.0:
                if kick != 0.0:
                    _sc_env = 1.0
                _sc_env *= _sc_coeff
                bass *= (1.0 - _sc_env * _sc_depth)

            # Pre-chorus snare fill: 16th-note roll in last 1.5 beats before chorus/hook
            if drums_enabled and _fill_zones:
                for _fz_s, _fz_e in _fill_zones:
                    if _fz_s <= t < _fz_e:
                        if (beat_pos * 4) % 1 < 0.14:
                            _fz_frac = (t - _fz_s) / (_fz_e - _fz_s)
                            snare += (rng.random() * 2 - 1) * (0.04 + 0.05 * _fz_frac)
                        break

            # Snare room reverb: 25ms comb for natural ambience
            _sr_out = _sr_buf[_sr_ptr]
            _sr_buf[_sr_ptr] = snare * 0.50 + _sr_out * 0.40
            _sr_ptr = (_sr_ptr + 1) % _sr_len
            snare = snare + _sr_out * 0.32

            # Crash cymbal at chorus/hook entry (first beat, 1.2s slow decay)
            if drums_enabled and section in ("chorus", "hook") and t - _section_changed_t < 1.2:
                perc += (rng.random() * 2 - 1) * profile.noise_amp * 1.8 * math.exp(-(t - _section_changed_t) * 1.8)

            sample = bass + pad + lead + vocal + kick + hat + snare + perc

            if profile.name == "lofi":
                wobble = 0.92 + 0.05 * math.sin(2 * math.pi * 0.38 * t) + 0.02 * math.sin(2 * math.pi * 0.13 * t)
                sample *= wobble
            if profile.name == "ambient":
                sample *= 0.82 + 0.18 * math.sin(2 * math.pi * 0.035 * t)
            if section == "outro":
                _op2 = (t - _outro_start) / max(1.0, float(duration) - _outro_start)
                sample *= max(0.0, 1.0 - _op2 * 0.55)  # gentle overall fade; per-instrument dropout above handles drama

            sample = math.tanh(sample * quality.mix_drive) * 0.84
            # Per-instrument stereo placement: pad sits left, lead sits right, hat/perc left
            # Offset is derived from pre-tanh instrument levels so it tracks content, not clipping
            _ster = pad * 0.30 - lead * 0.22 + (hat + perc) * 0.15
            pan_lfo = _pan_depth * math.sin(2 * math.pi * (0.045 if profile.name == "ambient" else 0.07) * t)
            if profile.name in ("club", "disco") and section in ("chorus", "hook", "build"):
                pan_lfo += 0.08
            left = sample * (1.0 - pan_lfo * 0.42) - _ster
            right = sample * (1.0 + pan_lfo * 0.42) + _ster

            prev_l = 0.90 * prev_l + 0.10 * left
            prev_r = 0.90 * prev_r + 0.10 * right
            left = 0.86 * left + 0.14 * prev_l
            right = 0.86 * right + 0.14 * prev_r

            # Presence boost for pop/acoustic: gentle high-shelf at ~3kHz
            if _do_presence:
                _pres_lp_l = _pres_lp_l * 0.875 + left * 0.125
                _pres_lp_r = _pres_lp_r * 0.875 + right * 0.125
                left = left + (left - _pres_lp_l) * 0.14
                right = right + (right - _pres_lp_r) * 0.14

            if profile.lowpass < 0.99:
                low_l = profile.lowpass * low_l + (1 - profile.lowpass) * left
                low_r = profile.lowpass * low_r + (1 - profile.lowpass) * right
                left = 0.65 * low_l + 0.35 * left
                right = 0.65 * low_r + 0.35 * right

            raw_l.append(left)
            raw_r.append(right)

            if vocal_frames is not None:
                v = math.tanh(vocal * 1.5) * 0.9
                v = max(-1.0, min(1.0, v))
                vocal_frames += int(v * 32767).to_bytes(2, "little", signed=True)
                vocal_frames += int(v * 32767).to_bytes(2, "little", signed=True)

        frames = self._master(raw_l, raw_r, quality)

        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(bytes(frames))

        vocal_stem_name: str | None = None
        vocal_plan_name: str | None = None
        if vocal_frames is not None:
            stem_path = output_path.with_name(output_path.stem + "_vocal.wav")
            with wave.open(str(stem_path), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(SAMPLE_RATE)
                wav.writeframes(bytes(vocal_frames))
            vocal_stem_name = stem_path.name
        if vocal_plan is not None and vocal_plan.syllable_count():
            plan_path = output_path.with_name(output_path.stem + "_vocal_plan.json")
            save_vocal_plan(vocal_plan, plan_path)
            vocal_plan_name = plan_path.name

        voice = self._voice(request, positive_text)
        syllable_count = vocal_plan.syllable_count() if vocal_plan else 0
        metadata: dict = {
            "engine": "procedural-v3.32",
            "style_profile": profile.name,
            "lyrics_behavior": "formant_singing" if request.mode in ("song", "vocal_demo") and syllable_count else "none",
            "singing_voice": voice.name,
            "vocal_intensity": request.vocal_intensity,
            "bpm": bpm,
            "key": request.key,
            "root_hz": round(root, 2),
            "channels": 2,
            "sections": sections,
            "drums_enabled": drums_enabled,
            "chord_system": "harmonic_progressions_v3.4",
            "syllable_events": syllable_count,
            "lyric_events": syllable_count,
        }
        if vocal_stem_name:
            metadata["vocal_stem_file"] = vocal_stem_name
        if vocal_plan_name:
            metadata["vocal_plan_file"] = vocal_plan_name
        return GenerationResult(
            file_name=output_path.name,
            duration_seconds=duration,
            sample_rate=SAMPLE_RATE,
            generator_name=self.name,
            metadata=metadata,
        )

    def _master(self, raw_l: list[float], raw_r: list[float], quality: QualityProfile) -> bytearray:
        """Post-generation mastering: high-pass mud cut, stereo widen, normalize, soft limit."""
        n = len(raw_l)

        # High-pass filter at ~40Hz — remove sub-bass mud (RC HP: a = RC/(RC+dt))
        _a = 0.9944
        pl = pr = xl = xr = 0.0
        for i in range(n):
            nl = _a * (pl + raw_l[i] - xl)
            nr = _a * (pr + raw_r[i] - xr)
            xl, xr = raw_l[i], raw_r[i]
            pl, pr = nl, nr
            raw_l[i] = nl
            raw_r[i] = nr

        # Presence boost: high-shelf +2.5dB above ~3kHz (LP coeff 0.65 → cutoff ≈3kHz)
        _sh_c = 0.65
        _sh_g = 0.35
        _sh_l = _sh_r = 0.0
        for i in range(n):
            _sh_l = _sh_l * _sh_c + raw_l[i] * (1.0 - _sh_c)
            _sh_r = _sh_r * _sh_c + raw_r[i] * (1.0 - _sh_c)
            raw_l[i] += (raw_l[i] - _sh_l) * _sh_g
            raw_r[i] += (raw_r[i] - _sh_r) * _sh_g

        # Stereo M/S widening: more width at higher quality
        width = 1.0 + quality.reverb_mix * 0.85  # 1.05 draft → 1.15 high
        for i in range(n):
            mid = (raw_l[i] + raw_r[i]) * 0.5
            side = (raw_l[i] - raw_r[i]) * 0.5 * width
            raw_l[i] = mid + side
            raw_r[i] = mid - side

        # Normalize to -6dBFS before compression to give compressor consistent input
        peak = max((max(abs(raw_l[i]), abs(raw_r[i])) for i in range(n)), default=0.001)
        if peak > 0.001:
            gain = min(0.50 / peak, 2.0)   # target -6dBFS, max +6dB boost
            # 3:1 compressor: threshold -6dBFS (0.50), attack 10ms, release 120ms
            _c_thr = 0.50
            _c_atk = 0.9977   # 1 - exp(-1/(0.010*44100))
            _c_rel = 0.9998   # 1 - exp(-1/(0.120*44100))
            _c_env = 0.0
            _lim_thr = 0.85
            _lim_inv = 1.0 / _lim_thr
            for i in range(n):
                l = raw_l[i] * gain
                r = raw_r[i] * gain
                level = l if l > -l else -l
                r_abs = r if r > -r else -r
                if r_abs > level:
                    level = r_abs
                # Envelope follower (one-pole IIR)
                if level > _c_env:
                    _c_env = _c_atk * _c_env + (1.0 - _c_atk) * level
                else:
                    _c_env = _c_rel * _c_env + (1.0 - _c_rel) * level
                # Gain reduction: 3:1 above threshold
                if _c_env > _c_thr:
                    gr = 1.0 / (1.0 + (_c_env / _c_thr - 1.0) * (2.0 / 3.0))
                else:
                    gr = 1.0
                l *= gr
                r *= gr
                # Soft limiter at -1.5dBFS
                if l > _lim_thr:
                    l = math.tanh(l * _lim_inv) * _lim_thr
                elif l < -_lim_thr:
                    l = math.tanh(l * _lim_inv) * _lim_thr
                if r > _lim_thr:
                    r = math.tanh(r * _lim_inv) * _lim_thr
                elif r < -_lim_thr:
                    r = math.tanh(r * _lim_inv) * _lim_thr
                raw_l[i] = l
                raw_r[i] = r

        # Encode to 16-bit stereo PCM
        CHUNK = 4096
        out = bytearray(n * 4)
        for start in range(0, n, CHUNK):
            end = min(start + CHUNK, n)
            chunk: list[int] = []
            for i in range(start, end):
                chunk.append(int(max(-32767.0, min(32767.0, raw_l[i] * 32767.0))))
                chunk.append(int(max(-32767.0, min(32767.0, raw_r[i] * 32767.0))))
            struct.pack_into(f"<{len(chunk)}h", out, start * 4, *chunk)
        return out

    def _profile(self, text: str, mode: str, negative_text: str) -> StyleProfile:
        if any(k in text for k in ["rap", "trap", "mixtape", "808", "hip hop", "hiphop"]):
            return PROFILES["rap"]
        if any(k in text for k in ["lofi", "lo-fi", "lo fi", "dusty", "tape wobble", "chillhop"]):
            return PROFILES["lofi"]
        if any(k in text for k in ["reggae", "dub", "ska", "dancehall", "jamaican", "ragga"]):
            return PROFILES["reggae"]
        if any(k in text for k in ["bossa nova", "bossanova", "bossa", "samba", "latin jazz", "brazilian"]):
            return PROFILES["bossa"]
        if any(k in text for k in ["jazz", "bebop", "swing jazz", "big band", "smooth jazz", "jazz club"]):
            return PROFILES["jazz"]
        if any(k in text for k in ["gospel", "hymn", "spiritual", "praise", "worship", "church"]):
            return PROFILES["gospel"]
        if any(k in text for k in ["r&b", "rnb", "neo-soul", "neo soul", "soul music", "motown", "contemporary r&b"]):
            return PROFILES["rnb"]
        if any(k in text for k in ["metal", "heavy metal", "hard rock", "thrash", "punk", "grunge", "hardcore", "death metal"]):
            return PROFILES["metal"]
        if any(k in text for k in ["country", "western", "country pop", "twang", "bluegrass", "nashville", "southern rock"]):
            return PROFILES["country"]
        if any(k in text for k in ["folk", "singer-songwriter", "celtic", "americana", "folk rock"]):
            return PROFILES["folk"]
        if any(k in text for k in ["acoustic", "guitar", "indie", "unplugged"]):
            return PROFILES["acoustic"]
        if any(k in text for k in ["club", "warehouse", "rave", "techno", "house", "edm", "electro", "synthwave"]):
            return PROFILES["club"]
        if any(k in text for k in ["disco", "dance", "french", "funky", "funk"]):
            return PROFILES["disco"]
        if any(k in text for k in ["cinematic", "trailer", "epic", "dramatic", "orchestral", "score"]):
            return PROFILES["cinematic"]
        if any(k in text for k in ["pop", "hook", "radio", "chart", "mainstream"]):
            return PROFILES["pop"]
        if "ambient" in text or (mode == "instrumental" and not any(k in text for k in ["cinematic", "trailer", "epic"])):
            return PROFILES["ambient"]
        return PROFILES["default"]

    def _apply_instrumentation_hints(self, profile: StyleProfile, text: str) -> StyleProfile:
        bass_amp = profile.bass_amp
        pad_amp = profile.pad_amp
        lead_amp = profile.lead_amp
        vocal_amp = profile.vocal_amp
        noise_amp = profile.noise_amp
        has_drums = profile.has_drums
        lead_kind = profile.lead_kind

        if any(k in text for k in ["solo piano", "piano only", "piano piece", "piano solo"]):
            pad_amp = max(pad_amp, 0.22)
            bass_amp = 0.0
            lead_amp = 0.0
            vocal_amp = 0.0
            has_drums = False
            lead_kind = "pluck"
        elif any(k in text for k in ["no bass", "without bass", "bass-free"]):
            bass_amp = 0.0
        if any(k in text for k in ["no lead", "no melody", "no melodic"]):
            lead_amp = 0.0
        if any(k in text for k in ["sparse", "minimal", "stripped", "stripped back", "stripped-back", "bare"]):
            bass_amp *= 0.65
            pad_amp *= 0.70
            lead_amp *= 0.65
            vocal_amp *= 0.75
            noise_amp *= 0.50
        if any(k in text for k in ["lush", "full", "orchestral", "rich", "dense", "layered", "wall of sound"]):
            pad_amp = min(pad_amp * 1.35, 0.40)
            lead_amp = min(lead_amp * 1.20, 0.30)
            bass_amp = min(bass_amp * 1.15, 0.35)
        if any(k in text for k in ["a cappella", "acappella", "vocals only", "voice only", "choir only"]):
            bass_amp = 0.0
            lead_amp = 0.0
            has_drums = False
            pad_amp = 0.0
            vocal_amp = min(vocal_amp * 1.60, 0.30)

        if (bass_amp == profile.bass_amp and pad_amp == profile.pad_amp
                and lead_amp == profile.lead_amp and vocal_amp == profile.vocal_amp
                and noise_amp == profile.noise_amp and has_drums == profile.has_drums
                and lead_kind == profile.lead_kind):
            return profile

        return StyleProfile(
            profile.name, profile.default_bpm, profile.scale, profile.drum_pattern,
            has_drums, bass_amp, pad_amp, lead_amp, vocal_amp, noise_amp,
            profile.swing, lead_kind, profile.bass_kind, profile.pad_kind,
            profile.chorus_lift, profile.lowpass,
        )

    def _infer_bpm(self, text: str, mode: str, profile: StyleProfile) -> int:
        if any(k in text for k in ["slow", "ballad", "lullaby", "meditation", "chill", "mellow", "dreamy", "relaxed", "calm", "gentle"]):
            return min(profile.default_bpm, 78)
        if any(k in text for k in ["fast", "punk", "energetic", "upbeat", "dance", "banger", "rave", "hyped", "rapid", "frantic", "intense"]):
            return min(max(profile.default_bpm, 120), 160)
        if any(k in text for k in ["groove", "funk", "soul", "r&b", "rnb", "smooth"]):
            return min(max(profile.default_bpm, 96), 114)
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
        # Detect key from prompt: "in C", "key of D", "C minor", "A major"
        text = prompt.lower()
        m = re.search(r'\b(?:in|key\s+of)\s+([a-g][b#]?)\b', text)
        if not m:
            m = re.search(r'\b([a-g][b#]?)\s+(?:major|minor|key)\b', text)
        if m:
            note = m.group(1)
            if note in notes:
                return notes[note]
        base = [261.63, 293.66, 329.63, 349.23, 392.0, 440.0]
        return base[sum(ord(c) for c in prompt.lower()) % len(base)]

    def _sections(self, duration: int, structure: str, profile_name: str) -> list[tuple[float, str]]:
        if structure in ("hook_loop", "ambient_loop"):
            return [(0, "hook"), (duration * 0.78, "outro")]
        if structure == "intro_verse_chorus":
            return [
                (0, "intro"), (duration * 0.18, "verse"), (duration * 0.48, "chorus"),
                (duration * 0.65, "bridge"), (duration * 0.78, "chorus"), (duration * 0.90, "outro"),
            ]
        if structure == "club_build" or profile_name == "club":
            return [
                (0, "intro"), (duration * 0.25, "build"),
                (duration * 0.52, "chorus"), (duration * 0.70, "breakdown"),
                (duration * 0.82, "chorus"), (duration * 0.93, "outro"),
            ]
        if profile_name == "ambient":
            return [(0, "intro"), (duration * 0.38, "build"), (duration * 0.82, "outro")]
        return [
            (0, "verse"), (duration * 0.40, "chorus"),
            (duration * 0.60, "bridge"), (duration * 0.75, "chorus"), (duration * 0.88, "outro"),
        ]

    def _section_at(self, t: float, sections: list[tuple[float, str]]) -> str:
        active = sections[0][1]
        for start, name in sections:
            if t >= start:
                active = name
        return active

    def _bass(self, profile: StyleProfile, chord_freq: float, t: float, beat_pos: float, section_gain: float, beat: float = 0.5) -> float:
        bk = profile.bass_kind
        if profile.name == "rap":
            beat_gate = 1.0 if int(beat_pos * 2) % 4 in (0, 3) else 0.35
            pitch = chord_freq / 2 * (0.5 if int(beat_pos // 8) % 2 else 1.0)
            return profile.bass_amp * _osc(pitch, t, bk, beat) * beat_gate
        if profile.name in ("disco", "club"):
            octave = 1.0 if int(beat_pos * 2) % 2 == 0 else 2.0
            pulse = 0.72 + 0.28 * math.sin(2 * math.pi * beat_pos)
            fifth = 1.0 if (int(beat_pos * 4) % 4 != 3) else 1.5
            return profile.bass_amp * _osc((chord_freq / 2) * octave * fifth, t, bk, beat) * pulse * section_gain
        if profile.name == "ambient":
            return profile.bass_amp * _osc(chord_freq / 4, t, bk, beat * 4)
        # Walking bass: root → maj3 → perf5 → maj6 over 4 beats
        if profile.name in ("lofi", "acoustic", "pop", "default", "folk", "country", "jazz", "bossa"):
            _walk = (1.0, _R_MAJ3, _R_PERF5, _R_MAJ6)[int(beat_pos) % 4]
            return profile.bass_amp * _osc(chord_freq / 2 * _walk, t, bk, beat) * (0.8 + 0.2 * math.sin(2 * math.pi * beat_pos))
        # Cinematic/other: root on beats 1/2/4, 5th on beat 3
        pitch = chord_freq / 2 * (_R_PERF5 if int(beat_pos) % 4 == 2 else 1.0)
        return profile.bass_amp * _osc(pitch, t, bk, beat) * (0.75 + 0.25 * math.sin(2 * math.pi * beat_pos))

    def _pad(self, profile: StyleProfile, chord_freq: float, t: float, section_gain: float, section: str = "") -> float:
        slow = 0.7 + 0.3 * math.sin(2 * math.pi * 0.06 * t)
        if profile.name == "ambient":
            return profile.pad_amp * (
                _osc(chord_freq / 2, t, "sine") + 0.6 * _osc(chord_freq * 0.75, t, "sine") + 0.4 * _osc(chord_freq, t, "sine")
            ) * slow
        pk = profile.pad_kind
        fifth_freq = chord_freq * _R_PERF5
        # Sus4 in build: suspended 4th replaces 3rd — creates unresolved tension before chorus
        third_freq = chord_freq * (_R_PERF4 if section == "build" else _R_MAJ3)
        seventh_freq = chord_freq * _R_MIN7
        ninth_freq = chord_freq * 2 * _R_MAJ2   # major 9th (octave above 2nd)
        pad = profile.pad_amp * (
            _osc(chord_freq, t, pk)
            + _osc(third_freq, t, pk) * 0.28
            + _osc(fifth_freq, t, pk) * 0.35
            + _osc(chord_freq * 2, t, pk) * 0.14
        ) * section_gain
        if section == "verse":
            pad += profile.pad_amp * _osc(ninth_freq, t, "sine") * 0.12 * section_gain
        if section in ("chorus", "hook"):
            pad += profile.pad_amp * _osc(seventh_freq, t, "sine") * 0.20 * section_gain
            # Detuned doubler: always sine so beating is clean regardless of pad_kind
            pad += profile.pad_amp * (
                _osc(chord_freq * _R_DET_UP, t, "sine") * 0.18
                + _osc(chord_freq * _R_DET_DN, t, "sine") * 0.18
                + _osc(fifth_freq * _R_DET_UP, t, "sine") * 0.10
            ) * section_gain
        return pad

    def _motif_notes(self, profile: StyleProfile, root: float) -> list[float]:
        octave = 2.0 if profile.name not in ("rap", "ambient") else 1.0
        return [_melody_freq(profile, root, 0, "verse", step, octave) for step in range(4)]

    def _lead(self, profile: StyleProfile, root: float, t: float, beat_pos: float, bar: int, section: str, section_gain: float, beat: float, motif: list[float] | None = None) -> float:
        if profile.name == "ambient":
            phrase_speed = 0.5
        elif profile.name == "rap":
            phrase_speed = 1.0
        elif profile.name in ("disco", "club"):
            phrase_speed = 4.0
        else:
            phrase_speed = 2.0
        phrase_step = int(beat_pos * phrase_speed) + (bar // 8) % 2
        octave = 1.0 if profile.name in ("rap", "ambient") else 2.0
        frac = (beat_pos * max(1.0, phrase_speed)) % 1

        # Bridge B-phrase: alternate contour every 4 bars for distinct B-section feel
        _eff_section = "bridge_b" if section == "bridge" and (bar // 4) % 2 == 1 else section

        # Motif replay: chorus/hook use captured verse motif transposed up a 5th
        _use_motif = section in ("chorus", "hook") and motif is not None and len(motif) > 0
        if _use_motif:
            _mi = phrase_step % len(motif)
            _step_lift = _R_MAJ2 if _mi % 3 == 2 else 1.0  # every 3rd note raised a whole tone for hook movement
            freq = motif[_mi] * _R_PERF5 * _step_lift
        else:
            _oct = 1.75 if _eff_section == "bridge_b" else octave
            freq = _melody_freq(profile, root, bar, _eff_section, phrase_step, _oct)

        if phrase_step > 0:
            time_in_note = frac * beat / max(1.0, phrase_speed)
            port_frac = min(1.0, time_in_note / LEAD_PORTAMENTO_SECONDS)
            if port_frac < 1.0:
                if _use_motif:
                    _mi_p = (phrase_step - 1) % len(motif)
                    _lift_p = _R_MAJ2 if _mi_p % 3 == 2 else 1.0
                    prev_freq = motif[_mi_p] * _R_PERF5 * _lift_p
                else:
                    _oct_p = 1.75 if _eff_section == "bridge_b" else octave
                    prev_freq = _melody_freq(profile, root, bar, _eff_section, phrase_step - 1, _oct_p)
                freq = prev_freq + (freq - prev_freq) * port_frac

        if profile.name == "rap":
            return profile.lead_amp * _osc(freq * 0.5, t, profile.lead_kind) * _env(frac, 0.01, 0.42) * 0.55
        if profile.name == "ambient":
            return profile.lead_amp * _osc(freq, t, profile.lead_kind) * (0.5 + 0.5 * math.sin(2 * math.pi * 0.04 * t))
        # Melody rest: skip every 8th phrase step in verse sections for breathing room
        if section == "verse" and phrase_step % 8 == 7 and profile.name not in ("rap", "ambient", "disco", "club"):
            return 0.0
        # Vibrato: ramps in over first 25% of note so the attack stays clean
        freq *= 1.0 + 0.011 * min(1.0, frac / 0.25) * math.sin(2 * math.pi * 5.5 * t)
        note_period = beat / max(1.0, phrase_speed)
        base = profile.lead_amp * _osc(freq, t, profile.lead_kind, note_period) * _env(frac, 0.01, 0.28) * section_gain
        if section in ("chorus", "hook"):
            harm_freq = freq * _R_PERF4
            base += profile.lead_amp * 0.28 * _osc(harm_freq, t, profile.lead_kind, note_period) * _env(frac, 0.01, 0.28) * section_gain
        return base

    def _voice(self, request: GenerationRequest, text: str, profile: StyleProfile | None = None) -> VoiceProfile:
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
            elif profile is not None:
                # No explicit voice style — pick based on genre profile
                if profile.name in ("jazz", "bossa"):
                    requested = "crooner"
                elif profile.name in ("gospel", "rnb"):
                    requested = "soul"
                elif profile.name in ("folk", "country", "acoustic"):
                    requested = "natural"
                elif profile.name in ("metal", "rap"):
                    requested = "male"
                elif profile.name in ("choir",):
                    requested = "choir"
                else:
                    requested = "female"
            else:
                requested = "female"
        return VOICE_PROFILES.get(requested, VOICE_PROFILES["female"])

    def _sung_voice(
        self,
        profile: StyleProfile,
        request: GenerationRequest,
        vocal_plan: VocalPlan | None,
        voice: "VoiceProfile",
        root: float,
        t: float,
        beat_pos: float,
        bar: int,
        section: str,
        max_harmonics_cap: int = 22,
        formant_cache: dict | None = None,
    ) -> float:
        if (
            request.mode not in ("song", "vocal_demo")
            or vocal_plan is None
            or vocal_plan.syllable_count() <= 0
            or profile.vocal_amp <= 0
            or request.vocal_intensity <= 0
        ):
            return 0.0

        hit = syllable_at(vocal_plan, beat_pos)
        if hit is None:
            return 0.0
        syllable, syllable_idx = hit

        word = syllable.text.lower()
        syllable_x = max(0.0, min(1.0, (beat_pos - syllable.beat_start) / max(syllable.beat_duration, 0.001)))

        phrase_cycle = (syllable_idx // 4) % 4

        pitch = midi_to_hz(syllable.pitch_midi) * voice.base_multiplier
        if profile.name == "rap":
            pitch *= 0.82

        if voice.quantized:
            pitch = round(pitch / 18.0) * 18.0

        # Phrase-cycle attack time: cycle 2 is softer; cycle 1 has slightly delayed onset
        _base_attack = 0.08 if voice.name != "whisper" else 0.16
        if phrase_cycle == 1:
            syllable_x = max(0.0, syllable_x - 0.07)   # onset delay
        elif phrase_cycle == 2:
            _base_attack = min(0.20, _base_attack * 1.9)  # softer attack
        envelope = _env(syllable_x, _base_attack, 0.34)
        # Phrase 3: louder tail (build to the end of each phrase)
        if phrase_cycle == 3 and syllable_x > 0.45:
            envelope *= 1.0 + 0.28 * ((syllable_x - 0.45) / 0.55)

        vowel = self._vowel_at(word, syllable_x)
        vowel_shift = VOWEL_FORMANT_SHIFTS[vowel]

        # Vibrato: cycle 3 gets stronger vibrato; chorus gets extra depth for expressiveness
        vibrato_onset = min(1.0, syllable_x / 0.20)
        vibrato_rate_mod = 1.0 + 0.07 * math.sin(2 * math.pi * 0.88 * t)
        _vib_sect = 1.30 if section in ("chorus", "hook") else 1.0
        _vib_depth = voice.vibrato_depth * (1.42 if phrase_cycle == 3 else 1.0) * _vib_sect
        vibrato = _vib_depth * math.sin(2 * math.pi * voice.vibrato_rate * vibrato_rate_mod * t) * vibrato_onset

        # Jitter: slow quasi-random pitch micro-variation for naturalness
        jitter = 0.0035 * math.sin(2 * math.pi * 8.3 * t + 0.31 * math.sin(2 * math.pi * 2.7 * t))

        # Portamento: scoop up from slightly below on note onset (natural singing scooping)
        if not voice.quantized:
            scoop = max(0.0, 1.0 - syllable_x / 0.12) * (1.0 - 2 ** (-1.2 / 12))
            pitch = pitch * (1.0 - scoop)

        # Formant basis: fetch or build per-note (freq, gain) pairs.
        # Gains depend only on pitch+vowel, not on t — cache them to avoid 4×exp per harmonic per sample.
        _fc_key = (int(pitch), vowel_shift, max_harmonics_cap)
        _cached = formant_cache.get(_fc_key) if formant_cache is not None else None
        if _cached is None:
            _cached = self._formant_basis(pitch, voice, vowel_shift, max_harmonics_cap)
            if formant_cache is not None:
                formant_cache[_fc_key] = _cached
        _h_freqs, _h_gains = _cached
        _pi2t = 6.283185307179586 * t

        voiced = 0.0
        for singer in range(voice.blend_count):
            detune = (singer - (voice.blend_count - 1) / 2) * 0.011
            ps = 1.0 + detune + vibrato + jitter   # pitch scale vs. cached basis
            ts_offset = singer * 0.003
            shimmer = 1.0 + 0.04 * math.sin(6.283185307179586 * 6.1 * t + singer * 1.2)
            tone = math.tanh(
                sum(math.sin(_pi2t * f * ps + 6.283185307179586 * f * ps * ts_offset) * g
                    for f, g in zip(_h_freqs, _h_gains)) * 0.48
            )
            voiced += tone * shimmer
        voiced /= voice.blend_count

        # Chorus/hook: add a harmony voice (perfect 5th) for a bigger, richer sound
        if section in ("chorus", "hook"):
            _hm_base = pitch * 1.4983070768766815   # 2^(7/12) = perfect 5th
            _hm_cap = max(6, max_harmonics_cap - 4)
            _hfc_key = (int(_hm_base), vowel_shift, _hm_cap)
            _hcached = formant_cache.get(_hfc_key) if formant_cache is not None else None
            if _hcached is None:
                _hcached = self._formant_basis(_hm_base, voice, vowel_shift, _hm_cap)
                if formant_cache is not None:
                    formant_cache[_hfc_key] = _hcached
            _hh_freqs, _hh_gains = _hcached
            hm_ps = 1.0 + vibrato * 0.7 + jitter * 0.5
            harmony = math.tanh(
                sum(math.sin(6.283185307179586 * f * hm_ps * (t + 0.006)) * g
                    for f, g in zip(_hh_freqs, _hh_gains)) * 0.48
            )
            harmony_shimmer = 1.0 + 0.03 * math.sin(6.283185307179586 * 5.3 * t)
            voiced = voiced * 0.82 + harmony * 0.28 * harmony_shimmer

        consonant = self._consonant_noise(word, syllable_x, t)
        # Breath: glottal noise + "air" band; cycle 2 gets extra breathiness
        _breath_mult = 1.55 if phrase_cycle == 2 else 1.0
        breath_noise = voice.breath * _breath_mult * (
            math.sin(2 * math.pi * 2_900 * t) * 0.5
            + math.sin(2 * math.pi * 4_100 * t) * 0.3
            + 0.2 * math.sin(2 * math.pi * 130 * t * math.sin(t * 3.1))
            + math.sin(2 * math.pi * 6_800 * t) * 0.15 * voice.brightness
        )

        level = profile.vocal_amp * (0.40 + 1.20 * request.vocal_intensity)
        if request.mode == "vocal_demo":
            level *= 1.40
        if section in ("chorus", "hook"):
            level *= 1.22
        # Cycle 2: softer overall level to match the softer attack
        if phrase_cycle == 2:
            level *= 0.82
        # Pitch-coupled dynamics: higher notes naturally louder, lower notes softer
        _ref_pitch = root * voice.base_multiplier
        _pitch_dyn = max(0.65, min(1.50, 1.0 + 0.20 * math.log2(max(0.5, pitch / _ref_pitch))))
        return level * envelope * _pitch_dyn * (0.80 * voiced + breath_noise + consonant)

    def _vowel_at(self, word: str, syllable_x: float) -> str:
        """Return the active vowel at position syllable_x (0→1) through the word.
        Multi-vowel words (e.g. 'shadow' a→o, 'emotional' e→o→i→o→a) transition naturally."""
        vowels = [c for c in word.lower() if c in VOWEL_FORMANT_SHIFTS]
        if not vowels:
            return "a"
        return vowels[min(int(syllable_x * len(vowels)), len(vowels) - 1)]

    def _formant_tone(self, pitch: float, t: float, voice: VoiceProfile, vowel_shift: tuple[float, float, float, float], max_harmonics_cap: int = 22) -> float:
        tone = 0.0
        max_harmonics = min(max_harmonics_cap, int(NYQUIST / max(pitch, 1.0)))
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

    def _formant_basis(self, pitch: float, voice: "VoiceProfile", vowel_shift: tuple, max_harmonics_cap: int) -> tuple[list[float], list[float]]:
        """Precompute per-harmonic (freq, gain) pairs that don't depend on t.
        The per-sample hot path only needs to evaluate math.sin(2π * freq * pitch_scale * t) * gain.
        """
        freqs: list[float] = []
        gains: list[float] = []
        bandwidths = (F1_BW, F2_BW, F3_BW, F4_BW)
        max_h = min(max_harmonics_cap, int(NYQUIST / max(pitch, 1.0)))
        for h in range(1, max_h + 1):
            freq = pitch * h
            if freq >= NYQUIST:
                break
            fg = 0.0
            for i, (formant, shift) in enumerate(zip(voice.formants, vowel_shift)):
                center = formant * shift
                bw = bandwidths[i]
                d = (freq - center) / bw
                w = 0.75 if i == 3 else 1.0
                fg += w * math.exp(-d * d * 0.5)
            tilt = 1.0 / (h ** (1.1 - voice.brightness * 0.4))
            src = 1.0 if h % 2 == 1 else (0.55 + 0.45 * voice.brightness)
            freqs.append(freq)
            gains.append(tilt * src * (0.28 + fg * 0.72))
        return freqs, gains

    def _consonant_noise(self, word: str, syllable_x: float, t: float) -> float:
        if syllable_x > 0.20 or not word:
            return 0.0
        c = word[0]
        if c not in "bcdfghjklmnpqrstvwxyz":
            return 0.0

        if c in "ptk":
            # Plosive stops: very hard transient click with inharmonic partials
            hard = math.exp(-syllable_x * 95.0)
            fb = {"p": 2_800, "t": 4_200, "k": 3_500}.get(c, 3_200)
            return hard * (
                0.032 * math.sin(2 * math.pi * fb * t)
                + 0.018 * math.sin(2 * math.pi * fb * 1.67 * t)
                + 0.010 * math.sin(2 * math.pi * fb * 2.41 * t)
            )

        if c == "s":
            # Sibilant: bright high-frequency quasi-noise via inharmonic sines
            burst = math.exp(-syllable_x * 18.0)
            return burst * (
                0.015 * math.sin(2 * math.pi * 6_200 * t)
                + 0.013 * math.sin(2 * math.pi * 8_100 * t)
                + 0.010 * math.sin(2 * math.pi * 6_200 * 1.31 * t)
                + 0.007 * math.sin(2 * math.pi * 9_500 * t)
            )

        if c in "fzv":
            # Fricatives: softer sibilance
            burst = math.exp(-syllable_x * 18.0)
            f0 = {"f": 5_100, "z": 5_400, "v": 4_800}.get(c, 5_500)
            return burst * (
                0.013 * math.sin(2 * math.pi * f0 * t)
                + 0.010 * math.sin(2 * math.pi * f0 * 1.31 * t)
                + 0.007 * math.sin(2 * math.pi * f0 * 1.71 * t)
            )

        if c == "h":
            # Breathy h: ramp-in (not decay) then soft fade
            ramp = min(1.0, syllable_x / 0.08) * math.exp(-syllable_x * 9.0)
            return ramp * (
                0.020 * math.sin(2 * math.pi * 2_800 * t)
                + 0.010 * math.sin(2 * math.pi * 1_400 * t)
            )

        if c in "mn":
            # Nasal resonance: two formant frequencies for nasal quality
            burst = math.exp(-syllable_x * 22.0)
            f1 = 250 if c == "m" else 300
            return burst * (
                0.018 * math.sin(2 * math.pi * f1 * t)
                + 0.012 * math.sin(2 * math.pi * f1 * 1.28 * t)
                + 0.006 * math.sin(2 * math.pi * f1 * 3.2 * t)
            )

        if c in "bdg":
            # Voiced stops: sharp but softer than ptk
            burst = math.exp(-syllable_x * 65.0)
            fb = {"b": 1_800, "d": 2_600, "g": 2_000}.get(c, 2_200)
            return burst * 0.022 * (
                math.sin(2 * math.pi * fb * t)
                + 0.45 * math.sin(2 * math.pi * fb * 1.55 * t)
            )

        burst = math.exp(-syllable_x * 22.0)
        return burst * 0.012 * math.sin(2 * math.pi * (3_600 + ord(c) % 800) * t)

    def _drums(self, profile: StyleProfile, rng: random.Random, t: float, beat_pos: float, section: str = "") -> tuple[float, float, float, float]:
        # Swing: delay off-beat 8th notes by profile.swing beats (lofi=0.08, acoustic=0.04, cinematic=0.06)
        if profile.swing > 0.0 and int(beat_pos * 2) % 2 == 1:
            drum_bp = beat_pos - profile.swing
        else:
            drum_bp = beat_pos
        beat_frac = drum_bp % 1
        kick = hat = snare = perc = 0.0
        pat = profile.drum_pattern
        bar_beat = int(drum_bp) % 4
        velocity = 1.0 if bar_beat == 0 else (0.82 if bar_beat == 2 else 0.68)

        if pat == "four_floor":
            if beat_frac < 0.12:
                kick_body = math.sin(2 * math.pi * (52 + 90 * math.exp(-beat_frac * 24)) * t) * math.exp(-beat_frac * 14)
                kick_click = math.sin(2 * math.pi * 2_200 * t) * math.exp(-beat_frac * 80)
                kick = (0.55 * kick_body + 0.08 * kick_click) * velocity
            hat_step = int(drum_bp * 2) % 2
            if hat_step == 1:
                # Open hihat on "and of beat 4" in chorus (slower decay = open sound)
                if section in ("chorus", "hook") and int(drum_bp * 4) % 8 == 7:
                    hat = (rng.random() * 2 - 1) * profile.noise_amp * 1.10 * math.exp(-beat_frac * 3.2)
                else:
                    hat_vel = 0.90 if int(drum_bp * 4) % 4 == 2 else 0.60
                    hat = (rng.random() * 2 - 1) * profile.noise_amp * hat_vel
            if int(drum_bp) % 4 in (1, 3) and beat_frac < 0.10:
                snare_body = (rng.random() * 2 - 1) * 0.06 * math.exp(-beat_frac * 22)
                snare_tone = math.sin(2 * math.pi * 280 * t) * math.exp(-beat_frac * 18) * 0.025
                snare = (snare_body + snare_tone) * velocity
            if int(drum_bp * 8) % 8 == 6 and beat_frac > 0.85:
                hat += (rng.random() * 2 - 1) * profile.noise_amp * 0.30
            # Conga hit on "and of beat 3": adds Latin percussion texture
            if int(drum_bp * 4) % 8 == 5 and beat_frac < 0.07:
                perc = math.sin(2 * math.pi * 235 * t) * math.exp(-beat_frac * 30) * 0.038

        elif pat == "half_time":
            half = int(drum_bp * 2) % 8
            if half in (0, 6) and beat_frac < 0.18:
                kick_body = math.sin(2 * math.pi * (44 + 68 * math.exp(-beat_frac * 20)) * t) * math.exp(-beat_frac * 9)
                kick = 0.62 * kick_body * velocity
            if int(drum_bp * 8) % 3 == 0:
                hat = (rng.random() * 2 - 1) * profile.noise_amp * 0.82
            if int(drum_bp) % 4 == 2 and beat_frac < 0.20:
                snare_noise = (rng.random() * 2 - 1) * 0.12 * math.exp(-beat_frac * 12)
                snare_crack = math.sin(2 * math.pi * 320 * t) * math.exp(-beat_frac * 25) * 0.035
                snare = (snare_noise + snare_crack) * velocity

        elif pat == "pulse":
            if int(drum_bp * 2) % 2 == 0 and beat_frac < 0.16:
                kick = 0.34 * math.sin(2 * math.pi * (50 + 55 * math.exp(-beat_frac * 10)) * t) * math.exp(-beat_frac * 7)
            if int(drum_bp * 4) % 8 == 7:
                perc = (rng.random() * 2 - 1) * profile.noise_amp * 0.55

        elif pat == "pop":
            if beat_frac < 0.11:
                kick_body = math.sin(2 * math.pi * (56 + 78 * math.exp(-beat_frac * 20)) * t) * math.exp(-beat_frac * 12)
                kick = 0.42 * kick_body * velocity
            if int(drum_bp) % 4 in (1, 3) and beat_frac < 0.16:
                snare = (rng.random() * 2 - 1) * 0.11 * math.exp(-beat_frac * 17) * velocity
                snare += math.sin(2 * math.pi * 300 * t) * math.exp(-beat_frac * 22) * 0.028
            hat_vel = 0.75 if int(drum_bp * 4) % 4 % 2 == 1 else 0.45
            if int(drum_bp * 4) % 2 == 1:
                hat = (rng.random() * 2 - 1) * profile.noise_amp * hat_vel

        elif pat == "soft_backbeat":
            if int(drum_bp) % 4 in (0, 2) and beat_frac < 0.10:
                kick = 0.25 * math.sin(2 * math.pi * (60 + 45 * math.exp(-beat_frac * 16)) * t) * math.exp(-beat_frac * 11)
            if int(drum_bp) % 4 in (1, 3) and beat_frac < 0.12:
                snare = (rng.random() * 2 - 1) * 0.055 * math.exp(-beat_frac * 15)
                if beat_frac < 0.035:
                    perc = math.sin(2 * math.pi * 1100 * t) * math.exp(-beat_frac * 60) * 0.030
            if int(drum_bp * 2) % 2 == 1:
                hat = (rng.random() * 2 - 1) * profile.noise_amp * 0.42

        elif pat == "reggae":
            # Kick on beats 1 and 3 only (no on-2-and-4 backbeat)
            if bar_beat in (0, 2) and beat_frac < 0.12:
                kick = 0.32 * math.sin(2 * math.pi * (55 + 50 * math.exp(-beat_frac * 18)) * t) * math.exp(-beat_frac * 10)
            # Snare on beat 3 (light rim)
            if bar_beat == 2 and beat_frac < 0.10:
                snare = (rng.random() * 2 - 1) * 0.032 * math.exp(-beat_frac * 14)
            # Skank: short chord stab on upbeats (and of every beat) — the reggae trademark
            _ub = drum_bp * 2 % 1
            if int(drum_bp * 2) % 2 == 1 and _ub < 0.10:
                perc = math.sin(2 * math.pi * 360 * t) * math.exp(-_ub * 32) * 0.045
                perc += (rng.random() * 2 - 1) * profile.noise_amp * 0.50
            elif int(drum_bp * 2) % 2 == 1:
                hat = (rng.random() * 2 - 1) * profile.noise_amp * 0.28

        elif pat == "jazz":
            # Ride cymbal: quarter-note pulse, chick accent on 2 and 4
            if beat_frac < 0.20:
                _ride_vel = 0.92 if bar_beat in (1, 3) else 0.58
                hat = (rng.random() * 2 - 1) * profile.noise_amp * _ride_vel * 1.25
            # Light kick on 1; occasional ghost on 3 (every 2 bars)
            if bar_beat == 0 and beat_frac < 0.09:
                kick = 0.20 * math.sin(2 * math.pi * (48 + 55 * math.exp(-beat_frac * 18)) * t) * math.exp(-beat_frac * 12)
            elif bar_beat == 2 and beat_frac < 0.07 and int(drum_bp / 4) % 2 == 0:
                kick = 0.13 * math.sin(2 * math.pi * (46 + 40 * math.exp(-beat_frac * 18)) * t) * math.exp(-beat_frac * 12)
            # Brush snare on 2 and 4 (long decay = brushed skin sound)
            if bar_beat in (1, 3) and beat_frac < 0.30:
                snare = (rng.random() * 2 - 1) * 0.040 * math.exp(-beat_frac * 7)
            # Rimshot tap between beats (triplet feel)
            if int(drum_bp * 3) % 3 == 2 and beat_frac < 0.05 and int(drum_bp / 2) % 3 == 1:
                perc = math.sin(2 * math.pi * 940 * t) * math.exp(-beat_frac * 50) * 0.020

        elif pat == "bossa":
            # Pandeiro: 8th notes, upbeat accent (gives bossa the rhythmic bounce)
            _bub = int(drum_bp * 2) % 2
            if beat_frac < 0.15:
                hat = (rng.random() * 2 - 1) * profile.noise_amp * (0.72 if _bub == 1 else 0.38)
            # Light kick on beat 1; chorus adds beat 3
            if bar_beat == 0 and beat_frac < 0.09:
                kick = 0.18 * math.sin(2 * math.pi * (58 + 45 * math.exp(-beat_frac * 16)) * t) * math.exp(-beat_frac * 10)
            elif bar_beat == 2 and beat_frac < 0.07 and section in ("chorus", "hook"):
                kick = 0.12 * math.sin(2 * math.pi * (52 + 35 * math.exp(-beat_frac * 16)) * t) * math.exp(-beat_frac * 10)
            # Rim on beat 3
            if bar_beat == 2 and beat_frac < 0.07:
                snare = (rng.random() * 2 - 1) * 0.025 * math.exp(-beat_frac * 20)
                perc = math.sin(2 * math.pi * 1_050 * t) * math.exp(-beat_frac * 55) * 0.016
            # Clave accent: "and of 2" (index 3 in 8th-note grid)
            if int(drum_bp * 4) % 8 == 3 and beat_frac < 0.05:
                perc += math.sin(2 * math.pi * 1_480 * t) * math.exp(-beat_frac * 70) * 0.028

        elif pat == "country":
            # Kick on 1 (strong) and 3 (medium)
            if bar_beat == 0 and beat_frac < 0.12:
                kick = 0.36 * math.sin(2 * math.pi * (60 + 65 * math.exp(-beat_frac * 18)) * t) * math.exp(-beat_frac * 12)
            elif bar_beat == 2 and beat_frac < 0.10:
                kick = 0.26 * math.sin(2 * math.pi * (58 + 52 * math.exp(-beat_frac * 18)) * t) * math.exp(-beat_frac * 12)
            # Tight snare crack on 2 and 4
            if bar_beat in (1, 3) and beat_frac < 0.10:
                snare = (rng.random() * 2 - 1) * 0.072 * math.exp(-beat_frac * 20)
                snare += math.sin(2 * math.pi * 310 * t) * math.exp(-beat_frac * 24) * 0.020
            # Shuffle hihat: downbeats quieter, upbeats accented
            _ch = int(drum_bp * 2) % 2
            if beat_frac < 0.12:
                hat = (rng.random() * 2 - 1) * profile.noise_amp * (0.70 if _ch == 1 else 0.42)
            # Ghost snare on "e of 3" — country shuffle signature
            if int(drum_bp * 4) % 8 == 5 and beat_frac < 0.04:
                perc = (rng.random() * 2 - 1) * 0.018 * math.exp(-beat_frac * 30)

        return kick, hat, snare, perc
