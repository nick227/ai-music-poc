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
