import json
import wave


def _payload(**overrides):
    payload = {
        'title': 'Test Song',
        'prompt': 'dark disco club song',
        'lyrics': 'one two three four',
        'generator': 'procedural-v3',
        'duration_seconds': 10,
        'mode': 'song',
        'structure': 'verse_chorus',
        'quality': 'draft',
        'genre_tags': ['disco'],
        'mood_tags': ['dark'],
        'allow_fallback': True,
    }
    payload.update(overrides)
    return payload


def test_generate_writes_wav_metadata_and_log(client):
    c, tmp = client
    res = c.post('/api/generate', json=_payload())
    assert res.status_code == 200
    job_id = res.json()['job_id']
    job = c.get(f'/api/jobs/{job_id}').json()['job']
    assert job['status'] == 'SUCCEEDED'
    wav_path = tmp / 'outputs' / f'{job_id}.wav'
    meta_path = tmp / 'outputs' / f'{job_id}.json'
    log_path = tmp / 'logs' / f'{job_id}.log'
    assert wav_path.exists()
    assert meta_path.exists()
    assert log_path.exists()
    with wave.open(str(wav_path), 'rb') as wav:
        assert wav.getnchannels() == 2
    meta = json.loads(meta_path.read_text())
    assert meta['title'] == 'Test Song'
    assert meta['lyrics_hash']
    assert 'lyrics' not in meta


def test_download_bundle(client):
    c, _ = client
    job_id = c.post('/api/generate', json=_payload()).json()['job_id']
    res = c.get(f'/api/download/{job_id}/bundle')
    assert res.status_code == 200
    assert res.headers['content-type'].startswith('application/zip')


def test_rerun(client):
    c, _ = client
    job_id = c.post('/api/generate', json=_payload()).json()['job_id']
    rerun = c.post(f'/api/jobs/{job_id}/rerun')
    assert rerun.status_code == 200
    assert rerun.json()['job_id'] != job_id


def test_unknown_generator_rejected(client):
    c, _ = client
    res = c.post('/api/generate', json=_payload(generator='missing'))
    assert res.status_code == 422
