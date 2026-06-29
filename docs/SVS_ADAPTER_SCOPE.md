# SVS Adapter — Implementation Scope (Phase 1)

Scope for the first **controlled vocal renderer** that consumes `vocal_plan.json`. This is Phase 1 step 1 in [`VOICE_ROADMAP.md`](VOICE_ROADMAP.md).

**Prerequisite:** Phase 0 manual listen sign-off on the three golden cases (`pop_chorus`, `rap_dense`, `ballad_held`).

---

## Goal

Replace procedural formant vocals with a **neural SVS stem** driven by the existing VocalPlan timing contract — without changing how plans are built or how ACE works.

```
lyrics → prosody → VocalPlan → SVS adapter → vocal_stem.wav → mix
```

ACE remains separate:

```
lyrics/prompt → ACE → audio   (no VocalPlan input)
```

---

## Non-Goals (Phase 1)

| Item | Why deferred |
|------|----------------|
| Voice cloning (RVC, So-VITS) | Timbre layer on top of correct performance — not timing |
| Forced alignment / `observed_vocal_plan.json` | Phase 1 step 2 |
| Time-warp / section re-sing | Needs observed plan first |
| ACE consuming VocalPlan | Architectural rule — ACE is end-to-end neural |
| Bundling SVS weights in the app repo | Follow ACE pattern: user-installed backend + command adapter |
| Real-time / streaming SVS | Batch render per job is enough for MVP |

---

## Architectural Decision

### Two layers, not one monolithic generator

| Layer | Responsibility | Protocol |
|-------|----------------|----------|
| **Plan builder** (exists) | `build_vocal_plan()` → `vocal_plan.json` | `VocalPlan` pydantic models |
| **Vocal renderer** (new) | `VocalPlan` → `vocal_stem.wav` | `VocalRenderer` protocol |
| **Song assembler** (exists, extended) | Instrumental + vocal stem → `song.wav` | `ProceduralGenerator` or thin hybrid |

Do **not** put SVS inference inside API routes. Mirror the ACE adapter layout:

```
app/generators/svs/
  adapter.py          # SvsCommandGenerator (MusicGenerator façade)
  vocal_renderer.py   # VocalRenderer protocol + orchestration
  plan_export.py      # VocalPlan → SvsScore
  g2p_en.py           # syllable/lyric → phoneme tokens (English v1)
  health.py           # readiness probe (like ace_step/health.py)
  command_builder.py  # SVS_COMMAND_TEMPLATE substitution
scripts/svs_runner.py # thin CLI entrypoint for external backends
```

### MVP delivery surface

Ship in this order:

1. **`vocal_demo` + generator `svs-vocal`** — vocal stem only from plan (fastest validation loop).
2. **`svs_score.json` export** — backend-neutral score beside every SVS job (debug + future backends).
3. **Hybrid `procedural-svs` song mode** — procedural instrumental bed + SVS vocal stem mixed to `song.wav`.

`auto-render` stays unchanged (draft procedural / final ACE). SVS is a **separate controlled path**, not a replacement for ACE finals.

---

## VocalPlan → SVS Input Mapping

### What VocalPlan already provides

| VocalPlan field | SVS use |
|-----------------|---------|
| `bpm` | Beat grid → seconds (`sec = beat * 60/bpm`) |
| `key` | Transpose reference (optional; pitch already in MIDI) |
| `duration_beats` | Output padding / total timeline |
| `sections[].name` | Expression flags later (verse vs chorus timbre) |
| `lines[].syllables[]` | Note + lyric events |
| `PlanSyllable.text` | Lyric token (syllable chunk) |
| `PlanSyllable.pitch_midi` | Target pitch |
| `PlanSyllable.beat_start` / `beat_duration` | Note onset + duration |
| `PlanSyllable.stressed` | Velocity / phoneme emphasis |
| `PlanSyllable.phrase_end` | Slur boundary / breath insert |
| `PlanLine.rest_beats_after` | Explicit rest events |

### What SVS backends additionally need

| Gap | Phase 1 approach |
|-----|------------------|
| **Phonemes** | New `g2p_en.py`: syllable text → ARPAbet/IPA phoneme list (`g2p-en` or `phonemizer` + espeak-ng) |
| **Note names** | `midi_to_note_name(pitch_midi)` → `C4`, `F#4`, `rest` |
| **Durations in seconds** | `beat_duration * 60 / bpm` |
| **Slur flags** | `is_slur=1` when next syllable shares word and no phrase_end |
| **Language** | English v1 only (matches Phase 0 syllabification) |

### Intermediate contract: `SvsScore` v1

Backend-neutral JSON written as `{stem}_svs_score.json`:

```json
{
  "version": 1,
  "bpm": 118,
  "language": "en",
  "duration_beats": 48.0,
  "events": [
    {
      "type": "note",
      "syllable_text": "walk",
      "phonemes": ["W", "AO", "K"],
      "midi": 69,
      "note_name": "A4",
      "start_beats": 0.25,
      "duration_beats": 0.50,
      "stressed": true,
      "phrase_end": false
    },
    {
      "type": "rest",
      "start_beats": 4.10,
      "duration_beats": 0.30
    }
  ]
}
```

Exporters translate `SvsScore` → backend payloads:

| Backend | Payload shape |
|---------|----------------|
| DiffSinger e2e | `text`, `notes`, `notes_duration`, `input_type` |
| DiffSinger phoneme | `ph_seq`, `note_seq`, `note_dur_seq`, `is_slur_seq` |
| NNSVS / HTS labels | `.lab` full-context labels per phoneme |
| Command runner | Pass `svs_score.json` path; runner owns translation |

**Rule:** `plan_export.py` is the only module that reads `VocalPlan`. Backends never parse `vocal_plan.json` directly.

---

## Backend Candidates

| Backend | Pros | Cons | MVP fit |
|---------|------|------|---------|
| **DiffSinger** (OpenCpop e2e) | Mature MIDI+lyric SVS, documented raw-input API | Chinese-trained checkpoints; English needs custom model or poor quality | **Reference adapter** via command runner |
| **NNSVS** + English support | Explicit MIDI/label pipeline, English community tooling | No shipped pretrained English voicebank; training-heavy | **Long-term** English path |
| **ONNX / in-process** | Lowest latency, no subprocess | Large deps, GPU packaging, model licensing | Defer to Phase 1.5 |
| **Hosted API** | No local GPU | Cost, latency, vendor lock | Out of scope |

### Recommendation

**Phase 1 MVP:** ACE-style **command adapter** + `scripts/svs_runner.py`.

- App ships: plan export, G2P, health checks, subprocess orchestration, stem validation.
- User installs: DiffSinger (or future NNSVS voicebank) in a separate venv, points env vars at it.
- Default when SVS not ready: **procedural vocal fallback** (same pattern as `ace_allow_fallback`).

English quality will be limited until we ship or document a trained English checkpoint. Phase 1 success = **correct note/phoneme timing on the stem**, measured with existing `assert_vocal_stem_timing()` — not commercial vocal timbre.

---

## `VocalRenderer` Protocol

```python
class VocalRenderer(Protocol):
    name: str

    def info(self) -> VocalRendererInfo: ...

    def render(
        self,
        plan: VocalPlan,
        *,
        output_path: Path,
        request: GenerationRequest,
    ) -> VocalRenderResult: ...
```

`VocalRenderResult` metadata (stored on job result):

| Key | Purpose |
|-----|---------|
| `vocal_backend` | `svs-command`, `procedural-fallback`, … |
| `vocal_plan_file` | unchanged |
| `svs_score_file` | `{stem}_svs_score.json` |
| `vocal_stem_file` | `{stem}_vocal_stem.wav` |
| `svs_elapsed_seconds` | perf |
| `svs_stdout_tail` / `svs_stderr_tail` | debug |
| `fallback_reason` | when procedural substitute used |

---

## Config (mirror ACE)

Add to `app/core/config.py` / `.env`:

| Variable | Purpose |
|----------|---------|
| `SVS_ENABLED` | Feature flag |
| `SVS_PYTHON` | External venv python |
| `SVS_SCRIPT` | Default `./scripts/svs_runner.py` |
| `SVS_COMMAND_TEMPLATE` | Optional full override |
| `SVS_MODEL_DIR` | Checkpoints root |
| `SVS_TIMEOUT_SECONDS` | Subprocess cap |
| `SVS_ALLOW_FALLBACK` | Procedural vocal when backend missing |
| `SVS_SAMPLE_RATE` | Expected output (resample on mix if ≠ 44100) |

Health endpoint: `GET /api/svs/runtime` (parallel to ACE runtime) — deps, GPU, checkpoint presence, smoke render.

---

## Implementation Slices

### Slice 1 — Plan export + mock renderer (no GPU) **shipped**

**Deliverables**

- `app/generators/svs/plan_export.py` — `vocal_plan_to_score(plan) -> SvsScore`
- `app/generators/svs/g2p_en.py` — English phoneme tokens (deterministic heuristic, no new deps)
- `app/generators/svs/mock_audio.py` + `MockSvsRenderer` — sine-burst debug stem
- `scripts/render_svs_mock_stem.py` — manual QA
- Golden fixtures: `tests/fixtures/svs_score/{pop_chorus,rap_dense,ballad_held}.json`
- Tests: `tests/test_svs_slice1.py`

**Exit:** Given golden VocalPlan fixtures, `SvsScore` round-trips and mock stem passes `assert_vocal_stem_timing()`.

**Do not start Slice 2** until Slice 1 is reviewed and Phase 0 manual sign-off is done.

### Slice 2 — Command adapter + `svs-vocal` generator

**Deliverables**

- `SvsCommandGenerator` registered in `registry.py`
- `scripts/svs_runner.py` — reads `svs_score.json`, calls DiffSinger inference script, writes WAV
- `svs/health.py` + API route
- Job metadata + bundle include `svs_score.json` and `vocal_stem.wav`
- `mode=vocal_demo` + `generator=svs-vocal` works end-to-end

**Exit:** With DiffSinger installed, `vocal_demo` job produces neural stem; without it, fallback or clear error per `SVS_ALLOW_FALLBACK`.

### Slice 3 — Hybrid song (`procedural-svs`)

**Deliverables**

- Refactor procedural loop: `render_instrumental_frames()` vs `render_vocal_frames()`
- New generator `procedural-svs` or request flag `vocal_backend: svs`
- Mix SVS stem at `vocal_intensity`; respect line rests (stem silence already in score)
- Re-use `assert_vocal_stem_timing()` regression suite on SVS stems

**Exit:** `pop_chorus` song mode produces full mix with neural vocal on planned beats.

### Slice 4 — Quality gates

**Deliverables**

- `tests/test_svs_plan_export.py` — score snapshots for 3 golden cases
- `tests/test_svs_adapter.py` — mock subprocess, fallback policy
- Extend `test_vocal_audio_energy.py` parametrized for `generator=svs-vocal` (skip if SVS not installed; mark `@pytest.mark.svs`)
- `scripts/regenerate_vocal_listen_demos.py --generator svs-vocal` flag

---

## Procedural Integration (Slice 3 detail)

Current procedural path interleaves instrumental + vocal per sample in one loop (`_sung_voice` at line ~741). Hybrid mode needs:

```
1. build_vocal_plan()                    # unchanged
2. render instrumental-only buffers      # skip _sung_voice when svs_backend set
3. VocalRenderer.render(plan) → stem wav
4. align/resample stem to 44100 if needed
5. mix: instrumental + stem * vocal_amp  # same sidechain/reverb sends as today
6. save vocal_plan.json, svs_score.json, vocal_stem.wav, song.wav
```

Keep `VocalEngine` as fallback backend implementing `VocalRenderer` for zero-dep dev.

---

## UI / API (minimal)

| Change | Scope |
|--------|-------|
| Generator dropdown | Add `svs-vocal` (hidden/disabled when `SVS_ENABLED=false`) |
| Generate page hint | "SVS uses VocalPlan timing; install backend per docs" |
| Job status | `vocal_stem_url`, `svs_score_url` download routes (mirror vocal-plan) |
| Workbench grid | No change — still reads `vocal_plan.json` |

No new singing_voice enum values in Slice 1–2. `singing_voice` maps to backend speaker/checkpoint later (Phase 1.5).

---

## Risks & Open Questions

| Risk | Mitigation |
|------|------------|
| No good English pretrained SVS | Ship timing-correct adapter first; document training path; accept fallback |
| G2P mismatch vs syllabification | Single `g2p_en` module; golden tests on phoneme sequences |
| Sample rate mismatch (24k vs 44.1k) | Resample stem at mix; validate with ffprobe |
| SVS slower than procedural | Async jobs already exist; timeout + progress logs |
| DiffSinger Chinese model on English lyrics | Label as experimental; do not block Slice 1–2 on timbre quality |

**Open questions for sign-off**

1. **First backend to wire in `svs_runner.py`:** DiffSinger e2e (fastest docs) vs wait for English NNSVS voicebank?
2. **Hybrid generator name:** `procedural-svs` vs extend `procedural-v3` with `vocal_backend` request field?
3. **Auto-render:** Should `balanced` ever route to SVS, or stay ACE-only for finals?

Default recommendations: DiffSinger for Slice 2 reference; separate `procedural-svs` generator; keep `auto-render` on ACE for finals.

---

## File Touch Map

| File | Slice | Change | Status |
|------|-------|--------|--------|
| `app/generators/svs/plan_export.py` | 1 | `VocalPlan` → `SvsScore` | done |
| `app/generators/svs/g2p_en.py` | 1 | English phonemes | done |
| `app/generators/svs/vocal_renderer.py` | 1 | `MockSvsRenderer` | done |
| `app/generators/svs/mock_audio.py` | 1 | Sine-burst debug stem | done |
| `scripts/render_svs_mock_stem.py` | 1 | Manual mock stem QA | done |
| `tests/test_svs_slice1.py` | 1 | Score + mock stem tests | done |
| `app/generators/svs/adapter.py` | 2 | `SvsCommandGenerator` | pending |
| `app/generators/svs/command_builder.py` | 2 | Template substitution |
| `app/generators/svs/health.py` | 2 | Readiness probe |
| `scripts/svs_runner.py` | 2 | External backend CLI |
| `app/generators/registry.py` | 2 | Register generators |
| `app/core/config.py` | 2 | `SVS_*` settings |
| `app/api/routes/svs_runtime.py` | 2 | Health API |
| `app/generators/procedural.py` | 3 | Instrumental/vocal split + mix |
| `app/services/bundle_service.py` | 2 | Bundle `svs_score.json` |
| `app/api/routes/files.py` | 2 | Download routes |
| `tests/test_svs_*.py` | 1–4 | Export + adapter tests |
| `docs/SVS_SETUP.md` | 2 | Install guide (like ACE_STEP_SETUP) |

---

## Related Docs

- [`VOICE_ROADMAP.md`](VOICE_ROADMAP.md) — Phase 0 / Phase 1 sequence
- [`GENERATOR_ADAPTERS.md`](GENERATOR_ADAPTERS.md) — `MusicGenerator` protocol
- [`ACE_STEP_SETUP.md`](ACE_STEP_SETUP.md) — pattern to copy for external backend setup
