# PM Brief — AI Music Studio

## One-line product definition

AI Music Studio is a local music generation lab where users import and categorize audio, define musical concepts, generate songs, review outputs, and evolve style/model versions over time.

## Current starting point

We currently have a working local ACE-Step music generation POC:
- FastAPI backend
- ACE-Step adapter / runner
- procedural fallback engine
- generation jobs
- WAV outputs
- model status and smoke-test tooling

This proves the generation engine can run locally. The next step is to build the Studio around it.

## Product center of gravity

The product is not primarily a training dashboard.

The rough split is:

```txt
80% = audio media management, categories, concepts, relationships, review, generated song history
20% = fine-tune runs, model artifacts, style versions, training monitoring
```

The generated song is the peak user experience. The media/category system is the operating system that makes better generations possible.

## Core loop

```txt
Import audio
→ categorize media
→ define concepts
→ generate songs
→ review songs
→ create dataset slices
→ fine-tune style versions
→ generate better songs
→ review again
```

## Product surfaces

### Workbench

The operating surface for:
- categories
- concepts
- media inbox
- quick categorization
- category/concept coverage
- pipeline state

### Generate

The first-class generation surface:
- target concept
- target categories
- prompt
- lyrics
- backend
- duration
- quality mode
- seed
- batch count
- purpose

Purposes:
- baseline
- concept test
- prompt test
- style evaluation
- version comparison
- keeper candidate

### Songs

Generated song library:
- review queue
- audio playback
- version details
- prompt/lyrics/settings
- decisions
- category/concept fit
- batch history

### Settings

Operational configuration:
- ACE status
- model paths
- backend config
- generation limits
- storage paths

Training can be exposed once the media/generation/review loop is stable.

## Important terminology

Use:
- Category
- Concept
- Media
- Song
- Generation
- Batch
- Version
- Style Version
- Dataset Slice
- Training Run

Do not use in UI:
- bucket
- lineage
- ancestry
- build chain

“Version Details” is the user-facing term for what created a generated song.

## Day-one user experience

On day one, the user has seeded categories but no audio.

They should:
1. Open Workbench.
2. Pick or create one concept they care about.
3. Import 3–8 reference audio files.
4. Quickly assign categories/concepts, quality, fit, role, and notes.
5. Generate a baseline ACE song against that concept.
6. Review the output.
7. Save the generated song with Version Details.

No fine-tuning is required on day one.

## First fine-tune target

Do not wait for a massive corpus before proving training.

First calibration run:
- 8–12 focused tracks
- one narrow concept
- baseline generations saved first
- reviewed media only
- clear quality/fit scores

The goal is to prove the full loop:

```txt
slice → train → artifact/style version → generate → review
```

## Later maturity

After a few GB of categorized audio, the platform becomes a slice recommendation engine:
- find high-quality/high-fit media
- create focused dataset slices
- compare training slices
- evaluate model/style versions against consistent prompts
- diagnose which categories/concepts are improving or failing

## MVP success criteria

The MVP succeeds when a user can:
1. Import multiple audio files.
2. Assign categories and concepts quickly.
3. Generate an ACE song against a concept.
4. Save the generated song as a first-class media asset.
5. Review the song.
6. See its Version Details.
7. Reuse generated songs as references, rejects, negative examples, keepers, or training candidates.

## Non-goals for MVP

Do not prioritize:
- billing
- multi-user permissions
- hosted scaling
- LoRA config complexity
- advanced waveform editing
- real-time loss charts
- AI auto-tagging
- complex dashboard views
- training automation before the media/generation/review loop is stable
