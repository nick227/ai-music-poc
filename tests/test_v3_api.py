def test_health_v3(client):
    c, _ = client
    data = c.get('/api/health').json()
    assert data['version'].startswith('3.')


def test_presets_api(client):
    c, _ = client
    data = c.get('/api/presets').json()
    assert len(data['presets']) >= 8
    assert any(p['id'] == 'french-disco-sad' for p in data['presets'])


def test_model_status_api(client):
    c, _ = client
    data = c.get('/api/model-status').json()
    assert data['fallback_enabled'] is True
    assert data['can_generate'] is False


def test_generators_include_v3_and_ace(client):
    c, _ = client
    names = [g['name'] for g in c.get('/api/generators').json()['generators']]
    assert 'procedural-v3' in names
    assert 'ace-step-command' in names
