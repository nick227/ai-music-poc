const TRAINING_ROLES = new Set(['GOLD_REFERENCE', 'TRAINING_CANDIDATE']);

let sessions = [];
let activeSession = null;
let mediaById = new Map();

function queryMediaId() {
  return new URLSearchParams(window.location.search).get('media_id');
}

function isTrainingEligible(item) {
  const role = item.primary_role;
  if (role && TRAINING_ROLES.has(role)) return true;
  const count = item.category_assignment_count ?? item.category_assignments?.length ?? 0;
  return item.review_status === 'REVIEWED' && count > 0;
}

function roleLabel(item) {
  if (item.primary_role) return item.primary_role.replace(/_/g, ' ').toLowerCase();
  return '—';
}

function catCount(item) {
  return item.category_assignment_count ?? item.category_assignments?.length ?? 0;
}

async function loadMedia() {
  const rows = await StudioApi.listMedia({ limit: 200 });
  mediaById = new Map(rows.map((row) => [row.id, row]));
}

function renderSessions() {
  const list = document.getElementById('session-list');
  if (!sessions.length) {
    list.innerHTML = '<p class="table-meta">No sessions yet</p>';
    return;
  }
  list.innerHTML = sessions.map((session) => `
    <button type="button" class="session-item ${activeSession?.id === session.id ? 'active' : ''}" data-id="${session.id}">
      <span class="session-item-name">${session.name}</span>
      <span class="session-item-meta">${session.media_ids.length} · ${session.status}</span>
    </button>
  `).join('');
  list.querySelectorAll('.session-item').forEach((btn) => {
    btn.addEventListener('click', () => selectSession(btn.dataset.id));
  });
}

function renderStats() {
  const payload = activeSession.media_ids.map((id) => mediaById.get(id)).filter(Boolean);
  const gold = payload.filter((item) => item.primary_role === 'GOLD_REFERENCE').length;
  const candidates = payload.filter((item) => item.primary_role === 'TRAINING_CANDIDATE').length;
  const cats = new Set();
  payload.forEach((item) => {
    (item.category_assignments || []).forEach((a) => cats.add(a.category_id));
  });
  document.getElementById('session-stats').innerHTML = `
    <span class="stat-pill">${payload.length} tracks</span>
    <span class="stat-pill">${gold} gold</span>
    <span class="stat-pill">${candidates} candidates</span>
    <span class="stat-pill">${cats.size} categories</span>
  `;
  document.getElementById('payload-count').textContent = String(payload.length);
}

function renderPayload() {
  const tbody = document.getElementById('payload-rows');
  const items = activeSession.media_ids.map((id) => mediaById.get(id)).filter(Boolean);
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="table-meta">No tracks in payload — add from pool below or Media</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => `
    <tr>
      <td class="table-title"><a href="${StudioRoutes.mediaDetail(item.id)}">${item.title}</a></td>
      <td class="table-meta">${roleLabel(item)}</td>
      <td><span class="count-pill ${catCount(item) ? 'has-value' : ''}">${catCount(item)}</span></td>
      <td class="table-meta">${item.review_status.replace(/_/g, ' ').toLowerCase()}</td>
      <td><button type="button" class="ghost small" data-remove="${item.id}">Remove</button></td>
    </tr>
  `).join('');
  tbody.querySelectorAll('[data-remove]').forEach((btn) => {
    btn.addEventListener('click', () => {
      activeSession = WorkbenchSessions.removeMedia(activeSession, btn.dataset.remove);
      sessions = WorkbenchSessions.loadAll();
      renderAll();
    });
  });
}

function renderPool() {
  const tbody = document.getElementById('pool-rows');
  const inPayload = new Set(activeSession.media_ids);
  const pool = [...mediaById.values()].filter((item) => isTrainingEligible(item) && !inPayload.has(item.id));
  if (!pool.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="table-meta">No eligible media — categorize and mark reviewed in Media</td></tr>';
    return;
  }
  tbody.innerHTML = pool.map((item) => `
    <tr>
      <td class="table-title"><a href="${StudioRoutes.mediaDetail(item.id)}">${item.title}</a></td>
      <td class="table-meta">${roleLabel(item)}</td>
      <td><span class="count-pill ${catCount(item) ? 'has-value' : ''}">${catCount(item)}</span></td>
      <td><button type="button" class="ghost small" data-add="${item.id}">Add</button></td>
    </tr>
  `).join('');
  tbody.querySelectorAll('[data-add]').forEach((btn) => {
    btn.addEventListener('click', () => {
      activeSession = WorkbenchSessions.addMedia(activeSession, btn.dataset.add);
      sessions = WorkbenchSessions.loadAll();
      renderAll();
    });
  });
}

function renderHistory() {
  const list = document.getElementById('history-list');
  const entries = activeSession.history || [];
  list.innerHTML = entries.map((entry) => `
    <li><time>${new Date(entry.at).toLocaleString()}</time> <strong>${entry.action}</strong> — ${entry.detail}</li>
  `).join('');
}

function renderActive() {
  const hasSession = !!activeSession;
  document.getElementById('session-main').hidden = !hasSession;
  document.getElementById('session-empty').hidden = hasSession;
  if (!hasSession) return;

  document.getElementById('session-name').value = activeSession.name;
  document.getElementById('session-notes').value = activeSession.notes || '';
  const statusEl = document.getElementById('session-status');
  statusEl.textContent = activeSession.status;
  statusEl.className = `status-pill ${activeSession.status === 'ready' ? 'reviewed' : 'needs-review'}`;

  renderStats();
  renderPayload();
  renderPool();
  renderHistory();
}

function renderAll() {
  renderSessions();
  renderActive();
}

function selectSession(id) {
  activeSession = WorkbenchSessions.get(id);
  renderAll();
}

function createSession() {
  activeSession = WorkbenchSessions.create();
  sessions = WorkbenchSessions.loadAll();
  renderAll();
}

function saveSessionFields() {
  if (!activeSession) return;
  activeSession.name = document.getElementById('session-name').value.trim() || activeSession.name;
  activeSession.notes = document.getElementById('session-notes').value.trim();
  activeSession = WorkbenchSessions.log(activeSession, 'updated', 'Session details saved');
  sessions = WorkbenchSessions.loadAll();
  renderSessions();
}

function exportPayload() {
  if (!activeSession) return;
  const payload = {
    session_id: activeSession.id,
    name: activeSession.name,
    status: activeSession.status,
    base_model_version: activeSession.base_model_version,
    media: activeSession.media_ids.map((id) => mediaById.get(id)).filter(Boolean),
    exported_at: new Date().toISOString(),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${activeSession.name.replace(/\s+/g, '-').toLowerCase()}-payload.json`;
  link.click();
  URL.revokeObjectURL(url);
  activeSession = WorkbenchSessions.log(activeSession, 'exported', 'Training payload exported');
  sessions = WorkbenchSessions.loadAll();
  renderHistory();
}

async function init() {
  await loadMedia();
  const status = await StudioApi.modelStatus();
  sessions = WorkbenchSessions.loadAll();
  sessions.forEach((session) => {
    if (!session.base_model_version) session.base_model_version = status.model_version || status.ace_model_dir || '';
  });

  if (!sessions.length) {
    renderSessions();
    document.getElementById('session-empty').hidden = false;
    document.getElementById('session-main').hidden = true;
  } else {
    activeSession = sessions[0];
    renderAll();
  }

  const mediaId = queryMediaId();
  if (mediaId) {
    if (!activeSession) createSession();
    if (mediaById.has(mediaId)) {
      activeSession = WorkbenchSessions.addMedia(activeSession, mediaId);
      sessions = WorkbenchSessions.loadAll();
      renderAll();
    }
  }

  document.getElementById('new-session-btn').addEventListener('click', createSession);
  document.getElementById('new-session-empty-btn').addEventListener('click', createSession);
  document.getElementById('session-name').addEventListener('change', saveSessionFields);
  document.getElementById('session-notes').addEventListener('change', saveSessionFields);
  document.getElementById('mark-ready-btn').addEventListener('click', () => {
    activeSession = WorkbenchSessions.setStatus(activeSession, 'ready');
    sessions = WorkbenchSessions.loadAll();
    renderAll();
  });
  document.getElementById('export-payload-btn').addEventListener('click', exportPayload);
}

init();
