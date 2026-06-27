const SLICE_ROLES = ['GOLD_REFERENCE', 'TRAINING_CANDIDATE', 'REFERENCE'];

let modelStatus = null;

function renderModelCard() {
  const ready = modelStatus?.can_generate || modelStatus?.wiring_ok;
  const statusEl = document.getElementById('model-status-text');
  const message = modelStatus?.user_message || (ready ? 'Your model is ready to generate.' : 'Your model still needs setup.');
  statusEl.textContent = ready
    ? `${message} Use the slice builder below to package reviewed reference audio.`
    : `${message} You can still build dataset slices while model setup continues in Settings.`;
  statusEl.classList.toggle('ready', !!ready);

  const rows = [
    ['Engine', 'ACE-Step'],
    ['Ready to generate', ready ? 'Yes' : 'No'],
    ['Model folder', modelStatus?.ace_model_dir || 'Not configured'],
    ['Checkpoints cache', modelStatus?.hf_cache_exists ? 'Found' : (modelStatus?.hf_cache_configured ? 'Path set, not found' : 'Not configured')],
    ['Fallback available', modelStatus?.fallback_enabled ? 'Yes' : 'No'],
  ];
  document.getElementById('model-details').innerHTML = rows
    .map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`)
    .join('');
}

async function init() {
  modelStatus = await StudioApi.modelStatus();
  renderModelCard();
  await WorkbenchSlice.init();
}

init();
