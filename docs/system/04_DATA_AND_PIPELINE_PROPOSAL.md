# Data and Pipeline Proposal — Taxonomy, Media, Versions, and Training

## Core philosophy

The platform is a taxonomy-driven media and generation system.

The database should represent:
- audio files
- category vocabulary
- concepts as category combinations
- relationships between media and categories/concepts
- generated songs
- reviews
- batches
- version details
- dataset slices
- training runs
- style versions

The data model must support reuse. The same track may be useful for many categories and concepts.

## Top-level category dimensions

Seed these dimensions:

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

See `09_CONTRACT_CONVENTIONS.md` for enum source-of-truth and casing rules.

Categories are ever-expanding.

Examples:
- Genre / Trip-Hop
- Mood / Haunting
- Instrument / Piano
- Technique / Ghost Notes
- Production / Tape Saturation
- Mix / Vocal Forward
- Rhythm / Half-Time
- Vocals / Intimate Male
- Quality Issue / Weak Chorus
- Training Role / Gold Reference

## Concepts

A concept is a named reusable combination of categories.

Example:

```txt
Concept: Dark Cinematic Piano Vocal
Categories:
  Genre / Cinematic
  Mood / Haunting
  Instrument / Piano
  Vocals / Intimate Male
  Production / Dark Reverb
  Energy / Low
```

Concepts are the preferred targets for generation, review, and training slices.

## Pipeline states

Use operational states to make the app feel live:

```txt
EMPTY
NEEDS_MEDIA
READY_FOR_TEST
GENERATING
NEEDS_REVIEW
TRAINING_CANDIDATE
PROMOTED
NEEDS_CLEANUP
WATCH
```

## Core pipeline

```txt
Media import
→ assignment/review
→ category/concept coverage
→ generation
→ song review
→ dataset slice
→ training run
→ style version
→ comparison generation
→ promotion/reuse
```

## Proposed schema

This is a declarative logical schema. Exact syntax may vary by FastAPI/Pydantic, SQLModel, Prisma, or SQLAlchemy.

### Category

```ts
Category {
  id: string
  parentId?: string
  dimension: CategoryDimension
  name: string
  slug: string
  description?: string
  status: CategoryStatus
  createdAt: datetime
  updatedAt: datetime
}
```

```ts
CategoryDimension =
  | "GENRE"
  | "MOOD"
  | "INSTRUMENT"
  | "TECHNIQUE"
  | "PRODUCTION"
  | "MIX"
  | "RHYTHM"
  | "VOCALS"
  | "ARRANGEMENT"
  | "ENERGY"
  | "QUALITY_ISSUE"
  | "TRAINING_ROLE"

CategoryStatus = "ACTIVE" | "ARCHIVED"
```

### Concept

```ts
Concept {
  id: string
  name: string
  slug: string
  description?: string
  status: ConceptStatus
  coverageState: CoverageState
  createdAt: datetime
  updatedAt: datetime
}
```

### ConceptCategory

```ts
ConceptCategory {
  id: string
  conceptId: string
  categoryId: string
  weight?: number
  required: boolean
}
```

### MediaAsset

```ts
MediaAsset {
  id: string
  title: string
  kind: MediaKind
  source: MediaSource
  filePath?: string
  durationSeconds?: number
  sampleRate?: number
  channels?: number
  reviewStatus: ReviewStatus
  rightsStatus: RightsStatus
  createdAt: datetime
  updatedAt: datetime
}
```

```ts
MediaKind = "REFERENCE" | "UPLOAD" | "GENERATED_SONG" | "CLIP" | "STEM" | "NOTE_ONLY"
MediaSource = "USER_IMPORT" | "GENERATION" | "MANUAL_REFERENCE"
ReviewStatus = "NEEDS_REVIEW" | "REVIEWED" | "REJECTED"
RightsStatus = "UNKNOWN" | "CONFIRMED" | "DO_NOT_TRAIN"
```

### MediaCategoryAssignment

```ts
MediaCategoryAssignment {
  id: string
  mediaAssetId: string
  categoryId: string
  qualityScore?: number // 1-5
  fitScore?: number // 1-5
  role: AssignmentRole
  confidence?: number
  notes?: string
  reviewed: boolean
  createdAt: datetime
  updatedAt: datetime
}
```

### MediaConceptAssignment

```ts
MediaConceptAssignment {
  id: string
  mediaAssetId: string
  conceptId: string
  qualityScore?: number
  fitScore?: number
  role: AssignmentRole
  confidence?: number
  notes?: string
  reviewed: boolean
  createdAt: datetime
  updatedAt: datetime
}
```

```ts
AssignmentRole =
  | "REFERENCE"
  | "GOLD_REFERENCE"
  | "TRAINING_CANDIDATE"
  | "GENERATED_TEST"
  | "NEGATIVE_EXAMPLE"
  | "EDGE_CASE"
  | "KEEPER"
  | "REJECT"
```

### GenerationBatch

```ts
GenerationBatch {
  id: string
  name: string
  purpose: GenerationPurpose
  targetConceptId?: string
  backend: ModelBackend
  modelVersion?: string
  styleVersionId?: string
  promptTemplate?: string
  seedStrategy?: string
  count: number
  status: JobStatus
  createdAt: datetime
  updatedAt: datetime
}
```

### Generation

For MVP, the runtime Generation record is **`JobRecord`** in code (`job_id`; expose `generation_id` as alias). See `09_CONTRACT_CONVENTIONS.md`. A separate `Generation` table/type may be introduced later if needed.

```ts
Generation {
  id: string
  batchId?: string
  mediaAssetId?: string
  parentGenerationId?: string
  status: JobStatus
  backend: ModelBackend
  modelVersion?: string
  styleVersionId?: string
  trainingRunId?: string
  datasetSliceId?: string
  modelArtifactId?: string
  targetConceptId?: string
  prompt: string
  lyrics?: string
  seed?: number
  durationSeconds?: number
  qualityMode?: string
  settingsJson?: object
  versionDetailsJson?: object
  outputPath?: string
  createdAt: datetime
  updatedAt: datetime
}
```

```ts
GenerationPurpose =
  | "BASELINE"
  | "CONCEPT_TEST"
  | "PROMPT_TEST"
  | "STYLE_EVALUATION"
  | "VERSION_COMPARISON"
  | "KEEPER_CANDIDATE"

ModelBackend = "ACE_STEP" | "PROCEDURAL" | "FUTURE_MODEL"
JobStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED"
```

### GenerationTargetCategory

```ts
GenerationTargetCategory {
  id: string
  generationId: string
  categoryId: string
}
```

### Review

```ts
Review {
  id: string
  mediaAssetId: string
  generationId?: string
  overallScore?: number
  decision: ReviewDecision
  tagsJson?: string[]
  notes?: string
  createdAt: datetime
  updatedAt: datetime
}
```

```ts
ReviewDecision =
  | "KEEPER"
  | "REJECT"
  | "COMPARE"
  | "PROMOTE"
  | "USE_AS_REFERENCE"
  | "USE_AS_NEGATIVE"
  | "REGENERATE"
```

### DatasetSlice

```ts
DatasetSlice {
  id: string
  name: string
  description?: string
  filterJson: object
  minQuality?: number
  minFit?: number
  assetCount: number
  status: DatasetSliceStatus
  version: number
  createdAt: datetime
  updatedAt: datetime
}
```

```ts
DatasetSliceStatus = "DRAFT" | "READY" | "ARCHIVED"
```

### TrainingRun

```ts
TrainingRun {
  id: string
  name: string
  backend: ModelBackend
  baseModelVersion: string
  datasetSliceId: string
  status: JobStatus
  configJson?: object
  startedAt?: datetime
  finishedAt?: datetime
  error?: string
  createdAt: datetime
  updatedAt: datetime
}
```

### ModelArtifact

```ts
ModelArtifact {
  id: string
  trainingRunId: string
  path: string
  format: ArtifactFormat
  sizeBytes?: number
  epoch?: number
  loss?: number
  status: ArtifactStatus
  createdAt: datetime
}
```

```ts
ArtifactFormat = "SAFETENSORS" | "CHECKPOINT_DIR" | "CONFIG"
ArtifactStatus = "CANDIDATE" | "PROMOTED" | "REJECTED"
```

### StyleVersion

```ts
StyleVersion {
  id: string
  name: string
  slug: string
  version: number
  backend: ModelBackend
  modelArtifactId?: string
  datasetSliceId?: string
  trainingRunId?: string
  triggerText?: string
  status: StyleVersionStatus
  createdAt: datetime
  updatedAt: datetime
}
```

```ts
StyleVersionStatus = "DRAFT" | "ACTIVE" | "ARCHIVED"
```

## Version Details

User-facing label: `Version Details`

Every generated song should be able to show:
- backend
- model version
- style version
- training run/version
- dataset slice version
- target concept
- target categories
- prompt text or prompt version
- lyrics
- seed
- settings
- parent generation
- batch

Implementation detail:
- typed Pydantic `VersionDetails` model; API field `version_details` (snake_case)
- keep normalized fields for querying
- also preserve `versionDetailsJson` in sidecar metadata files as a frozen audit alias (see `09_CONTRACT_CONVENTIONS.md` for field mapping and legacy camelCase reads)

## Why generated songs are also MediaAssets

Generated songs must be reviewable and reusable.

Therefore:

```txt
Generation.mediaAssetId → MediaAsset.id
MediaAsset.kind = GENERATED_SONG
```

This lets generated songs be assigned to categories/concepts just like imported references.

## Dataset slice construction

A DatasetSlice is a saved query over categorized media.

Example filter:

```json
{
  "includeConceptIds": ["concept_dark_piano_vocal"],
  "includeCategoryIds": ["mood_haunting", "instrument_piano"],
  "roles": ["GOLD_REFERENCE", "TRAINING_CANDIDATE"],
  "minQuality": 4,
  "minFit": 4,
  "excludeCategoryIds": ["quality_issue_muddy_mix", "quality_issue_weak_vocal"]
}
```

## Query examples

### Strong references for a concept

```txt
Media assets where:
  concept = Dark Cinematic Piano Vocal
  role in GOLD_REFERENCE/TRAINING_CANDIDATE
  quality >= 4
  fit >= 4
```

### Generated songs needing review

```txt
Media assets where:
  kind = GENERATED_SONG
  reviewStatus = NEEDS_REVIEW
```

### Failed category fit

```txt
Generated songs assigned to:
  Concept / Dark Cinematic Piano Vocal
where:
  Category / Vocals / Intimate Male fit <= 2
```

## Future data additions

Later:
- audio embeddings
- duplicate detection
- waveform previews
- BPM/key detection
- stem links
- transcript/lyrics timing
- AI-suggested categories
- similarity clusters
