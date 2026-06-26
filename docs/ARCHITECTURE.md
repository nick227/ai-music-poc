# Architecture

V1.5 separates HTTP routes from generation logic.

```txt
app/api/routes     HTTP endpoints
app/core           config, logging, path safety, app errors
app/domain         typed request/response/job models
app/generators     model adapters and registry
app/services       job and generation orchestration
app/storage        local disk persistence
app/web/static     browser console
```

Routes should stay thin. They validate input, create jobs, and return responses. Services own orchestration. Generators own audio creation. Storage owns persistence.

## Job flow

1. Browser posts `GenerationRequest` to `/api/generate`.
2. API validates the selected generator.
3. `JobService` creates a `QUEUED` job JSON file.
4. Background task calls `GenerationService.run_job`.
5. Job moves to `RUNNING`.
6. Generator writes a WAV to `data/outputs`.
7. Job moves to `SUCCEEDED` or `FAILED`.
8. Browser polls `/api/jobs/{job_id}` and downloads from `/api/download/{job_id}`.

## Why disk JSON

Disk JSON is intentionally simple for V1.5. It makes refreshes and restarts safer without introducing database decisions before auth, billing, and account history are designed.
