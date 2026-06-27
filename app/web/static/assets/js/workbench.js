let modelStatus = null;

function renderModelCard() {
  const ready = modelStatus?.can_generate || modelStatus?.wiring_ok;
  const statusEl = document.getElementById('model-status-text');
  const message = modelStatus?.user_message || (ready ? 'Your model is ready to generate.' : 'Your model still needs setup.');
  statusEl.textContent = ready
    ? `${message} Curate audio in Media, then create a training package below.`
    : `${message} You can still create training packages from ready audio while setup continues.`;
  statusEl.classList.toggle('ready', !!ready);

  const rows = [
    ['Engine', 'ACE-Step'],
    ['Ready to generate', ready ? 'Yes' : 'No'],
    ['Model folder', modelStatus?.ace_model_dir || 'Not configured'],
  ];
  document.getElementById('model-details').innerHTML = rows
    .map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`)
    .join('');
}

async function init() {
  modelStatus = await StudioApi.modelStatus();
  renderModelCard();
  await WorkbenchPackages.init();
}

init();
