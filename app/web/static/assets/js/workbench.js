const TRAINING_ROLES = new Set(['GOLD_REFERENCE', 'TRAINING_CANDIDATE', 'REFERENCE']);

let sessions = [];
let activeSession = null;
let modelStatus = null;
let categoriesById = new Map();
let eligibleMedia = [];

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
  const first = item.category_assignments?.[0];
  if (first?.role) return first.role.replace(/_/g, ' ').toLowerCase();
  return '—';
}

function categoryLabels(item) {
  const assignments = item.category_assignments || [];
  return assignments.map((a) => {
    const cat = categoriesById.get(a.category_id);
    return cat ? cat.name : a.category_id;
  });
}

function renderModelCard() {
  const summary = document.getElementById('model-summary');
  const ready = modelStatus?.can_generate || modelStatus?.wiring_ok;
  summary.textContent = modelStatus?.user_message || (ready ? 'Model wiring looks ready' : 'Model not fully configured');
  summary.classList.toggle('ready', !!ready);

  const rows = [
    ['Backend', 'ACE-Step'],
    ['Model dir', modelStatus?.ace_model_dir || '—'],
    ['Generate ready', ready ? 'yes' : 'no'],
    ['HF cache', modelStatus?.hf_cache_exists ? 'present' : 'missing'],
  ];
  document.getElementById('model-meta').innerHTML = rows
    .map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`)
    .join('');
}

function renderSessionSelect() {
  const select = document.getElementById('session-select');
  if (!sessions.length) {
    select.innerHTML = '<option value="">No sessions</option>';
    return;
  }
  select.innerHTML = sessions.map((s) => `
    <option value="${s.id}" ${s.id === activeSession?.id ? 'selected' : ''}>${s.name} (${s.media_ids.length})</option>
  `).join('');
}

function renderStats() {
  const inSlice = activeSession.media_ids
    .map((id) => eligibleMedia.find((m) => m.id === id))
    .filter(Boolean);
  const gold = inSlice.filter((item) => item.primary_role === 'GOLD_REFERENCE').length;
  const candidates = inSlice.filter((item) => item.primary_role === 'TRAINING_CANDIDATE').length;
  const cats = new Set();
  inSlice.forEach((item) => {
    (item.category_assignments || []).forEach((a) => cats.add(a.category_id));
  });
  const eligibleCount = eligibleMedia.length;

  document.getElementById('session-stats').innerHTML = `
    <span class="stat-pill highlight">${inSlice.length} in slice</span>
    <span class="stat-pill">${eligibleCount} eligible in Media</span>
    <span class="stat-pill">${gold} gold ref</span>
    <span class="stat-pill">${candidates} candidates</span>
    <span class="stat-pill">${cats.size} categories covered</span>
  `;
  document.getElementById('slice-count').textContent = String(inSlice.length);

  const hint = document.getElementById('slice-hint');
  if (!eligibleCount) {
    hint.textContent = 'No eligible tracks yet — categorize and mark reviewed in Media, then return here.';
  } else if (!inSlice.length) {
    hint.textContent = `${eligibleCount} reviewed categorized track${eligibleCount === 1 ? '' : 's'} available. Toggle rows or use "Include all eligible".`;
  } else {
    hint.textContent = `Slice pulls ${inSlice.length} of ${eligibleCount} eligible tracks toward the target model above.`;
  }
}

function renderTrainingTable() {
  const tbody = document.getElementById('training-rows');
  const inSlice = new Set(activeSession?.media_ids || []);

  if (!eligibleMedia.length) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="table-meta">
          No training-ready media — <a href="${StudioRoutes.media}">open Media</a> to import, categorize, and mark reviewed.
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = eligibleMedia.map((item) => {
    const included = inSlice.has(item.id);
    const labels = categoryLabels(item);
    const tags = labels.length
      ? labels.map((name) => `<span class="cat-tag">${name}</span>`).join('')
      : '<span class="table-meta">—</span>';
    const reviewClass = item.review_status === 'NEEDS_REVIEW' ? 'status-pill needs-review' : 'status-pill reviewed';
    return `
      <tr data-id="${item.id}">
        <td><input type="checkbox" class="slice-toggle" data-id="${item.id}" ${included ? 'checked' : ''} /></td>
        <td class="table-title"><a href="${StudioRoutes.mediaDetail(item.id)}">${item.title}</a></td>
        <td class="table-meta">${roleLabel(item)}</td>
        <td><div class="cat-tags">${tags}</div></td>
        <td><span class="${reviewClass}">${item.review_status.replace(/_/g, ' ').toLowerCase()}</span></td>
        <td><a class="button ghost small" href="${StudioRoutes.mediaDetail(item.id)}">Edit</a></td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.slice-toggle').forEach((input) => {
    input.addEventListener('change', () => toggleSlice(input.dataset.id, input.checked));
  });
}

function renderHistory() {
  const list = document.getElementById('history-list');
  const entries = activeSession?.history || [];
  list.innerHTML = entries.length
    ? entries.map((entry) => `
        <li><time>${new Date(entry.at).toLocaleString()}</time> <strong>${entry.action}</strong> — ${entry.detail}</li>
      `).join('')
    : '<li class="table-meta">No history yet</li>';
}

function renderActive() {
  if (!activeSession) return;

  document.getElementById('session-name').value = activeSession.name;
  document.getElementById('session-notes').value = activeSession.notes || '';
  const statusEl = document.getElementById('session-status');
  statusEl.textContent = activeSession.status;
  statusEl.className = `status-pill ${activeSession.status === 'ready' ? 'reviewed' : 'needs-review'}`;

  if (modelStatus && !activeSession.base_model_version) {
    activeSession.base_model_version = modelStatus.ace_model_dir || '';
    WorkbenchSessions.update(activeSession);
  }

  renderSessionSelect();
  renderStats();
  renderTrainingTable();
  renderHistory();
}

function renderAll() {
  renderSessionSelect();
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

function toggleSlice(mediaId, included) {
  const media = eligibleMedia.find((m) => m.id === mediaId);
  const title = media?.title || mediaId;
  if (included) {
    activeSession = WorkbenchSessions.addMedia(activeSession, mediaId, title);
  } else {
    activeSession = WorkbenchSessions.removeMedia(activeSession, mediaId, title);
  }
  sessions = WorkbenchSessions.loadAll();
  renderAll();
}

function syncAllEligible() {
  let added = 0;
  for (const item of eligibleMedia) {
    if (!activeSession.media_ids.includes(item.id)) {
      activeSession = WorkbenchSessions.addMedia(activeSession, item.id, item.title);
      added += 1;
    }
  }
  if (added) {
    activeSession = WorkbenchSessions.log(activeSession, 'synced', `Included ${added} eligible track${added === 1 ? '' : 's'} from Media`);
  }
  sessions = WorkbenchSessions.loadAll();
  renderAll();
}

function saveSessionFields() {
  if (!activeSession) return;
  activeSession.name = document.getElementById('session-name').value.trim() || activeSession.name;
  activeSession.notes = document.getElementById('session-notes').value.trim();
  activeSession = WorkbenchSessions.log(activeSession, 'updated', 'Session details saved');
  sessions = WorkbenchSessions.loadAll();
  renderSessionSelect();
}

function exportPayload() {
  if (!activeSession) return;
  const media = activeSession.media_ids
    .map((id) => eligibleMedia.find((m) => m.id === id))
    .filter(Boolean);
  const payload = {
    session_id: activeSession.id,
    name: activeSession.name,
    status: activeSession.status,
    target_model: {
      backend: 'ACE-Step',
      model_dir: modelStatus?.ace_model_dir || activeSession.base_model_version,
      can_generate: modelStatus?.can_generate ?? false,
    },
    media: media.map((item) => ({
      id: item.id,
      title: item.title,
      role: item.primary_role,
      review_status: item.review_status,
      categories: (item.category_assignments || []).map((a) => ({
        category_id: a.category_id,
        name: categoriesById.get(a.category_id)?.name || a.category_id,
        role: a.role,
        quality_score: a.quality_score,
        fit_score: a.fit_score,
      })),
    })),
    exported_at: new Date().toISOString(),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${activeSession.name.replace(/\s+/g, '-').toLowerCase()}-payload.json`;
  link.click();
  URL.revokeObjectURL(url);
  activeSession = WorkbenchSessions.log(activeSession, 'exported', `Exported ${media.length} tracks toward target model`);
  sessions = WorkbenchSessions.loadAll();
  renderHistory();
}

async function loadTaxonomy() {
  const res = await StudioApi.listCategories();
  categoriesById = new Map((res.categories || []).map((c) => [c.id, c]));
}

async function loadEligibleMedia() {
  const summaries = await StudioApi.listMedia({ limit: 200 });
  const candidates = summaries.filter(isTrainingEligible);
  eligibleMedia = await Promise.all(candidates.map((s) => StudioApi.getMedia(s.id)));
}

async function init() {
  const [status] = await Promise.all([StudioApi.modelStatus(), loadTaxonomy(), loadEligibleMedia()]);
  modelStatus = status;
  renderModelCard();

  sessions = WorkbenchSessions.loadAll();
  if (!sessions.length) {
    activeSession = WorkbenchSessions.create();
    sessions = WorkbenchSessions.loadAll();
  } else {
    activeSession = sessions[0];
  }

  const mediaId = queryMediaId();
  if (mediaId && eligibleMedia.some((m) => m.id === mediaId)) {
    if (!activeSession.media_ids.includes(mediaId)) {
      const item = eligibleMedia.find((m) => m.id === mediaId);
      activeSession = WorkbenchSessions.addMedia(activeSession, mediaId, item?.title);
      sessions = WorkbenchSessions.loadAll();
    }
  }

  renderAll();

  document.getElementById('session-select').addEventListener('change', (e) => selectSession(e.target.value));
  document.getElementById('new-session-btn').addEventListener('click', createSession);
  document.getElementById('sync-eligible-btn').addEventListener('click', syncAllEligible);
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
