# Roadmap

## Current product stack

- Parametric generator: instant drafts, tests, benchmarks, offline fallback.
- ACE-Step 1.5: primary local neural final render.
- Stable Audio 3 / Stable Audio Open: future secondary instrumental, loop, and sound-bed backend.
- YuE: research lane for lyrics-first full songs.
- MusicGen: legacy/simple baseline, not primary.

## Phase 1 — integrate existing model

- Use `auto-render` as the default generator.
- Route `quality=draft` to `procedural-v3`.
- Route `quality=balanced` and `quality=high` to `ace-step-command`.
- Keep procedural fallback available until ACE-Step can produce one local song reliably.

## Phase 2 — local style packs

Curated presets are the product-control layer before training:

- dark cinematic piano
- French disco
- heavy rap mixtape
- ambient post-indie
- retro electro
- trailer orchestra / cinematic cue

## Phase 3 — LoRA/fine-tuning only

Consider lightweight personalization only after local ACE rendering works:

- User uploads 3-10 owned/reference tracks.
- Train a LoRA/style adapter.
- Apply it to the ACE backend.

Allowed training material:

- user-owned music
- licensed stems
- public-domain or Creative Commons material compatible with the intended use
- in-house generated datasets

Do not train on commercial music without rights.

## V2.0 complete

- ACE-Step adapter seam
- functional CPU fallback
- model status endpoint
- expanded generation controls
- safe copy-over packaging

## V2.1

- real ACE runner script for a pinned ACE-Step checkout
- command health check
- generation progress callbacks where possible
- per-generator max duration/quality caps

## V2.2

- GPU worker process
- queue cancellation
- MP3 export through ffmpeg when available
- stronger prompt presets and lyric structure helper

## V3

- accounts and libraries
- cloud object storage
- billing/credits
- section regeneration
- stems and visualizer/video export

## Voice (Phase 0 MVP)

Syllable timing contract before SVS or cloning: [`VOICE_ROADMAP.md`](VOICE_ROADMAP.md)
