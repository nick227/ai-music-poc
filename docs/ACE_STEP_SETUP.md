# ACE-Step Setup

V3.4 does not vendor ACE-Step. Install ACE-Step separately, then point this app at your local runner.

## Quick diagnostic

```bash
python scripts/ace_smoke_test.py --dry-run-only
curl -X POST http://localhost:8000/api/model-status/test | python -m json.tool
```

These checks verify:
- `.env` paths (`ACE_PYTHON`, `ACE_SCRIPT`, `ACE_MODEL_DIR`)
- Command template validity
- Torch/CUDA in the ACE venv
- Common ML packages (`torch`, `transformers`, `diffusers`, etc.)
- `ace_runner.py --dry-run` (bridge wiring, no inference)

## Required `.env` values

```env
ACE_ENABLED=true
ACE_PYTHON=/path/to/ace-env/bin/python
ACE_SCRIPT=./scripts/ace_runner.py
ACE_MODEL_DIR=/path/to/ACE-Step-1.5/checkpoints
ACE_TIMEOUT_SECONDS=1200
ACE_DEVICE=cuda
ACE_ALLOW_FALLBACK=true
ACE_COMMAND_TEMPLATE=$python $script --prompt-file $prompt_file --lyrics-file $lyrics_file --negative-file $negative_file --output $output_path --duration $duration_seconds --seed $seed --guidance-scale $guidance_scale --quality $quality --singing-voice $singing_voice --vocal-intensity $vocal_intensity --vocal-style $vocal_style --model-dir $model_dir --device $device
```

## Runner script

The repo includes `scripts/ace_runner.py` — a bridge to ACE-Step `cli.py`. Copy or adapt it for your checkout:

```bash
python scripts/ace_runner.py --dry-run
```

When packages are missing, install into the **ACE venv** (not the app venv):

```bash
/path/to/ACE-Step-1.5/.venv/bin/pip install torch torchaudio transformers diffusers accelerate
```

## Smoke test progression

1. `python scripts/ace_smoke_test.py --dry-run-only` — wiring only
2. `python scripts/ace_smoke_test.py` — render command, no inference
3. `python scripts/ace_smoke_test.py --run-generation --duration 10` — full ACE call

In the UI, use `ace-step-command` with **allow fallback: off** while debugging ACE errors.

## How generation works

The adapter writes temp files to `data/tmp/<job_id>/`:
- `prompt.txt` (includes vocal direction when singing)
- `lyrics.txt`
- `negative_prompt.txt`
- `request.json`

The command must write the final WAV to `$output_path`.

## Procedural vs ACE vocals

| Mode | Singing quality | Setup |
|------|-----------------|-------|
| `procedural-v3` | CPU formant demo vocals | None |
| `ace-step-command` | Neural ACE-Step singing | GPU + ACE venv + checkpoints |

Procedural jobs at `balanced`/`high` quality may include `vocal_stem.wav` in bundles and at `/api/download/{job_id}/vocal`.
