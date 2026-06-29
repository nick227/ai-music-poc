# SVS Setup Guide

Singing Voice Synthesis (SVS) in this project is a controlled, opt-in pipeline. The default backend is `mock` (sine-burst debug audio). The `diffsinger` backend produces real neural vocal stems using a local TIGER ONNX voice pack.

---

## Architecture

```
SvsCommandGenerator (adapter.py)
  └── SvsCommandBuilder (command_builder.py)
        └── scripts/svs_runner.py --backend [mock|diffsinger]
              ├── mock: MockSvsRenderer → sine-burst WAV
              └── diffsinger: scripts/diffsinger_infer.py → TIGER ONNX → WAV
```

The app never routes auto-render to SVS. SVS is only used when `generator=svs-vocal` is explicitly requested.

---

## Quick Start (mock backend)

No setup needed. The mock backend works out of the box with default settings:

```bash
# Default: SVS_BACKEND=mock, SVS_ENABLED=true, SVS_ALLOW_FALLBACK=true
python -m app.web.app
```

---

## DiffSinger Backend (TIGER ONNX)

### Prerequisites

| Component | Version | Notes |
|---|---|---|
| Python (SVS venv) | 3.12 | Isolated venv recommended |
| onnxruntime-gpu | 1.20.1 | Must match CUDA 13 runtime |
| CUDA driver | ≥13.1 | RTX 3060 confirmed |
| cuDNN | 9.x | From `nvidia-cudnn` pip package |
| TIGER voice pack | v106 | See download below |

### 1. Create an isolated SVS venv

```bash
python3.12 -m venv ~/web/diffsinger-env/venv
source ~/web/diffsinger-env/venv/bin/activate
pip install onnxruntime-gpu==1.20.1 numpy soundfile
```

> **Why isolated?** onnxruntime-gpu 1.20.1 links against CUDA 13 runtime (`libcudart.so.13`). This may conflict with other packages in your main venv.

### 2. Set LD_LIBRARY_PATH for CUDA (if needed)

The `svs_runner.py` automatically adds the ltx-env CUDA libraries when `--tiger-dir` is provided. If you run `diffsinger_infer.py` directly, set:

```bash
export LTX_NVIDIA=~/web/ltx-env/.venv/lib/python3.12/site-packages/nvidia
export LD_LIBRARY_PATH=$LTX_NVIDIA/cu13/lib:$LTX_NVIDIA/cudnn/lib:$LTX_NVIDIA/cuda_runtime/lib:$LD_LIBRARY_PATH
```

### 3. Download the TIGER voice pack

```bash
mkdir -p ~/web/diffsinger-env/tiger
# Download tiger_diffsinger_v106.zip from:
# https://github.com/spicytigermeat/tiger_diffsinger/releases/tag/v106
# Then extract:
cd ~/web/diffsinger-env/tiger
unzip ~/Downloads/tiger_diffsinger_v106.zip
```

**Do not commit TIGER files to this repo.** The pack is ~550 MB extracted.

Expected structure:
```
~/web/diffsinger-env/tiger/
  dsacoustic/
    acoustic.onnx         (327 MB — acoustic model)
    phonemes.txt          (phoneme map)
    tiger_fresh.emb       (speaker embedding, 1 KB)
    tiger_disco.emb
    ... (7 speaker files total)
  dsvocoder/
    tgm_hifigan.onnx      (56 MB — NSF-HiFiGAN vocoder)
  dsdur/                  (duration model — not used, SvsScore provides timing)
  dspitch/                (pitch model — not used, MIDI notes used directly)
  extra/
    LICENSE.md            ← check before any product use
```

> **License:** TIGER is a community voice. Check `extra/LICENSE.md` in the pack for redistribution terms before any commercial or public use.

### 4. Configure environment variables

Add to `.env` or export before starting the app:

```bash
# Core SVS settings
SVS_ENABLED=true
SVS_BACKEND=diffsinger
SVS_PYTHON=/home/<you>/web/diffsinger-env/venv/bin/python
SVS_TIGER_DIR=/home/<you>/web/diffsinger-env/tiger
SVS_SPEAKER=tiger_fresh        # Options: tiger_fresh, tiger_disco, tiger_electric,
                               #          tiger_vinyl, tiger_glam, tiger_mystic, tiger_royal
SVS_TIMEOUT_SECONDS=300
SVS_ALLOW_FALLBACK=true        # false = raise on failure instead of using mock

# Optional: separate Python for diffsinger inference (if different from SVS_PYTHON)
# SVS_DIFFSINGER_PYTHON=/home/<you>/web/diffsinger-env/venv/bin/python
```

### 5. Verify setup

```bash
python scripts/svs_doctor.py
```

Expected output:
```
SVS Doctor
  Backend: diffsinger
  Enabled: true

── Environment variables ──
  OK  SVS_BACKEND = 'diffsinger'
  OK  SVS_ENABLED = true
  OK  SVS_TIGER_DIR = /home/.../tiger
  ...

── TIGER model directory ──
  OK  dsacoustic/acoustic.onnx (327 MB)
  OK  dsacoustic/phonemes.txt
  OK  dsvocoder/tgm_hifigan.onnx (56 MB)
  OK  Speaker embedding: tiger_fresh.emb

── Summary ──
  All checks passed.
```

### 6. Generate a test stem

```bash
# Through the runner directly:
SVS_BACKEND=diffsinger \
SVS_TIGER_DIR=~/web/diffsinger-env/tiger \
python scripts/svs_runner.py \
  --score data/experiments/svs-diffsinger-v01/pop_chorus_score.json \
  --output /tmp/test_vocal.wav \
  --backend diffsinger \
  --tiger-dir ~/web/diffsinger-env/tiger \
  --speaker tiger_fresh
```

Or through the app API:
```bash
curl -s -X POST http://localhost:8000/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"title":"Test","prompt":"pop vocal","lyrics":"Verse:\nhello world\n","generator":"svs-vocal","duration_seconds":10,"mode":"vocal_demo"}' \
  | python -m json.tool
```

---

## Environment Variable Reference

| Variable | Default | Description |
|---|---|---|
| `SVS_ENABLED` | `true` | Enable SVS pipeline |
| `SVS_BACKEND` | `mock` | `mock` or `diffsinger` |
| `SVS_PYTHON` | system Python | Interpreter for svs_runner.py |
| `SVS_SCRIPT` | `./scripts/svs_runner.py` | Runner script path |
| `SVS_TIGER_DIR` | *(unset)* | Path to extracted TIGER voice pack |
| `SVS_SPEAKER` | `tiger_fresh` | Speaker/style for TIGER inference |
| `SVS_DIFFSINGER_PYTHON` | *(unset)* | Python for diffsinger_infer.py (overrides SVS_PYTHON for inference only) |
| `SVS_TIMEOUT_SECONDS` | `300` | Subprocess timeout (TIGER inference takes ~30–90s) |
| `SVS_ALLOW_FALLBACK` | `true` | Fall back to mock on failure vs raise |
| `SVS_MODEL_DIR` | `./data/svs_models` | Model dir (openvpi DiffSinger, not TIGER) |
| `SVS_COMMAND_TEMPLATE` | *(empty)* | Override full command template |

---

## Diagnostic Tool

```bash
python scripts/svs_doctor.py              # all checks including smoke render
python scripts/svs_doctor.py --skip-smoke # skip smoke render
```

The doctor checks in order:
1. Env vars are configured correctly
2. SVS_PYTHON exists
3. svs_runner.py exists
4. onnxruntime is importable (diffsinger backend only)
5. CUDAExecutionProvider available (diffsinger backend only)
6. TIGER dir has required files (diffsinger backend only)
7. Smoke render with mock backend (unless --skip-smoke)

---

## Known Constraints

- **CUDA required**: The TIGER acoustic model (`acoustic.onnx`) crashes onnxruntime 1.20.1's graph optimizer on CPU. `ORT_DISABLE_ALL` + `CUDAExecutionProvider` is the workaround built into `diffsinger_infer.py`.
- **LD_LIBRARY_PATH**: `svs_runner.py` automatically sets CUDA 13 + cuDNN library paths from `ltx-env` when `--tiger-dir` is provided. If you move libraries, update `_CUDA_LIB_DIRS` in `scripts/svs_runner.py`.
- **No duration model**: Phoneme durations come from `SvsScore` directly. The TIGER `dsdur` model is not used.
- **No pitch expression**: F0 comes from MIDI notes (flat per note). The TIGER `dspitch` model is not used.
- **Auto-render isolation**: The `auto-render` generator never routes to SVS. This is intentional and must not be changed.
