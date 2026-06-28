# AI Music POC – Developer Handoff

Welcome to the AI Music POC (v3.4). This document serves as the primary handoff and onboarding guide for developers joining the project.

## Project Overview

This is a local, prompt-and-lyrics music generation console. It features persistent generation jobs, downloadable WAVs/bundles, instant parametric drafts using a procedural synthesizer, and a command-bridge to an external **ACE-Step** neural model for final vocal renders.

**Current State (v3.4):**
- **Procedural Engine:** Supports line-aware lyric timing, formant singing voices (female, male, choir, robot, whisper), vocal harmony, and style-specific chord progressions.
- **Neural Engine (ACE-Step):** Connected via a command adapter. We route based on quality tiers (`draft` -> procedural, `balanced/high` -> ACE-Step).
- **Architecture:** API decoupled from generation. Uses local disk JSON for job state (no DB yet) to keep iterations fast and robust.

Users only use **this app's UI** at http://localhost:8000. ACE-Step is never exposed as a separate product surface.

---

## 1. Architecture & Core Concepts

The application uses FastAPI and is structured to keep HTTP routes thin while pushing orchestration to services and rendering to generators.

- **`app/api/`**: HTTP endpoints. They validate requests, create jobs, and return JSON.
- **`app/domain/`**: Typed Pydantic models for requests, responses, and jobs.
- **`app/generators/`**: The swappable generator boundary.
  - `procedural.py` (CPU fallback with formant synthesis)
  - `ace_step/` (External subprocess caller)
- **`app/services/`**: Orchestrates workflows (`JobService`, `GenerationService`, `BundleService`).
- **`app/storage/`**: Local disk persistence (`metadata_store`, `log_store`).
- **`app/web/`**: Static browser console UI.

**Job Flow:**
1. UI POSTs to `/api/generate`.
2. `JobService` creates a `QUEUED` JSON file.
3. A FastAPI background task picks it up, transitioning to `RUNNING`.
4. `GenerationService` routes to the selected generator.
5. Generator produces a WAV in `data/outputs`.
6. Job completes (`SUCCEEDED` or `FAILED`).

For deeper architectural details, see `docs/V3_ARCHITECTURE.md` and `docs/ARCHITECTURE.md`.

---

## 2. Local Setup & Development

### Day-to-day configuration (recommended)

Use `./scripts/dev_bootstrap.sh` as the runtime source of truth. It:

1. Starts the external ACE-Step runtime from `~/models/ACE-Step-1.5` (`uv run acestep`)
2. Waits for ACE, then starts this app from `~/web/ai-music-poc`
3. Exports canonical ACE paths into the app process (`ACE_STEP_DIR`, `ACE_PYTHON`, `ACE_MODEL_DIR`, `ACE_TRAIN_CHECKPOINT_DIR`) so config cannot drift to stale cache paths

Users only visit **this app's UI** at http://localhost:8000. ACE generation/training jobs also use ACE as a **subprocess** (`scripts/ace_runner.py`, `scripts/ace_train_runner.py`) against the same checkout.

| Work | Bootstrap (`dev_bootstrap.sh`) | ACE checkout on disk |
|------|------------------------------|----------------------|
| UI, media, taxonomy, slices | yes | no |
| Procedural generation | yes | no |
| ACE neural generation | yes | yes |
| ACE LoRA training | yes | yes |

**`.env` essentials** (bootstrap exports override these at runtime; keep `.env` aligned for direct `python run.py` use):

```env
DEFAULT_GENERATOR=auto-render
ACE_ENABLED=true
ACE_STEP_DIR=/home/administrator/models/ACE-Step-1.5
ACE_PYTHON=/home/administrator/models/ACE-Step-1.5/.venv/bin/python
ACE_SCRIPT=./scripts/ace_runner.py
ACE_MODEL_DIR=/home/administrator/models/ACE-Step-1.5/checkpoints
ACE_DEVICE=cuda
ACE_ALLOW_FALLBACK=true
```

For real LoRA training (when ready), also set `TRAINING_ADAPTER=ace-step-real`, `ACE_REAL_TRAINING_ENABLED=true`, and `ACE_TRAIN_DRY_RUN=false`.

**Start everything:**

```bash
./scripts/dev_bootstrap.sh
```

Logs: `logs/ace-step.log`, `logs/app.log` (truncated each boot). ACE Gradio: http://localhost:7860. App UI: http://localhost:8000.

**App only** (no ACE daemon, subprocess jobs still work if `.env` paths are correct):

```bash
python run.py
```

**Verify ACE wiring** after first start: `GET /api/model-status` and `POST /api/model-status/test`.

### Prerequisites

- Python 3.10+
- `ffmpeg` on PATH (required for ACE subprocess jobs)
- ACE-Step checkout with `.venv` and checkpoints (for neural generation/training)
- CUDA (recommended for ACE neural work)

### Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set ACE paths for your machine
```

### Running Tests

```bash
pytest
```

---

## 3. The Generator Engines

### 3.1 Procedural Fallback (`procedural-v3`)

Pure CPU synthesis for fast drafts. No ACE install required.

### 3.2 ACE-Step Integration

Neural renders call ACE via subprocess. Setup:

1. Install ACE-Step separately (e.g. `~/models/ACE-Step-1.5`).
2. Set `ACE_ENABLED=true` and ACE paths in `.env` (runner is already `scripts/ace_runner.py`).
3. Confirm with `GET /api/model-status`.

**Testing ACE integration:**

- Readiness: `python scripts/ace_readiness.py`
- Smoke test: `python scripts/ace_smoke_test.py --run-generation --duration 10`

---

## 4. Helpful Endpoints

- **`GET /api/health`**: Basic uptime check.
- **`GET /api/model-status`**: Diagnostics for ACE-Step wiring, HuggingFace cache presence, and fallback state.
- **`POST /api/model-status/test`**: Runs subprocess checks for CUDA and model dependencies without full inference.
- **`GET /api/presets`**: Available prompt/style templates.

*See `docs/API.md` for full API specifications.*

---

## 5. Next Steps / Roadmap

As you take over, focus on these upcoming priorities from `docs/ROADMAP.md`:

1. **Stabilize ACE-Step Rendering:** Move beyond fallback mode and lock in a reliable local neural song generation.
2. **Local Style Packs:** Curated presets (e.g., "dark cinematic piano", "French disco") to act as a product-control layer.
3. **Advanced Integrations:** Phase 3 includes LoRA/fine-tuning pipelines using user-uploaded reference tracks.

Please refer to the `docs/` folder for comprehensive specs, API routes, and operational playbooks.
