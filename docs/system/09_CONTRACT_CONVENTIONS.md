# Contract Conventions — Enums, Casing, Structure, and MVP Decisions

This document is the source of truth for cross-agent implementation conventions. When other docs conflict on enums, casing, persistence, or generation identity, follow this file.

## MVP direction decisions (locked)

### Generation identity

For MVP, **`JobRecord` is the runtime Generation record**. Do not refactor or rename it yet.

- Preserve existing **`job_id`** contracts and tests (`POST /api/generate`, `GET /api/jobs/{job_id}/status`, etc.).
- Expose **`generation_id`** as an alias where product surfaces need Studio terminology (e.g. `/api/generations/{id}`, `MediaAsset.generation_id`, Version Details).
- Alias rule: `generation_id === job_id` for all current and near-term records.
- Split `JobRecord` vs a separate persisted `Generation` entity only if the domain later requires it.

### Version Details

- Add and use a typed Pydantic **`VersionDetails`** model in domain code.
- Persist as JSON on `JobRecord` and `MediaAsset`; do not require a separate DB table for MVP.
- API wire field name: **`version_details`** (snake_case).
- User-facing label: **Version Details**. Do not use `lineage`, `ancestry`, or `bucket`.

### UI stack

- Do **not** scaffold Vite/React yet.
- Keep the current static UI for proof-of-flow.
- **Antigravity** designs Workbench / Generate / Songs component architecture.
- UI implementation waits for stable backend contracts unless the static UI becomes a blocker.

### Persistence

- Keep current **JSON file stores** through the immediate generation / version-details slice.
- Category / Concept / Assignment may use JSON on first pass.
- Introduce **SQLite** only as a scoped upgrade when many-to-many assignment storage becomes awkward — not as a broad rewrite upfront.

### Routes

- **Wrap** existing routes; do **not** replace them.
- Keep: `POST /api/generate`, `GET /api/jobs/{job_id}/status`, job download routes, smoke-test contracts.
- Add product views as wrappers: `/api/media`, `/api/categories`, `/api/concepts`, `/api/generations/{id}`, `/api/songs`, `/api/reviews`.

### Agent ownership

| Agent | Owns |
|-------|------|
| **Cursor** | Backend, API, contracts, integration, domain models, services, route wrappers |
| **Antigravity** | UI product flow, component architecture, Workbench/Generate/Songs/Settings design |
| **Codex** | Runtime hardening, persistence contracts, smoke tooling, generation output preservation, focused tests |

## Enum source of truth

All product enums are defined once in Python domain code and imported everywhere else. Do not duplicate enum string literals in routes, services, UI, or tests.

**Canonical location (target layout):**

```txt
app/domain/enums.py      # str Enums: CategoryDimension, AssignmentRole, ReviewDecision, etc.
app/domain/models.py     # Pydantic models composing enums + VersionDetails
app/domain/seeds.py      # seeded Category rows per dimension (optional first-pass fixture)
```

Until `enums.py` is split out, new enums may live in `models.py` but must be moved to `enums.py` when the taxonomy slice lands — not re-declared in route files.

**Rules:**

- Enum values use **`SCREAMING_SNAKE_CASE`** string values (e.g. `"GENERATED_SONG"`, `"NEEDS_REVIEW"`).
- API JSON uses the enum **value** string, not Python member names.
- Frontend / static UI must consume values from API responses or a generated OpenAPI spec — never hard-code parallel enum lists.
- When adding an enum member, update: domain enum → persistence compatibility → API models → tests. UI last.

## Casing conventions

| Layer | Convention | Example |
|-------|------------|---------|
| Python models / fields | `snake_case` | `target_concept_id`, `version_details` |
| API request/response JSON keys | `snake_case` | `"review_status"`, `"version_details"` |
| Enum values | `SCREAMING_SNAKE_CASE` | `"GOLD_REFERENCE"` |
| Domain record IDs | prefixed slugs | `media_…`, `cat_…`, `concept_…`, job hex id |
| Metadata audit alias (legacy) | `versionDetailsJson` | duplicate frozen snapshot in sidecar metadata files only |

### Version Details field mapping

Typed `VersionDetails` uses **snake_case** in Python and **snake_case** in API JSON going forward.

| Python / API field | Notes |
|--------------------|-------|
| `generation_id` | alias of `job_id` |
| `backend` | model backend or generator key |
| `model_version` | engine / checkpoint label |
| `style_version_id` | optional |
| `training_run_id` | optional |
| `dataset_slice_id` | optional |
| `model_artifact_id` | optional |
| `target_concept_id` | optional |
| `target_category_ids` | list of category ids |
| `prompt` | generation prompt |
| `lyrics` | generation lyrics |
| `negative_prompt` | optional |
| `seed` | optional int |
| `duration_seconds` | optional |
| `settings` | nested object (snake_case keys) |
| `parent_generation_id` | optional |
| `batch_id` | optional |
| `generator_name` | resolved generator |
| `output_file` | WAV file name |

**Legacy snapshots** written before this convention may contain **camelCase** inner keys (`modelVersion`, `targetConceptId`, …). Readers should normalize on load; new writes use snake_case only.

## Category dimensions (including Energy)

Seeded top-level dimensions:

```txt
Genre
Mood
Instrument
Technique
Production
Mix
Rhythm
Vocals
Arrangement
Energy
Quality Issue
Training Role
```

`CategoryDimension` enum value: **`ENERGY`** (display label: Energy).

Energy was referenced in concept examples but was missing from the original seed list — it is now a first-class dimension (e.g. Energy / Low, Energy / High).

## Current repository structure (MVP baseline)

What exists today and should be extended, not replaced:

```txt
app/
  domain/
    models.py           # JobRecord, MediaAsset, GenerationRequest, partial studio enums
    presets.py          # generation presets (not taxonomy seeds)
  api/routes/
    generate.py         # POST /api/generate
    jobs.py             # job status, list, log
    model_status.py     # ACE wiring / probe
    files.py            # download / bundle
    health.py, generators.py, presets.py, analyze.py, lyrics.py
  services/
    generation_service.py   # run_job, version_details, MediaAsset on success
    job_service.py
  storage/
    local_job_store.py      # JSON job records
    local_media_store.py    # JSON media assets
    local_file_store.py     # WAV outputs
    metadata_store.py       # sidecar generation metadata
  generators/               # ACE adapter, procedural, registry
  web/static/               # single-page static UI (keep for proof-of-flow)
tests/
  test_studio_api_contract.py
  test_generation_persistence_contract.py
  … ACE / procedural smoke tests
```

**Not yet present (planned by Cursor, Slice 1):**

```txt
app/domain/enums.py           # CategoryDimension, AssignmentRole, CoverageState, …
app/domain/seeds.py             # category dimension seeds
app/api/routes/media.py
app/api/routes/categories.py
app/api/routes/concepts.py
app/storage/category_store.py   # JSON first pass
app/storage/concept_store.py
app/storage/assignment_store.py
app/services/media_service.py
app/services/category_service.py
app/services/concept_service.py
```

## Product term → code mapping

| Product term | MVP code entity | Notes |
|--------------|-----------------|-------|
| Generation | `JobRecord` | `job_id` / `generation_id` |
| Song | `MediaAsset` where `kind == GENERATED_SONG` | plus linked job + review |
| Version Details | `VersionDetails` / `version_details` | typed model, JSON storage |
| Category | `Category` | seeded dimensions |
| Concept | `Concept` + `ConceptCategory` links | category combination |
| Assignment | `MediaCategoryAssignment`, `MediaConceptAssignment` | not string arrays on media |

## Definition of done (contract change)

A contract change is complete when:

1. Enum/model updated in `app/domain/`
2. Persistence read/write path exists (JSON OK for MVP)
3. Typed API request/response models added
4. Service layer implements behavior
5. Route wrapper exposed (existing routes unchanged unless explicitly versioned)
6. Contract test covers happy path
7. No duplicated enum literals outside domain
