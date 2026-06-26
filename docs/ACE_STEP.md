# ACE-Step adapter foundation

`app/generators/ace_step.py` provides the model integration seam without locking the app to one installer or CLI shape.

## Design

The app sends every generation request through the same `MusicGenerator` contract:

```python
generate(request: GenerationRequest, output_path: Path) -> GenerationResult
```

The ACE-Step adapter receives the full V2 request and can either:

1. Call an external command configured by `ACE_STEP_COMMAND_TEMPLATE`.
2. Fall back to the procedural generator when not configured and fallback is allowed.
3. Fail cleanly if fallback is disabled.

## Why command-template integration first

ACE-Step packaging and model-loading details may change. A subprocess boundary lets you test real inference without tying the web app to one Python environment, CUDA version, or model checkout.

Recommended later migration:

1. Keep this adapter.
2. Add a dedicated ACE runner script.
3. Once stable, add an in-process adapter or GPU worker adapter.
4. Keep the API and job service unchanged.

## Required command behavior

The command must:

- read prompt/lyrics/request data from supplied files
- generate one WAV
- write it exactly to `$output_path`
- exit `0` on success
- write useful errors to stderr on failure

## Example template

```env
ACE_STEP_COMMAND_TEMPLATE=python scripts/run_ace_step_example.py --request $request_file --out $output_path
```

`scripts/run_ace_step_example.py` is intentionally not a real ACE implementation. It documents the expected shape for your runner.
