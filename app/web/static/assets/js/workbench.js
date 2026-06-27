const TRAINING_ROLES = new Set(['GOLD_REFERENCE', 'TRAINING_CANDIDATE', 'REFERENCE']);

let workspace = null;
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

function categoryText(item) {
  const assignments = item.category_assignments || [];
  const names = assignments.map((a) => categoriesById.get(a.category_id)?.name || null).filter(Boolean);
  return names.length ? names.join(', ') : 'No categories';
}

function selectedCount() {
  return workspace.media_ids.filter((id) => eligibleMedia.some((m) => m.id === id)).length;
}

function renderModelLine() {
  const el = document.getElementById('model-line');
  const ready = modelStatus?.can_generate || modelStatus?.wiring_ok;
  const base = modelStatus?.user_message || (ready ? 'Your model is ready to generate.' : 'Your model still needs setup.');
  el.textContent = ready ? `${base} Selected tracks will be packaged for fine-tuning.` : `${base} You can still pick tracks — finish setup in Settings when you're ready to train.`;
  el.classList.toggle('ready', !!ready);
}

function renderSummary() {
  const total = eligibleMedia.length;
  const selected = selectedCount();
  const summary = document.getElementById('tracks-summary');
  const downloadBtn = document.getElementById('download-btn');
  const selectAllBtn = document.getElementById('select-all-btn');

  if (!total) {
    summary.textContent = 'No tracks ready yet';
    downloadBtn.disabled = true;
    selectAllBtn.disabled = true;
    return;
  }

  if (!selected) {
    summary.textContent = `${total} track${total === 1 ? '' : 's'} available — none selected`;
  } else if (selected === total) {
    summary.textContent = `All ${total} track${total === 1 ? '' : 's'} selected`;
  } else {
    summary.textContent = `${selected} of ${total} tracks selected`;
  }

  downloadBtn.disabled = selected === 0;
  selectAllBtn.disabled = false;
  selectAllBtn.textContent = selected === total ? 'Clear selection' : 'Select all';
}

function renderTracks() {
  const list = document.getElementById('tracks-list');
  const empty = document.getElementById('empty-hint');
  const selected = new Set(workspace.media_ids);

  if (!eligibleMedia.length) {
    list.innerHTML = '';
    empty.hidden = false;
    return;
  }

  empty.hidden = true;
  list.innerHTML = eligibleMedia.map((item) => {
    const checked = selected.has(item.id);
    return `
      <label class="track-row ${checked ? 'selected' : ''}">
        <input type="checkbox" data-id="${item.id}" ${checked ? 'checked' : ''} />
        <span class="track-info">
          <a class="track-title" href="${StudioRoutes.mediaDetail(item.id)}">${item.title}</a>
          <span class="track-tags">${categoryText(item)}</span>
        </span>
      </label>
    `;
  }).join('');

  list.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    input.addEventListener('change', () => {
      workspace = WorkbenchSessions.toggleMedia(input.dataset.id, input.checked);
      renderAll();
    });
  });

  list.querySelectorAll('.track-title').forEach((link) => {
    link.addEventListener('click', (e) => e.stopPropagation());
  });
}

function renderAll() {
  renderSummary();
  renderTracks();
}

function selectAllOrClear() {
  const allSelected = selectedCount() === eligibleMedia.length;
  workspace = WorkbenchSessions.setMediaIds(allSelected ? [] : eligibleMedia.map((m) => m.id));
  renderAll();
}

function downloadPackage() {
  const media = workspace.media_ids
    .map((id) => eligibleMedia.find((m) => m.id === id))
    .filter(Boolean);
  if (!media.length) return;

  const payload = {
    name: 'Training package',
    target_model: {
      backend: 'ACE-Step',
      model_dir: modelStatus?.ace_model_dir || '',
      can_generate: modelStatus?.can_generate ?? false,
    },
    tracks: media.map((item) => ({
      id: item.id,
      title: item.title,
      categories: (item.category_assignments || []).map((a) => ({
        name: categoriesById.get(a.category_id)?.name || a.category_id,
        role: a.role,
      })),
    })),
    exported_at: new Date().toISOString(),
  };

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `training-package-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
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
  workspace = WorkbenchSessions.getOrCreate();

  const mediaId = queryMediaId();
  if (mediaId && eligibleMedia.some((m) => m.id === mediaId) && !workspace.media_ids.includes(mediaId)) {
    workspace = WorkbenchSessions.toggleMedia(mediaId, true);
  }

  renderModelLine();
  renderAll();

  document.getElementById('select-all-btn').addEventListener('click', selectAllOrClear);
  document.getElementById('download-btn').addEventListener('click', downloadPackage);
}

init();
