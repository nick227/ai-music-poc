# Cursor Instruction — App Integration, API, and Model-First Surface

## Role

You are responsible for connecting product surfaces to the current app/API while keeping the implementation model-first and contract-driven.

## Direction

Build AI Music Studio around the current ACE-Step POC.

The app should expose:
- Workbench
- Generate
- Songs
- Settings

Generation is first-class. Generated songs must carry Version Details.

## Architecture for now

Use the current FastAPI backend for MVP unless explicitly told otherwise.

Do not introduce Node/Fastify or Prisma yet.

Future architecture can migrate to Node/Fastify + Python model worker, but current goal is proving the loop inside the existing stack.

## Backend surfaces to add/shape

Routes should be declarative and typed.

Suggested route groups:

```txt
/api/media
/api/categories
/api/concepts
/api/generations
/api/songs
/api/reviews
/api/slices
/api/model-status
```

## Required model behavior

### MediaAsset

Must support:
- imported audio
- generated songs
- clips/stems later
- review status
- rights status
- file path
- duration metadata if available

### Category / Concept

Must support:
- seeded top-level category dimensions
- many-to-many media assignments
- concepts as category combinations

### Generation

Must support:
- target concept
- target categories
- prompt
- lyrics
- backend
- seed/settings
- batch
- status
- output path
- Version Details

### Songs

A Song is a generated MediaAsset plus its Generation metadata and Review state.

## Version Details

Every Generation should preserve:
- backend
- model version
- style version id
- training run id
- dataset slice id
- target concept id
- target category ids
- prompt
- lyrics
- seed
- duration
- settings
- parent generation id
- batch id

Use UI/API field name:
- `version_details`

Do not use:
- `lineage`

## Declarative model-first rules

Implementation order:
1. domain enums/models
2. persistence shape
3. API request/response models
4. service layer
5. UI binding
6. tests

Avoid:
- UI-only fields with no model
- route-only JSON blobs that are not typed
- duplicated enum strings across frontend/backend
- ACE-specific fields leaking into generic product surfaces

## Initial implementation slices

### Slice 1 — Media Inbox

- upload one or more audio files
- list unreviewed media
- quick assign categories/concepts
- quality/fit/role/notes
- save + next

### Slice 2 — Generate with version details

- generate from target concept/category context
- create Generation immediately
- save output
- create generated MediaAsset
- show generated song in Songs

### Slice 3 — Songs review

- list generated songs
- play output
- display Version Details
- review decision
- category/concept assignment

## Tests

Add tests for:
- media import creates MediaAsset
- category assignment stores relationship metadata
- generation creates Generation + MediaAsset
- version_details are stored
- songs list includes generated outputs
- review updates decision/status

## Do not do

Do not:
- create separate training app
- start Prisma or Node migration
- delete current ACE generation path
- break existing smoke tests
- remove procedural fallback
- use bucket/lineage terminology
- start real ACE batch jobs without clear operator intent

## Return format

Return:
- changed files
- route list
- model/schema changes
- tests run
- any breaking changes
- current local run instructions
