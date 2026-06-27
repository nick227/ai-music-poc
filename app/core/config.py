from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    data_dir: Path = Field(default=Path("./data"), alias="DATA_DIR")
    default_generator: str = Field(default="procedural-v3", alias="DEFAULT_GENERATOR")
    max_duration_seconds: int = Field(default=240, alias="MAX_DURATION_SECONDS")
    max_prompt_chars: int = Field(default=2000, alias="MAX_PROMPT_CHARS")
    max_lyrics_chars: int = Field(default=10000, alias="MAX_LYRICS_CHARS")
    enable_cors: bool = Field(default=True, alias="ENABLE_CORS")
    cors_origins: str = Field(default="http://localhost:8000,http://localhost:5173", alias="CORS_ORIGINS")

    ace_enabled: bool = Field(default=False, alias="ACE_ENABLED")
    ace_step_dir: Path | None = Field(default=None, alias="ACE_STEP_DIR")
    ace_python: Path = Field(default=Path("python"), alias="ACE_PYTHON")
    ace_script: Path = Field(default=Path("./models/ACE-Step/infer.py"), alias="ACE_SCRIPT")
    ace_model_dir: Path = Field(default=Path("./models/ace-step"), alias="ACE_MODEL_DIR")
    ace_output_dir: Path = Field(default=Path("./data/model_outputs"), alias="ACE_OUTPUT_DIR")
    ace_timeout_seconds: int = Field(default=900, alias="ACE_TIMEOUT_SECONDS")
    ace_device: str = Field(default="auto", alias="ACE_DEVICE")
    ace_command_template: str = Field(default="", alias="ACE_COMMAND_TEMPLATE")
    ace_allow_fallback: bool = Field(default=True, alias="ACE_ALLOW_FALLBACK")
    hf_cache_dir: Path | None = Field(default=None, alias="HF_CACHE_DIR")
    save_full_lyrics: bool = Field(default=False, alias="SAVE_FULL_LYRICS")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    training_enabled: bool = Field(default=True, alias="TRAINING_ENABLED")
    training_mock_step_delay_seconds: float = Field(default=0.05, alias="TRAINING_MOCK_STEP_DELAY_SECONDS")

    @property
    def job_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def taxonomy_dir(self) -> Path:
        return self.data_dir / "taxonomy"

    @property
    def categories_dir(self) -> Path:
        return self.taxonomy_dir / "categories"

    @property
    def concepts_dir(self) -> Path:
        return self.taxonomy_dir / "concepts"

    @property
    def assignments_dir(self) -> Path:
        return self.taxonomy_dir / "assignments"

    @property
    def slices_dir(self) -> Path:
        return self.data_dir / "slices"

    @property
    def training_runs_dir(self) -> Path:
        return self.data_dir / "training_runs"

    @property
    def style_versions_dir(self) -> Path:
        return self.data_dir / "style_versions"

    @property
    def metadata_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def cors_origin_list(self) -> List[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
