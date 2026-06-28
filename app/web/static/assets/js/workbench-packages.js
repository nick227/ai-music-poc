window.WorkbenchPackages = (() => {
  const POLL_MS = 1000;

  let readyAudio = { total: 0, groups: [], items: [] };
  let packages = [];
  let runs = [];
  let styleVersions = [];
  let concepts = [];
  let pollTimer = null;
  let activeRunId = null;

  function setStatus(message, isError = false) {
    const el = document.getElementById('package-status');
    el.textContent = message;
    el.classList.toggle('error', isError);
  }

  function selectedConceptId() {
    return null;
  }

  function activeRun() {
    return runs.find((run) => run.status === 'QUEUED' || run.status === 'RUNNING') || null;
  }

  function formatWhen(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  }

  function trackMeta(item) {
    const tags = [];
    if (item.concept_count) tags.push(`${item.concept_count} concept${item.concept_count === 1 ? '' : 's'}`);
    if (item.category_count) tags.push(`${item.category_count} categor${item.category_count === 1 ? 'y' : 'ies'}`);
    const role = item.primary_role ? item.primary_role.replace(/_/g, ' ').toLowerCase() : 'tagged';
    return `${tags.join(' · ') || 'tagged'} · ${role} · updated ${formatWhen(item.updated_at)}`;
  }



  function renderPackages() {
    const list = document.getElementById('packages-list');
    if (!packages.length) {
      list.innerHTML = '<p class="empty-hint muted">No datasets yet. Create or generate one to begin.</p>';
      return;
    }
    list.innerHTML = packages.map((pkg) => `
      <div class="history-row">
        <div class="history-main">
          <span class="history-kind">${pkg.is_auto_generated && pkg.status === 'DRAFT' ? 'Dataset Candidate' : 'Dataset'}</span>
          <span class="history-title">${pkg.name}</span>
          <span class="status-pill ready">${StudioTrainingStatus.packageSummary(pkg)}</span>
        </div>
        <p class="history-meta">${pkg.track_count} track${pkg.track_count === 1 ? '' : 's'} · ${formatWhen(pkg.created_at)}</p>
        <div class="panel-actions package-actions">
          <a class="button ghost small" href="${pkg.download_url}" download>Download</a>
          <button type="button" class="button small start-training-btn" data-slice-id="${pkg.id}">Start Fine-Tuning</button>
        </div>
      </div>
    `).join('');

    list.querySelectorAll('.start-training-btn').forEach((btn) => {
      btn.addEventListener('click', () => startFineTuning(btn.dataset.sliceId, btn).catch((err) => setStatus(err.message, true)));
    });
  }

  function renderRuns() {
    const list = document.getElementById('runs-list');
    if (!runs.length) {
      list.innerHTML = '<p class="muted">No training runs yet.</p>';
      return;
    }
    list.innerHTML = runs.slice(0, 12).map((run) => `
        <div class="history-row">
          <div class="history-main">
            <span class="history-kind">Run</span>
            <span class="history-title">${run.name}</span>
            <span class="status-pill ${StudioTrainingStatus.runBadgeClass(run)}">${StudioTrainingStatus.runSummary(run)}</span>
          </div>
          <p class="history-meta">${formatWhen(run.created_at)}${run.artifact_produced ? ' · artifact produced' : run.dry_run ? ' · no artifact' : ''}${run.error ? ` · ${run.error}` : ''}</p>
        </div>
      `).join('');
  }

  function renderModels() {
    const list = document.getElementById('models-list');
    if (!list) return;
    
    if (!styleVersions.length) {
      list.innerHTML = '<p class="muted">No model versions yet. Complete a training run to generate one.</p>';
      return;
    }
    
    list.innerHTML = styleVersions.map((model) => {
      // Find lineage
      const run = runs.find(r => r.id === model.training_run_id);
      const pkg = run ? packages.find(p => p.id === run.dataset_slice_id) : null;
      
      const lineageText = pkg ? `Trained on: ${pkg.name} (via ${run.name})` : (run ? `Trained via ${run.name}` : '');
      const baseInfo = `Base: ${model.base_model_name || 'ACE v1'} · Mode: ${model.training_mode || 'lora'} · Type: ${model.artifact_type || 'adapter'}`;
      
      return `
        <div class="history-row">
          <div class="history-main">
            <span class="history-kind">Model</span>
            <span class="history-title">${model.name}</span>
            <span class="status-pill ready">${model.status || 'ACTIVE'}</span>
          </div>
          <p class="history-meta">${baseInfo}</p>
          <p class="history-meta" style="margin-top: 4px; font-size: 11px;">${lineageText}</p>
        </div>
      `;
    }).join('');
  }



  function renderLiveRun(run, logText = '') {
    const panel = document.getElementById('live-run-panel');
    const cancelBtn = document.getElementById('cancel-run-btn');
    if (!run || (run.status !== 'QUEUED' && run.status !== 'RUNNING')) {
      if (!run || run.status === 'SUCCEEDED' || run.status === 'FAILED' || run.status === 'CANCELLED') {
        if (run && run.status === 'SUCCEEDED') {
          panel.classList.remove('hidden');
          document.getElementById('live-run-name').textContent = run.name;
          document.getElementById('live-run-badge').textContent = StudioTrainingStatus.runSummary(run);
          document.getElementById('live-run-badge').className = `status-pill ${StudioTrainingStatus.runBadgeClass(run)}`;
          document.getElementById('live-run-log').textContent = logText;
        } else {
          panel.classList.add('hidden');
        }
      }
      cancelBtn.classList.add('hidden');
      cancelBtn.disabled = true;
      return;
    }
    panel.classList.remove('hidden');
    cancelBtn.classList.remove('hidden');
    cancelBtn.disabled = false;
    document.getElementById('live-run-name').textContent = run.name;
    const badge = document.getElementById('live-run-badge');
    badge.textContent = StudioTrainingStatus.runSummary(run);
    badge.className = `status-pill ${StudioTrainingStatus.runBadgeClass(run)}`;
    document.getElementById('live-run-log').textContent = logText || 'Waiting for logs…';
  }



  async function refreshAll() {
    const conceptId = selectedConceptId();
    const [readyRes, packageList, runList, styles, conceptList] = await Promise.all([
      StudioApi.getReadyAudio(conceptId),
      StudioApi.listTrainingPackages(),
      StudioApi.listTrainingRuns(),
      StudioApi.listStyleVersions(),
      StudioApi.listConcepts(),
    ]);
    readyAudio = readyRes;
    packages = packageList;
    runs = runList;
    styleVersions = styles;
    concepts = conceptList;
    renderPackages();
    renderRuns();
    renderModels();

    const running = activeRun();
    if (running) {
      activeRunId = running.id;
      await pollOnce(running.id);
      startPolling(running.id);
    } else if (activeRunId) {
      const finished = runs.find((item) => item.id === activeRunId);
      if (finished) {
        const logs = await StudioApi.getTrainingRunLogs(finished.id).catch(() => ({ log: '' }));
        renderLiveRun(finished, logs.log || '');
      }
      stopPolling();
    } else {
      renderLiveRun(null);
    }
  }

  async function pollOnce(runId) {
    const [run, logs] = await Promise.all([
      StudioApi.getTrainingRun(runId),
      StudioApi.getTrainingRunLogs(runId).catch(() => ({ log: '' })),
    ]);
    runs = runs.map((item) => (item.id === runId ? run : item));
    renderLiveRun(run, logs.log || '');
    renderRuns();
    if (run.status === 'QUEUED' || run.status === 'RUNNING') return run;
    stopPolling();
    activeRunId = run.id;
    await refreshAll();
    if (run.status === 'SUCCEEDED') {
      setStatus(StudioTrainingStatus.completionMessage(run));
    } else {
      setStatus(`Run ${run.status.toLowerCase()}.`, run.status === 'FAILED');
    }
    return run;
  }

  function startPolling(runId) {
    stopPolling();
    pollTimer = window.setInterval(() => pollOnce(runId).catch((err) => setStatus(err.message, true)), POLL_MS);
  }

  function stopPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function startFineTuning(sliceId, btn) {
    btn.disabled = true;
    btn.textContent = 'Starting…';
    try {
      const run = await StudioApi.createTrainingRun({
        name: `Training Run`,
        dataset_slice_id: sliceId,
        config_preset: 'calibration',
      });
      activeRunId = run.id;
      runs = [run, ...runs.filter((item) => item.id !== run.id)];
      renderLiveRun(run);
      startPolling(run.id);
      setStatus('Training started…');
      await refreshAll();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'Start Fine-Tuning';
      throw err;
    }
  }

  async function createPackage() {
    const button = document.getElementById('create-package-btn');
    await StudioSave.run(
      button,
      async () => {
        const res = await StudioApi.createTrainingPackage({
          concept_id: selectedConceptId(),
          start_training: false,
          config_preset: 'calibration',
        });
        packages = [res.package, ...packages.filter((item) => item.id !== res.package.id)];
        renderPackages();
        setStatus('Training package created.');
        await refreshAll();
        return res;
      },
      {
        savingLabel: 'Creating package…',
        successMessage: 'Training package created.',
        feedbackEl: 'package-feedback',
      },
    );
  }

  async function cancelRun() {
    const run = activeRun();
    if (!run) return;
    setStatus('Cancelling…');
    await StudioApi.cancelTrainingRun(run.id);
    stopPolling();
    await refreshAll();
    setStatus('Run cancelled.');
  }

  async function generateRecommendedDatasets() {
    const btn = document.getElementById('generate-datasets-btn');
    btn.disabled = true;
    btn.textContent = 'Generating…';
    try {
      await StudioApi.generateRecommendedPackages();
      setStatus('Recommended datasets generated.');
      await refreshAll();
    } catch (err) {
      setStatus(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Generate Recommended Datasets';
    }
  }

  async function init() {
    document.getElementById('create-package-btn').addEventListener('click', () => createPackage().catch(() => {}));
    document.getElementById('generate-datasets-btn').addEventListener('click', () => generateRecommendedDatasets().catch(() => {}));
    document.getElementById('cancel-run-btn').addEventListener('click', () => cancelRun().catch((err) => setStatus(err.message, true)));
    await refreshAll();
  }

  return { init, refreshAll };
})();
