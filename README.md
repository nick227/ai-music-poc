# AI Music POC – Developer Handoff

Welcome to the AI Music POC (v3.4). This document serves as the primary handoff and onboarding guide for developers joining the project.

## Project Overview

This is a local, prompt-and-lyrics music generation console. It features persistent generation jobs, downloadable WAVs/bundles, instant parametric drafts using a procedural synthesizer, and a command-bridge to an external **ACE-Step** neural model for final vocal renders.

**Current State (v3.4):**
- **Procedural Engine:** Supports line-aware lyric timing, formant singing voices (female, male, choir, robot, whisper), vocal harmony, and style-specific chord progressions.
- **Neural Engine (ACE-Step):** Connected via a command adapter. We route based on quality tiers (`draft` -> procedural, `balanced/high` -> ACE-Step).
- **Architecture:** API decoupled from generation. Uses local disk JSON for job state (no DB yet) to keep iterations fast and robust.

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

### Prerequisites
- Python 3.10+
- (Optional) CUDA for running local models like ACE-Step.

### Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

### Running the API

```bash
python run.py
```
*The UI will be available at http://localhost:8000*

### Running Tests

```bash
pytest
```
*Expected output: 29 tests passing.*

---

## 3. The Generator Engines

### 3.1 Procedural Fallback (`procedural-v3`)
This is a pure CPU synthesis engine used for fast drafts. It doesn't sound like a real studio vocal but proves the pipeline immediately. It supports formants, chords, and multi-track mixing.

### 3.2 ACE-Step Integration
For neural, realistic renders, we bridge to an external ACE-Step installation.
To set up ACE-Step locally:
1. Install ACE-Step in a separate environment (e.g., `~/models/ACE-Step-1.5`).
2. Copy our runner script: `cp scripts/model_runners/ace_runner.example.py ~/models/ace_runner.py`
3. Edit `~/models/ace_runner.py` to point to your ACE-Step entry point.
4. Update `.env`:
   - `ACE_ENABLED=true`
   - `ACE_STEP_DIR=...`
   - `ACE_PYTHON=...`
   - `ACE_SCRIPT=...`
   - `ACE_ALLOW_FALLBACK=true` (Falls back to procedural if ACE errors)

**Testing ACE-Step Integration:**
- Smoke Test: `python scripts/ace_smoke_test.py`
- With inference: `python scripts/ace_smoke_test.py --run-generation --duration 10`

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
