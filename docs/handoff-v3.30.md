# AI Music POC — Hand-off Document
**Version:** V3.30  
**Date:** 2026-06-27  
**Generator:** `app/generators/procedural.py`  
**Test suite:** 156 tests, all pass  

---

## What We're Building

A Python/FastAPI procedural music generator targeting Suno-level song generation quality without a trained model. The architecture is entirely CPU-side: oscillators, formant synthesis, chord progressions, section automation, reverb/compression, and vocal synthesis — all computed sample-by-sample at 44100 Hz.

The system accepts a text prompt and generates a WAV file. Genre, mood, key, tempo, structure, and instrumentation are all inferred from the prompt.

---

## Work Done This Session (V3.22 → V3.30)

### V3.22 — Prompt Intelligence
- Scale/mood inference from keywords: sad/dark/minor → MINOR scale, happy/bright/major → MAJOR
- Key detection from prompt: regex matches "in C", "key of D", "A minor", "B major"

### V3.23 — Stereo Placement
- Per-instrument stereo field: `_ster = pad * 0.30 - lead * 0.22 + (hat + perc) * 0.15`
- Rim shot layered into soft_backbeat pattern

### V3.24 — Bridge Section
- Bridge added to all song structures between second verse and final chorus
- Bridge-specific chord progressions per profile (e.g. pop: vi–IV–V–I)
- Stripped-back mix: 72% chorus gain, quieter kick, heavier reverb
- Auto-snare fill before final chorus re-entry; crash cymbal fires at both chorus entries

### V3.25 — Lead Portamento
- 15ms pitch glide between consecutive melody notes (`LEAD_PORTAMENTO_SECONDS = 0.015`)
- Prevents the stepped/robotic quality in fast passages

### V3.26 — Vocal Dynamics
- Pitch-coupled vocal amplitude: `max(0.65, min(1.50, 1.0 + 0.20 * log2(pitch / ref_pitch)))`
- Chorus/hook vibrato boost: ×1.30 multiplier so hooks feel more expressive

### V3.27 — EDM Breakdown
- Breakdown section for club profile: kick/bass/lead/vocal all silenced, only pad + hihat
- Club structure becomes: intro → build → chorus → breakdown → chorus → outro
- Breakdown mix: section_gain=0.28, no kick, reverb ×1.90

### V3.28 — Richer Harmony
- Sus4 voicing in build sections: suspended 4th replaces major 3rd — unresolved tension before chorus
- 9th chord added in verse: `ninth_freq = chord_freq * 2 * _R_MAJ2` at 12% volume
- Walking bass extended from lofi/acoustic to pop and default profiles

### V3.29 — Genre Expansion + Karplus-Strong + Prompt Instrumentation
- **8 new genre profiles:** folk, jazz, r&b, reggae, metal, bossa nova, gospel, country
- Each has unique BPM, scale, drum pattern, amp balance, swing
- **Karplus-Strong oscillator** (`karplusstrong` kind): stateless approximation using `t % note_period` for per-note decay envelope reset; 4 harmonic partials with frequency-dependent decay rates. No ring buffer — avoids statefulness problem.
- **Reggae drum pattern:** offbeat skank perc on upbeats, sparse kick on beats 1/3
- **Prompt instrumentation parsing** (`_apply_instrumentation_hints()`):
  - `"solo piano"` → no drums, no bass, no lead, boosted pad
  - `"no bass"` / `"no lead"` → zeroes that channel
  - `"sparse"` / `"stripped back"` → 65–75% amp reduction
  - `"lush"` / `"orchestral"` → amp boost
  - `"a cappella"` → instruments silenced, vocal ×1.6
- **Updated `_profile()` keyword routing:** 8 new genre checks ordered before acoustic fallback

### V3.30 — Per-Instrument Timbre (current)
- `StyleProfile` now has `lead_kind`, `bass_kind`, `pad_kind` replacing the single `pluck_kind`
- Every profile specifies a distinct oscillator type per instrument:

| Profile | lead | bass | pad |
|---------|------|------|-----|
| folk / country | Karplus-Strong | Karplus-Strong | sine |
| jazz / bossa | pluck | pluck (walking) | sine |
| acoustic | pluck | pluck | sine |
| lofi / cinematic / disco | pluck | sine | sine |
| club | saw | saw | saw |
| metal | square | saw | square |
| rap | square | saw | sine |
| reggae | pluck | sine | sine |
| pop / r&b / gospel / default / ambient | sine | sine | sine |

- Walking bass extended to folk, country, jazz, bossa
- Detuned pad doubler stays sine regardless of `pad_kind` (sine beating is clean; saw/square beating is noise)

---

## Current State

### Architecture
```
app/generators/procedural.py   ← primary generator, all synthesis here
app/api/routes/health.py       ← version string (currently "3.30")
app/domain/models.py           ← GenerationRequest, field is duration_seconds
tests/                         ← 156 tests
```

### Key Types
```python
class StyleProfile:
    # identity
    name: str; default_bpm: int; scale: list[int]; drum_pattern: str
    # mix
    has_drums: bool; bass_amp: float; pad_amp: float; lead_amp: float
    vocal_amp: float; noise_amp: float
    # character
    swing: float; lead_kind: str; bass_kind: str; pad_kind: str
    chorus_lift: float; lowpass: float
```

### 17 Genre Profiles
disco, club, rap, ambient, acoustic, lofi, cinematic, pop, default,  
folk, jazz, rnb, reggae, metal, bossa, gospel, country

### Oscillator kinds available
`sine` | `square` | `saw` | `pluck` | `karplusstrong`

### Benchmarks (V3.30, 30s clip)
| Quality | Realtime ratio | Limit | Status |
|---------|---------------|-------|--------|
| draft | 0.36× | 0.95× | PASS |
| balanced | 0.25× | 1.25× | PASS |
| high | 0.25× | 1.50× | PASS |

---

## Proposed Next Moves

These are ordered by quality impact per engineering effort.

---

### 1. Profile Blending — "jazzy folk", "pop country"  
**What:** When two genre keywords match, interpolate parameters between the top two profiles instead of hard-routing to one.  
**Why:** Currently "jazzy folk" routes entirely to jazz (first keyword hit). Blending would give 60% jazz swing + 40% folk KS timbre.  
**How:** Score each keyword match, take top-2 profiles, lerp all numeric fields (`bass_amp`, `pad_amp`, `lead_amp`, `swing`, `chorus_lift`, `lowpass`), and pick the dominant profile's categorical fields (`drum_pattern`, `scale`, `lead_kind`, `bass_kind`).  
**Tradeoff:** Poorly matched pairs (e.g. metal + ambient) can produce mud. Needs a compatibility matrix or a minimum score threshold to avoid blending wildly different profiles.  
**Estimated complexity:** Medium (~1 session).

---

### 2. Melody Improvement — Contour Variety and Motif Repetition  
**What:** The current melody is generated phrase-by-phrase from a static contour table. Adding motif memory (repeat a 4-note phrase from bar 1 in bar 9) and contour variation per section would make songs feel composed rather than improvised.  
**Why:** This is the single biggest gap between the output and Suno quality. Suno's melodies feel like someone wrote them; ours feel generated.  
**How:**
- Capture the first 4 phrase steps of the verse as a "motif"
- In chorus/hook, replay the motif at a higher octave with slight variation
- Add a second contour table per profile for the B-section (bridge/breakdown)  
**Tradeoff:** Motif repetition is compelling but can feel repetitive if over-applied. Needs a variation probability (~20% chance of deviation per note).  
**Estimated complexity:** Medium (~1 session).

---

### 3. Self-Evaluation Loop — Parameter Auto-Tuning  
**What:** Generate a 15-second clip per profile, extract audio features (RMS per instrument estimated from channel weights, spectral centroid from FFT sample, stereo width), compare against target signatures, and surface which profiles are out of range.  
**Why:** Profile parameter tuning is currently guesswork. This turns it into a measurable feedback loop. After each version you'd run it and see which profiles drifted.  
**How:** 
- Write `scripts/evaluate_profiles.py` — generates one clip per profile, runs feature extraction, prints a table
- Define target ranges per feature per profile type (e.g. bass_rms 0.18–0.28 for club, 0.08–0.14 for ambient)
- Flag profiles outside range as candidates for manual tuning  
**Tradeoff:** Feature extraction doesn't capture "does this sound like jazz?" — it catches balance issues, not character issues. It's a floor checker, not a quality judge.  
**Estimated complexity:** Low (~half session).

---

### 4. Richer Drum Engine — More Pattern Variety  
**What:** The current drum engine has 6 patterns (four_floor, soft_backbeat, half_time, pop, pulse, reggae). Adding patterns for jazz ride cymbal, country shuffle, metal double-kick, bossa clave, and gospel call-response would complete the profile identity.  
**Why:** Right now jazz and bossa share `half_time`, which is a lo-fi hip-hop pattern — not authentic. Metal uses `four_floor` (a disco kick pattern).  
**How:** Add pattern branches to `_drums()` for each new type, then update the affected profiles.  
**Tradeoff:** Each new pattern adds complexity to an already long function. Consider extracting pattern data into a dict of beat-by-beat specs.  
**Estimated complexity:** Low-medium (~1 session).

---

### 5. Formant Singing Voices — Voice Character Expansion  
**What:** The current VoiceProfiles (female, male, choir, rap, child) share the same 4-formant model. Adding profile-specific formant shapes — e.g. a "gospel belt" with pushed F1, a "breathy indie" with low breath threshold, a "jazz crooner" with wide vibrato — would give vocal identity beyond pitch and vibrato rate.  
**Why:** Vocals are the most perceptually important element. Profile-matched voices make the genre feel authentic end-to-end.  
**How:** Extend `VoiceProfile` with a `style` field and add formant preset tables per style. Wire style selection into `_voice()` based on the active `StyleProfile`.  
**Tradeoff:** Formant tuning is time-intensive and perceptually subtle — hard to get right without a lot of listening tests.  
**Estimated complexity:** Medium-high (~2 sessions).

---

## Run Commands

```bash
# Start server
.venv/bin/python run.py

# Run tests
.venv/bin/pytest tests/ -q

# Quick benchmark (30s clip, three quality tiers)
.venv/bin/python -c "
import time; from pathlib import Path
from app.domain.models import GenerationRequest
from app.generators.procedural import ProceduralGenerator
gen = ProceduralGenerator()
for q in ['draft', 'balanced', 'high']:
    req = GenerationRequest(prompt='upbeat pop song', quality=q, duration_seconds=30,
        mode='song', genre_tags=[], mood_tags=[], structure='verse_chorus', negative_prompt='')
    t0 = time.time(); gen.generate(req, Path(f'/tmp/bench_{q}.wav')); e = time.time()-t0
    print(f'{q}: {e/30:.2f}x realtime')
"
```

---

## Notes for Next Collaborator

- `GenerationRequest.duration_seconds` — not `duration`. Default is 60s; always pass explicit value in benchmarks.
- `StyleProfile` uses `__slots__` — can't add attributes dynamically; all fields must be in `__slots__` and `__init__`.
- The `karplusstrong` oscillator in `_osc()` is stateless by design — it uses `t % note_period` to reset the decay envelope per note. This avoids needing a ring buffer but means `note_period` must be passed correctly from `_lead()` and `_bass()`.
- The detuned pad doubler (±4 cents in chorus) deliberately stays `sine` regardless of `pad_kind`. Saw or square at ±4 cents beating against itself produces a harsh comb effect rather than lush width.
- Walking bass currently applies to: lofi, acoustic, pop, default, folk, country, jazz, bossa. Other profiles use their own rhythm patterns (rap gates, disco octave jumps, ambient drone).
- `_apply_instrumentation_hints()` is called after the mood/scale override block in `generate()` — so instrumentation hints layer on top of scale changes, not the other way around.
