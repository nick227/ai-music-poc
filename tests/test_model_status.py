def test_model_status_reports_fallback(client):
    c, _ = client
    res = c.get('/api/model-status')
    assert res.status_code == 200
    body = res.json()
    assert body['fallback_enabled'] is True
    assert body['can_generate'] is False


def test_model_status_includes_paths(client):
    c, _ = client
    body = c.get('/api/model-status').json()
    assert 'ace_python' in body
    assert 'ace_script' in body
    assert 'ace_model_dir' in body
