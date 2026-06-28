# Declarative Model-First Code Surface Best Practices

## Goal

Keep the AI Music Studio implementation easy for multiple agents to modify without accidental drift.

The code should be declarative, model-first, and contract-driven.

**Cross-cutting conventions** (enums, casing, Energy dimension, JobRecord alias, persistence, routes): see `09_CONTRACT_CONVENTIONS.md`.

## Core rule

Do not start by scattering UI state, API payloads, and database fields independently.

Start with domain models, enums, and explicit contracts.

```txt
Domain model → API schema → service boundary → UI surface
```

## Naming rules

Use consistent product terms:
- Category
- Concept
- MediaAsset
- Generation
- GenerationBatch
- Review
- DatasetSlice
- TrainingRun
- ModelArtifact
- StyleVersion
- Version Details

Do not use:
- bucket
- lineage
- ancestry
- random ad hoc synonyms

## Domain-first structure

Organize by domain, not by random helper functions.

Suggested FastAPI/Python shape:

```txt
app/
  domain/
    models.py
    enums.py
  api/
    routes/
      media.py
      categories.py
      concepts.py
      generations.py
      songs.py
      reviews.py
      slices.py
      model_status.py
  services/
    media_service.py
    category_service.py
    concept_service.py
    generation_service.py
    review_service.py
    slice_service.py
    model_adapter_service.py
  repositories/
    media_repository.py
    category_repository.py
    generation_repository.py
  adapters/
    ace_step_adapter.py
    procedural_adapter.py
```

For a TS/Fastify future:

```txt
packages/
  domain/
  db/
  api-spec/
  sdk/
apps/
  studio-web/
  api/
  model-worker/
```

## API surface rules

Every route should:
- accept typed request models
- return typed response models
- avoid leaking internal file paths unless intended
- include stable IDs
- include status fields for async jobs
- avoid ACE-specific details outside adapter/status payloads

Bad:

```json
{
  "thing": "foo",
  "data": {}
}
```

Good:

```json
{
  "id": "gen_123",
  "status": "SUCCEEDED",
  "output_path": "generated/gen_123.wav",
  "backend": "ACE_STEP",
  "model_version": "ace-step-1.5"
}
```

## Generated song rule

Every generated song must create:
1. a `Generation` record
2. a `MediaAsset` record with `kind = GENERATED_SONG`

Do not treat generated WAVs as disposable temp files.

## Version Details rule

Every generation should store:
- typed `VersionDetails` model in domain code
- normalized fields for querying
- frozen JSON snapshot for audit/history (`version_details` on records; `versionDetailsJson` in sidecar metadata)

Example (API JSON, snake_case):

```json
{
  "backend": "ACE_STEP",
  "model_version": "ace-step-1.5",
  "style_version_id": null,
  "training_run_id": null,
  "dataset_slice_id": null,
  "target_concept_id": "concept_dark_piano",
  "seed": 12345,
  "duration_seconds": 30
}
```

Legacy snapshots may use camelCase inner keys until normalized on read — new writes use snake_case only.

## Relationship metadata rule

Do not store media categories as string arrays.

Use assignment records with metadata:

```txt
MediaCategoryAssignment
MediaConceptAssignment
```

Each assignment carries:
- quality score
- fit score
- role
- reviewed flag
- notes
- confidence

## UI rules

UI should reflect the domain model:
- Workbench = categories/concepts/media assignments
- Generate = create generations/batches
- Songs = review generated media and version details
- Settings = runtime/model config

Avoid building isolated screens that hide core relationships.

## Declarative UI config

For repeated forms and tables, prefer explicit field definitions.

Example:

```ts
const mediaAssignmentFields = [
  { key: "categories", label: "Categories", type: "categorySearch" },
  { key: "qualityScore", label: "Quality", type: "score" },
  { key: "fitScore", label: "Fit", type: "score" },
  { key: "role", label: "Role", type: "select", options: assignmentRoleOptions },
  { key: "notes", label: "Notes", type: "textarea" }
]
```

This makes agents less likely to create inconsistent forms.

## Job rules

For MVP, **`JobRecord` is the Generation record** (`job_id`; `generation_id` alias). See `09_CONTRACT_CONVENTIONS.md`.

Async jobs should always have:
- id
- type
- status
- createdAt
- updatedAt
- error
- output reference if succeeded

Statuses:
- QUEUED
- RUNNING
- SUCCEEDED
- FAILED
- CANCELLED

## Adapter boundary rules

Only model adapters should know:
- ACE command templates
- ACE directories
- checkpoint paths
- subprocess behavior
- model-specific flags

Product services should call generic methods:
- generate
- getGenerationStatus
- train
- getTrainingStatus

## Testing rules

Each new surface needs at least:
- model validation test
- route contract test
- service happy-path test
- one failure-path test

For generation:
- creates Generation record (`JobRecord`)
- creates MediaAsset record
- preserves version details
- returns stable job status
- handles failure without losing metadata

## Migration rules

When adding fields:
- add enum/model first
- add persistence
- add API response
- add UI display
- add tests

Do not add UI-only fields that are not represented in the domain model.

## Agent safety rules

Agents should:
- run `git status --short` before editing
- avoid broad renames unless requested
- preserve current ACE generation path
- not delete model caches or generated outputs
- not start multiple heavy ACE jobs at once
- not mutate venv while generation is running
- commit/savepoint frequently if working locally

## Definition of done

A change is done when:
- domain model is updated
- API contract is updated
- service behavior is implemented
- UI displays/uses the field if relevant
- tests cover the path
- generated songs/media/version details remain intact
