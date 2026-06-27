window.WorkbenchTraining = (() => {
  const POLL_MS = 1200;
  const CALIBRATION_PRESET = 'calibration';

  let trainingRuns = [];
  let pollTimer = null;
  let activeRunId = null;

  function setStatus(message, isError = false) {
    const el = document.getElementById('training-status');
    el.textContent = message;
    el.classList.toggle('error', isError);
  }

  function sliceById(id) {
    return WorkbenchSlice.listSlices().find((item) => item.id === id) || null;
  }

  function runsForSlice(sliceId) {
    return trainingRuns.filter((run) => run.dataset_slice_id === sliceId);
  }

  function latestSucceededRun(sliceId) {
    return runsForSlice(sliceId)
      .filter((run) => run.status === 'SUCCEEDED')
      .sort((a, b) => (b.finished_at || '').localeCompare(a.finished_at || ''))[0] || null;
  }

  function activeRun() {
    return trainingRuns.find((run) => run.status === 'QUEUED' || run.status === 'RUNNING') || null;
  }

  function formatWhen(iso) {
    if (!iso) return '—';
    const date = new Date(iso);
    return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  }

  function statusClass(status) {
    if (status === 'SUCCEEDED') return 'ready';
    if (status === 'FAILED' || status === 'CANCELLED') return 'draft';
    return 'running';
  }

  function renderTrainSliceSelect() {
    const select = document.getElementById('train-slice-select');
    const current = select.value;
    const ready = WorkbenchSlice.listSlices().filter((item) => item.status === 'READY');
    select.innerHTML = ready.length
      ? '<option value="">Select a locked set…</option>' + ready.map((slice) => {
        const done = latestSucceededRun(slice.id);
        const suffix = done ? ' · trained' : '';
        return `<option value="${slice.id}">${slice.name} (${slice.asset_count} tracks${suffix})</option>`;
      }).join('')
      : '<option value="">No locked sets yet</option>';
    if (current && ready.some((item) => item.id === current)) select.value = current;
    updateTrainControls();
  }

  function updateTrainControls() {
    const sliceId = document.getElementById('train-slice-select').value;
    const slice = sliceId ? sliceById(sliceId) : null;
    const hint = document.getElementById('train-slice-hint');
    const startBtn = document.getElementById('start-training-btn');
    const cancelBtn = document.getElementById('cancel-training-btn');
    const inFlight = activeRun();

    if (inFlight) {
      startBtn.disabled = true;
      cancelBtn.classList.remove('hidden');
      cancelBtn.disabled = false;
      hint.textContent = `Run in progress: ${inFlight.name}. Wait or cancel before starting another.`;
      hint.classList.add('warn');
      return;
    }

    cancelBtn.classList.add('hidden');
    cancelBtn.disabled = true;

    if (!slice) {
      startBtn.disabled = true;
      hint.textContent = 'Lock a training set in Step 1 first.';
      hint.classList.remove('warn');
      return;
    }

    const prior = latestSucceededRun(slice.id);
    const minTracks = WorkbenchSlice.calibrationMinTracks;
    if (slice.asset_count < minTracks) {
      startBtn.disabled = true;
      hint.textContent = `Need at least ${minTracks} tracks. This set has ${slice.asset_count}.`;
      hint.classList.add('warn');
      return;
    }
    if (prior) {
      startBtn.disabled = true;
      hint.textContent = `Already trained on ${formatWhen(prior.finished_at)}. Pick a different locked set or build a new one.`;
      hint.classList.add('warn');
      return;
    }

    startBtn.disabled = false;
    hint.textContent = `Ready for calibration on ${slice.asset_count} locked tracks.`;
    hint.classList.remove('warn');
  }

  function renderActiveRunPanel(run, logText = '') {
    const panel = document.getElementById('active-run-panel');
    if (!run) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    document.getElementById('active-run-name').textContent = run.name;
    const badge = document.getElementById('active-run-badge');
    badge.textContent = run.status.toLowerCase();
    badge.className = `status-pill ${statusClass(run.status)}`;
    document.getElementById('active-run-log').textContent = logText || 'Waiting for logs…';
  }

  function renderHistory() {
    const container = document.getElementById('history-list');
    const slices = WorkbenchSlice.listSlices();
    if (!slices.length && !trainingRuns.length) {
      container.innerHTML = '<p class="muted">No training sets or runs yet.</p>';
      return;
    }

    const rows = [];
    trainingRuns.forEach((run) => {
      const slice = sliceById(run.dataset_slice_id);
      rows.push({
        kind: 'run',
        sortAt: run.created_at,
        html: `
          <div class="history-row">
            <div class="history-main">
              <span class="history-kind">Run</span>
              <span class="history-title">${run.name}</span>
              <span class="status-pill ${statusClass(run.status)}">${run.status.toLowerCase()}</span>
            </div>
            <p class="history-meta">${slice ? slice.name : run.dataset_slice_id} · ${formatWhen(run.created_at)}${run.error ? ` · ${run.error}` : ''}</p>
          </div>
        `,
      });
    });
    slices.forEach((slice) => {
      const done = latestSucceededRun(slice.id);
      rows.push({
        kind: 'slice',
        sortAt: slice.updated_at,
        html: `
          <div class="history-row clickable" data-slice-id="${slice.id}">
            <div class="history-main">
              <span class="history-kind">Set</span>
              <span class="history-title">${slice.name}</span>
              <span class="status-pill ${slice.status === 'READY' ? 'ready' : 'draft'}">${slice.status === 'READY' ? 'locked' : 'draft'}</span>
            </div>
            <p class="history-meta">${slice.asset_count} track${slice.asset_count === 1 ? '' : 's'} · updated ${formatWhen(slice.updated_at)}${done ? ' · trained ' + formatWhen(done.finished_at) : ''}</p>
          </div>
        `,
      });
    });

    rows.sort((a, b) => b.sortAt.localeCompare(a.sortAt));
    container.innerHTML = rows.map((row) => row.html).join('');
    container.querySelectorAll('[data-slice-id]').forEach((el) => {
      el.addEventListener('click', () => {
        WorkbenchSlice.loadSlice(el.dataset.sliceId).catch((err) => setStatus(err.message, true));
        if (sliceById(el.dataset.sliceId)?.status === 'READY') {
          document.getElementById('train-slice-select').value = el.dataset.sliceId;
          updateTrainControls();
        }
      });
    });
  }

  async function refreshRuns() {
    trainingRuns = await StudioApi.listTrainingRuns();
    renderHistory();
    renderTrainSliceSelect();
    const running = activeRun();
    if (running) {
      activeRunId = running.id;
      await pollOnce(running.id);
      startPolling(running.id);
    } else if (activeRunId) {
      const finished = trainingRuns.find((item) => item.id === activeRunId);
      if (finished) {
        const log = await StudioApi.getTrainingRunLogs(finished.id).catch(() => ({ log: '' }));
        renderActiveRunPanel(finished, log.log || '');
      }
      stopPolling();
    }
    updateTrainControls();
  }

  async function pollOnce(runId) {
    const [run, logs] = await Promise.all([
      StudioApi.getTrainingRun(runId),
      StudioApi.getTrainingRunLogs(runId).catch(() => ({ log: '' })),
    ]);
    trainingRuns = trainingRuns.map((item) => (item.id === runId ? run : item));
    renderActiveRunPanel(run, logs.log || '');
    renderHistory();
    if (run.status === 'QUEUED' || run.status === 'RUNNING') return run;
    stopPolling();
    activeRunId = run.id;
    renderTrainSliceSelect();
    updateTrainControls();
    setStatus(run.status === 'SUCCEEDED'
      ? `Calibration run finished. Check history before starting another on the same set.`
      : `Run ${run.status.toLowerCase()}.`);
    return run;
  }

  function startPolling(runId) {
    stopPolling();
    pollTimer = window.setInterval(() => {
      pollOnce(runId).catch((err) => setStatus(err.message, true));
    }, POLL_MS);
  }

  function stopPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function startTraining() {
    const sliceId = document.getElementById('train-slice-select').value;
    const slice = sliceId ? sliceById(sliceId) : null;
    if (!slice || slice.status !== 'READY') {
      setStatus('Select a locked training set first.', true);
      return;
    }
    if (latestSucceededRun(sliceId)) {
      setStatus('This set was already trained. Pick another set.', true);
      return;
    }
    setStatus('Starting calibration run…');
    const run = await StudioApi.createTrainingRun({
      name: `${slice.name} calibration`,
      dataset_slice_id: sliceId,
      config_preset: CALIBRATION_PRESET,
    });
    activeRunId = run.id;
    trainingRuns = [run, ...trainingRuns.filter((item) => item.id !== run.id)];
    renderActiveRunPanel(run);
    renderHistory();
    updateTrainControls();
    startPolling(run.id);
    setStatus('Calibration run started.');
  }

  async function cancelTraining() {
    const run = activeRun();
    if (!run) return;
    setStatus('Cancelling run…');
    await StudioApi.cancelTrainingRun(run.id);
    await refreshRuns();
    setStatus('Run cancelled.');
  }

  async function init() {
    await WorkbenchSlice.refreshSlices();
    await refreshRuns();
    document.getElementById('train-slice-select').addEventListener('change', updateTrainControls);
    document.getElementById('start-training-btn').addEventListener('click', () => startTraining().catch((err) => setStatus(err.message, true)));
    document.getElementById('cancel-training-btn').addEventListener('click', () => cancelTraining().catch((err) => setStatus(err.message, true)));
  }

  return {
    init,
    refreshHistory: refreshRuns,
    refreshTrainableSlices: renderTrainSliceSelect,
  };
})();
