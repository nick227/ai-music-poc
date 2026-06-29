# Voice Roadmap

Focused MVP: **Phase 0 only** — establish the timing contract before any neural voice work.

Full singing quality depends on a shared **VocalPlan** for controlled renderers. Until a future neural renderer is wired, SVS adapters and voice cloning add complexity without fixing the root issue: **equal per-word timing**.

---

## Current Status

| Area | Status |
|------|--------|
| Phase 0 VocalPlan v0 — schema, syllable timing, VocalEngine wiring | **shipped** |
| VocalPlan v0.1 — phrase holds, rest gaps, section density, pitch contours, debug grid | **shipped** |
| Workbench syllable timing grid | **shipped** |
| Current focus: validate procedural draft timing/audio behavior; protect against regressions | **in progress** |
| SVS, forced alignment, ACE observed plans, voice cloning | **deferred** |

---

## Core Architectural Decision

**Controlled render path** (procedural draft today; SVS later):

```
lyrics → prosody → VocalPlan → controlled render → align/mix
```

**Not:**

```
lyrics → TTS/singer → hope it fits
```

- **Prosody + timing** are planned first and stored as `vocal_plan.json`.
- **Controlled render** (procedural, future SVS) produces audio from the plan.
- **Align/mix** (forced alignment, time-warp, stem mixdown) refines output against the plan — deferred until Phase 0 is validated.

**ACE separation rule:** ACE outputs audio only. It does not consume `VocalPlan`. Any `observed_vocal_plan.json` derived from ACE output is a post-render analysis artifact produced by forced alignment — not an input to ACE inference.

```
lyrics/prompt → ACE → audio → (post-render forced alignment) → observed_vocal_plan.json
```

Cloning, when it arrives, is **timbre conversion on top of a correct performance**, not a substitute for timing generation.

---

## Problem Statement

Before VocalPlan, `app/generators/lyrics_timeline.py` assigned equal duration to every word:

```python
word_beats = beats_per_line / len(words)
```

That ignored syllable count, stress, section density, and melodic contour. Each renderer invented its own timeline independently. VocalPlan is the shared contract that fixes this.

---

## Phase 0 — VocalPlan v0 [done]

### 1. VocalPlan JSON schema

First-class artifact saved beside each generation job as `data/jobs/<id>/vocal_plan.json`.

```json
{
  "version": 0,
  "bpm": 118,
  "key": "Am",
  "duration_beats": 64.0,
  "sections": [
    {
      "name": "verse",
      "beat_start": 0.0,
      "beat_end": 16.0,
      "lines": [
        {
          "text": "I saw your shadow in the rain",
          "rest_beats_after": 0.5,
          "syllables": [
            { "text": "I",    "beat_start": 0.00, "beat_duration": 0.25, "pitch_midi": 67, "stressed": false, "phrase_end": false },
            { "text": "saw",  "beat_start": 0.25, "beat_duration": 0.50, "pitch_midi": 69, "stressed": true,  "phrase_end": false },
            { "text": "your", "beat_start": 0.75, "beat_duration": 0.25, "pitch_midi": 67, "stressed": false, "phrase_end": false }
          ]
        }
      ]
    }
  ]
}
```

*The `syllables` array above is abbreviated. A full line produces one entry per syllable.*

| Field | Purpose |
|-------|---------|
| `bpm`, `key` | Locked musical grid from request or inferred |
| `sections` | Verse/chorus/bridge boundaries |
| `lines` | Raw lyric line text + rest gap after the line |
| `syllables` | Atomic timing unit — beat start, duration, pitch, stress flag, phrase-end flag |

**Pitch in v0:** `pitch_midi` values are heuristic — generated from existing procedural melodic contour patterns (scale-degree sequences mapped to MIDI). No pitch inference or neural melody extraction is performed in Phase 0.

### 2. Syllable-weighted timing [done]

- Lyrics are syllabified (English v1: `pyphen`).
- Beats are allocated by **syllable count**, not word count.
- Stressed syllables receive longer duration and are placed nearer downbeats.
- Section-aware density: chorus tighter than verse; rap higher syllables/beat.
- `VocalPlan` is the source of truth; the equal-word `LyricEvent` path is deprecated.

### 3. VocalEngine consumes VocalPlan [done]

- One `build_vocal_plan()` call per job (`app/generators/vocal_plan.py`).
- `VocalEngine` reads syllable events and pitch from the plan — no internal `build_lyric_timeline()` call.
- Procedural generator passes the same plan it exports to job metadata.
- Controlled renderers do not invent timing independently.

---

## Phase 0 — v0.1 Timing/Musicality Pass [done]

- Phrase-end syllables held longer with softer release in procedural renderer
- Explicit `rest_beats_after` gaps between lines and sections
- `SectionDensityKnobs` + `VocalPlanTiming` exposed on the plan (`section_density`, `timing` fields)
- Workbench syllable timing grid: visual track + debug table (beat start/duration, `pitch_midi`, stress, phrase end)
- Golden fixtures: `tests/fixtures/vocal_plan/{pop_chorus,rap_dense,ballad_held}.json`

---

## Current Focus: Validation [current]

Validate that procedural draft timing and audio behaviour match the VocalPlan contract. Protect against regressions as the codebase evolves.

Active validation targets:
- Syllable timing correctness across section types (verse, chorus, bridge, rap)
- Section density and rest gap behaviour
- Bundle plumbing: `vocal_plan.json` present in every vocal job output
- API contract: plan accessible via job result metadata
- Procedural draft audio lands on the beat for simple verse–chorus lyrics

---

## Definition of Done / Validation Gates

All gates below must pass for Phase 0 to be considered complete.

| Gate | Target | Status |
|------|--------|--------|
| Plan persistence | 100% of vocal jobs write `vocal_plan.json` | done |
| Syllable coverage | Every lyric token syllabified or flagged | done |
| Timing sanity | Syllable count and stress drive duration; word length alone does not | done |
| Phrase/rest pacing | Phrase-end holds and inter-line rests are present and non-zero | done |
| Grid preview | Workbench syllable grid columns align with draft vocal onsets | done |
| No new model installs | Phase 0 uses `pyphen` + heuristics only; no neural model required | done |
| Procedural draft audio | Draft vocals land on the beat for simple verse–chorus lyrics; auto-polish is skipped by default in draft/procedural mode | in progress |

---

## Non-Goals

- **No SVS integration.** DiffSinger-style renderers are deferred until Phase 0 validation is complete.
- **No voice cloning.** RVC, So-VITS, and timbre conversion are deferred.
- **No forced alignment.** Post-render alignment is a Phase 1+ concern.
- **ACE does not consume VocalPlan.** ACE receives lyrics and prompt; `VocalPlan` is not an ACE input.
- **Procedural renderer is not a commercial vocal path.** The formant/procedural renderer validates timing logic and structure. It is not the target audio quality for end users.

---

## Current Known Limitation

The procedural/formant renderer sounds synthetic. This is expected and acceptable in Phase 0.

VocalPlan validates: syllable timing, phrasing, section density, rests, pitch event structure, API plumbing, and bundle output. Commercial vocal realism requires a future controlled renderer (SVS, DiffSinger-style) that consumes the same `VocalPlan` contract. That renderer is deferred.

---

## Deferred [deferred]

| Track | Notes |
|-------|-------|
| **SVS** (DiffSinger-style) | MIDI + lyrics → singing; consumes `VocalPlan` pitch/duration |
| **ACE stem + forced align** | Derive `observed_vocal_plan.json` from ACE vocal; post-render analysis only, not an ACE input |
| **Time-warp / section re-sing** | Post-render alignment loop |
| **Voice cloning** | Timbre conversion (RVC / So-VITS) on SVS performance — **not** timing generation |

Do **not** start with RVC, So-VITS, or voice cloning. Model complexity before the timing contract is validated wastes effort.

---

## File Touch Map

| File | Change | Status |
|------|--------|--------|
| `app/generators/vocal_plan.py` | Schema, builder, serialization | done |
| `app/generators/lyrics_timeline.py` | Syllable events; superseded by vocal_plan | done |
| `app/generators/vocal_engine.py` | Consumes `VocalPlan` | done |
| `app/generators/procedural.py` | Builds plan once; exports to job metadata | done |
| `app/services/generation_service.py` | Persists plan path in job result | done |
| `app/web/static/workbench/` | Syllable grid / karaoke preview | done |
| `tests/test_vocal_plan.py` | Timing contract tests + golden fixtures | done |

---

## Related Docs

- [`ROADMAP.md`](ROADMAP.md) — product phases
- [`ACE_STEP_SETUP.md`](ACE_STEP_SETUP.md) — ACE neural render path (separate from `vocal_plan.json`)
- [`GENERATOR_ADAPTERS.md`](GENERATOR_ADAPTERS.md) — adapter pattern for future SVS
