window.WorkbenchSlice = (() => {
  const DIMENSION_ORDER = [
    'GENRE', 'MOOD', 'INSTRUMENT', 'VOCALS', 'ENERGY', 'RHYTHM', 'TECHNIQUE',
    'PRODUCTION', 'MIX', 'ARRANGEMENT', 'QUALITY_ISSUE', 'TRAINING_ROLE',
  ];

  let categories = [];
  let concepts = [];
  let previewMedia = [];
  let savedSlices = [];
  let activeSliceId = null;

  function readFilter() {
    const roles = [...document.querySelectorAll('input[name="role"]:checked')].map((el) => el.value);
    const categoryIds = [...document.querySelectorAll('#filter-categories input:checked')].map((el) => el.value);
    const minQuality = document.getElementById('filter-min-quality').value;
    const minFit = document.getElementById('filter-min-fit').value;
    return {
      concept_id: document.getElementById('filter-concept').value || null,
      category_ids: categoryIds,
      roles,
      min_quality: minQuality ? Number(minQuality) : null,
      min_fit: minFit ? Number(minFit) : null,
      review_status: document.getElementById('filter-review-status').value || null,
      rights_status: document.getElementById('filter-rights-status').value || null,
    };
  }

  function applyFilterToForm(filter) {
    document.getElementById('filter-concept').value = filter.concept_id || '';
    document.getElementById('filter-review-status').value = filter.review_status || '';
    document.getElementById('filter-rights-status').value = filter.rights_status || '';
    document.getElementById('filter-min-quality').value = filter.min_quality ?? '';
    document.getElementById('filter-min-fit').value = filter.min_fit ?? '';
    document.querySelectorAll('input[name="role"]').forEach((el) => {
      el.checked = (filter.roles || []).includes(el.value);
    });
    document.querySelectorAll('#filter-categories input').forEach((el) => {
      el.checked = (filter.category_ids || []).includes(el.value);
    });
  }

  function setStatus(message, isError = false) {
    const el = document.getElementById('slice-status');
    el.textContent = message;
    el.classList.toggle('error', isError);
  }

  function activeSlice() {
    return savedSlices.find((item) => item.id === activeSliceId) || null;
  }

  function updateActionButtons() {
    const slice = activeSlice();
    const freezeBtn = document.getElementById('freeze-slice-btn');
    const downloadBtn = document.getElementById('download-package-btn');
    freezeBtn.disabled = !slice || slice.status !== 'DRAFT' || slice.asset_count === 0;
    downloadBtn.disabled = !slice || slice.status !== 'READY';
  }

  function renderCategoryFilters() {
    const container = document.getElementById('filter-categories');
    const grouped = new Map();
    categories.forEach((cat) => {
      if (!grouped.has(cat.dimension)) grouped.set(cat.dimension, []);
      grouped.get(cat.dimension).push(cat);
    });
    container.innerHTML = DIMENSION_ORDER.filter((dim) => grouped.has(dim)).map((dim) => {
      const items = grouped.get(dim).map((cat) => `
        <label class="checkline category-option">
          <input type="checkbox" value="${cat.id}" />
          ${cat.name}
        </label>
      `).join('');
      return `<div class="category-group"><p class="category-group-label">${dim.replace(/_/g, ' ')}</p>${items}</div>`;
    }).join('');
  }

  function renderConceptOptions() {
    const select = document.getElementById('filter-concept');
    select.innerHTML = '<option value="">Any concept</option>' + concepts.map((c) => `<option value="${c.id}">${c.name}</option>`).join('');
  }

  function renderPreview() {
    const summary = document.getElementById('preview-summary');
    const list = document.getElementById('preview-list');
    summary.textContent = `${previewMedia.length} eligible track${previewMedia.length === 1 ? '' : 's'} match the current filters.`;
    if (!previewMedia.length) {
      list.innerHTML = '<p class="empty-hint muted">No media matches these filters. Import and review tracks in Media, or loosen the filters.</p>';
      updateActionButtons();
      return;
    }
    list.innerHTML = previewMedia.map((item) => `
      <div class="preview-row">
        <a class="track-title" href="${StudioRoutes.mediaDetail(item.id)}">${item.title}</a>
        <span class="preview-meta">${item.review_status.replace(/_/g, ' ').toLowerCase()} · ${item.rights_status.replace(/_/g, ' ').toLowerCase()} · ${item.primary_role || 'no role'}</span>
      </div>
    `).join('');
    updateActionButtons();
  }

  function renderSavedSlices() {
    const list = document.getElementById('saved-slices-list');
    if (!savedSlices.length) {
      list.innerHTML = '<p class="muted">No saved slices yet.</p>';
      return;
    }
    list.innerHTML = savedSlices.map((slice) => {
      const selected = slice.id === activeSliceId ? 'selected' : '';
      const statusClass = slice.status === 'READY' ? 'ready' : 'draft';
      return `
        <button type="button" class="saved-slice-row ${selected}" data-id="${slice.id}">
          <span class="saved-slice-name">${slice.name}</span>
          <span class="status-pill ${statusClass}">${slice.status.toLowerCase()}</span>
          <span class="saved-slice-meta">${slice.asset_count} track${slice.asset_count === 1 ? '' : 's'}</span>
        </button>
      `;
    }).join('');
    list.querySelectorAll('.saved-slice-row').forEach((btn) => {
      btn.addEventListener('click', () => loadSlice(btn.dataset.id));
    });
  }

  async function runPreview() {
    setStatus('Loading preview…');
    const res = await StudioApi.previewSlices(readFilter());
    previewMedia = res.media || [];
    renderPreview();
    setStatus('Preview updated. Save a draft slice when the match set looks right.');
  }

  async function saveDraft() {
    const name = document.getElementById('slice-name').value.trim();
    if (!name) {
      setStatus('Enter a slice name before saving.', true);
      return;
    }
    const filter = readFilter();
    const payload = { name, filter };
    setStatus('Saving draft slice…');
    const slice = activeSliceId && activeSlice()?.status === 'DRAFT'
      ? await StudioApi.updateSlice(activeSliceId, payload)
      : await StudioApi.createSlice(payload);
    activeSliceId = slice.id;
    await refreshSlices();
    setStatus(`Saved draft slice “${slice.name}” with ${slice.asset_count} track${slice.asset_count === 1 ? '' : 's'}.`);
  }

  async function freezeSlice() {
    if (!activeSliceId) return;
    setStatus('Freezing slice…');
    const slice = await StudioApi.freezeSlice(activeSliceId);
    await refreshSlices();
    setStatus(`Frozen “${slice.name}”. You can download the dataset package — training has not started.`);
  }

  function downloadPackage() {
    const slice = activeSlice();
    if (!slice || slice.status !== 'READY') return;
    window.location.href = StudioApi.slicePackageUrl(slice.id);
  }

  async function loadSlice(sliceId) {
    const slice = await StudioApi.getSlice(sliceId);
    activeSliceId = slice.id;
    document.getElementById('slice-name').value = slice.name;
    applyFilterToForm(slice.filter);
    await runPreview();
    renderSavedSlices();
    updateActionButtons();
    setStatus(`Loaded slice “${slice.name}” (${slice.status.toLowerCase()}).`);
  }

  async function refreshSlices() {
    savedSlices = await StudioApi.listSlices();
    renderSavedSlices();
    updateActionButtons();
  }

  async function init() {
    const [categoryRes, conceptList] = await Promise.all([
      StudioApi.listCategories(),
      StudioApi.listConcepts(),
    ]);
    categories = categoryRes.categories || [];
    concepts = conceptList;
    renderCategoryFilters();
    renderConceptOptions();
    await refreshSlices();
    await runPreview();

    document.getElementById('preview-btn').addEventListener('click', () => runPreview().catch((err) => setStatus(err.message, true)));
    document.getElementById('save-slice-btn').addEventListener('click', () => saveDraft().catch((err) => setStatus(err.message, true)));
    document.getElementById('freeze-slice-btn').addEventListener('click', () => freezeSlice().catch((err) => setStatus(err.message, true)));
    document.getElementById('download-package-btn').addEventListener('click', downloadPackage);
    document.getElementById('slice-filter-form').addEventListener('change', () => {
      if (activeSliceId && activeSlice()?.status === 'DRAFT') activeSliceId = null;
      updateActionButtons();
    });
  }

  return { init };
})();
