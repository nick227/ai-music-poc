def test_empty_prompt_rejected(client):
    c, _ = client
    res = c.post('/api/generate', json={'prompt': '', 'lyrics': 'x'})
    assert res.status_code == 422


def test_unknown_generator_rejected(client):
    c, _ = client
    res = c.post('/api/generate', json={'prompt': 'test', 'generator': 'missing'})
    assert res.status_code == 422
    assert res.json()['error'] == 'validation_error'


def test_duration_above_max_rejected(client):
    c, _ = client
    res = c.post('/api/generate', json={'prompt': 'test', 'duration_seconds': 999})
    assert res.status_code == 422
