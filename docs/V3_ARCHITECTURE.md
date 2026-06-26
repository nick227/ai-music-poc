# V3 Architecture

V3 is organized around a swappable generator boundary.

Browser UI -> API route -> GenerationService -> JobService -> selected generator -> output stores.

Routes never generate audio directly. Generators receive a `GenerationRequest` and an output path, then return a `GenerationResult`.

## Main paths

- `app/domain/models.py`: API and job models
- `app/domain/presets.py`: reusable song draft presets
- `app/generators/procedural.py`: CPU fallback generator
- `app/generators/ace_step/`: ACE command adapter
- `app/services/generation_service.py`: job execution
- `app/services/bundle_service.py`: reproducible zip bundle
- `app/storage/metadata_store.py`: sidecar metadata JSON
- `app/storage/log_store.py`: per-job logs
