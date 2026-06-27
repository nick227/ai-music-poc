import json
import time

from app.api import dependencies
from app.core.config import get_settings
from tests.conftest import clear_caches
from tests.test_slices_api import _import_and_tag, _seed_categories


def _wait_for_terminal_status(client, run_id: str, timeout_seconds: float = 2.0) -> dict:
    c, _ = client
    deadline = time.time() + timeout_seconds
    detail = c.get(f"/api/training/runs/{run_id}").json()
    while detail["status"] in {"QUEUED", "RUNNING"} and time.time() < deadline:
        time.sleep(0.02)
        detail = c.get(f"/api/training/runs/{run_id}").json()
    return detail


def test_pipeline_status_reports_mock_adapter(client):
    c, _ = client
    body = c.get("/api/training/pipeline-status").json()
    assert body["adapter"] == "mock-training"
    assert body["adapter_label"] == "Mock training"
    assert body["training_enabled"] is True
    assert body["ace_training_enabled"] is False


def test_mock_run_includes_truthful_status_labels(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="status-mock.wav", category_id=genre["id"])

    create = c.post("/api/training/packages", json={"config_preset": "calibration"}).json()
    assert create["package"]["status_label"] == "Training package ready"
    run_id = create["run"]["id"]
    assert create["run"]["status_label"] == "Training queued"
    assert create["run"]["ace_training_enabled"] is False

    detail = _wait_for_terminal_status(client, run_id)
    assert detail["status"] == "SUCCEEDED"
    assert detail["status_label"] == "Mock training complete · artifact produced"
    assert detail["artifact_produced"] is True
    assert detail["dry_run"] is False
    assert detail["mock_training"] is True
    assert detail["style_version_created"] is True

    media = c.get(f"/api/media/{tagged['id']}").json()
    assert media["ingestion_status"] == "INGESTED"


def test_dry_run_adapter_renders_command_without_artifact_or_ingest(client, monkeypatch):
    c, data_dir = client
    monkeypatch.setenv(
        "ACE_TRAIN_COMMAND_TEMPLATE",
        "$python $script --request-file $request_file --package $package_path --config $config_file "
        "--output-dir $output_dir --model-dir $model_dir --device $device --steps $steps --rank $rank "
        "--learning-rate $learning_rate --epochs $epochs",
    )
    monkeypatch.setenv("TRAINING_ADAPTER", "ace-step-dry-run")
    get_settings.cache_clear()
    clear_caches()

    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="status-dry.wav", category_id=genre["id"])

    create = c.post("/api/training/packages", json={}).json()
    run_id = create["run"]["id"]
    detail = _wait_for_terminal_status(client, run_id)

    assert detail["status"] == "SUCCEEDED"
    assert detail["status_label"] == "ACE command rendered · real training not enabled"
    assert detail["artifact_produced"] is False
    assert detail["dry_run"] is True
    assert detail["style_version_created"] is False
    assert detail["artifact_path"] is None

    media = c.get(f"/api/media/{tagged['id']}").json()
    assert media["ingestion_status"] != "INGESTED"
    assert media["ready_audio"] is True

    command_path = data_dir / "training_runs" / run_id / "ace_train_command.json"
    assert command_path.exists()
    command_payload = json.loads(command_path.read_text(encoding="utf-8"))
    assert command_payload["dry_run"] is True
    assert command_payload["command"]

    pipeline = c.get("/api/training/pipeline-status").json()
    assert pipeline["adapter"] == "ace-step-dry-run"
    assert pipeline["ace_training_enabled"] is False

    dependencies.get_training_adapter.cache_clear()
    dependencies.get_training_service.cache_clear()
    get_settings.cache_clear()
