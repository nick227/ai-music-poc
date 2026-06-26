# Command Template

`ACE_COMMAND_TEMPLATE` is rendered with Python `string.Template`.

## Core variables

- `$python`
- `$script`
- `$prompt_file`
- `$lyrics_file`
- `$negative_file`
- `$request_file`
- `$output_path`
- `$duration_seconds`
- `$seed`
- `$bpm`
- `$key`
- `$mode`
- `$structure`
- `$quality`
- `$guidance_scale`
- `$model_dir`
- `$device`

## Vocal variables (V3.4+)

- `$singing_voice` — `auto`, `female`, `male`, `choir`, `robot`, `whisper`
- `$vocal_intensity` — `0.0`–`1.0`
- `$vocal_style` — free-text vocal direction

Your runner should accept these even if ACE-Step ignores them directly (embed in prompt or map to ACE params).

## Example

```env
ACE_COMMAND_TEMPLATE=$python $script --prompt-file $prompt_file --lyrics-file $lyrics_file --negative-file $negative_file --output $output_path --duration $duration_seconds --seed $seed --guidance-scale $guidance_scale --quality $quality --singing-voice $singing_voice --vocal-intensity $vocal_intensity --vocal-style $vocal_style --model-dir $model_dir --device $device
```

Prefer file arguments over embedding long prompt text directly in the shell command.

## Validation

`GET /api/model-status` reports template warnings (e.g. missing `$output_path`).

`POST /api/model-status/test` also runs package checks and `ace_runner.py --dry-run`.
