# Generator adapters

All generators should follow the `MusicGenerator` protocol in `app/generators/base.py`.

```python
class MusicGenerator(Protocol):
    name: str
    label: str
    supports_lyrics: bool
    supports_seed: bool
    supports_duration: bool
    description: str

    def info(self) -> GeneratorInfo: ...
    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult: ...
```

## Adding ACE-Step or YuE later

Create a new file such as:

```txt
app/generators/ace_step.py
```

Then implement:

```python
class AceStepGenerator:
    name = "ace-step"
    ...

    def generate(self, request, output_path):
        # load model or call worker
        # write audio to output_path
        # return GenerationResult
```

Register it in `app/generators/registry.py`.

## SVS (controlled vocal path)

SVS consumes `vocal_plan.json` indirectly via `SvsScore` export — not raw plan parsing in the backend.

See [`SVS_ADAPTER_SCOPE.md`](SVS_ADAPTER_SCOPE.md) for the full Phase 1 design. Summary:

- **`VocalRenderer`** — narrow protocol: `VocalPlan` → `vocal_stem.wav`
- **`SvsCommandGenerator`** — `MusicGenerator` façade for `vocal_demo` / hybrid song modes
- **Command runner** — `scripts/svs_runner.py` + `SVS_*` env vars (same pattern as ACE)

Do not put DiffSinger/NNSVS inference code in API routes.

## Rule

Do not put model logic in API routes. Routes should not know whether generation is procedural, local GPU, remote GPU, or hosted API.
