# Antigravity / Claude Instruction — Studio UI and Product Loop

## Role

You are responsible for product flow, Studio UI, and user-facing workflow clarity.

**Conventions:** `09_CONTRACT_CONVENTIONS.md`. **Do not scaffold Vite/React yet** — design component architecture and flows; implement UI against stable backend contracts unless static UI blocks progress.

## Current direction

The ACE music POC is becoming AI Music Studio.

The product is:
- 80% media/category/concept management
- 20% fine-tune/training orchestration
- generation is the emotional peak and must be first-class from day one

The generator is not a separate app. It is a core section inside Studio.

## Main surfaces

Design around:

```txt
Workbench
Generate
Songs
Settings
```

### Workbench

For:
- media inbox
- quick categorization
- categories
- concepts
- coverage states
- assignment/review

### Generate

For:
- target concept
- target categories
- prompt
- lyrics
- backend
- seed/settings
- purpose
- small batch generation

### Songs

For:
- generated song library
- playback
- review
- Version Details
- decisions
- category/concept assignments

### Settings

For:
- ACE status
- model/backend paths
- runtime config

## Terminology

Use:
- Category
- Concept
- Media
- Song
- Generation
- Batch
- Version
- Version Details

Do not use:
- bucket
- lineage
- ancestry

## UI requirements

### Media Inbox

Primary user case:
- user uploads one or more audio files
- files enter inbox
- user quickly assigns categories/concepts

Must support:
- file list
- audio player
- category/concept search
- chips
- quality score
- fit score
- role
- notes
- Save + Next
- batch apply

### Generate screen

Must support:
- target concept/categories
- purpose: baseline, concept test, prompt test, style evaluation, keeper candidate
- backend: ACE/procedural
- prompt
- lyrics
- duration
- seed
- batch count if feasible

Generated songs must be saved and sent to Songs.

### Songs screen

Must support:
- generated song list
- play audio
- review status
- decision
- version details
- prompt/lyrics display
- category/concept assignment

## Declarative UI best practices

Avoid one-off uncontrolled forms. Prefer declarative field configs and shared components:
- ScoreInput
- CategorySearch
- ConceptSearch
- RoleSelect
- MediaPlayer
- VersionDetailsPanel
- ReviewDecisionBar
- SaveAndNextControls

## First MVP flow

1. User opens Workbench.
2. User selects or creates a concept.
3. User imports audio.
4. User assigns categories/concepts quickly.
5. User goes to Generate.
6. User generates baseline song.
7. User reviews generated song in Songs.
8. User sees Version Details.

## Do not do

Do not:
- build a separate training app
- overbuild dashboards
- start advanced waveform editor
- add billing/auth/multi-user work
- add real-time training charts
- bury generation under training
- use “lineage” in UI

## Return format

Return:
- proposed UI surfaces
- changed files
- screenshots/route names if applicable
- tests run
- known gaps
