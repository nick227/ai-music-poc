window.WorkbenchPackages = (() => {
  const POLL_MS = 1000;
  const H = WorkbenchHelpers;

  let readyAudio = { total: 0, groups: [], items: [] };
  let slices = [];
  let packages = [];
  let runs = [];
  let styleVersions = [];
  let pollTimer = null;
  let activeRunId = null;
  let selectedRunId = null;
  let runAllQueue = [];

  function setStatus(message, isError = false) {
    const el = document.getElementById('package-status');
    el.textContent = message;
    el.classList.toggle('error', isError);
    el.hidden = !message;
  }

  function candidates() {
    return slices.filter((slice) => slice.status === 'DRAFT' && slice.is_auto_generated);
  }

  function packageById(id) {
    return packages.find((pkg) => pkg.id === id);
  }

  function activeRun() {
    return runs.find((run) => run.status === 'QUEUED' || run.status === 'RUNNING') || null;
  }

  function globalRunBusy() {
    return Boolean(activeRun());
  }

  function renderPendingSummary() {
    document.getElementById('pending-songs-summary').innerHTML = H.pendingSummaryHtml(readyAudio);
  }

  function renderCandidates() {
    const list = document.getElementById('candidates-list');
    const items = candidates();
    if (!items.length) {
      list.innerHTML = '<p class="empty-hint muted">No candidates yet. Scan tagged songs to discover trainable groupings.</p>';
      return;
    }
    list.innerHTML = items.map((slice) => `
      <div class="history-row">
        <div class="history-main">
          <span class="history-kind">Candidate</span>
          <span class="history-title">${slice.name}</span>
          <span class="status-pill draft">${H.tierLabel(slice.confidence_tier)}</span>
        </div>
        <p class="history-meta">${slice.asset_count} song${slice.asset_count === 1 ? '' : 's'} · draft · updated ${H.formatWhen(slice.updated_at)}</p>
        <div class="panel-actions package-actions">
          <button type="button" class="button small primary freeze-candidate-btn" data-slice-id="${slice.id}">Freeze for training</button>
        </div>
      </div>
    `).join('');
    list.querySelectorAll('.freeze-candidate-btn').forEach((btn) => {
      btn.addEventListener('click', () => freezeCandidate(btn.dataset.sliceId, btn).catch((err) => setStatus(err.message, true)));
    });
  }

  function renderPackages() {
    const list = document.getElementById('packages-list');
    const busy = globalRunBusy();
    if (!packages.length) {
      list.innerHTML = '<p class="empty-hint muted">No frozen training packages yet. Freeze a candidate or package all pending songs.</p>';
      return;
    }
    list.innerHTML = packages.map((pkg) => {
      const state = H.packageTrainingState(runs, pkg.id, busy);
      const action = H.trainingActionLabel(state);
      const disabled = busy && !state.isActive;
      const btnClass = state.neverTrained ? 'primary' : 'ghost';
      const title = state.neverTrained
        ? 'Start the first fine-tuning run for this package'
        : 'Creates a new training run and model version. Previous runs are kept in history.';
      return `
        <div class="history-row${state.isActive ? ' row-active' : ''}">
          <div class="history-main">
            <span class="history-kind">Package</span>
            <span class="history-title">${pkg.name}</span>
            <span class="status-pill ${state.neverTrained ? 'draft' : state.succeeded ? 'ready' : 'running'}">${state.neverTrained ? 'untrained' : state.isActive ? 'training' : 'trained'}</span>
          </div>
          <p class="history-meta">${pkg.track_count} song${pkg.track_count === 1 ? '' : 's'} · frozen ${H.formatWhen(pkg.created_at)}</p>
          <p class="history-meta training-status-line">${H.trainingStatusLine(state)}</p>
          <div class="panel-actions package-actions">
            <a class="button ghost small" href="${pkg.download_url}" download>Download</a>
            <button type="button" class="button small ${btnClass} start-training-btn" data-slice-id="${pkg.id}" title="${title}" ${disabled ? 'disabled' : ''}>${action}</button>
          </div>
        </div>
      `;
    }).join('');

    list.querySelectorAll('.start-training-btn').forEach((btn) => {
      btn.addEventListener('click', () => startFineTuning(btn.dataset.sliceId, btn).catch((err) => setStatus(err.message, true)));
    });

    const untrainedCount = packages.filter((pkg) => H.packageTrainingState(runs, pkg.id, busy).neverTrained).length;
    const runAllBtn = document.getElementById('run-all-untrained-btn');
    runAllBtn.disabled = !untrainedCount || busy;
    runAllBtn.textContent = untrainedCount
      ? `Run all untrained (${untrainedCount})`
      : 'Run all untrained';
  }

  function renderRuns() {
    const list = document.getElementById('runs-list');
    if (!runs.length) {
      list.innerHTML = '<p class="empty-hint muted">No training runs yet. Start training on a frozen package above.</p>';
      return;
    }
    list.innerHTML = runs.slice(0, 20).map((run) => {
      const pkg = packageById(run.dataset_slice_id);
      const expanded = selectedRunId === run.id;
      return `
        <div class="history-row clickable run-row${expanded ? ' row-expanded' : ''}" data-run-id="${run.id}">
          <div class="history-main">
            <span class="history-kind">Run</span>
            <span class="history-title">${run.name}</span>
            <span class="status-pill ${StudioTrainingStatus.runBadgeClass(run)}">${StudioTrainingStatus.runSummary(run)}</span>
          </div>
          <p class="history-meta">${pkg ? `Package: ${pkg.name}` : `Package id: ${run.dataset_slice_id}`}</p>
          <p class="history-meta">${H.formatWhen(run.created_at)}${run.finished_at ? ` → ${H.formatWhen(run.finished_at)}` : ''}${run.artifact_produced ? ' · artifact produced' : run.dry_run ? ' · dry run' : ''}${run.style_version_created ? ' · model version created' : ''}${run.error ? ` · ${run.error}` : ''}</p>
          <pre class="run-log-preview${expanded ? '' : ' hidden'}" id="run-log-${run.id}">${expanded ? 'Loading log…' : ''}</pre>
        </div>
      `;
    }).join('');

    list.querySelectorAll('.run-row').forEach((row) => {
      row.addEventListener('click', () => toggleRunLog(row.dataset.runId).catch((err) => setStatus(err.message, true)));
    });
  }

  function renderModels() {
    const list = document.getElementById('models-list');
    if (!list) return;
    if (!styleVersions.length) {
      list.innerHTML = '<p class="empty-hint muted">No model versions yet. Complete a training run to generate one.</p>';
      return;
    }
    list.innerHTML = styleVersions.map((model) => {
      const run = runs.find((item) => item.id === model.training_run_id);
      const pkg = run ? packageById(run.dataset_slice_id) : null;
      const lineageText = pkg ? `Trained on ${pkg.name}` : (run ? `From run ${run.name}` : '');
      return `
        <div class="history-row">
          <div class="history-main">
            <span class="history-kind">Model</span>
            <span class="history-title">${model.name}</span>
            <span class="status-pill ready">${model.status || 'ACTIVE'}</span>
          </div>
          <p class="history-meta">Base: ${model.base_model_name || 'ACE v1'} · ${model.training_mode || 'lora'} · ${model.artifact_type || 'adapter'}</p>
          <p class="history-meta">${lineageText}${run ? ` · ${H.formatWhen(run.finished_at || run.created_at)}` : ''}</p>
        </div>
      `;
    }).join('');
  }

  function renderLiveRun(run, logText = '') {
    const panel = document.getElementById('live-run-panel');
    const cancelBtn = document.getElementById('cancel-run-btn');
    const isLive = run && (run.status === 'QUEUED' || run.status === 'RUNNING');
    if (!isLive) {
      if (run && run.status === 'SUCCEEDED' && activeRunId === run.id) {
        panel.classList.remove('hidden');
        document.getElementById('live-run-name').textContent = run.name;
        document.getElementById('live-run-badge').textContent = StudioTrainingStatus.runSummary(run);
        document.getElementById('live-run-badge').className = `status-pill ${StudioTrainingStatus.runBadgeClass(run)}`;
        document.getElementById('live-run-log').textContent = logText;
      } else if (!isLive && !activeRun()) {
        panel.classList.add('hidden');
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

  async function toggleRunLog(runId) {
    selectedRunId = selectedRunId === runId ? null : runId;
    renderRuns();
    if (!selectedRunId) return;
    const logs = await StudioApi.getTrainingRunLogs(runId).catch(() => ({ log: '' }));
    const el = document.getElementById(`run-log-${runId}`);
    if (el) {
      el.classList.remove('hidden');
      el.textContent = logs.log || 'No log output yet.';
    }
    const run = runs.find((item) => item.id === runId);
    if (run && (run.status === 'QUEUED' || run.status === 'RUNNING')) {
      activeRunId = runId;
      startPolling(runId);
    }
  }

  async function refreshAll() {
    const [readyRes, sliceList, packageList, runList, styles] = await Promise.all([
      StudioApi.getReadyAudio(),
      StudioApi.listSlices(),
      StudioApi.listTrainingPackages(),
      StudioApi.listTrainingRuns(),
      StudioApi.listStyleVersions(),
    ]);
    readyAudio = readyRes;
    slices = sliceList;
    packages = packageList;
    runs = runList;
    styleVersions = styles;

    renderPendingSummary();
    renderCandidates();
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
      await maybeStartNextQueuedRun();
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
    renderPackages();
    if (selectedRunId === runId) {
      const el = document.getElementById(`run-log-${runId}`);
      if (el) el.textContent = logs.log || 'No log output yet.';
    }
    if (run.status === 'QUEUED' || run.status === 'RUNNING') return run;
    stopPolling();
    activeRunId = run.id;
    await refreshAll();
    if (run.status === 'SUCCEEDED') setStatus(StudioTrainingStatus.completionMessage(run));
    else setStatus(`Run ${run.status.toLowerCase()}.`, run.status === 'FAILED');
    await maybeStartNextQueuedRun();
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

  async function startFineTuning(sliceId, btn, name) {
    const pkg = packageById(sliceId);
    const state = H.packageTrainingState(runs, sliceId, globalRunBusy());
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Starting…';
    }
    try {
      const run = await StudioApi.createTrainingRun({
        name: name || `${pkg?.name || 'Training'} · ${H.formatWhen(new Date().toISOString())}`,
        dataset_slice_id: sliceId,
        config_preset: 'calibration',
      });
      activeRunId = run.id;
      runs = [run, ...runs.filter((item) => item.id !== run.id)];
      renderLiveRun(run);
      renderPackages();
      renderRuns();
      startPolling(run.id);
      setStatus(state.neverTrained ? 'Training started.' : 'Re-run started — a new model version will be created.');
    } catch (err) {
      if (btn) {
        btn.disabled = false;
        btn.textContent = H.trainingActionLabel(state);
      }
      throw err;
    }
  }

  async function maybeStartNextQueuedRun() {
    if (globalRunBusy() || !runAllQueue.length) return;
    const sliceId = runAllQueue.shift();
    const btn = document.querySelector(`.start-training-btn[data-slice-id="${sliceId}"]`);
    await startFineTuning(sliceId, btn).catch((err) => {
      setStatus(err.message, true);
      runAllQueue = [];
    });
  }

  async function runAllUntrained() {
    const untrained = packages
      .filter((pkg) => H.packageTrainingState(runs, pkg.id, false).neverTrained)
      .map((pkg) => pkg.id);
    if (!untrained.length) {
      setStatus('All packages have been trained at least once.');
      return;
    }
    if (globalRunBusy()) {
      setStatus('A training run is already active.', true);
      return;
    }
    runAllQueue = untrained.slice(1);
    setStatus(`Starting ${untrained.length} training run${untrained.length === 1 ? '' : 's'} sequentially…`);
    await startFineTuning(untrained[0], null);
  }

  async function freezeCandidate(sliceId, btn) {
    btn.disabled = true;
    btn.textContent = 'Freezing…';
    try {
      await StudioApi.freezeSlice(sliceId);
      setStatus('Candidate frozen — ready for training.');
      await refreshAll();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'Freeze for training';
      throw err;
    }
  }

  async function packageAllPending() {
    const button = document.getElementById('package-all-btn');
    if (!readyAudio.total) {
      setStatus('No pending tagged songs to package.', true);
      return;
    }
    await StudioSave.run(
      button,
      async () => {
        const res = await StudioApi.createTrainingPackage({
          start_training: false,
          config_preset: 'calibration',
        });
        packages = [res.package, ...packages.filter((item) => item.id !== res.package.id)];
        renderPackages();
        setStatus(`Packaged ${res.package.track_count} pending song${res.package.track_count === 1 ? '' : 's'}.`);
        await refreshAll();
        return res;
      },
      {
        savingLabel: 'Packaging…',
        successMessage: (res) => `Packaged ${res.package.track_count} song${res.package.track_count === 1 ? '' : 's'}.`,
        feedbackEl: 'package-feedback',
      },
    );
  }

  async function scanForCandidates() {
    const btn = document.getElementById('generate-datasets-btn');
    btn.disabled = true;
    btn.textContent = 'Scanning…';
    try {
      const created = await StudioApi.generateRecommendedPackages();
      setStatus(H.candidateSummaryMessage(created, readyAudio));
      await refreshAll();
    } catch (err) {
      setStatus(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Scan for dataset candidates';
    }
  }

  async function cancelRun() {
    const run = activeRun();
    if (!run) return;
    setStatus('Cancelling…');
    runAllQueue = [];
    await StudioApi.cancelTrainingRun(run.id);
    stopPolling();
    await refreshAll();
    setStatus('Run cancelled.');
  }

  async function init() {
    document.getElementById('generate-datasets-btn').addEventListener('click', () => scanForCandidates().catch(() => {}));
    document.getElementById('run-all-untrained-btn').addEventListener('click', () => runAllUntrained().catch((err) => setStatus(err.message, true)));
    document.getElementById('package-all-btn').addEventListener('click', () => packageAllPending().catch(() => {}));
    document.getElementById('cancel-run-btn').addEventListener('click', () => cancelRun().catch((err) => setStatus(err.message, true)));
    await refreshAll();
  }

  return { init, refreshAll };
})();
