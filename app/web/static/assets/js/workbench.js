let modelStatus = null;
let pipelineStatus = null;
let runtimeStatus = null;

function gate(ok) {
  return ok ? '<span class="status-pill ready">ok</span>' : '<span class="status-pill failed">fail</span>';
}

function renderModelCard() {
  const rt = runtimeStatus;
  const legacy = modelStatus;

  // Primary readiness signal: prefer runtime status when available
  const aceUsable = rt?.ace_usable ?? false;
  const wiringOk = legacy?.can_generate || legacy?.wiring_ok || false;
  const ready = aceUsable || wiringOk;

  const statusEl = document.getElementById('model-status-text');
  const message = rt?.user_message || legacy?.user_message || (ready ? 'ACE ready' : 'ACE not ready');
  statusEl.textContent = ready
    ? message
    : `${message} You can create training packages during setup.`;
  statusEl.classList.toggle('ready', ready);

  const hw = rt?.hardware;
  const safe = hw?.safe_recommended_config;
  const detected = hw?.detected_available_config;

  // Runtime status gate rows
  const gateRows = rt ? [
    ['Packages', gate(rt.deps_ok)],
    ['CUDA', gate(rt.cuda_ok)],
    ['Checkpoints', gate(rt.checkpoints_ok)],
    ['ffprobe', gate(rt.ffprobe_ok)],
    ['Generation', gate(rt.generation_ok)],
    ['Audio valid', gate(rt.audio_valid)],
  ] : [];

  // Hardware info rows
  const hwRows = hw ? [
    ['GPU', hw.gpu_name ? `${hw.gpu_name} (${Math.round(hw.gpu_vram_mb / 1024)} GB)` : 'Not detected'],
    ['CUDA version', hw.cuda_version || '—'],
    ['Turbo checkpoint', hw.turbo_checkpoint || 'Not found'],
    ['Safe LM (0.6B)', hw.lm_safe_checkpoint || 'Not installed'],
    ['Advanced LM (1.7B)', hw.lm_checkpoint && hw.lm_checkpoint !== hw.lm_safe_checkpoint ? hw.lm_checkpoint : '—'],
    ['VAE', hw.vae_present ? 'Present' : 'Missing'],
  ] : [];

  // Safe config rows
  const safeRows = safe ? [
    ['Active checkpoint', safe.checkpoint || '—'],
    ['LM model', safe.lm_model || 'none'],
    ['Inference steps', String(safe.inference_steps)],
    ['Offload to CPU', safe.offload_to_cpu ? 'Yes' : 'No'],
    ['Batch size', String(safe.batch_size)],
  ] : [];

  // Last smoke test
  const smoke = rt?.last_smoke_test;
  const smokeRows = smoke ? [
    ['Last smoke test', smoke.ok ? 'Passed' : `Failed: ${smoke.error || 'unknown'}`],
    ['Audio duration', smoke.audio?.duration_seconds ? `${smoke.audio.duration_seconds}s` : '—'],
    ['Codec', smoke.audio?.codec_name ? `${smoke.audio.codec_name} @ ${smoke.audio.sample_rate}Hz` : '—'],
    ['Tested at', smoke.ran_at ? new Date(smoke.ran_at).toLocaleString() : '—'],
  ] : [
    ['Smoke test', 'Not run — POST /api/ace-runtime-status/validate to run'],
  ];

  // Legacy wiring rows (always shown as fallback)
  const legacyRows = [
    ['Training mode', pipelineStatus?.adapter_label || '—'],
    ['ACE training', pipelineStatus?.ace_training_enabled ? 'Enabled' : 'Not enabled'],
    ['Model folder', legacy?.ace_model_dir || '—'],
  ];

  function section(heading, rows) {
    if (!rows.length) return '';
    const inner = rows.map(([l, v]) => `<dl><dt>${l}</dt><dd>${v}</dd></dl>`).join('');
    return `<div class="model-detail-section"><p class="model-detail-heading">${heading}</p>${inner}</div>`;
  }

  const lmWarnHtml = rt?.lm_warning
    ? `<div class="lm-warning">${rt.lm_warning}</div>`
    : '';

  document.getElementById('model-details').innerHTML =
    lmWarnHtml +
    section('Runtime gates', gateRows) +
    section('Hardware', hwRows) +
    section('Safe recommended config', safeRows) +
    section('Smoke test', smokeRows) +
    section('Pipeline', legacyRows);

  const pipelineEl = document.getElementById('pipeline-status-text');
  if (pipelineEl && pipelineStatus) {
    pipelineEl.textContent = pipelineStatus.message;
  }
}

async function init() {
  [modelStatus, pipelineStatus, runtimeStatus] = await Promise.all([
    StudioApi.modelStatus().catch(() => null),
    StudioApi.getTrainingPipelineStatus().catch(() => null),
    StudioApi.aceRuntimeStatus().catch(() => null),
  ]);
  renderModelCard();
  await WorkbenchPackages.init();

  const validateBtn = document.getElementById('validate-runtime-btn');
  if (validateBtn) {
    validateBtn.addEventListener('click', async () => {
      validateBtn.disabled = true;
      validateBtn.textContent = 'Running…';
      try {
        runtimeStatus = await StudioApi.validateAceRuntime();
        renderModelCard();
      } catch (err) {
        console.error('Runtime validation failed', err);
      } finally {
        validateBtn.disabled = false;
        validateBtn.textContent = 'Run validation';
      }
    });
  }
}

init();
