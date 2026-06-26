def test_health(client):
    c, _ = client
    res = c.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
