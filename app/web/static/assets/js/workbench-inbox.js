window.WorkbenchInbox = (() => {
  const POLL_MS = 1000;

  let queue = [];
  let ingested = [];
  let runs = [];
  let styleVersions = [];
  let pollTimer = null;
  let activeRunId = null;

  function setStatus(message, isError = false) {
    const el = document.getElementById('inbox-status');
    el.textContent = message;
    el.classList.toggle('error', isError);
  }

  function activeRun() {
    return runs.find((run) => run.status === 'QUEUED' || run.status === 'RUNNING') || null;
  }

  function formatWhen(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  }

  function renderQueue() {
    const list = document.getElementById('queue-list');
    const ingestBtn = document.getElementById('ingest-btn');
    const inFlight = activeRun();

    if (!queue.length) {
      list.innerHTML = '<p class="empty-hint muted">No tracks waiting. Import audio in Media, add at least one category, then return here.</p>';
      ingestBtn.disabled = true;
      return;
    }

    list.innerHTML = queue.map((item) => `
      <div class="inbox-row">
        <div class="inbox-main">
          <a class="track-title" href="${StudioRoutes.mediaDetail(item.id)}">${item.title}</a>
          <span class="status-pill draft">${item.ingestion_status.toLowerCase()}</span>
        </div>
        <p class="inbox-meta">${item.category_count} tag${item.category_count === 1 ? '' : 's'} · ${item.review_status.replace(/_/g, ' ').toLowerCase()} · updated ${formatWhen(item.updated_at)}</p>
      </div>
    `).join('');

    ingestBtn.disabled = !!inFlight || queue.length === 0;
  }

  function renderIngested() {
    const list = document.getElementById('ingested-list');
    if (!ingested.length) {
      list.innerHTML = '<p class="empty-hint muted">Nothing ingested yet.</p>';
      return;
    }
    list.innerHTML = ingested.map((item) => `
      <div class="inbox-row">
        <div class="inbox-main">
          <a class="track-title" href="${StudioRoutes.mediaDetail(item.id)}">${item.title}</a>
          <span class="status-pill ready">ingested</span>
        </div>
        <p class="inbox-meta">${item.category_count} tags · ${formatWhen(item.ingested_at)}</p>
      </div>
    `).join('');
  }

  function renderRuns() {
    const list = document.getElementById('runs-list');
    if (!runs.length) {
      list.innerHTML = '<p class="muted">No training runs yet.</p>';
      return;
    }
    list.innerHTML = runs.slice(0, 12).map((run) => {
      const style = run.style_version_id ? styleVersions.find((v) => v.id === run.style_version_id) : null;
      return `
        <div class="history-row">
          <div class="history-main">
            <span class="history-kind">Run</span>
            <span class="history-title">${run.name}</span>
            <span class="status-pill ${run.status === 'SUCCEEDED' ? 'ready' : run.status === 'FAILED' ? 'draft' : 'running'}">${run.status.toLowerCase()}</span>
          </div>
          <p class="history-meta">${formatWhen(run.created_at)}${style ? ` · style: ${style.name}` : ''}${run.error ? ` · ${run.error}` : ''}</p>
        </div>
      `;
    }).join('');
  }

  function renderActiveStyle() {
    const line = document.getElementById('active-style-line');
    const active = styleVersions.filter((v) => v.status === 'ACTIVE');
    if (!active.length) {
      line.classList.add('hidden');
      return;
    }
    line.classList.remove('hidden');
    line.textContent = `Active style versions: ${active.map((v) => v.name).join(', ')} — use them on Generate.`;
  }

  function renderLiveRun(run, logText = '') {
    const panel = document.getElementById('live-run-panel');
    const cancelBtn = document.getElementById('cancel-run-btn');
    if (!run || (run.status !== 'QUEUED' && run.status !== 'RUNNING')) {
      if (!run || run.status === 'SUCCEEDED' || run.status === 'FAILED' || run.status === 'CANCELLED') {
        if (run && run.status === 'SUCCEEDED') {
          panel.classList.remove('hidden');
          document.getElementById('live-run-name').textContent = run.name;
          document.getElementById('live-run-badge').textContent = run.status.toLowerCase();
          document.getElementById('live-run-badge').className = 'status-pill ready';
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
    badge.textContent = run.status.toLowerCase();
    badge.className = 'status-pill running';
    document.getElementById('live-run-log').textContent = logText || 'Waiting for logs…';
  }

  async function refreshAll() {
    const [queueRes, runList, styles] = await Promise.all([
      StudioApi.getIngestionQueue(),
      StudioApi.listTrainingRuns(),
      StudioApi.listStyleVersions(),
    ]);
    queue = queueRes.queue || [];
    ingested = queueRes.ingested || [];
    runs = runList;
    styleVersions = styles;
    renderQueue();
    renderIngested();
    renderRuns();
    renderActiveStyle();

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
    renderActiveStyle();
    if (run.status === 'QUEUED' || run.status === 'RUNNING') return run;
    stopPolling();
    activeRunId = run.id;
    await refreshAll();
    if (run.status === 'SUCCEEDED') {
      setStatus(`Ingestion complete. Style version ${run.style_version_id || 'pending'} ready for Generate.`);
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

  async function ingestNow() {
    const button = document.getElementById('ingest-btn');
    await StudioSave.run(
      button,
      async () => {
        const res = await StudioApi.ingestTrainingQueue({});
        activeRunId = res.run.id;
        runs = [res.run, ...runs.filter((item) => item.id !== res.run.id)];
        renderLiveRun(res.run);
        startPolling(res.run.id);
        setStatus('Ingestion started…');
        await refreshAll();
        return res;
      },
      {
        savingLabel: 'Starting ingestion…',
        successMessage: 'Ingestion started.',
        feedbackEl: 'inbox-feedback',
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

  async function init() {
    await refreshAll();
    document.getElementById('ingest-btn').addEventListener('click', () => ingestNow().catch(() => {}));
    document.getElementById('cancel-run-btn').addEventListener('click', () => cancelRun().catch((err) => setStatus(err.message, true)));
  }

  return { init, refreshAll };
})();
