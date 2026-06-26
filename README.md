# AI Music POC v3.4

Local prompt-and-lyrics music generation console with persistent jobs, downloadable WAV/bundles, instant parametric drafts with synthetic singing voices, and an ACE-Step final-render bridge.

## What V3.4 adds

- Line-aware lyric timing (phrases follow lyric lines, not flat word cycling)
- Formant singing voices: female, male, choir, robot, whisper (auto-detected from prompt)
- Chorus vocal harmony (thirds and fifths)
- Quality tiers affect synthesis depth: draft / balanced / high
- Vocal reverb, delay, and room mix on balanced/high
- Style-specific chord progressions (pop I–V–vi–IV, etc.)
- Optional `vocal_stem.wav` export in balanced/high bundles
- ACE runner contract extended with `--singing-voice`, `--vocal-intensity`, `--vocal-style`

## What V3.2 adds

- Stronger `ace-step-command` bridge
- Stable external runner contract in `scripts/model_runners/ace_runner.example.py`
- `scripts/ace_smoke_test.py` for command rendering and optional real model execution
- Torch/CUDA diagnostic through `POST /api/model-status/test`
- WAV validation for external model output
- ACE stdout/stderr tails captured in generation metadata
- Better failure behavior when fallback is disabled

## What this is not

This zip does **not** include ACE-Step, YuE, model weights, CUDA dependencies, or a neural singing model. Procedural mode uses CPU formant synthesis — useful for melody/lyric demos, not studio vocals. Real sung lyrics require wiring ACE-Step externally.

## Run the app

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Open:

```txt
http://localhost:8000
```

## Test fallback generation

Use generator:

```txt
auto-render
```

Render routing:

```txt
Draft            -> procedural-v3 parametric engine
Balanced / High  -> ACE-Step command adapter, with procedural fallback while allowed
```

This proves the app/job/download/bundle pipeline immediately while ACE setup is still in progress. Procedural mode sings lyrics with synthetic formant voices. Use `quality: balanced` or `high` for vocal stem export in bundles and, once ACE is enabled, neural final renders.

## ACE bridge setup

1. Install ACE-Step in a separate folder, for example `~/models/ACE-Step-1.5`.
2. Confirm ACE works outside this app.
3. Copy the example runner:

```bash
mkdir -p ~/models
cp scripts/model_runners/ace_runner.example.py ~/models/ace_runner.py
chmod +x ~/models/ace_runner.py
```

4. Edit `~/models/ace_runner.py` and replace `run_ace_step()` with the real ACE-Step call for your installed checkout.
5. Update `.env`:

```env
ACE_ENABLED=true
ACE_STEP_DIR=/home/administrator/models/ACE-Step-1.5
ACE_PYTHON=/home/administrator/models/ACE-Step-1.5/.venv/bin/python
ACE_SCRIPT=/home/administrator/models/ace_runner.py
ACE_MODEL_DIR=/mnt/c/Users/Administrator/.cache/huggingface/ace-step-checkpoints
ACE_DEVICE=cuda
ACE_ALLOW_FALLBACK=true
ACE_TIMEOUT_SECONDS=1200
HF_CACHE_DIR=/mnt/c/Users/Administrator/.cache/huggingface
ACE_COMMAND_TEMPLATE=$python $script --prompt-file $prompt_file --lyrics-file $lyrics_file --negative-file $negative_file --output $output_path --duration $duration_seconds --seed $seed --guidance-scale $guidance_scale --quality $quality --singing-voice $singing_voice --vocal-intensity $vocal_intensity --vocal-style $vocal_style --model-dir $model_dir --device $device
```

`HF_CACHE_DIR` should point at one shared Hugging Face cache. `ACE_MODEL_DIR` should point at one shared ACE checkpoint folder. ACE-Step can reuse compatible Hugging Face cache files there, but it cannot reuse Ollama's `.ollama/models` blobs.

## ACE smoke test

Render and inspect the command without running model inference:

```bash
python scripts/ace_smoke_test.py
```

Run the configured command and validate the WAV:

```bash
python scripts/ace_smoke_test.py --run-generation --duration 10
```

For true testing in the UI, choose:

```txt
generator: ace-step-command
allow fallback: off
```

That prevents procedural fallback from hiding ACE errors.

## API checks

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/model-status | python -m json.tool
curl -X POST http://localhost:8000/api/model-status/test | python -m json.tool
curl http://localhost:8000/api/presets | python -m json.tool
```

## Tests

```bash
pytest
```

Expected for this package:

```txt
29 passed
```

## Safe copy-over notes

The package contains source, docs, tests, config examples, static UI, and empty data placeholders only. It intentionally excludes virtualenvs, caches, generated audio, job JSON, logs, model weights, and Windows `Zone.Identifier` sidecars.
