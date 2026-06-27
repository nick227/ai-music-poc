# API

## `GET /api/health`

Returns app health.

## `GET /api/generators`

Returns registered generators and status.

## `GET /api/model-status`

Fast wiring check — no subprocesses. Fields are grouped by subsystem:

| Field | Subsystem | Meaning |
|---|---|---|
| `wiring_ok` | Wiring | All path/config conditions pass (shorthand) |
| `ace_enabled` | Wiring | `ACE_ENABLED=true` in `.env` |
| `command_template_valid` | Wiring | Template has `$output_path` and `$prompt*` |
| `ace_python_exists` | Wiring | `ACE_PYTHON` path resolves |
| `ace_script_exists` | Wiring | `ACE_SCRIPT` file exists |
| `ace_model_dir_exists` | Wiring | `ACE_MODEL_DIR` directory exists |
| `can_generate` | Wiring | All wiring conditions pass; does **not** require packages to be probed |
| `hf_cache_configured` | Cache | `HF_CACHE_DIR` is set in `.env` |
| `hf_cache_exists` | Cache | Configured `HF_CACHE_DIR` path exists on disk |
| `packages_checked` | Packages | Always `false` on GET; populated by POST `/test` |
| `packages_ok` | Packages | `null` on GET; `true`/`false` after POST `/test` |
| `missing_packages` | Packages | Empty on GET; filled by POST `/test` when imports fail |
| `cuda_expected` | CUDA | `ACE_DEVICE=cuda` in config |
| `cuda_available` | CUDA | `null` on GET; populated by POST `/test` |
| `cuda_ready` | CUDA | `null` on GET; `true` when packages OK and CUDA available (or CPU mode) |
| `first_real_generation_verified` | History | `true` when app metadata shows a prior ACE `external-command` job |
| `first_real_generation` | History | Summary of most recent verified ACE job, or `null` |
| `fallback_enabled` | Fallback | `ACE_ALLOW_FALLBACK=true` in `.env` |
| `user_message` | Summary | Human-readable description of current state |

**First-run note:** The first real ACE generation may take much longer than subsequent runs while Hugging Face checkpoints download into `HF_CACHE_DIR`. Wiring and package checks passing does not mean checkpoints are fully cached yet.

## `POST /api/model-status/test`

Runs subprocesses to probe the ACE venv. Returns the same shape as GET `/api/model-status` under a `"status"` key, but with:
- `packages_checked: true`
- `packages_ok: true|false`
- `missing_packages: [...]` (names of imports that failed)
- `cuda_available: true|false`
- updated `user_message`

Also returns `"diagnostic"`, `"packages"`, `"dry_run"`, `"recommended_actions"` keys.
**Does not run model inference.**

## Studio job contract (v1, stable)

The studio integrates with two endpoints that share the same **frozen** response shape. Do not rename or remove these fields; add new fields only on extended endpoints (e.g. `GET /api/jobs/{job_id}`).

| Field | Type | Meaning |
|---|---|---|
| `job_id` | string | Opaque job identifier |
| `status` | string | `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMEOUT`, or `CANCELLED` |
| `output_path` | string \| null | Relative path under `DATA_DIR` when `status` is `SUCCEEDED`, e.g. `outputs/{job_id}.wav`; otherwise `null` |

Poll `GET /api/jobs/{job_id}/status` until `status` is terminal. Use `output_path` to locate the WAV on disk (or `GET /api/download/{job_id}` over HTTP).

## `POST /api/generate`

Creates a background job. Returns the studio contract immediately (`output_path` is always `null` on create).

**Request** (all fields optional except where noted):

```json
{
  "title": "Midnight Demo",
  "prompt": "dark french disco, emotional vocal",
  "lyrics": "I saw your shadow...",
  "generator": "ace-step-command",
  "duration_seconds": 45,
  "seed": 1234,
  "mode": "song",
  "bpm": 116,
  "key": "A",
  "structure": "verse_chorus",
  "quality": "draft",
  "guidance_scale": 7.5,
  "negative_prompt": "muddy mix",
  "allow_fallback": false
}
```

**Response** (studio contract v1):

```json
{
  "job_id": "abc123",
  "status": "QUEUED",
  "output_path": null
}
```

## `GET /api/jobs/{job_id}/status`

Returns the studio contract v1 for polling.

**Response** (while running):

```json
{
  "job_id": "abc123",
  "status": "RUNNING",
  "output_path": null
}
```

**Response** (success):

```json
{
  "job_id": "abc123",
  "status": "SUCCEEDED",
  "output_path": "outputs/abc123.wav"
}
```

## `GET /api/jobs`

Lists recent jobs.

## `GET /api/jobs/{job_id}`

Extended job detail (download URLs, request echo, error text). Not part of the stable studio contract; fields may evolve.

## `GET /api/download/{job_id}`

Downloads the generated WAV.
