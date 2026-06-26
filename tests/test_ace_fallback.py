def test_ace_fallback_generates_when_not_configured(client):
    c, tmp = client
    res = c.post('/api/generate', json={
        'title': 'ACE fallback',
        'prompt': 'ambient instrumental',
        'lyrics': '',
        'generator': 'ace-step-command',
        'duration_seconds': 10,
        'mode': 'instrumental',
        'allow_fallback': True,
    })
    assert res.status_code == 200
    job_id = res.json()['job_id']
    job = c.get(f'/api/jobs/{job_id}').json()['job']
    assert job['status'] == 'SUCCEEDED'
    assert (tmp / 'outputs' / f'{job_id}.wav').exists()
    assert job['result']['generator_name'] == 'ace-step-command'
