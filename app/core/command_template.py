from __future__ import annotations

import shlex
from pathlib import Path
from string import Template
from typing import Mapping

REQUIRED_OUTPUT_TOKEN = "$output_path"


def validate_template(template: str) -> list[str]:
    warnings: list[str] = []
    if not template.strip():
        warnings.append("ACE_COMMAND_TEMPLATE is empty.")
    if REQUIRED_OUTPUT_TOKEN not in template and "${output_path}" not in template:
        warnings.append("ACE_COMMAND_TEMPLATE should include $output_path so the app can find the generated WAV.")
    if "$prompt_file" not in template and "${prompt_file}" not in template and "$prompt" not in template and "${prompt}" not in template:
        warnings.append("ACE_COMMAND_TEMPLATE should include prompt input via $prompt_file or $prompt.")
    return warnings


def render_command(template: str, values: Mapping[str, object]) -> list[str]:
    rendered = Template(template).safe_substitute({key: str(value) for key, value in values.items()})
    return shlex.split(rendered)


def safe_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
