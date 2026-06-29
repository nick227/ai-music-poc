from __future__ import annotations

import shlex
import sys
from pathlib import Path

from app.core.command_template import render_command, safe_write_text
from app.core.config import Settings

REQUIRED_OUTPUT_TOKEN = "$output_path"
REQUIRED_SCORE_TOKEN = "$score_path"


def validate_svs_template(template: str) -> list[str]:
    warnings: list[str] = []
    if not template.strip():
        warnings.append("SVS_COMMAND_TEMPLATE is empty.")
    if REQUIRED_OUTPUT_TOKEN not in template and "${output_path}" not in template:
        warnings.append("SVS_COMMAND_TEMPLATE should include $output_path.")
    if REQUIRED_SCORE_TOKEN not in template and "${score_path}" not in template:
        warnings.append("SVS_COMMAND_TEMPLATE should include $score_path.")
    return warnings


class SvsCommandBuilder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def default_template(self) -> str:
        python = self.settings.svs_python if self.settings.svs_python.exists() else Path(sys.executable)
        script = self.settings.svs_script.expanduser().resolve()
        return f"{python} {script} --score $score_path --output $output_path --backend mock"

    def build(self, *, score_path: Path, output_path: Path) -> list[str]:
        template = self.settings.svs_command_template.strip() or self.default_template()
        values = {
            "python": self.settings.svs_python if self.settings.svs_python.exists() else Path(sys.executable),
            "script": self.settings.svs_script,
            "score_path": score_path,
            "output_path": output_path,
            "model_dir": self.settings.svs_model_dir,
        }
        return render_command(template, values)

    def write_score_copy(self, score_path: Path, output_path: Path) -> Path:
        tmp_dir = self.settings.tmp_dir / output_path.stem
        tmp_dir.mkdir(parents=True, exist_ok=True)
        staged = tmp_dir / "svs_score.json"
        safe_write_text(staged, score_path.read_text(encoding="utf-8"))
        return staged
