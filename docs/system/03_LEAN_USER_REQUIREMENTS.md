# Lean User Requirements — AI Music Studio MVP

## Primary user

A local creator/operator building an AI music library and generation workflow around ACE-Step.

The user wants to:
- import audio references
- classify/categorize them quickly
- generate songs
- review output quality
- track which model/style/prompt versions produced which songs
- eventually fine-tune style versions from curated slices

## Core user jobs

### Job 1 — Import audio

As a user, I want to add one or more audio files so that they become manageable media assets.

Requirements:
- Import one file or multiple files.
- Create `MediaAsset` records.
- Store file paths.
- Extract at least basic metadata: filename, extension, duration if available.
- Mark imported assets as `NEEDS_REVIEW` or `NEEDS_CATEGORIZATION`.
- Do not require complete categorization during upload.

### Job 2 — Quickly categorize audio

As a user, I want to assign categories and concepts quickly so that audio becomes reusable evidence.

Requirements:
- Search categories and concepts.
- Add category/concept chips.
- Support multiple assignments per asset.
- Capture quality score.
- Capture fit score.
- Capture role.
- Capture notes.
- Provide Save + Next.
- Support batch apply to selected assets.

Roles:
- reference
- gold_reference
- training_candidate
- generated_test
- negative_example
- edge_case
- keeper
- reject

### Job 3 — Manage category/concept coverage

As a user, I want to see which categories/concepts are empty, thin, usable, strong, confused, or need cleanup.

Requirements:
- Show seeded categories.
- Show concepts as category combinations.
- Show media count.
- Show reviewed count.
- Show strong references count.
- Show generated tests count.
- Show coverage state.

Coverage states:
- empty
- thin
- usable
- strong
- confused
- needs_cleanup

### Job 4 — Generate songs

As a user, I want to generate songs from a prompt, lyrics, backend, and target concept/categories.

Requirements:
- Generate from current ACE backend.
- Support procedural fallback where appropriate.
- Select target concept.
- Select target categories.
- Capture prompt and lyrics.
- Capture seed.
- Capture duration.
- Capture backend.
- Capture quality mode.
- Capture purpose.
- Create a `Generation` record immediately.
- Save output WAV.
- Save generated song as `MediaAsset.kind = generated_song`.

Generation purposes:
- baseline
- concept_test
- prompt_test
- style_evaluation
- version_comparison
- keeper_candidate

### Job 5 — Review generated songs

As a user, I want to listen to generated songs and decide what they are good or bad for.

Requirements:
- Play audio.
- View prompt/lyrics/settings.
- View Version Details.
- Assign categories/concepts to generated song.
- Score overall quality.
- Score category/concept fit.
- Add tags/issues.
- Add notes.
- Set decision.

Decisions:
- keeper
- reject
- compare
- promote
- use_as_reference
- use_as_negative
- regenerate

### Job 6 — View generated song history

As a user, I want generated songs to be searchable and filterable.

Requirements:
- Filter by concept.
- Filter by category.
- Filter by backend.
- Filter by batch.
- Filter by review status.
- Filter by decision.
- Filter by score.
- Filter by created date.

### Job 7 — Track Version Details

As a user, I want every generated song to show what created it.

Requirements:
- Show backend.
- Show model version.
- Show style version if any.
- Show training run/version if any.
- Show dataset slice if any.
- Show target concept/categories.
- Show prompt version or prompt text.
- Show lyrics.
- Show seed.
- Show settings.
- Show parent generation if any.
- Show batch if any.

Use UI label: `Version Details`.

### Job 8 — Create dataset slices

As a user, I want to create dataset slices from category/concept filters so that training can consume curated media.

Requirements:
- Select category/concept filters.
- Set minimum quality.
- Set minimum fit.
- Select roles.
- Preview matching media.
- Save as DatasetSlice.

### Job 9 — Run first calibration training

As a user, I want to run a small focused training experiment once a concept has enough reviewed audio.

Requirements:
- Select dataset slice.
- Select backend/base model.
- Create training run record.
- Capture config.
- Track status.
- Register produced artifact/style version manually if automation is not ready.
- Generate comparison outputs after training.

This can be deferred until after media/generation/review MVP is stable.

## MVP screens

### Workbench

- categories
- concepts
- media inbox
- quick categorizer
- pipeline state

### Generate

- target concept/categories
- prompt
- lyrics
- backend
- settings
- generate single or small batch

### Songs

- generated song library
- review queue
- version details
- decisions

### Settings

- model status
- ACE config
- storage paths

## MVP non-requirements

The MVP does not need:
- multi-user auth
- billing
- cloud storage
- public publishing
- waveform editor
- automatic audio tagging
- stem separation
- real-time training charts
- advanced LoRA configuration UI
- large-scale queue management
