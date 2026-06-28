#!/usr/bin/env python3
"""One-shot XL/SFT generation using ACE inference API with Gradio-matched params.

Use this to check whether XL noise was caused by our cli.py bridge misconfiguration
(dcw_enabled, steps, guidance) vs the model/hardware itself.

Compare output against compare_ace_xl.py / ace_runner (CLI path).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from app.core.config import get_settings
from app.generators.ace_step.env import ace_subprocess_env
from app.generators.ace_step.inference_presets import build_generation_params_kwargs

DEFAULT_PROMPT = "ambient ocean waves, soft pads, gentle rhythm, cinematic"
DEFAULT_LYRICS = "[Instrumental]"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fair XL/SFT probe via ACE inference API")
    parser.add_argument("--checkpoint", default="acestep-v15-xl-sft")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--lyrics", default=DEFAULT_LYRICS)
    parser.add_argument("--seed", type=int, default=4242)
    parser.add_argument("--duration", type=int, default=15)
    parser.add_argument("--inference-steps", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    checkpoint_dir = settings.ace_model_dir.expanduser().resolve()
    ace_step_dir = settings.ace_step_dir.expanduser().resolve() if settings.ace_step_dir else Path("/home/administrator/models/ACE-Step-1.5")
    out_dir = settings.data_dir / "experiments" / "ace-fair-probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = args.output or (out_dir / f"{args.checkpoint.replace('/', '_')}_fair.wav")

    params_kwargs = build_generation_params_kwargs(
        checkpoint=args.checkpoint,
        caption=args.prompt,
        lyrics=args.lyrics,
        duration=args.duration,
        seed=args.seed,
        inference_steps=args.inference_steps,
        use_lm=False,
    )

    worker = textwrap.dedent(
        f"""
import json
import sys
from pathlib import Path

sys.path.insert(0, {repr(str(ace_step_dir))})

from acestep.handler import AceStepHandler
from acestep.inference import GenerationConfig, GenerationParams, generate_music

checkpoint = {repr(args.checkpoint)}
checkpoint_dir = Path({repr(str(checkpoint_dir))})
output = Path({repr(str(output.resolve()))})
params_kwargs = json.loads({json.dumps(params_kwargs)!r})

dit = AceStepHandler()
status, ok = dit.initialize_service(
    project_root={repr(str(ace_step_dir))},
    config_path=checkpoint,
    device="cuda",
    offload_to_cpu=True,
)
if not ok:
    raise SystemExit(f"DiT init failed: {{status}}")

params = GenerationParams(**params_kwargs)
config = GenerationConfig(batch_size=1, audio_format="wav", use_random_seed=False)
result = generate_music(dit, None, params=params, config=config, save_dir=str(output.parent))
if not result.success or not result.audios:
    raise SystemExit(result.status_message or "generation failed")
src = Path(result.audios[0].get("path", ""))
if src.resolve() != output.resolve():
    output.write_bytes(src.read_bytes())
print(json.dumps({{"ok": True, "output": str(output), "params": params_kwargs}}))
"""
    )

    env = ace_subprocess_env(settings)
    print(f"Fair probe: {args.checkpoint}")
    print(f"Params: {json.dumps(params_kwargs, indent=2)}")
    print(f"Output: {output}")
    print("(Loading XL may take several minutes on 12GB VRAM)\n")

    result = subprocess.run(
        [str(settings.ace_python), "-c", worker],
        cwd=str(ace_step_dir),
        env=env,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr[-4000:], file=sys.stderr)
        return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
