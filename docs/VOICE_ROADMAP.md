# Voice Roadmap

Focused MVP: **Phase 0 only** — establish the timing contract before any neural voice work.

Full singing quality (Suno-like alignment) depends on a shared **VocalPlan** that every renderer consumes. Until that exists, SVS adapters and voice cloning add complexity without fixing the real bug: **equal per-word timing**.

---

## Core architectural decision

```
lyrics → prosody → VocalPlan → render → align/mix
```

**Not:**

```
lyrics → TTS/singer → hope it fits
```

- **Prosody + timing** are planned first and stored as `VocalPlan`.
- **Render** (procedural draft today; SVS / ACE later) produces audio from the plan.
- **Align/mix** (forced alignment, time-warp, stem mixdown) refines output against the plan — deferred until Phase 0 is proven.

Cloning, when it arrives, is **timbre conversion on top of a correct performance**, not a substitute for timing generation.

---

## Current gap

`app/generators/lyrics_timeline.py` assigns equal duration to every word:

```python
word_beats = beats_per_line / len(words)
```

That ignores syllable count, stress, section density, and melodic contour. `VocalEngine` rebuilds its own timeline internally, so each renderer can invent timing separately.

---

## Phase 0 — MVP (build this first)

### 1. VocalPlan JSON schema (v0)

First-class artifact saved beside each generation job (e.g. `data/jobs/<id>/vocal_plan.json` or in job result metadata).

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
          "syllables": [
            {
              "text": "saw",
              "beat_start": 1.0,
              "beat_duration": 0.5,
              "pitch_midi": 69
            }
          ]
        }
      ]
    }
  ]
}
```

| Field | Purpose |
|-------|---------|
| `bpm`, `key` | Locked musical grid from request or inferred |
| `sections` | Verse/chorus/bridge boundaries |
| `lines` | Raw lyric line text |
| `syllables` | Atomic timing unit — beat start, duration, pitch |

v0 pitch can come from existing melodic contours; v0 prosody can be heuristic (no ML).

### 2. Replace word timing with syllable-weighted timing

- Syllabify lyrics (English v1: `pyphen`, `syllables`, or `g2p_en`).
- Allocate beats by **syllable count**, not word count.
- Stressed syllables → longer duration, nearer downbeats.
- Section-aware density (chorus tighter than verse; rap higher syllables/beat).
- Output populates `VocalPlan`; deprecate equal-word `LyricEvent` as the source of truth.

### 3. Make `VocalEngine` consume `VocalPlan`

- Build plan once per job (new module, e.g. `app/generators/vocal_plan.py`).
- `VocalEngine` reads syllable events + pitch from the plan — no internal `build_lyric_timeline()` call.
- Procedural generator passes the same plan it exports to metadata.
- Future SVS / ACE adapters receive the same file; no renderer invents timing independently.

### 4. Draft karaoke / grid preview

- Workbench overlay: syllable grid on waveform or beat ruler.
- Proves timing **before** neural generation.
- Foundation for future line-level edit UI and “match to audio.”

### Exit criteria

- `VocalPlan` saved on every vocal job.
- Draft vocals audibly land on the beat for simple verse–chorus lyrics.
- Karaoke grid visually matches perceived syllable onset.
- No new model installs required.

---

## Deferred (only after Phase 0)

| Track | Notes |
|-------|-------|
| **SVS** (DiffSinger-style) | MIDI + lyrics → singing; consumes `VocalPlan` pitch/duration |
| **ACE stem + forced align** | Learn from / correct neural output against plan |
| **Time-warp / section re-sing** | Post-render alignment loop |
| **Voice cloning** | Timbre conversion (RVC / So-VITS) on SVS performance — **not** timing generation |

Do **not** start with RVC, So-VITS, or voice cloning. Model complexity before the timing contract exists wastes effort.

---

## First implementation issue

**Title:** Implement VocalPlan v0 and syllable-based lyric timing

**Scope:**

1. Define `VocalPlan` schema (Pydantic model + JSON serialization).
2. Implement `build_vocal_plan(lyrics, bpm, key, duration_beats, structure)` with syllable-weighted beat allocation.
3. Wire procedural generation to save `vocal_plan.json` per job.
4. Refactor `VocalEngine` to sample from `VocalPlan` syllables.
5. Add tests: syllable count, section boundaries, no equal-word regression.
6. (Stretch) Workbench syllable grid preview.

**Out of scope:** SVS subprocess, clone training, forced alignment, ACE plan input.

---

## File touch map (Phase 0)

| File | Change |
|------|--------|
| `app/generators/vocal_plan.py` | **New** — schema, builder, serialization |
| `app/generators/lyrics_timeline.py` | Syllable events; or fold into vocal_plan |
| `app/generators/vocal_engine.py` | Consume `VocalPlan` |
| `app/generators/procedural.py` | Build plan once; export to job metadata |
| `app/services/generation_service.py` | Persist plan path in job result |
| `app/web/static/workbench/` | Grid / karaoke preview |
| `tests/test_vocal_plan.py` | **New** — timing contract tests |

---

## Success metrics (Phase 0)

| Metric | Target |
|--------|--------|
| Plan persistence | 100% of vocal jobs write `vocal_plan.json` |
| Syllable coverage | Every lyric token syllabified or flagged |
| Timing sanity | Longer words ≠ longer beats; syllable count drives duration |
| Preview | Grid columns align with draft vocal onsets (informal listen test) |

---

## Related docs

- [`ROADMAP.md`](ROADMAP.md) — product phases
- [`ACE_STEP_SETUP.md`](ACE_STEP_SETUP.md) — neural render path (uses plan later)
- [`GENERATOR_ADAPTERS.md`](GENERATOR_ADAPTERS.md) — adapter pattern for future SVS
