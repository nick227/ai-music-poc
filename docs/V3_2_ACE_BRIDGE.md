# V3.2 ACE Bridge

V3.2 keeps the web app independent from heavy model dependencies. ACE-Step should run in its own Python environment and be called as a subprocess through `ACE_COMMAND_TEMPLATE`.

## Boundary

```txt
FastAPI app → ace-step-command adapter → ACE_COMMAND_TEMPLATE → external runner → WAV output
```

The adapter validates the returned WAV and records command output tails in metadata.

## Runner contract

The app is designed to call a stable wrapper script with this shape:

```bash
python ~/models/ace_runner.py \
  --prompt-file /tmp/prompt.txt \
  --lyrics-file /tmp/lyrics.txt \
  --negative-file /tmp/negative_prompt.txt \
  --output /tmp/song.wav \
  --duration 30 \
  --seed 1234 \
  --guidance-scale 7.5 \
  --quality draft \
  --model-dir /path/to/checkpoints \
  --device cuda
```

ACE internals may change. Keep this wrapper stable and translate inside it.

## Smoke test

Use:

```bash
python scripts/ace_smoke_test.py
```

This checks env/config and renders the command. Add `--run-generation` only after the external ACE runner is real.

## Failure policy

When `allow_fallback` is true and `ACE_ALLOW_FALLBACK=true`, failed or missing ACE config produces procedural fallback output with fallback reason in metadata.

For real ACE debugging, disable fallback in the UI/request.
