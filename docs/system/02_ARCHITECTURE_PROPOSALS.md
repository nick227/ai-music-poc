# Architecture Proposals — AI Music Studio

## Context

The current system is a local FastAPI-based ACE music POC. The next platform must support:
- media upload and storage
- category/concept assignment
- generated song records
- reviews
- version details
- generation batches
- dataset slices
- future fine-tune/training runs
- ACE-Step and future model adapters

## Shared architectural principles

Across all options:
- ACE-Step is one backend, not the architecture.
- Generation is first-class from day one.
- Generated songs are stored as both `Generation` records and `MediaAsset` records.
- Categories/concepts are many-to-many assignments with relationship metadata.
- The model runtime is abstracted behind a Model Adapter interface.
- Version Details are captured at generation time.

## Proposal A — Single FastAPI backend, Vite frontend

```txt
Vite/React Studio UI
        ↓
FastAPI Studio API
        ↓
Local DB + filesystem
        ↓
ACE-Step adapter / procedural adapter
```

### What FastAPI owns

- media upload
- local file storage paths
- category CRUD
- concept CRUD
- media assignments
- generated song records
- generation batches
- reviews
- dataset slices
- model status
- ACE generation job kickoff
- serving local WAV files

### Pros

- fastest path from current POC
- minimal moving pieces
- Python is natural for audio/model work
- avoids premature Node/Python coordination
- easiest local development
- best for proving the product loop

### Cons

- less aligned with Prisma/OpenAPI/SDK stack preference
- frontend type generation may be less polished unless OpenAPI discipline is added
- long jobs may eventually strain the API process
- hosted/multi-user product may eventually want a product API split

### Best use

Recommended for current MVP/local POC.

## Proposal B — FastAPI Studio API + separate Python worker

```txt
Vite/React Studio UI
        ↓
FastAPI Studio API
        ↓
DB + filesystem
        ↓
Python worker
        ↓
ACE-Step / future models
```

### What changes

FastAPI still owns product state, but long jobs move to a worker:
- ACE generation
- batch generation
- audio analysis
- waveform preview generation
- future training

### Pros

- preserves Python-first simplicity
- prevents long generation jobs from blocking API responsiveness
- good local evolution path
- easier to queue one model job at a time

### Cons

- introduces queue/state complexity
- requires job polling or event updates
- still not the usual TS product architecture

### Best use

Phase 2, once batch generation or audio analysis becomes heavy.

## Proposal C — Node/Fastify product API + Python model runtime

```txt
Vite/React Studio UI
        ↓
Fastify Product API
        ↓
Prisma DB
        ↓
Python Model Runtime / Worker
        ↓
ACE-Step / future models
```

### What Node owns

- user/product state
- categories/concepts
- media metadata
- reviews
- generated song records
- version details
- style versions
- dataset slices
- OpenAPI spec and generated SDK

### What Python owns

- generation
- training
- audio analysis
- model loading
- ACE integration
- future ML tooling

### Pros

- strong long-term product architecture
- aligns with Prisma + OpenAPI + generated SDK preference
- clear service boundaries
- easier multi-user/hosted path
- stable TS contracts for frontend

### Cons

- too many seams for immediate POC
- React → Node → Python → ACE adds latency and coordination
- more setup work before product loop is proven
- risk of architecture drag

### Best use

Productization phase after Studio loop is validated.

## Proposal D — Hybrid monorepo now, runtime split later

```txt
ai-music-studio/
  apps/
    studio-web/         # Vite React
    api/                # FastAPI now
    model-worker/       # optional later
  packages/
    api-spec/           # OpenAPI-first contract
    shared/             # declarative models/types
    sdk/                # generated client later
```

This keeps the current FastAPI implementation, while enforcing model/spec discipline so migration to Node/Fastify later remains possible.

### Pros

- practical now
- does not lock the project into FastAPI forever
- enforces declarative model-first surfaces
- keeps future Node/Prisma migration possible
- lets agents work against clean contracts

### Cons

- requires discipline to avoid ad hoc Python-only shapes
- may duplicate types if not managed carefully

### Best use

Recommended implementation posture.

## Recommendation

Use Proposal D with Proposal A runtime for MVP:

```txt
Frontend: Vite + React
Backend: FastAPI
Storage: local filesystem
Database: SQLite or existing local DB
Model runtime: existing ACE-Step adapter + procedural fallback
Contracts: OpenAPI/documented declarative models from day one
```

Move to Proposal B when long-running jobs increase.

Move to Proposal C only if the project becomes a hosted, multi-user product or needs the full Prisma/OpenAPI/SDK stack.

## Server count recommendation

### Now

```txt
1 backend server + frontend dev server

Vite/React
FastAPI
```

### Next

```txt
2 backend processes

FastAPI API
Python worker
```

### Later product architecture

```txt
3 servers/process types

Fastify Product API
Python model runtime/worker
React app
```

## Model Adapter interface

All model backends should conform to:

```ts
interface MusicModelAdapter {
  generate(request: GenerateRequest): Promise<GenerateResult>
  getGenerationStatus(jobId: string): Promise<JobStatus>
  train?(request: TrainingRequest): Promise<TrainingResult>
  getTrainingStatus?(runId: string): Promise<TrainingStatus>
}
```

The Studio should not depend on ACE-specific CLI arguments or paths outside the adapter.

## Storage layout

```txt
data/
  uploads/
  media/
  generated/
  batches/
  slices/
  artifacts/
  style_versions/
  training_runs/
```

## Critical constraints

- Only one heavy ACE generation at a time on local GPU unless queueing proves safe.
- Do not delete checkpoint/model caches.
- Do not mutate Python venv while generation is running.
- Save generated outputs and version details immediately.
- Do not treat output WAVs as disposable temp files.
