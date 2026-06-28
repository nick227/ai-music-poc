from __future__ import annotations

from typing import Any


_KEY_ALIASES: dict[str, str] = {
    "generationId": "generation_id",
    "modelVersion": "model_version",
    "styleVersionId": "style_version_id",
    "trainingRunId": "training_run_id",
    "datasetSliceId": "dataset_slice_id",
    "modelArtifactId": "model_artifact_id",
    "targetConceptId": "target_concept_id",
    "targetCategoryIds": "target_category_ids",
    "negativePrompt": "negative_prompt",
    "durationSeconds": "duration_seconds",
    "parentGenerationId": "parent_generation_id",
    "batchId": "batch_id",
    "generatorName": "generator_name",
    "outputFile": "output_file",
    "vocalStyle": "vocal_style",
    "singingVoice": "singing_voice",
    "vocalIntensity": "vocal_intensity",
    "genreTags": "genre_tags",
    "moodTags": "mood_tags",
    "guidanceScale": "guidance_scale",
    "allowFallback": "allow_fallback",
    "loraLoadAttempted": "lora_load_attempted",
    "loraLoadSucceeded": "lora_load_succeeded",
    "loraLoadMessage": "lora_load_message",
    "loraPath": "lora_path",
    "loraScale": "lora_scale",
    "useLora": "use_lora",
    "renderRoute": "render_route",
    "renderBackend": "render_backend",
    "loraAdapterName": "lora_adapter_name",
}


def normalize_version_details(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        snake = _KEY_ALIASES.get(key, key)
        if snake in normalized and normalized[snake] not in (None, "", [], {}):
            continue
        normalized[snake] = value
    settings = normalized.get("settings")
    if isinstance(settings, dict):
        normalized["settings"] = {
            _KEY_ALIASES.get(k, k): v for k, v in settings.items()
        }
    return normalized
