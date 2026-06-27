# ACE-Step Training Discovery

Discovery performed against the local checkout at `/home/administrator/models/ACE-Step-1.5` on 2026-06-27. This document records **source-verified** training integration facts only. No GPU training was run.

---

## Scope

Goal: identify the exact LoRA training entrypoint, preprocessing step, dataset layout, output artifact shape, and generation adapter loading path for AI Music Studio integration.

**Out of scope for this pass:** implementing real training, wiring `scripts/ace_train_runner.py`, or running long GPU jobs.

---

## Files Inspected

### CLI / training entry

| Path | What was verified |
|------|-------------------|
| `/home/administrator/models/ACE-Step-1.5/train.py` | Root CLI; subcommands `vanilla`, `fixed`, `estimate`; preprocess dispatch via `--preprocess` |
| `/home/administrator/models/ACE-Step-1.5/acestep/training_v2/cli/args.py` | All argparse flags for `fixed`, `estimate`, preprocess group |
| `/home/administrator/models/ACE-Step-1.5/acestep/training_v2/cli/common.py` | Re-exports `build_root_parser`, `validate_paths` |
| `/home/administrator/models/ACE-Step-1.5/acestep/training_v2/cli/validation.py` | Checkpoint/model/dataset path validation; `VARIANT_DIR_MAP` resolution |
| `/home/administrator/models/ACE-Step-1.5/acestep/training_v2/cli/train_fixed.py` | `run_fixed()` training flow; module alt entry |
| `/home/administrator/models/ACE-Step-1.5/acestep/training_v2/trainer_fixed.py` | Output layout: `final/`, `checkpoints/epoch_N_loss_X/`, TensorBoard `runs/` |
| `/home/administrator/models/ACE-Step-1.5/acestep/training_v2/trainer_helpers.py` | `save_adapter_flat()`, `save_final()`, artifact filenames |
| `/home/administrator/models/ACE-Step-1.5/pyproject.toml` | Declared training deps: `peft`, `lycoris-lora`, `lightning`, `tensorboard` |

### Preprocessing

| Path | What was verified |
|------|-------------------|
| `/home/administrator/models/ACE-Step-1.5/acestep/training_v2/preprocess.py` | Two-pass pipeline; final `.pt` tensor keys |
| `/home/administrator/models/ACE-Step-1.5/acestep/training_v2/preprocess_discovery.py` | Audio discovery; dataset JSON parsing; supported extensions |
| `/home/administrator/models/ACE-Step-1.5/acestep/training_v2/make_test_fixtures.py` | Synthetic `.pt` + `manifest.json` generator (no GPU) |
| `/home/administrator/models/ACE-Step-1.5/acestep/training/dataset_builder_modules/preprocess_manifest.py` | Legacy Gradio manifest writer (relative sample paths) |

### Dataset / data loading

| Path | What was verified |
|------|-------------------|
| `/home/administrator/models/ACE-Step-1.5/acestep/training/data_module.py` | `PreprocessedTensorDataset`; manifest optional; `.pt` scan fallback |
| `/home/administrator/models/ACE-Step-1.5/docs/sidestep/Dataset Preparation.md` | ACE-compatible dataset JSON formats (cross-checked against source) |
| `/home/administrator/models/ACE-Step-1.5/docs/sidestep/End-to-End Tutorial.md` | End-to-end command examples (note CLI quirk below) |
| `/home/administrator/models/ACE-Step-1.5/docs/sidestep/Using Your Adapter.md` | Output directory layout; Gradio loading instructions |

### Inference / adapter loading

| Path | What was verified |
|------|-------------------|
| `/home/administrator/models/ACE-Step-1.5/acestep/core/generation/handler/lora/lifecycle.py` | `add_lora()`, `load_lora()`; PEFT dir vs LoKR safetensors detection |
| `/home/administrator/models/ACE-Step-1.5/acestep/api/http/lora_routes.py` | HTTP API: `/v1/lora/load`, `/unload`, `/toggle`, `/scale`, `/status` |
| `/home/administrator/models/ACE-Step-1.5/acestep/inference.py` | Generation includes `use_lora`, `lora_scale`, `lora_loaded` in params |

### Local environment

| Path | What was verified |
|------|-------------------|
| `/home/administrator/models/ACE-Step-1.5/checkpoints/` | Local checkpoint tree present |
| `/home/administrator/models/ACE-Step-1.5/checkpoints/acestep-v15-turbo/config.json` | Turbo model config (`is_turbo: true`, `hidden_size: 2048`, etc.) |

### AI Music POC (integration boundary, not ACE source)

| Path | What was verified |
|------|-------------------|
| `/home/administrator/web/ai-music-poc/app/training/ace_adapter.py` | Dry-run only; writes `ace_train_command.json`, no subprocess |
| `/home/administrator/web/ai-music-poc/app/services/slice_package_service.py` | Studio package layout (`training-package/…`) — **not** ACE-native JSON |
| `/home/administrator/web/ai-music-poc/.env.example` | Placeholder `ACE_TRAIN_COMMAND_TEMPLATE`; `scripts/ace_train_runner.py` referenced but **does not exist** in repo |

---

## Commands Run (safe only)

All commands used `/home/administrator/models/ACE-Step-1.5/.venv/bin/python`.

### Help / flag discovery (no GPU, no training)

```bash
cd /home/administrator/models/ACE-Step-1.5
.venv/bin/python train.py --help
.venv/bin/python train.py fixed --help
.venv/bin/python train.py estimate --help
.venv/bin/python -m acestep.training_v2.cli.train_fixed --help
```

Observed on `train.py fixed --help`:
- Required for training: `--checkpoint-dir`, `--dataset-dir`, `--output-dir`
- Preprocess flags on same subcommand: `--preprocess`, `--audio-dir`, `--dataset-json`, `--tensor-output`, `--max-duration`
- Default LoRA hyperparams: `--rank 64`, `--alpha 128`, `--epochs 100`, `--shift 3.0`, `--num-inference-steps 8` (turbo defaults)
- Warnings emitted because **PEFT, Lightning, and LyCORIS are not importable** in this venv snapshot

### Argparse quirk confirmed (preprocess-only)

Tutorial examples omit `--dataset-dir` and `--output-dir` for preprocess-only runs. Source behavior:

```bash
.venv/bin/python train.py fixed \
  --checkpoint-dir ./checkpoints \
  --model-variant turbo \
  --preprocess \
  --audio-dir /tmp \
  --tensor-output /tmp/out
```

**Result:** argparse error — `the following arguments are required: --dataset-dir, --output-dir`

Preprocess dispatch in `train.py` would skip training paths, but argparse still requires them on the `fixed` subcommand (`require_training_paths=True` in `args.py`). The standalone module parser sets `require_training_paths=False`:

```bash
python -m acestep.training_v2.cli.train_fixed --preprocess ...
```

### Synthetic fixture dry-run (CPU only, no model load)

```bash
cd /home/administrator/models/ACE-Step-1.5
.venv/bin/python -m acestep.training_v2.make_test_fixtures \
  --output-dir /tmp/ace_discovery_fixtures \
  --num-samples 2
```

**Output:**
```
[OK] Generated 2 synthetic fixtures in /tmp/ace_discovery_fixtures
```

Produced:
- `/tmp/ace_discovery_fixtures/test_0000.pt`
- `/tmp/ace_discovery_fixtures/test_0001.pt`
- `/tmp/ace_discovery_fixtures/manifest.json`

---

## Training Entrypoint

### Primary CLI

**File:** `/home/administrator/models/ACE-Step-1.5/train.py`

**Recommended subcommand:** `fixed` (Side-Step Training V2 — corrected timesteps + CFG dropout)

From `train.py` docstring:

```bash
python train.py fixed --checkpoint-dir ./checkpoints --model-variant turbo \
    --dataset-dir ./preprocessed_tensors/jazz --output-dir ./lora_output/jazz
```

**Alternate module entry** (equivalent per `train_fixed.py` header):

```bash
python -m acestep.training_v2.cli.train_fixed [same flags]
```

**Other subcommands:**
| Subcommand | Purpose |
|------------|---------|
| `vanilla` | Legacy/back-compat training path |
| `estimate` | Gradient sensitivity analysis — **no weight updates** (still loads model + dataset) |
| *(no subcommand)* | Interactive wizard session loop |

**Implementation chain:** `train.py` → `run_fixed()` → `FixedLoRATrainer` → `PreprocessedDataModule` → `save_final()` → flat PEFT adapter in `{output_dir}/final/`.

---

## Preprocessing

### Trigger

Preprocessing is **not** a separate top-level subcommand. It is invoked via `--preprocess` on `fixed` (or via the wizard / Gradio dataset builder).

`train.py` routes `--preprocess` to `_run_preprocess()` **before** path validation for training.

### Required inputs (from `_run_preprocess` in `train.py`)

| Input | Flag | Required |
|-------|------|----------|
| Checkpoint root | `--checkpoint-dir` | Yes |
| Model variant | `--model-variant` (default `turbo`) | No |
| Audio source | `--audio-dir` **or** `--dataset-json` | At least one |
| Tensor output dir | `--tensor-output` | Yes |
| Max clip length | `--max-duration` (default `240.0` seconds) | No |
| Device / precision | `--device`, `--precision` | No |

### Pipeline (from `acestep/training_v2/preprocess.py`)

Two sequential low-VRAM passes:

1. **Pass 1 (~3 GB):** VAE + text encoder → intermediate `{stem}.tmp.pt`
2. **Pass 2 (~6 GB):** DiT encoder → final `{stem}.pt` (intermediate deleted)

### Supported audio

Extensions in source: `.wav`, `.mp3`, `.flac`, `.ogg`, `.opus`, `.m4a`  
Discovery: recursive directory scan, or paths from dataset JSON.

### Dataset JSON (preprocess metadata input)

Parsed by `preprocess_discovery.py`. Accepted top-level shapes:
- JSON **array** of sample objects
- JSON **object** with `"samples": [...]`
- Full ACE format with top-level `"metadata"` block (`custom_tag`, `tag_position`, `genre_ratio`, …)

Per-sample fields used include: `audio_path`, `filename`, `caption`, `lyrics`, `genre`, `bpm`, `keyscale`, `timesignature`, `custom_tag`, `is_instrumental`, etc.

Relative `audio_path` values resolve from the **JSON file's directory**.

### Preprocess output

Directory of `{stem}.pt` files. **Training V2 preprocess does not write `manifest.json`** (verified: no manifest write in `preprocess.py`). Training still works via directory scan in `PreprocessedTensorDataset`.

Legacy Gradio path (`preprocess_manifest.save_manifest`) and `make_test_fixtures` do write `manifest.json`.

### Final `.pt` tensor schema (from `preprocess.py` pass 2 save + `data_module.py`)

Each file is a PyTorch dict:

| Key | Shape (turbo) | Notes |
|-----|---------------|-------|
| `target_latents` | `[T, 64]` | VAE-encoded audio |
| `attention_mask` | `[T]` | Latent mask |
| `encoder_hidden_states` | `[L, 2048]` | Condition encoder output |
| `encoder_attention_mask` | `[L]` | Encoder mask |
| `context_latents` | `[T, 128]` | 64 src + 64 chunk masks (preprocess); data_module comment says `[T, 65]` — treat shapes as model-dependent |
| `metadata` | dict | caption, lyrics, duration, tags, etc. |

---

## Dataset Layout for Training

### Input to `train.py fixed`

| Input | Flag | Required |
|-------|------|----------|
| Preprocessed tensors | `--dataset-dir` | Yes (directory of `.pt` files) |
| Checkpoint root | `--checkpoint-dir` | Yes |
| LoRA output root | `--output-dir` | Yes |
| Model variant | `--model-variant` (default `turbo`) | No |

`validate_paths()` resolves `--model-variant turbo` → `{checkpoint-dir}/acestep-v15-turbo` via `VARIANT_DIR_MAP`.

**Local checkpoint layout verified:**

```
/home/administrator/models/ACE-Step-1.5/checkpoints/
├── acestep-v15-turbo/    ← --model-variant turbo
├── acestep-v15-base/
├── acestep-v15-sft/      (if present)
├── vae/
├── Qwen3-Embedding-0.6B/
└── acestep-5Hz-lm-1.7B/
```

### `manifest.json` (optional)

If present in `--dataset-dir`, `PreprocessedTensorDataset` loads `"samples"` list. Paths may be relative to the tensor directory. If absent, all `*.pt` files in the directory are used.

---

## Training Command (exact flags from `--help`, not invented)

### Minimal training example (after real preprocessing)

```bash
cd /home/administrator/models/ACE-Step-1.5
.venv/bin/python train.py fixed \
  --checkpoint-dir ./checkpoints \
  --model-variant turbo \
  --dataset-dir ./my_tensors \
  --output-dir ./output/my_lora \
  --epochs 100 \
  --yes
```

`--yes` skips the interactive confirmation prompt (`confirm_start` in `run_fixed`).

### Preprocess + train in one invocation

When `--preprocess` is set **and** training paths are provided, `run_fixed` preprocesses first, then trains on `--tensor-output` (see `train_fixed.py` flow — not re-run here).

### Preprocess-only (standalone module — avoids dummy training paths)

```bash
.venv/bin/python -m acestep.training_v2.cli.train_fixed \
  --checkpoint-dir ./checkpoints \
  --model-variant turbo \
  --preprocess \
  --audio-dir ./my_audio \
  --dataset-json ./my_audio/my_dataset.json \
  --tensor-output ./my_tensors \
  --yes
```

### Resume

Flag exists: `--resume-from ./output/my_lora/checkpoints/epoch_100`  
Checkpoint dirs contain adapter files + `training_state.pt`.

### Estimate (analysis only, not run)

```bash
.venv/bin/python train.py estimate \
  --checkpoint-dir ./checkpoints \
  --model-variant turbo \
  --dataset-dir ./my_tensors \
  [--output module_config.json]
```

Requires GPU model load + forward passes. **Not executed** in this discovery.

---

## Expected Training Outputs

From `trainer_fixed.py` + `trainer_helpers.py` + sidestep docs (confirmed in source for save paths):

```
{output-dir}/
├── final/
│   ├── adapter_config.json         # PEFT config (LoRA)
│   └── adapter_model.safetensors   # LoRA weights
├── checkpoints/
│   └── epoch_{N}_loss_{avg}/       # e.g. epoch_10_loss_0.1234
│       ├── adapter_config.json
│       ├── adapter_model.safetensors
│       └── training_state.pt       # optimizer/scheduler for resume
└── runs/
    └── [TensorBoard event files]
```

**LoKR** (`--adapter-type lokr`) writes `lokr_weights.safetensors` instead of PEFT pair.

**Inference-ready path:** `{output-dir}/final/` (or any checkpoint subdirectory — adapter files are flat inside each checkpoint dir).

`save_adapter_flat()` uses PEFT `save_pretrained()` → `adapter_config.json` + `adapter_model.safetensors`.

---

## How Generated Songs Should Load the Adapter

### Path to pass

Point at the **directory** containing `adapter_config.json`, not the safetensors file alone:

```
/full/path/to/output/my_lora/final
```

### Gradio UI

1. Initialize ACE-Step service (quantization **disabled** — LoRA blocked on quantized models per `lifecycle.py`)
2. LoRA Adapter panel → enter path → **Load LoRA**
3. Enable **Use LoRA**; set **LoRA Scale** (default `1.0`)
4. Generate with turbo settings: `shift=3.0`, `8` inference steps (per sidestep docs + default CLI flags)

If training used a `custom_tag` in dataset metadata, include that tag in the generation prompt.

### Programmatic / HTTP API

`acestep/api/http/lora_routes.py`:

| Endpoint | Body | Effect |
|----------|------|--------|
| `POST /v1/lora/load` | `{"lora_path": "/path/to/final"}` | Calls `handler.load_lora()` → `add_lora()` |
| `POST /v1/lora/toggle` | `{"use_lora": true}` | Enable/disable without unloading |
| `POST /v1/lora/scale` | `{"scale": 0.8}` | Set strength 0.0–1.0 |
| `POST /v1/lora/unload` | — | Restore base decoder |
| `GET /v1/lora/status` | — | Current load state |

Core loading logic (`lifecycle.py`):
- Validates `adapter_config.json` exists (PEFT) or resolves `lokr_weights.safetensors` (LoKR)
- Wraps decoder: `PeftModel.from_pretrained(decoder, lora_path, is_trainable=False)`
- Sets `lora_loaded=True`, `use_lora=True`

Generation path (`inference.py`) propagates LoRA state into generation params for reproducibility.

### AI Music POC today

Generation uses `ACE_COMMAND_TEMPLATE` + `scripts/ace_runner.py` (inference bridge). **No LoRA path is wired** in the POC generation adapter yet. A future integration must either:
- extend the ACE runner / API client to call `/v1/lora/load` before generate, or
- pass a LoRA directory into ACE-Step CLI if supported there (not verified in this pass)

---

## Studio Package → ACE Gap

Studio training packages (`slice_package_service.py`) produce:

```
training-package/
├── manifest.json          # slice metadata (format_version 1, not ACE dataset JSON)
├── captions.csv
├── rights.json
└── tracks/{media_id}/
    ├── audio.wav
    ├── caption.txt
    ├── labels.json
    ├── annotation.json    # has audio_path, caption, music.bpm/key, etc.
    └── lyrics.txt         # optional
```

ACE preprocess expects either:
- a folder of audio files (`--audio-dir`), or
- ACE-compatible `dataset.json` with `audio_path` per sample

**A conversion step is required** before calling ACE preprocess — e.g. unpack package, emit ACE `dataset.json` pointing at extracted `audio.wav` paths with captions/lyrics from per-track files. This converter does not exist yet.

---

## Remaining Unknowns

1. **Venv incomplete for training:** `peft`, `lightning`, and `lycoris-lora` are declared in `pyproject.toml` but `import peft` fails in `.venv`. Real training requires installing/syncing deps (likely `uv sync` or equivalent in the ACE checkout — not run here).

2. **Preprocess CLI vs docs mismatch:** Sidestep tutorial preprocess examples omit `--dataset-dir` / `--output-dir`, but `train.py fixed` argparse requires them. Workaround: use `python -m acestep.training_v2.cli.train_fixed` for preprocess-only, or supply placeholder values.

3. **`manifest.json` after Training V2 preprocess:** Docs imply a manifest is produced; `preprocess.py` does not write one. Training falls back to scanning `*.pt` — behavior is fine but manifest-based filtering/order is unavailable unless we generate one.

4. **`scripts/ace_train_runner.py`:** Referenced in POC `.env.example` but missing from the repo. No verified wrapper exists for package → preprocess → train.

5. **End-to-end training smoke not run:** Synthetic fixtures prove tensor layout only. Real preprocess + 1-epoch train not executed (GPU/time + missing deps).

6. **`estimate` subcommand:** Exact VRAM/runtime and whether its `--output` JSON integrates with `--target-modules` auto-selection not verified hands-on.

7. **POC → ACE generation with LoRA:** Whether `scripts/ace_runner.py` / `cli.py` accepts a LoRA flag vs requiring HTTP `/v1/lora/load` not inspected in this pass.

8. **context_latents width:** Preprocess saves `[T, 128]`; `data_module.py` comment says `[T, 65]`. Likely doc drift — verify against a real preprocessed file before hard-coding shapes.

9. **Checkpoint dir vs `ACE_MODEL_DIR`:** POC `.env.example` points generation checkpoints at HuggingFace cache; local discovery used `./checkpoints` inside the ACE repo. Training and inference must use consistent checkpoint roots — mapping not validated.

10. **Turbo vs base/sft for Studio:** Default is turbo (`shift=3.0`, 8 steps). Whether Studio style training should target turbo exclusively is a product decision, not resolved here.

---

## Recommended Next Steps (post-discovery)

1. Sync ACE venv training dependencies and confirm `train.py fixed --help` runs without PEFT/Lightning warnings.
2. Implement `scripts/ace_train_runner.py`: unpack Studio package → write ACE `dataset.json` → preprocess → train (subprocess, bounded timeout).
3. Store `{output-dir}/final/` as the StyleVersion artifact path.
4. Wire generation to load adapter via ACE HTTP API or documented CLI path before calling generate.
5. Run a **short** real training smoke (1 epoch, 2–4 clips) only after steps 1–2.
