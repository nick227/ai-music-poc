StudioApi.modelStatus().then((s) => {
  const el = document.getElementById('model-status');
  el.textContent = s.user_message || (s.can_generate ? 'Ready to generate' : 'Not ready');
  el.classList.toggle('ready', !!s.can_generate);
  document.getElementById('model-detail').textContent = JSON.stringify(s, null, 2);
});
