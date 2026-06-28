# AI Music Studio

A local web app for making music from prompts and lyrics. Upload reference tracks, organize them into datasets, generate new songs, and train style models — all from one interface at **http://localhost:8000**.

Drafts can be made instantly on CPU. Higher-quality renders use **ACE-Step**, a separate neural model that lives outside this repo.

---

## How it works

```
You write a prompt + lyrics
        ↓
App creates a job and picks an engine
        ↓
   draft quality  →  fast CPU preview (procedural)
   balanced/high  →  ACE-Step neural render
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

Everything runs locally. Job state is stored as JSON files under `data/` — no database required.

---

## Install

**You need:** Python 3.10+, `git`, `curl`, `ffmpeg`, and [`uv`](https://docs.astral.sh/uv/) (for ACE-Step's environment).

```bash
git clone <this-repo>
cd <this-repo>
./scripts/dev_bootstrap.sh
```

On first run the bootstrap will:

- Create `.env` from `.env.example` if missing
- Create the app `.venv` and install `requirements.txt` if missing
- Clone ACE-Step into `~/models/ACE-Step-1.5` if missing
- Run `uv sync` in ACE if its `.venv` is missing

Set `AUTO_SETUP=0` to skip clone/venv creation and only validate paths.

**Manual install** (optional):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

After bootstrap, download ACE model weights once:

```bash
cd ~/models/ACE-Step-1.5 && uv run acestep-download
```

---

## Run

**Recommended** — validates ACE paths, exports canonical env vars, starts the app:

```bash
./scripts/dev_bootstrap.sh
```

Default mode is **app/subprocess**: ACE runs per job via `scripts/ace_runner.py`. No ACE daemon is started.

Paths resolve automatically: app repo = wherever you cloned this project; ACE = `~/models/ACE-Step-1.5` (override with `ACE_STEP_DIR` or `ACE_MODELS_ROOT`).

| Mode | Command | What starts |
|------|---------|-------------|
| App only (default) | `./scripts/dev_bootstrap.sh` | App at http://localhost:8000 |
| ACE Gradio + app | `ACE_MODE=gradio ./scripts/dev_bootstrap.sh` | Gradio at :7860, then app |
| ACE API + app | `ACE_MODE=api ./scripts/dev_bootstrap.sh` | API at :8001, then app |

Log: `logs/app.log` (plus `logs/ace-step-gradio.log` or `logs/ace-step-api.log` in daemon modes).

**Without bootstrap** (paths must already be correct in `.env`):

```bash
python run.py
```

**Tests:**

```bash
pytest
```

---

## ACE-Step

ACE-Step is **not part of this repo**. It installs separately:

```
~/models/ACE-Step-1.5/     ← neural model + its own Python env
~/web/ai-music-poc/        ← this app
```

The bootstrap script validates ACE paths and passes them into the app. By default it starts **only this app** — ACE runs as a per-job subprocess, not as a background service.

When you generate or train, the app calls `scripts/ace_runner.py` or `scripts/ace_train_runner.py`. It does not call `acestep-api`.

**Check that ACE is wired up:**

- Open http://localhost:8000 and generate something at balanced/high quality, or
- Hit `GET /api/model-status` in the browser or API client

**Key `.env` settings** (also set automatically by the bootstrap):

```env
ACE_ENABLED=true
ACE_STEP_DIR=/home/administrator/models/ACE-Step-1.5
ACE_PYTHON=/home/administrator/models/ACE-Step-1.5/.venv/bin/python
ACE_MODEL_DIR=/home/administrator/models/ACE-Step-1.5/checkpoints
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
| `scripts/dev_bootstrap.sh` | Start ACE + app together (day-to-day entry point) |
| `scripts/ace_runner.py` | Called by the app to generate audio via ACE |
| `scripts/ace_train_runner.py` | Called by the app to run LoRA training via ACE |
| `scripts/ace_readiness.py` | Check GPU, ffmpeg, checkpoints, run a smoke test |
| `scripts/ace_smoke_test.py` | Quick ACE integration test |
| `scripts/ace_paths_doctor.py` | Diagnose ACE path / config problems |

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
```

More depth: [`docs/V3_ARCHITECTURE.md`](docs/V3_ARCHITECTURE.md) · [`docs/ROADMAP.md`](docs/ROADMAP.md)
