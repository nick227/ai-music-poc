window.WorkbenchSlice = (() => {
  const CALIBRATION_MIN_TRACKS = 8;
  const CALIBRATION_MAX_TRACKS = 12;

  const BASE_FILTER = {
    review_status: 'REVIEWED',
    rights_status: 'CONFIRMED',
    min_quality: 3,
    min_fit: 3,
    roles: ['GOLD_REFERENCE', 'TRAINING_CANDIDATE', 'REFERENCE'],
    category_ids: [],
  };

  let categoriesById = new Map();
  let conceptsById = new Map();
  let eligibleMedia = [];
  let savedSlices = [];
  let activeSliceId = null;

  function baseFilter(conceptId = null, categoryIds = []) {
    return {
      ...BASE_FILTER,
      concept_id: conceptId,
      category_ids: categoryIds,
    };
  }

  function readCategoryIds() {
    return [...document.querySelectorAll('#filter-categories input:checked')].map((el) => el.value);
  }

  function selectedConceptId() {
    return document.getElementById('filter-concept').value || null;
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
    const conceptId = selectedConceptId();
    const saveBtn = document.getElementById('save-slice-btn');
    const freezeBtn = document.getElementById('freeze-slice-btn');
    const hasName = document.getElementById('slice-name').value.trim().length > 0;
    const canSave = !!conceptId && previewMedia.length > 0 && hasName
      && (!slice || slice.status === 'DRAFT');
    saveBtn.disabled = !canSave;
    freezeBtn.disabled = !slice || slice.status !== 'DRAFT' || slice.asset_count === 0;
  }

  function renderConceptOptions() {
    const counts = new Map();
    eligibleMedia.forEach((item) => {
      item.concept_ids.forEach((id) => counts.set(id, (counts.get(id) || 0) + 1));
    });
    const select = document.getElementById('filter-concept');
    const current = select.value;
    const options = [...counts.entries()]
      .map(([id, count]) => {
        const concept = conceptsById.get(id);
        return concept ? { id, name: concept.name, count } : null;
      })
      .filter(Boolean)
      .sort((a, b) => a.name.localeCompare(b.name));
    select.innerHTML = options.length
      ? '<option value="">Select a concept…</option>' + options.map((c) => `<option value="${c.id}">${c.name} (${c.count} ready track${c.count === 1 ? '' : 's'})</option>`).join('')
      : '<option value="">No concepts with ready tracks yet</option>';
    if (current && options.some((c) => c.id === current)) select.value = current;
  }

  function mediaForConcept(conceptId) {
    return eligibleMedia.filter((item) => item.concept_ids.includes(conceptId));
  }

  function renderCategoryFilters(conceptId) {
    const block = document.getElementById('tag-refine-block');
    const container = document.getElementById('filter-categories');
    if (!conceptId) {
      block.classList.add('hidden');
      container.innerHTML = '';
      return;
    }
    const counts = new Map();
    mediaForConcept(conceptId).forEach((item) => {
      item.category_ids.forEach((id) => counts.set(id, (counts.get(id) || 0) + 1));
    });
    const tags = [...counts.entries()]
      .map(([id, count]) => {
        const cat = categoriesById.get(id);
        return cat ? { ...cat, count } : null;
      })
      .filter(Boolean)
      .sort((a, b) => a.name.localeCompare(b.name));
    if (!tags.length) {
      block.classList.add('hidden');
      container.innerHTML = '';
      return;
    }
    block.classList.remove('hidden');
    container.innerHTML = tags.map((cat) => `
      <label class="checkline category-option">
        <input type="checkbox" value="${cat.id}" />
        ${cat.name} <span class="tag-count">(${cat.count})</span>
      </label>
    `).join('');
    container.querySelectorAll('input').forEach((el) => {
      el.addEventListener('change', () => runPreview().catch((err) => setStatus(err.message, true)));
    });
  }

  let previewMedia = [];

  function renderPreview() {
    const summary = document.getElementById('preview-summary');
    const guidance = document.getElementById('preview-guidance');
    const list = document.getElementById('preview-list');
    const conceptId = selectedConceptId();
    if (!conceptId) {
      summary.textContent = 'Select a concept to see matching tracks.';
      guidance.classList.add('hidden');
      list.innerHTML = '<p class="empty-hint muted">Import and review tracks in Media first. Only reviewed tracks with confirmed training rights appear here.</p>';
      updateActionButtons();
      return;
    }
    const count = previewMedia.length;
    summary.textContent = `${count} track${count === 1 ? '' : 's'} ready for this concept.`;
    guidance.classList.remove('hidden');
    if (count < CALIBRATION_MIN_TRACKS) {
      guidance.textContent = `Add ${CALIBRATION_MIN_TRACKS - count} more reviewed track${CALIBRATION_MIN_TRACKS - count === 1 ? '' : 's'} before calibration training (target ${CALIBRATION_MIN_TRACKS}–${CALIBRATION_MAX_TRACKS}).`;
      guidance.classList.add('warn');
    } else if (count > CALIBRATION_MAX_TRACKS) {
      guidance.textContent = `${count} tracks match. Calibration works best with ${CALIBRATION_MIN_TRACKS}–${CALIBRATION_MAX_TRACKS} focused tracks — consider narrowing tags.`;
      guidance.classList.remove('warn');
    } else {
      guidance.textContent = `Good size for calibration (${CALIBRATION_MIN_TRACKS}–${CALIBRATION_MAX_TRACKS} tracks). Save, then lock the set before training.`;
      guidance.classList.remove('warn');
    }
    if (!count) {
      list.innerHTML = '<p class="empty-hint muted">No tracks match this concept and tag filter. Loosen tags or add more reviewed media.</p>';
      updateActionButtons();
      return;
    }
    list.innerHTML = previewMedia.map((item) => `
      <div class="preview-row">
        <a class="track-title" href="${StudioRoutes.mediaDetail(item.id)}">${item.title}</a>
        <span class="preview-meta">${item.primary_role ? item.primary_role.replace(/_/g, ' ').toLowerCase() : 'no role'}</span>
      </div>
    `).join('');
    updateActionButtons();
  }

  async function runPreview() {
    const conceptId = selectedConceptId();
    renderCategoryFilters(conceptId);
    if (!conceptId) {
      previewMedia = [];
      renderPreview();
      return;
    }
    setStatus('Updating track list…');
    const res = await StudioApi.previewSlices(baseFilter(conceptId, readCategoryIds()));
    previewMedia = res.media || [];
    renderPreview();
    setStatus('');
  }

  async function saveDraft() {
    const name = document.getElementById('slice-name').value.trim();
    const conceptId = selectedConceptId();
    if (!conceptId) {
      setStatus('Select a concept before saving.', true);
      return;
    }
    if (!name) {
      setStatus('Enter a training set name before saving.', true);
      return;
    }
    const filter = baseFilter(conceptId, readCategoryIds());
    const payload = { name, filter };
    setStatus('Saving training set…');
    const slice = activeSliceId && activeSlice()?.status === 'DRAFT'
      ? await StudioApi.updateSlice(activeSliceId, payload)
      : await StudioApi.createSlice(payload);
    activeSliceId = slice.id;
    await refreshSlices();
    window.WorkbenchTraining?.refreshHistory?.();
    setStatus(`Saved “${slice.name}” with ${slice.asset_count} track${slice.asset_count === 1 ? '' : 's'}. Lock tracks when ready.`);
  }

  async function freezeSlice() {
    if (!activeSliceId) return;
    setStatus('Locking tracks…');
    const slice = await StudioApi.freezeSlice(activeSliceId);
    await refreshSlices();
    window.WorkbenchTraining?.refreshHistory?.();
    window.WorkbenchTraining?.refreshTrainableSlices?.();
    setStatus(`Locked “${slice.name}”. You can start calibration training in Step 2.`);
  }

  function applyFilterToForm(filter) {
    document.getElementById('filter-concept').value = filter.concept_id || '';
    renderCategoryFilters(filter.concept_id || null);
    document.querySelectorAll('#filter-categories input').forEach((el) => {
      el.checked = (filter.category_ids || []).includes(el.value);
    });
  }

  async function loadSlice(sliceId) {
    const slice = await StudioApi.getSlice(sliceId);
    activeSliceId = slice.id;
    document.getElementById('slice-name').value = slice.name;
    applyFilterToForm(slice.filter);
    await runPreview();
    updateActionButtons();
    setStatus(`Loaded “${slice.name}” (${slice.status === 'READY' ? 'locked' : 'draft'}).`);
  }

  async function refreshSlices() {
    savedSlices = await StudioApi.listSlices();
    updateActionButtons();
  }

  async function loadEligiblePool() {
    const res = await StudioApi.previewSlices(baseFilter());
    eligibleMedia = res.media || [];
    renderConceptOptions();
  }

  async function init() {
    const [categoryRes, conceptList] = await Promise.all([
      StudioApi.listCategories(),
      StudioApi.listConcepts(),
    ]);
    (categoryRes.categories || []).forEach((cat) => categoriesById.set(cat.id, cat));
    conceptList.forEach((c) => conceptsById.set(c.id, c));
    await loadEligiblePool();
    await refreshSlices();

    document.getElementById('filter-concept').addEventListener('change', () => {
      if (activeSliceId && activeSlice()?.status === 'DRAFT') activeSliceId = null;
      runPreview().catch((err) => setStatus(err.message, true));
    });
    document.getElementById('slice-name').addEventListener('input', updateActionButtons);
    document.getElementById('save-slice-btn').addEventListener('click', () => saveDraft().catch((err) => setStatus(err.message, true)));
    document.getElementById('freeze-slice-btn').addEventListener('click', () => freezeSlice().catch((err) => setStatus(err.message, true)));
  }

  return {
    init,
    refreshSlices,
    loadSlice,
    listSlices: () => savedSlices,
    calibrationMinTracks: CALIBRATION_MIN_TRACKS,
  };
})();
