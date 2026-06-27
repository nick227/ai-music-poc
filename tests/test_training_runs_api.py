import json
import time

from app.domain.models import JobStatus
from app.domain.training import TrainingRun
from app.domain.training_presets import resolve_training_preset
from app.storage.training_run_store import TrainingRunStore
from tests.test_slices_api import _import_and_tag, _seed_categories


def _ready_slice(client) -> dict:
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="train-source.wav", category_id=genre["id"], rights_status="CONFIRMED")
    created = c.post(
        "/api/slices",
        json={"name": "Training Source", "media_ids": [tagged["id"]], "filter": {}},
    ).json()
    return c.post(f"/api/slices/{created['id']}/freeze").json()


def _draft_slice(client) -> dict:
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="draft-source.wav", category_id=genre["id"], rights_status="CONFIRMED")
    return c.post(
        "/api/slices",
        json={"name": "Draft Source", "media_ids": [tagged["id"]], "filter": {}},
    ).json()


def _wait_for_terminal_status(client, run_id: str, timeout_seconds: float = 2.0) -> dict:
    c, _ = client
    deadline = time.time() + timeout_seconds
    detail = c.get(f"/api/training/runs/{run_id}").json()
    while detail["status"] in {"QUEUED", "RUNNING"} and time.time() < deadline:
        time.sleep(0.02)
        detail = c.get(f"/api/training/runs/{run_id}").json()
    return detail


def test_create_training_run_requires_ready_slice(client):
    c, _ = client
    draft = _draft_slice(client)

    res = c.post(
        "/api/training/runs",
        json={
            "name": "Should fail",
            "dataset_slice_id": draft["id"],
            "config_preset": "calibration",
        },
    )

    assert res.status_code == 422
    assert "READY" in res.json()["message"]


def test_training_run_lifecycle_succeeds_with_logs_and_artifact(client):
    c, data_dir = client
    slice_record = _ready_slice(client)

    create = c.post(
        "/api/training/runs",
        json={
            "name": "Mock calibration",
            "dataset_slice_id": slice_record["id"],
            "config_preset": "calibration",
        },
    )
    assert create.status_code == 200
    body = create.json()
    assert body["status"] == "QUEUED"
    assert body["config_preset"] == "calibration"
    assert body["config"]["steps"] == 100
    assert body["style_version_id"] is None

    detail = _wait_for_terminal_status(client, body["id"])
    assert detail["status"] == "SUCCEEDED"
    assert detail["artifact_path"] == f"training_runs/{body['id']}/artifacts/lora.mock.json"
    assert detail["started_at"] is not None
    assert detail["finished_at"] is not None

    logs = c.get(f"/api/training/runs/{body['id']}/logs").json()
    assert logs["run_id"] == body["id"]
    assert "mock adapter: succeeded" in logs["log"]

    artifact_path = data_dir / detail["artifact_path"]
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["training_run_id"] == body["id"]
    assert artifact["dataset_slice_id"] == slice_record["id"]

    config_path = data_dir / "training_runs" / body["id"] / "config.json"
    assert config_path.exists()


def test_list_and_get_training_run(client):
    c, _ = client
    slice_record = _ready_slice(client)
    created = c.post(
        "/api/training/runs",
        json={"name": "Listed run", "dataset_slice_id": slice_record["id"], "config_preset": "standard"},
    ).json()

    listed = c.get("/api/training/runs").json()["runs"]
    assert any(item["id"] == created["id"] for item in listed)

    detail = c.get(f"/api/training/runs/{created['id']}").json()
    assert detail["name"] == "Listed run"
    assert detail["config_preset"] == "standard"


def test_single_flight_blocks_second_training_run(client):
    c, data_dir = client
    slice_record = _ready_slice(client)
    store = TrainingRunStore(data_dir / "training_runs")
    active = TrainingRun(
        name="Active run",
        dataset_slice_id=slice_record["id"],
        config_preset="calibration",
        config=resolve_training_preset("calibration"),
        status=JobStatus.RUNNING,
    )
    store.save(active)

    res = c.post(
        "/api/training/runs",
        json={"name": "Second", "dataset_slice_id": slice_record["id"], "config_preset": "calibration"},
    )
    assert res.status_code == 422
    assert "already active" in res.json()["message"]


def test_cancel_training_run(client):
    c, data_dir = client
    slice_record = _ready_slice(client)
    store = TrainingRunStore(data_dir / "training_runs")
    run = TrainingRun(
        name="Cancel me",
        dataset_slice_id=slice_record["id"],
        config_preset="calibration",
        config=resolve_training_preset("calibration"),
        status=JobStatus.RUNNING,
    )
    store.save(run)
    store.append_log(run.id, "running before cancel")

    res = c.post(f"/api/training/runs/{run.id}/cancel")
    assert res.status_code == 200
    cancelled = res.json()
    assert cancelled["status"] == "CANCELLED"

    logs = c.get(f"/api/training/runs/{run.id}/logs").json()
    assert "cancel requested" in logs["log"]


def test_unknown_config_preset_rejected(client):
    c, _ = client
    slice_record = _ready_slice(client)

    res = c.post(
        "/api/training/runs",
        json={"name": "Bad preset", "dataset_slice_id": slice_record["id"], "config_preset": "unknown"},
    )
    assert res.status_code == 422
