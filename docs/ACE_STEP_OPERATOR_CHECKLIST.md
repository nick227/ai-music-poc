# ACE-Step Operator Checklist

Use this after the ACE venv install finishes. Do **not** run these checks while `pip` is still installing packages in the ACE venv.

## Three separate layers

| Layer | What it is | Configured by |
|-------|------------|---------------|
| **App bridge** | FastAPI job orchestration, command template, HF env injection | `.env` in this repo (`ACE_*`, `HF_CACHE_DIR`) |
| **ACE venv** | Python + torch + transformers + diffusers for inference | `/home/administrator/models/ACE-Step-1.5/.venv` (external) |
| **Checkpoint cache** | Model weights on disk | `ACE_MODEL_DIR` + shared Hugging Face cache |

Wiring can be **ready** (`can_generate=true`) while the ACE venv is still broken or mid-install. The app bridge only confirms paths, template, and dry-run — not successful inference.

## Ollama models are not reusable

Ollama stores LLMs under `~/.ollama/models` in its own format. ACE-Step uses **Hugging Face** checkpoints (diffusers/transformers). Pointing ACE at Ollama blobs will not work.

## HF_CACHE_DIR prevents duplicate downloads

When `HF_CACHE_DIR` is set, the app injects these into every ACE subprocess:

- `HF_HOME`
- `HUGGINGFACE_HUB_CACHE`
- `TRANSFORMERS_CACHE`
- `DIFFUSERS_CACHE`
- `ACESTEP_CHECKPOINTS_DIR` (from `ACE_MODEL_DIR`)

Use a shared Windows-visible path (WSL: `/mnt/c/Users/.../.cache/huggingface`) so WSL and Windows tools reuse the same hub cache.

## Before you start

- [ ] No active `pip install` in the ACE venv (wait for the other terminal to finish)
- [ ] `.env` has `ACE_ENABLED=true`, `ACE_COMMAND_TEMPLATE`, `ACE_SCRIPT=./scripts/ace_runner.py`
- [ ] Checkpoint folder exists: `ACE_MODEL_DIR` (e.g. `.../ace-step-checkpoints`)

## Step 1 — Torch CUDA check (ACE venv only)

Run **after pip finishes**. Uses the ACE venv, not the app venv:

```bash
/home/administrator/models/ACE-Step-1.5/.venv/bin/python -c "
import torch
print('torch', torch.__version__)
print('cuda_available', torch.cuda.is_available())
print('cuda_device_count', torch.cuda.device_count())
"
```

Expect `cuda_available True` when CUDA PyTorch is installed correctly.

## Step 2 — App bridge dry-run (no inference)

From the app repo, app venv:

```bash
cd ~/web/ai-music-poc
source .venv/bin/activate
python scripts/ace_smoke_test.py --dry-run-only
```

Or call the runner directly with HF env (matches what the adapter passes):

```bash
HF_HOME=/mnt/c/Users/Administrator/.cache/huggingface \
HUGGINGFACE_HUB_CACHE=/mnt/c/Users/Administrator/.cache/huggingface/hub \
TRANSFORMERS_CACHE=/mnt/c/Users/Administrator/.cache/huggingface/transformers \
DIFFUSERS_CACHE=/mnt/c/Users/Administrator/.cache/huggingface/diffusers \
ACESTEP_CHECKPOINTS_DIR=/mnt/c/Users/Administrator/.cache/huggingface/ace-step-checkpoints \
ACE_STEP_DIR=/home/administrator/models/ACE-Step-1.5 \
/home/administrator/models/ACE-Step-1.5/.venv/bin/python scripts/ace_runner.py --dry-run
```

Confirm output includes:

- `ACE_STEP_DIR=... exists=True`
- `HF_HOME=...`
- `HUGGINGFACE_HUB_CACHE=...`
- `TRANSFORMERS_CACHE=...`
- `DIFFUSERS_CACHE=...`
- `ACESTEP_CHECKPOINTS_DIR=...`
- Resolved `prompt_file`, `lyrics_file`, `output`, `model_dir`, `device` when args are passed

API equivalent:

```bash
curl -X POST http://localhost:8000/api/model-status/test | python -m json.tool
```

## Step 3 — Tiny 10-second generation (optional, after Step 1 passes)

Only when torch/packages are healthy:

```bash
python scripts/ace_smoke_test.py --run-generation --duration 10
```

In the UI: generator `ace-step-command`, **allow fallback: off**.

## Do not run while pip is active

Avoid concurrently:

- `pip install` in the ACE venv
- `python scripts/ace_smoke_test.py --run-generation`
- ACE-Step `cli.py` or `app.py` inference
- UI jobs on `ace-step-command` with fallback disabled

Competing installs corrupt wheels (e.g. torch `null bytes` errors).

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `can_generate=true` but packages missing | App wiring OK, venv not | Finish/repair ACE venv pip install |
| `torch ... null bytes` | Corrupted wheel mid-install | Reinstall torch **after** pip quiesces |
| Duplicate HF downloads | `HF_CACHE_DIR` unset | Set in `.env`, restart app |
| `ACE_SCRIPT does not exist` | Wrong path | Use `./scripts/ace_runner.py` inside repo |
| Dry-run exit 2 | Missing ACE checkout paths | Fix `ACE_STEP_DIR`, venv, or `cli.py` |

## Safe vs unsafe commands

| Safe anytime | Wait for pip + torch OK |
|--------------|-------------------------|
| `ace_smoke_test.py --dry-run-only` | `ace_smoke_test.py --run-generation` |
| `ace_runner.py --dry-run` | ACE `cli.py` inference |
| `GET /api/model-status` | UI `ace-step-command` without fallback |
| `POST /api/model-status/test` | |
