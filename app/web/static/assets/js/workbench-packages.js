window.WorkbenchPackages = (() => {
  const POLL_MS = 1000;
  const H = WorkbenchHelpers;

  let readyAudio = { total: 0, groups: [], items: [] };
  let slices = [];
  let packages = [];
  let runs = [];
  let styleVersions = [];
  let categories = [];
  let pollTimer = null;
  let activeRunId = null;
  let selectedRunId = null;
  let runAllQueue = [];
  let selectedDatasets = new Set();

  function el(id) {
    return document.getElementById(id);
  }

  function bindClick(id, handler) {
    const node = el(id);
    if (node) node.addEventListener('click', handler);
  }

  function setStatus(message, isError = false) {
    const statusEl = el('package-status');
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.classList.toggle('error', isError);
    statusEl.hidden = !message;
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
    const summary = el('pending-songs-summary');
    if (summary) summary.innerHTML = H.pendingSummaryHtml(readyAudio);
  }

  function formatCategories(categoryIds) {
    if (!categoryIds || !categoryIds.length) return '';
    return categoryIds.map((id) => {
      const cat = categories.find(c => c.id === id);
      return `<span class="cat-pill">${cat ? cat.name : id}</span>`;
    }).join('');
  }

  function renderDatasetItem(ds, busy) {
    const isCandidate = ds.status === 'DRAFT';
    const state = isCandidate ? { neverTrained: true, isActive: false } : H.packageTrainingState(runs, ds.id, busy);
    const statusLabel = isCandidate ? H.tierLabel(ds.confidence_tier || 'CANDIDATE') : (state.neverTrained ? 'untrained' : state.isActive ? 'training' : 'trained');
    const pillClass = isCandidate ? 'draft' : (state.neverTrained ? 'draft' : state.succeeded ? 'ready' : 'running');
    const isSelected = selectedDatasets.has(ds.id);
    const cardClass = `dataset-card ${isSelected ? 'selected' : ''} ${state.isActive ? 'row-active' : ''}`;
    
    return `
      <div class="${cardClass}" data-dataset-id="${ds.id}">
        <div class="dataset-card-check"></div>
        <div class="history-main">
          <span class="history-kind">Dataset</span>
          <span class="history-title">${ds.name}</span>
          <span class="status-pill ${pillClass}">${statusLabel}</span>
        </div>
        <div class="history-categories">${formatCategories(ds.filter?.category_ids)}</div>
        <p class="history-meta">${ds.asset_count || ds.track_count || 0} song${(ds.asset_count || ds.track_count) === 1 ? '' : 's'} · ${isCandidate ? 'auto-generated' : 'frozen'} ${H.formatWhen(ds.updated_at || ds.created_at)}</p>
        ${!state.neverTrained ? `<p class="history-meta training-status-line">${H.trainingStatusLine(state)}</p>` : ''}
      </div>
    `;
  }

  function updateBatchRunnerToolbar() {
    const toolbar = el('batch-runner-toolbar');
    const countEl = el('batch-runner-count');
    const btn = el('start-batch-run-btn');
    if (!toolbar || !countEl || !btn) return;
    
    const count = selectedDatasets.size;
    if (count > 0) {
      toolbar.hidden = false;
      countEl.textContent = `${count} selected`;
      btn.disabled = globalRunBusy();
    } else {
      toolbar.hidden = true;
    }
  }

  function renderDatasets() {
    const untrainedList = el('untrained-datasets-list');
    const trainedList = el('trained-datasets-list');
    if (!untrainedList || !trainedList) return;
    
    const busy = globalRunBusy();
    const allDatasets = [...candidates(), ...packages];
    
    const untrained = allDatasets.filter(ds => ds.status === 'DRAFT' || H.packageTrainingState(runs, ds.id, busy).neverTrained);
    const trained = allDatasets.filter(ds => ds.status !== 'DRAFT' && !H.packageTrainingState(runs, ds.id, busy).neverTrained);
    
    if (!untrained.length) {
      untrainedList.innerHTML = '<p class="empty-hint muted">No untrained datasets. Scan tagged songs to discover trainable groupings.</p>';
    } else {
      untrainedList.innerHTML = untrained.map(ds => renderDatasetItem(ds, busy)).join('');
    }

    if (!trained.length) {
      trainedList.innerHTML = '<p class="empty-hint muted">No trained datasets yet. Run a batch training above to create a model version.</p>';
    } else {
      trainedList.innerHTML = trained.map(ds => renderDatasetItem(ds, busy)).join('');
    }

    document.querySelectorAll('.dataset-card').forEach((card) => {
      card.onclick = (e) => {
        const id = card.dataset.datasetId;
        if (selectedDatasets.has(id)) {
          selectedDatasets.delete(id);
          card.classList.remove('selected');
        } else {
          selectedDatasets.add(id);
          card.classList.add('selected');
        }
        updateBatchRunnerToolbar();
      };
    });

    updateBatchRunnerToolbar();
  }

  function renderRuns() {
    const list = el('runs-list');
    if (!list) return;
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
    const list = el('models-list');
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
          <p class="history-meta">Base Model: ${model.base_model_name || 'ACE-Step v1.5 Turbo'} · Type: ${model.type || 'LoRA'}</p>
          <p class="history-meta">Generation uses: Base Model + LoRA</p>
          <p class="history-meta">${lineageText}${run ? ` · ${H.formatWhen(run.finished_at || run.created_at)}` : ''}</p>
        </div>
      `;
    }).join('');
  }

  function renderLiveRun(run, logText = '') {
    const panel = el('live-run-panel');
    const cancelBtn = el('cancel-run-btn');
    const queueContainer = el('batch-queue-container');
    if (!panel) return;
    
    const isLive = run && (run.status === 'QUEUED' || run.status === 'RUNNING');
    
    if (!isLive) {
      if (run && run.status === 'SUCCEEDED' && activeRunId === run.id) {
        panel.classList.remove('hidden');
        const nameEl = el('live-run-name');
        const badgeEl = el('live-run-badge');
        const logEl = el('live-run-log');
        if (nameEl) nameEl.textContent = run.name;
        if (badgeEl) {
          badgeEl.textContent = StudioTrainingStatus.runSummary(run).replace(/training/i, 'processing');
          badgeEl.className = `status-pill ${StudioTrainingStatus.runBadgeClass(run)}`;
        }
        if (logEl) logEl.textContent = logText;
        if (queueContainer) queueContainer.innerHTML = '';
      } else if (!isLive && !activeRun() && !runAllQueue.length) {
        panel.classList.add('hidden');
      }
      if (cancelBtn) {
        cancelBtn.classList.add('hidden');
        cancelBtn.disabled = true;
      }
      return;
    }
    
    panel.classList.remove('hidden');
    if (cancelBtn) {
      cancelBtn.classList.remove('hidden');
      cancelBtn.disabled = false;
    }
    
    const nameEl = el('live-run-name');
    const badgeEl = el('live-run-badge');
    const logEl = el('live-run-log');
    if (nameEl) nameEl.textContent = run.name;
    if (badgeEl) {
      badgeEl.textContent = StudioTrainingStatus.runSummary(run).replace(/training/i, 'processing');
      badgeEl.className = `status-pill ${StudioTrainingStatus.runBadgeClass(run)}`;
    }
    if (logEl) logEl.textContent = logText || 'Waiting for logs…';

    // Render visual queue
    if (queueContainer) {
      const activePkg = packages.find(p => p.id === run.dataset_slice_id) || slices.find(s => s.id === run.dataset_slice_id);
      const queueHtml = [];
      
      // Active item
      if (activePkg) {
        queueHtml.push(`
          <div class="batch-queue-item active">
            <span>Processing: <strong>${activePkg.name}</strong></span>
            <span class="status-pill running">active</span>
          </div>
        `);
      }
      
      // Queued items
      runAllQueue.forEach(sliceId => {
        const queuedPkg = packages.find(p => p.id === sliceId) || slices.find(s => s.id === sliceId);
        if (queuedPkg) {
          queueHtml.push(`
            <div class="batch-queue-item pending">
              <span>Waiting: <strong>${queuedPkg.name}</strong></span>
              <span class="status-pill draft">pending</span>
            </div>
          `);
        }
      });
      
      queueContainer.innerHTML = queueHtml.join('');
    }
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
    const [readyRes, sliceList, packageList, runList, styles, catList] = await Promise.all([
      StudioApi.getReadyAudio(),
      StudioApi.listSlices(),
      StudioApi.listTrainingPackages(),
      StudioApi.listTrainingRuns(),
      StudioApi.listStyleVersions(),
      StudioApi.listCategories(),
    ]);
    readyAudio = readyRes;
    slices = sliceList;
    packages = packageList;
    runs = runList;
    styleVersions = styles;
    categories = catList;

    renderPendingSummary();
    renderDatasets();
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
    renderDatasets();
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
      renderDatasets();
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

  async function startBatchRun() {
    const ids = Array.from(selectedDatasets);
    if (!ids.length) return;
    
    if (globalRunBusy()) {
      setStatus('A batch job is already active.', true);
      return;
    }
    
    setStatus(`Preparing ${ids.length} dataset${ids.length === 1 ? '' : 's'} for batch processing...`);
    const btn = el('start-batch-run-btn');
    if (btn) btn.disabled = true;

    // Freeze any drafts first
    try {
      for (const id of ids) {
        const slice = slices.find(s => s.id === id) || packages.find(p => p.id === id);
        if (slice && slice.status === 'DRAFT') {
          await StudioApi.freezeSlice(id);
        }
      }
    } catch (err) {
      setStatus(`Failed to freeze dataset: ${err.message}`, true);
      if (btn) btn.disabled = false;
      return;
    }

    await refreshAll();
    
    runAllQueue = [...ids];
    setStatus(`Starting ${runAllQueue.length} batch job${runAllQueue.length === 1 ? '' : 's'} sequentially…`);
    
    // Start the first one
    await maybeStartNextQueuedRun();
    
    // Clear selection
    selectedDatasets.clear();
    updateBatchRunnerToolbar();
  }

  function selectAllDatasets() {
    const allDatasets = [...candidates(), ...packages];
    if (selectedDatasets.size === allDatasets.length && allDatasets.length > 0) {
      selectedDatasets.clear();
    } else {
      allDatasets.forEach(ds => selectedDatasets.add(ds.id));
    }
    renderDatasets();
  }

  async function trainCandidate(sliceId, btn) {
    btn.disabled = true;
    btn.textContent = 'Freezing…';
    try {
      await StudioApi.freezeSlice(sliceId);
      btn.textContent = 'Starting training…';
      await refreshAll();
      const updatedBtn = document.querySelector(`.start-training-btn[data-slice-id="${sliceId}"]`);
      await startFineTuning(sliceId, updatedBtn);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'Train';
      throw err;
    }
  }



  async function scanForCandidates() {
    const btn = el('generate-datasets-btn');
    if (!btn) {
      setStatus('Scan action is unavailable on this page.', true);
      return;
    }
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
    bindClick('select-all-datasets-btn', () => selectAllDatasets());
    bindClick('generate-datasets-btn', () => scanForCandidates().catch(() => {}));
    bindClick('start-batch-run-btn', () => startBatchRun().catch((err) => setStatus(err.message, true)));
    bindClick('cancel-run-btn', () => cancelRun().catch((err) => setStatus(err.message, true)));
    await refreshAll();
  }

  return { init, refreshAll };
})();
