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
    return document.getElementById('concept-filter').value || null;
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

  function renderReadyAudio() {
    const list = document.getElementById('ready-audio-list');
    const createBtn = document.getElementById('create-package-btn');
    const inFlight = activeRun();

    if (!readyAudio.total) {
      list.innerHTML = '<p class="empty-hint muted">No ready audio yet. Import audio in Media, add a category or concept, then return here.</p>';
      createBtn.disabled = true;
      return;
    }

    list.innerHTML = readyAudio.groups.map((group) => `
      <div class="audio-group">
        <h3 class="audio-group-title">${group.label} <span class="tag-count">(${group.items.length})</span></h3>
        ${group.items.map((item) => `
          <div class="inbox-row">
            <div class="inbox-main">
              <a class="track-title" href="${StudioRoutes.mediaDetail(item.id)}">${item.title}</a>
              ${item.primary_role ? `<span class="status-pill draft">${item.primary_role.replace(/_/g, ' ').toLowerCase()}</span>` : ''}
            </div>
            <p class="inbox-meta">${trackMeta(item)}</p>
          </div>
        `).join('')}
      </div>
    `).join('');

    createBtn.disabled = !!inFlight || readyAudio.total === 0;
    setStatus(`${readyAudio.total} track${readyAudio.total === 1 ? '' : 's'} ready`);
  }

  function renderPackages() {
    const list = document.getElementById('packages-list');
    if (!packages.length) {
      list.innerHTML = '<p class="empty-hint muted">No training packages yet. Create one from ready audio above.</p>';
      return;
    }
    list.innerHTML = packages.map((pkg) => `
      <div class="history-row">
        <div class="history-main">
          <span class="history-kind">Package</span>
          <span class="history-title">${pkg.name}</span>
          <span class="status-pill ready">${pkg.status.toLowerCase()}</span>
        </div>
        <p class="history-meta">${pkg.track_count} track${pkg.track_count === 1 ? '' : 's'} · ${formatWhen(pkg.created_at)}</p>
        <div class="panel-actions package-actions">
          <a class="button ghost small" href="${pkg.download_url}" download>Download Package</a>
        </div>
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

  function renderConceptFilter() {
    const select = document.getElementById('concept-filter');
    const current = select.value;
    select.innerHTML = '<option value="">All ready audio</option>' + concepts
      .map((concept) => `<option value="${concept.id}">${concept.name}</option>`)
      .join('');
    select.value = current;
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
    renderConceptFilter();
    renderReadyAudio();
    renderPackages();
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
      setStatus(`Training complete. Style version ${run.style_version_id || 'pending'} ready for Generate.`);
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

  async function createPackage() {
    const button = document.getElementById('create-package-btn');
    await StudioSave.run(
      button,
      async () => {
        const res = await StudioApi.createTrainingPackage({
          concept_id: selectedConceptId(),
          start_training: true,
          config_preset: 'calibration',
        });
        if (res.run) {
          activeRunId = res.run.id;
          runs = [res.run, ...runs.filter((item) => item.id !== res.run.id)];
          renderLiveRun(res.run);
          startPolling(res.run.id);
        }
        packages = [res.package, ...packages.filter((item) => item.id !== res.package.id)];
        renderPackages();
        setStatus('Training package created. Training started…');
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

  async function init() {
    document.getElementById('concept-filter').addEventListener('change', () => {
      refreshAll().catch((err) => setStatus(err.message, true));
    });
    document.getElementById('create-package-btn').addEventListener('click', () => createPackage().catch(() => {}));
    document.getElementById('cancel-run-btn').addEventListener('click', () => cancelRun().catch((err) => setStatus(err.message, true)));
    await refreshAll();
  }

  return { init, refreshAll };
})();
