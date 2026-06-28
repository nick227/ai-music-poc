# Codex Instruction — AI Music Studio Runtime and Contract Hardening

## Role

You are responsible for low-level runtime, tests, contracts, smoke tooling, and safe preservation of generated outputs.

Do not start unrelated product architecture work unless explicitly asked.

## Current direction

We are turning the ACE music POC into AI Music Studio.

Generated songs are first-class from day one. Every generated song should create:
1. a `Generation` record
2. a `MediaAsset` record with `kind = GENERATED_SONG`
3. saved Version Details

Use “Version Details,” not “lineage.”

**Conventions:** `09_CONTRACT_CONVENTIONS.md` (JobRecord = Generation for MVP, enum source of truth, casing).

## Primary objectives

1. Harden the current generation job path.
2. Preserve generated WAV outputs.
3. Ensure metadata/version details are captured reliably.
4. Add or update tests around generated song persistence.
5. Keep ACE-specific logic behind adapter/runtime boundaries.

## Do not do

Do not:
- create a separate training product
- create Node/Fastify architecture
- start Prisma work
- rename product terms broadly
- delete generated outputs
- delete model checkpoints
- run multiple ACE generations at once
- mutate the ACE venv while another generation is running

## Code surface rules

Follow declarative model-first practice:

```txt
Domain model → API schema → service behavior → tests
```

Avoid ad hoc JSON blobs unless they are intentionally frozen snapshots such as `versionDetailsJson`.

## Terms

Use:
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

Avoid:
- bucket
- lineage
- ancestry

## Suggested implementation tasks

### Task 1 — generation persistence contract

Verify that every successful generation:
- has a stable generation id (`job_id`; alias `generation_id`)
- writes output WAV to persistent storage
- creates/updates a Generation record (`JobRecord`)
- creates MediaAsset record with `kind = GENERATED_SONG`
- stores backend/model version/settings
- stores target concept/categories if supplied

### Task 2 — generation failure contract

Verify failed generation:
- keeps Generation record
- stores error
- does not create fake successful MediaAsset
- preserves request metadata for debugging

### Task 3 — smoke test preservation

Keep and extend smoke test output preservation:
- support explicit output path
- support persistent model output directory
- print final WAV path
- validate file size/duration/channel metadata where possible

### Task 4 — tests

Add focused tests:
- generation creates media asset
- generation stores version details
- generation status returns stable contract
- generated outputs are not temp-only
- failed generation keeps metadata

## Return format

When finished, return:
- changed files
- tests run
- failures or skipped areas
- any commands that trigger real ACE generation
- whether generated output was preserved
