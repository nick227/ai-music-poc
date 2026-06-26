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

## Rule

Do not put model logic in API routes. Routes should not know whether generation is procedural, local GPU, remote GPU, or hosted API.
