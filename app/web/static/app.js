const form = document.querySelector('#generate-form');
const statusEl = document.querySelector('#status');
const progressEl = document.querySelector('#progress');
const errorEl = document.querySelector('#error');
const playerEl = document.querySelector('#player');
const downloadEl = document.querySelector('#download');
const bundleEl = document.querySelector('#bundle');
const jobsEl = document.querySelector('#jobs');
const generatorEl = document.querySelector('#generator');
const presetEl = document.querySelector('#preset');
const modelStatusEl = document.querySelector('#model-status');
const metadataEl = document.querySelector('#metadata');
const vocalIntensityEl = document.querySelector('#vocal_intensity');
const vocalIntensityValueEl = document.querySelector('#vocal_intensity_value');
const analyzeBtn = document.querySelector('#analyze');
const analyzeStatusEl = document.querySelector('#analyze-status');
let currentJobId = null;
let presets = [];

function setError(message) { errorEl.hidden = !message; errorEl.textContent = message || ''; }
function tags(value) { return value.split(',').map(x => x.trim()).filter(Boolean).slice(0, 12); }
function formPayload() {
  return {
    title: document.querySelector('#title').value,
    prompt: document.querySelector('#prompt').value,
    lyrics: document.querySelector('#lyrics').value,
    generator: generatorEl.value,
    duration_seconds: Number(document.querySelector('#duration').value),
    mode: document.querySelector('#mode').value,
    structure: document.querySelector('#structure').value,
    quality: document.querySelector('#quality').value,
    bpm: document.querySelector('#bpm').value ? Number(document.querySelector('#bpm').value) : null,
    key: document.querySelector('#key').value || null,
    vocal_style: document.querySelector('#vocal_style').value || null,
    singing_voice: document.querySelector('#singing_voice').value,
    vocal_intensity: Number(document.querySelector('#vocal_intensity').value),
    genre_tags: tags(document.querySelector('#genre_tags').value),
    mood_tags: tags(document.querySelector('#mood_tags').value),
    guidance_scale: Number(document.querySelector('#guidance').value),
    seed: document.querySelector('#seed').value ? Number(document.querySelector('#seed').value) : null,
    negative_prompt: document.querySelector('#negative').value,
    allow_fallback: document.querySelector('#fallback').checked,
    include_lyrics_in_bundle: document.querySelector('#lyrics_bundle').checked,
  };
}
async function api(url, options = {}) {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error(data?.message || data?.detail?.[0]?.msg || 'Request failed');
  return data;
}
async function loadGenerators() {
  const data = await api('/api/generators');
  generatorEl.innerHTML = data.generators.map(g => `<option value="${g.name}">${g.label} — ${g.status}</option>`).join('');
  if ([...generatorEl.options].some(o => o.value === 'procedural-v3')) generatorEl.value = 'procedural-v3';
}
async function loadPresets() {
  const data = await api('/api/presets');
  presets = data.presets;
  presetEl.innerHTML = '<option value="">Custom</option>' + presets.map(p => `<option value="${p.id}">${p.label}</option>`).join('');
}
function applyPreset(id) {
  const p = presets.find(x => x.id === id);
  if (!p) return;
  document.querySelector('#prompt').value = `${document.querySelector('#prompt').value}\n\nPreset direction: ${p.prompt_suffix}`.trim();
  document.querySelector('#negative').value = p.negative_prompt || '';
  document.querySelector('#mode').value = p.mode;
  document.querySelector('#structure').value = p.structure;
  document.querySelector('#quality').value = p.quality;
  document.querySelector('#duration').value = p.duration_seconds;
  document.querySelector('#bpm').value = p.bpm || '';
  document.querySelector('#key').value = p.key || '';
  document.querySelector('#vocal_style').value = p.vocal_style || '';
  document.querySelector('#singing_voice').value = p.singing_voice || 'auto';
  document.querySelector('#vocal_intensity').value = p.vocal_intensity ?? 0.65;
  vocalIntensityValueEl.textContent = (p.vocal_intensity ?? 0.65).toFixed(2);
  document.querySelector('#genre_tags').value = (p.genre_tags || []).join(', ');
  document.querySelector('#mood_tags').value = (p.mood_tags || []).join(', ');
}
async function loadModelStatus() {
  const s = await api('/api/model-status');
  const label = s.can_generate ? 'ACE Ready' : (s.fallback_enabled ? 'Fallback Active' : 'ACE Misconfigured');
  modelStatusEl.className = `status-strip ${s.can_generate ? 'ready' : ''}`;
  modelStatusEl.textContent = `${label} · command=${s.ace_command_configured ? 'set' : 'missing'} · python=${s.ace_python_exists ? 'ok' : 'missing'} · script=${s.ace_script_exists ? 'ok' : 'missing'} · model=${s.ace_model_dir_exists ? 'ok' : 'missing'}${s.warnings.length ? ' · ' + s.warnings.join(' ') : ''}`;
}
async function poll(jobId) {
  const data = await api(`/api/jobs/${jobId}`);
  const job = data.job;
  statusEl.textContent = `${job.status}\n${job.message}${job.error ? '\n' + job.error : ''}`;
  progressEl.value = job.progress || 0;
  metadataEl.hidden = !job.result;
  metadataEl.textContent = job.result ? JSON.stringify(job.result.metadata, null, 2) : '';
  if (data.download_url) {
    playerEl.hidden = false; playerEl.src = data.download_url;
    downloadEl.hidden = false; downloadEl.href = data.download_url;
    bundleEl.hidden = false; bundleEl.href = data.bundle_url;
    await loadJobs(); return;
  }
  if (['FAILED', 'TIMEOUT', 'CANCELLED'].includes(job.status)) { await loadJobs(); return; }
  setTimeout(() => poll(jobId).catch(err => setError(err.message)), 1200);
}
async function loadJobs() {
  const data = await api('/api/jobs');
  if (!data.jobs.length) { jobsEl.textContent = 'No jobs found.'; return; }
  jobsEl.classList.remove('muted');
  jobsEl.innerHTML = data.jobs.map(job => {
    const ready = job.status === 'SUCCEEDED' && job.result;
    return `<div class="job"><strong>${job.request.title}</strong><span>${job.status} · ${job.request.generator} · ${job.request.duration_seconds}s</span><small>${job.request.prompt.slice(0, 180)}</small><div class="actions">${ready ? `<a class="button ghost small" href="/api/download/${job.id}">WAV</a><a class="button ghost small" href="/api/download/${job.id}/bundle">Bundle</a>` : ''}<button class="small rerun" data-id="${job.id}" type="button">Rerun</button></div></div>`;
  }).join('');
  document.querySelectorAll('.rerun').forEach(btn => btn.addEventListener('click', async () => {
    setError('');
    const data = await api(`/api/jobs/${btn.dataset.id}/rerun`, { method: 'POST' });
    currentJobId = data.job_id; poll(currentJobId);
  }));
}
form.addEventListener('submit', async (event) => {
  event.preventDefault(); setError('');
  document.querySelector('#submit').disabled = true;
  playerEl.hidden = true; downloadEl.hidden = true; bundleEl.hidden = true; metadataEl.hidden = true;
  try {
    const data = await api('/api/generate', { method: 'POST', body: JSON.stringify(formPayload()) });
    currentJobId = data.job_id; statusEl.textContent = 'QUEUED\nJob submitted'; progressEl.value = 0; poll(currentJobId);
  } catch (err) { setError(err.message); }
  finally { document.querySelector('#submit').disabled = false; }
});
document.querySelector('#refresh').addEventListener('click', () => loadJobs().catch(err => setError(err.message)));
presetEl.addEventListener('change', () => applyPreset(presetEl.value));
vocalIntensityEl.addEventListener('input', () => { vocalIntensityValueEl.textContent = Number(vocalIntensityEl.value).toFixed(2); });
analyzeBtn.addEventListener('click', async () => {
  setError('');
  analyzeStatusEl.hidden = false;
  analyzeStatusEl.textContent = 'Analyzing prompt with Claude…';
  analyzeBtn.disabled = true;
  try {
    const result = await api('/api/analyze-prompt', {
      method: 'POST',
      body: JSON.stringify({ prompt: document.querySelector('#prompt').value, lyrics: document.querySelector('#lyrics').value }),
    });
    if (result.bpm) document.querySelector('#bpm').value = result.bpm;
    if (result.key) document.querySelector('#key').value = result.key;
    if (result.mode) document.querySelector('#mode').value = result.mode;
    if (result.structure) document.querySelector('#structure').value = result.structure;
    if (result.quality) document.querySelector('#quality').value = result.quality;
    if (result.singing_voice) document.querySelector('#singing_voice').value = result.singing_voice;
    if (result.vocal_style) document.querySelector('#vocal_style').value = result.vocal_style;
    if (result.genre_tags?.length) document.querySelector('#genre_tags').value = result.genre_tags.join(', ');
    if (result.mood_tags?.length) document.querySelector('#mood_tags').value = result.mood_tags.join(', ');
    if (result.negative_prompt) document.querySelector('#negative').value = result.negative_prompt;
    if (result.enhanced_prompt) document.querySelector('#prompt').value = result.enhanced_prompt;
    analyzeStatusEl.textContent = 'Prompt analyzed — fields updated. Review and generate.';
  } catch (err) {
    analyzeStatusEl.hidden = true;
    setError('Analyze failed: ' + err.message);
  } finally {
    analyzeBtn.disabled = false;
  }
});
Promise.all([loadGenerators(), loadPresets(), loadModelStatus(), loadJobs()]).catch(err => setError(err.message));
