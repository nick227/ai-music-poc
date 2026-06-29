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
        return f"{python} {script} --score $score_path --output $output_path --backend {self.settings.svs_backend}"

    def build(
        self,
        *,
        score_path: Path,
        output_path: Path,
        report_path: Path | None = None,
    ) -> list[str]:
        if self.settings.svs_command_template.strip():
            values = {
                "python": self.settings.svs_python if self.settings.svs_python.exists() else Path(sys.executable),
                "script": self.settings.svs_script,
                "score_path": score_path,
                "output_path": output_path,
                "model_dir": self.settings.svs_model_dir,
            }
            cmd = render_command(self.settings.svs_command_template, values)
            if report_path:
                cmd += ["--report", str(report_path)]
            return cmd

        python = str(self.settings.svs_python) if self.settings.svs_python.exists() else sys.executable
        script = str(self.settings.svs_script.expanduser().resolve())
        cmd = [
            python, script,
            "--score", str(score_path),
            "--output", str(output_path),
            "--backend", self.settings.svs_backend,
            "--timeout", str(self.settings.svs_timeout_seconds),
        ]
        if self.settings.svs_backend == "diffsinger":
            if self.settings.svs_tiger_dir:
                cmd += ["--tiger-dir", str(self.settings.svs_tiger_dir)]
            if self.settings.svs_diffsinger_python:
                cmd += ["--diffsinger-python", str(self.settings.svs_diffsinger_python)]
            cmd += ["--speaker", self.settings.svs_speaker]
        if report_path:
            cmd += ["--report", str(report_path)]
        return cmd

    def write_score_copy(self, score_path: Path, output_path: Path) -> Path:
        tmp_dir = self.settings.tmp_dir / output_path.stem
        tmp_dir.mkdir(parents=True, exist_ok=True)
        staged = tmp_dir / "svs_score.json"
        safe_write_text(staged, score_path.read_text(encoding="utf-8"))
        return staged
