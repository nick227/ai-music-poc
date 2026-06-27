def test_generate_stable_contract(client):
    c, _ = client
    res = c.post("/api/generate", json={
        "title": "Contract",
        "prompt": "dark disco",
        "generator": "procedural-v3",
        "duration_seconds": 10,
    })
    assert res.status_code == 200
    body = res.json()
    assert body.keys() == {"job_id", "status", "output_path"}
    assert body["output_path"] is None

    poll = c.get(f"/api/jobs/{body['job_id']}/status")
    assert poll.status_code == 200
    poll_body = poll.json()
    assert poll_body.keys() == {"job_id", "status", "output_path"}
    assert poll_body["status"] == "SUCCEEDED"
    assert poll_body["output_path"] == f"outputs/{body['job_id']}.wav"


def test_job_status_not_found(client):
    c, _ = client
    res = c.get("/api/jobs/missing-job-id/status")
    assert res.status_code == 404
