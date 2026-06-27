let modelStatus = null;

function renderModelCard() {
  const ready = modelStatus?.can_generate || modelStatus?.wiring_ok;
  const statusEl = document.getElementById('model-status-text');
  const message = modelStatus?.user_message || (ready ? 'Your model is ready to generate.' : 'Your model still needs setup.');
  statusEl.textContent = ready
    ? `${message} Tag media in Media, then ingest from the queue below.`
    : `${message} You can still queue and ingest tagged media while setup continues.`;
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
  await WorkbenchInbox.init();
}

init();
