# API

## `GET /api/health`

Returns app health.

## `GET /api/generators`

Returns registered generators and status.

## `GET /api/model-status`

Returns generator readiness plus whether the app is functional without GPU.

## `POST /api/generate`

Creates a background job.

```json
{
  "title": "Midnight Demo",
  "prompt": "dark french disco, emotional vocal",
  "lyrics": "I saw your shadow...",
  "generator": "ace-step-local",
  "duration_seconds": 45,
  "seed": 1234,
  "mode": "song",
  "bpm": 116,
  "key": "A",
  "structure": "verse_chorus",
  "quality": "draft",
  "guidance_scale": 7.5,
  "negative_prompt": "muddy mix",
  "use_fallback": true
}
```

## `GET /api/jobs`

Lists recent jobs.

## `GET /api/jobs/{job_id}`

Returns a persisted job record and download URL when successful.

## `GET /api/download/{job_id}`

Downloads the generated WAV.
