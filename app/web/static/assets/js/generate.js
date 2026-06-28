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
const styleVersionEl = document.querySelector('#style_version');
const loraScaleWrap = document.querySelector('#lora-scale-wrap');
const loraScaleEl = document.querySelector('#lora_scale');
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
    generator: 'auto-render',
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
    style_version_id: styleVersionEl.value || null,
    lora_scale: styleVersionEl.value ? Number(loraScaleEl.value) : 1.0,
  };
}
function syncStyleVersionControls() {
  const styled = Boolean(styleVersionEl.value);
  loraScaleWrap.hidden = !styled;
  if (styled) {
    document.querySelector('#fallback').checked = false;
    const qualityEl = document.querySelector('#quality');
    if (qualityEl.value === 'draft') qualityEl.value = 'balanced';
  }
}
async function api(url, options = {}) {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error(data?.message || data?.detail?.[0]?.msg || 'Request failed');
  return data;
}
async function loadStyleVersions() {
  const versions = await api('/api/style-versions').then((r) => r.style_versions || []);
  const loadable = versions.filter((v) => v.ace_loadable === true);
  styleVersionEl.innerHTML = '<option value="">Base model only (no LoRA)</option>' + loadable
    .map((v) => `<option value="${v.id}">LoRA: ${v.name}</option>`)
    .join('');
  syncStyleVersionControls();
}
styleVersionEl.addEventListener('change', syncStyleVersionControls);
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
    await loadJobs();
    if (typeof window.loadSongs === 'function') await window.loadSongs();
    return;
  }
  if (['FAILED', 'TIMEOUT', 'CANCELLED'].includes(job.status)) { await loadJobs(); return; }
  setTimeout(() => poll(jobId).catch(err => setError(err.message)), 1200);
}
let recentJobsCache = [];

async function loadJobs() {
  const data = await api('/api/jobs');
  if (!data.jobs.length) { jobsEl.textContent = 'No songs found.'; return; }
  recentJobsCache = data.jobs;
  jobsEl.classList.remove('muted');
  jobsEl.innerHTML = data.jobs.map(job => {
    const ready = job.status === 'SUCCEEDED' && job.result;
    const req = job.request;
    const meta = [
      job.status,
      req.quality || 'balanced',
      req.style_version_id ? 'LoRA' : 'base',
      `${req.duration_seconds}s`,
      req.mode,
      req.singing_voice,
      req.vocal_intensity != null ? `vocal_intensity: ${req.vocal_intensity}` : null,
      req.vocal_style,
    ].filter(Boolean).join(' · ');
    
    const playBtn = ready ? `<button style="min-width: 90px;" class="button ghost small play-btn" data-url="/api/download/${job.id}" type="button">▶ Play</button>` : '';
    const wavBtn = ready ? `<a class="button ghost small" href="/api/download/${job.id}">WAV</a>` : '';
    const bundleBtn = ready ? `<a class="button ghost small" href="/api/download/${job.id}/bundle">Bundle</a>` : '';
    
    return `<div class="job"><strong>${req.title}</strong><span style="display: block; margin-bottom: 4px;">${meta}</span><small>${req.prompt.slice(0, 180)}</small><div class="actions">${playBtn}${wavBtn}${bundleBtn}<button class="small load-btn" data-id="${job.id}" type="button">Cover</button></div></div>`;
  }).join('');
  
  document.querySelectorAll('.load-btn').forEach(btn => btn.addEventListener('click', () => {
    const job = recentJobsCache.find(j => j.id === btn.dataset.id);
    if (!job) return;
    const req = job.request;
    
    document.querySelector('#title').value = req.title || '';
    document.querySelector('#prompt').value = req.prompt || '';
    document.querySelector('#lyrics').value = req.lyrics || '';
    if (req.generator) { /* always auto-render */ }
    document.querySelector('#duration').value = req.duration_seconds || 60;
    if (req.mode) document.querySelector('#mode').value = req.mode;
    if (req.structure) document.querySelector('#structure').value = req.structure;
    if (req.quality) document.querySelector('#quality').value = req.quality;
    document.querySelector('#bpm').value = req.bpm || '';
    document.querySelector('#key').value = req.key || '';
    document.querySelector('#vocal_style').value = req.vocal_style || '';
    if (req.singing_voice) document.querySelector('#singing_voice').value = req.singing_voice;
    if (req.vocal_intensity != null) {
      document.querySelector('#vocal_intensity').value = req.vocal_intensity;
      vocalIntensityValueEl.textContent = Number(req.vocal_intensity).toFixed(2);
    }
    document.querySelector('#genre_tags').value = (req.genre_tags || []).join(', ');
    document.querySelector('#mood_tags').value = (req.mood_tags || []).join(', ');
    if (req.guidance_scale != null) document.querySelector('#guidance').value = req.guidance_scale;
    document.querySelector('#seed').value = req.seed || '';
    document.querySelector('#negative').value = req.negative_prompt || '';
    if (req.allow_fallback != null) document.querySelector('#fallback').checked = req.allow_fallback;
    if (req.include_lyrics_in_bundle != null) document.querySelector('#lyrics_bundle').checked = req.include_lyrics_in_bundle;
    if (req.style_version_id) document.querySelector('#style_version').value = req.style_version_id;
    else document.querySelector('#style_version').value = '';
    if (req.lora_scale != null) loraScaleEl.value = req.lora_scale;
    syncStyleVersionControls();
    
    document.querySelector('#preset').value = ''; // Reset preset since we loaded custom values
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }));
  
  document.querySelectorAll('.play-btn').forEach(btn => btn.addEventListener('click', () => {
    if (playerEl.src.endsWith(btn.dataset.url)) {
      if (playerEl.paused) playerEl.play();
      else playerEl.pause();
    } else {
      playerEl.hidden = false;
      playerEl.src = btn.dataset.url;
      playerEl.play();
    }
  }));
}

playerEl.addEventListener('play', () => {
  document.querySelectorAll('.play-btn').forEach(b => {
    b.textContent = playerEl.src.endsWith(b.dataset.url) ? '⏸ Pause' : '▶ Play';
  });
});

playerEl.addEventListener('pause', () => {
  document.querySelectorAll('.play-btn').forEach(b => b.textContent = '▶ Play');
});

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
  analyzeStatusEl.textContent = 'Analyzing prompt…';
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
    analyzeStatusEl.textContent = result.ai_enhanced
      ? 'AI-enhanced analysis done — fields updated. Review and generate.'
      : 'Prompt analyzed (heuristic) — fields updated. Add ANTHROPIC_API_KEY to .env for AI analysis.';
  } catch (err) {
    analyzeStatusEl.hidden = true;
    setError('Analyze failed: ' + err.message);
  } finally {
    analyzeBtn.disabled = false;
  }
});
async function loadContextMedia() {
  const mediaId = new URLSearchParams(window.location.search).get('context_media');
  if (!mediaId) return;
  const media = await StudioApi.getMedia(mediaId);
  const banner = document.querySelector('#context-banner');
  banner.hidden = false;
  document.querySelector('#context-title').textContent = media.title;
  document.querySelector('#context-workbench').href = StudioRoutes.workbench;
  const cats = (media.category_assignments || []).map((a) => a.category_id);
  if (cats.length) {
    const taxonomy = await StudioApi.listCategories();
    const byId = new Map((taxonomy.categories || []).map((c) => [c.id, c]));
    const labels = cats.map((id) => {
      const cat = byId.get(id);
      return cat ? `${cat.dimension.toLowerCase()}: ${cat.name}` : id;
    });
    document.querySelector('#context-cats').textContent = labels.join(' · ');
    const genreTags = labels.filter((l) => l.startsWith('genre:')).map((l) => l.split(': ')[1]);
    const moodTags = labels.filter((l) => l.startsWith('mood:')).map((l) => l.split(': ')[1]);
    if (genreTags.length) document.querySelector('#genre_tags').value = genreTags.join(', ');
    if (moodTags.length) document.querySelector('#mood_tags').value = moodTags.join(', ');
    if (!document.querySelector('#title').value || document.querySelector('#title').value === 'Midnight Demo') {
      document.querySelector('#title').value = `${media.title} (baseline)`;
    }
  }
}

Promise.all([loadPresets(), loadStyleVersions(), loadModelStatus(), loadJobs(), loadContextMedia()]).catch(err => setError(err.message));
