# Cursor Instruction — App Integration, API, and Model-First Surface

## Role

You are responsible for connecting product surfaces to the current app/API while keeping the implementation model-first and contract-driven.

**Locked conventions:** read `09_CONTRACT_CONVENTIONS.md` before changing domain, API, or persistence.

## Direction

Build AI Music Studio around the current ACE-Step POC.

The app should expose:
- Workbench
- Generate
- Songs
- Settings

Generation is first-class. Generated songs must carry Version Details.

## MVP decisions (do not override without explicit ask)

- **`JobRecord` = runtime Generation** — keep `job_id` contracts; expose `generation_id` alias where useful.
- **`VersionDetails`** — typed Pydantic model; API field `version_details`; stored as JSON.
- **Persistence** — JSON stores for now; SQLite only as scoped upgrade for assignment awkwardness.
- **Routes** — wrap existing generation/job routes; add product views (`/api/media`, `/api/songs`, …).
- **UI** — no Vite/React scaffold; backend contracts first; static UI proof-of-flow only.
- **Agent split** — Cursor owns backend/API/integration; Antigravity owns UI architecture; Codex owns runtime/smoke/tests.

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

**Preserve unchanged:** `POST /api/generate`, `GET /api/jobs/{job_id}/status`, download routes, existing contract tests.

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
- seeded top-level category dimensions (including **Energy** — see `09_CONTRACT_CONVENTIONS.md`)
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

MVP implementation: extend **`JobRecord`** / generation service — do not rename to a separate entity yet.

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
- `version_details` (snake_case keys in new JSON)

Do not use:
- `lineage`

## Declarative model-first rules

Implementation order:
1. domain enums/models (`app/domain/enums.py`, `VersionDetails`, taxonomy models)
2. persistence shape (JSON stores first)
3. API request/response models
4. service layer
5. UI binding (static UI only until contracts stable)
6. tests

Avoid:
- UI-only fields with no model
- route-only JSON blobs that are not typed
- duplicated enum strings across frontend/backend
- ACE-specific fields leaking into generic product surfaces

## Initial implementation slices

### Slice 1 — Media Inbox (backend first)

- upload one or more audio files
- list unreviewed media
- quick assign categories/concepts
- quality/fit/role/notes
- save + next

### Slice 2 — Generate with version details

- generate from target concept/category context
- create Generation immediately (`JobRecord`)
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
- scaffold Vite/React unless explicitly requested
- rename `JobRecord` to `Generation` in MVP

## Return format

Return:
- changed files
- route list
- model/schema changes
- tests run
- any breaking changes
- current local run instructions
