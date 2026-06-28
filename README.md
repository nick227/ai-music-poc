# AI Music Studio

A local web app for making music from prompts and lyrics. Upload reference tracks, organize them into datasets, generate new songs, and train style models — all from one interface at **http://localhost:8000**.

Drafts run instantly on CPU. Higher-quality renders use **ACE-Step**, installed separately under `~/models/ACE-Step-1.5`.

---

## How it works

```
You write a prompt + lyrics
        ↓
App creates a job and picks an engine
        ↓
   draft quality  →  fast CPU preview (procedural)
   balanced/high  →  ACE-Step neural render (subprocess)
        ↓
WAV saved to disk, shown in the UI
```

**Dataset & training flow:**

```
Upload audio  →  tag with categories  →  build a dataset slice
        ↓
Package tracks for training  →  run a training job
        ↓
Trained style available for future generations
```

Everything runs locally. Job state lives in `data/` as JSON files — no database.

---

## Two repos, one workflow

```
<anywhere>/ai-music-poc/          ← this app (clone anywhere)
~/models/ACE-Step-1.5/            ← ACE runtime + weights (fixed location)
  ├── .venv/                      ← ACE Python env (uv)
  └── checkpoints/                ← ~11GB model weights (real files, not in app repo)
```

**Do not** put checkpoints inside this app repo. Weights belong only under `~/models/ACE-Step-1.5/checkpoints`.

---

## Install

**You need:** Python 3.10+, `git`, `curl`, `ffmpeg`, and [`uv`](https://docs.astral.sh/uv/) (for ACE).

```bash
git clone <this-repo>
cd <this-repo>
./scripts/dev_bootstrap.sh
```

First run can automatically:

- Create `.env` from `.env.example`
- Create the app `.venv` and install dependencies
- Clone ACE-Step into `~/models/ACE-Step-1.5`
- Run `uv sync` in the ACE checkout

Set `AUTO_SETUP=0` to validate only (no clone/venv creation).

**Download model weights** (once, after ACE is installed):

```bash
cd ~/models/ACE-Step-1.5 && uv run acestep-download
```

Weights must be **real files** under `~/models/ACE-Step-1.5/checkpoints`, not symlinks to a Windows cache.

**Verify ACE is ready:**

```bash
cd <this-repo>
python scripts/ace_paths_doctor.py
python scripts/ace_readiness.py --keep-output
```

---

## Run

**Recommended:**

```bash
./scripts/dev_bootstrap.sh
```

Bootstrap resolves paths from wherever you cloned this repo. ACE paths default to `~/models/ACE-Step-1.5` and are exported into the app process at runtime.

| `ACE_MODE` | Command | What starts |
|------------|---------|-------------|
| `none` (default) | `./scripts/dev_bootstrap.sh` | App only → http://localhost:8000 |
| `gradio` | `ACE_MODE=gradio ./scripts/dev_bootstrap.sh` | ACE Gradio (:7860) + app |
| `api` | `ACE_MODE=api ./scripts/dev_bootstrap.sh` | ACE HTTP API (:8001) + app |

Default mode is **app/subprocess**: generation calls `scripts/ace_runner.py` per job. No ACE daemon is required. Gradio/API modes are for debugging ACE upstream only.

Log: `logs/app.log` (bootstrap sets `APP_RELOAD=false` so log writes do not restart the server).

**Direct start** (hot reload on code changes; `.env` must have correct ACE paths):

```bash
python run.py
```

**Tests:**

```bash
pytest
```

---

## ACE-Step integration

The app never embeds ACE source code. It shells out to ACE for neural jobs:

| Job | Script |
|-----|--------|
| Generation | `scripts/ace_runner.py` |
| Training | `scripts/ace_train_runner.py` |

The app does **not** use `acestep-api` today.

**Check wiring:** `GET /api/model-status` or generate at balanced/high quality in the UI.

**`.env` paths** (bootstrap exports these at runtime; keep aligned for `python run.py`):

```env
ACE_ENABLED=true
ACE_STEP_DIR=${HOME}/models/ACE-Step-1.5
ACE_PYTHON=${HOME}/models/ACE-Step-1.5/.venv/bin/python
ACE_MODEL_DIR=${HOME}/models/ACE-Step-1.5/checkpoints
```

---

## API endpoints

| Endpoint | What it does |
|----------|--------------|
| `GET /api/health` | Is the app up? |
| `GET /api/generators` | List available engines |
| `POST /api/generate` | Start a new song job |
| `GET /api/jobs/{id}` | Job status and result |
| `GET /api/songs` | Browse finished songs |
| `POST /api/media/import` | Upload audio files |
| `GET /api/slices` | List dataset slices |
| `POST /api/slices` | Create a dataset slice |
| `POST /api/training/runs` | Start a training run |
| `GET /api/training/runs/{id}` | Training progress |
| `GET /api/model-status` | Is ACE configured correctly? |
| `POST /api/model-status/test` | Run ACE dependency checks |
| `GET /api/presets` | Prompt/style templates |

Full API reference: [`docs/API.md`](docs/API.md)

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/dev_bootstrap.sh` | Day-to-day entry: validate paths, export ACE env, start app |
| `run.py` | Start app directly (used by bootstrap and manual dev) |
| `scripts/ace_runner.py` | ACE generation subprocess (called by app) |
| `scripts/ace_train_runner.py` | ACE training subprocess (called by app) |
| `scripts/ace_readiness.py` | GPU/ffmpeg/checkpoint check + smoke generation |
| `scripts/ace_paths_doctor.py` | Diagnose ACE path and config drift |
| `scripts/ace_smoke_test.py` | Quick ACE integration test |

---

## Project layout

```
app/api/          HTTP routes
app/services/     Business logic
app/generators/   Song engines (procedural + ACE)
app/web/static/   Browser UI
data/             Songs, media, jobs, training runs
docs/             Detailed specs and runbooks
scripts/          Bootstrap, ACE runners, dev tools
logs/             Bootstrap runtime logs (gitignored)
```

More depth: [`docs/V3_ARCHITECTURE.md`](docs/V3_ARCHITECTURE.md) · [`docs/ROADMAP.md`](docs/ROADMAP.md)
