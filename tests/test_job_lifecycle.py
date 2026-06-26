def test_generate_job_succeeds_and_downloads(client):
    c, data_dir = client
    res = c.post("/api/generate", json={"prompt": "dark disco", "lyrics": "hello night", "duration_seconds": 10, "seed": 1})
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    status = c.get(f"/api/jobs/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["job"]["status"] == "SUCCEEDED"
    assert body["download_url"] == f"/api/download/{job_id}"

    assert (data_dir / "jobs" / f"{job_id}.json").exists()
    assert (data_dir / "outputs" / f"{job_id}.wav").exists()

    download = c.get(f"/api/download/{job_id}")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("audio/wav")
    assert len(download.content) > 1000
