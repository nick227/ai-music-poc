let queue = [];
let activeItem = null;

const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-upload');
const queueList = document.getElementById('queue-list');
const queueCount = document.getElementById('queue-count');
const editorPanel = document.getElementById('editor-panel');
const workbenchLayout = document.getElementById('workbench-layout');
const editorForm = document.getElementById('editor-form');
const activeFilename = document.getElementById('active-filename');
const mediaPlayer = document.getElementById('media-player');
const pipelineCard = document.getElementById('pipeline-card');

function queryMediaId() {
  return new URLSearchParams(window.location.search).get('media_id');
}

function categoryCount(item) {
  if (item.category_assignment_count != null) return item.category_assignment_count;
  return item.category_assignments?.length ?? 0;
}

function syncQueueItem(media) {
  const index = queue.findIndex((entry) => entry.id === media.id);
  if (index >= 0) {
    queue[index] = {
      ...queue[index],
      ...media,
      category_assignment_count: media.category_assignments?.length ?? media.category_assignment_count ?? 0,
    };
  }
}

function setEditorOpen(open) {
  editorPanel.classList.toggle('editor-panel--idle', !open);
  workbenchLayout.classList.toggle('workbench-layout--editor-open', open);
  editorForm.hidden = !open;
  pipelineCard.hidden = !open;
}

function updatePipeline() {
  if (!activeItem) {
    pipelineCard.hidden = true;
    return;
  }
  const count = WorkbenchTaxonomy.getSelectedCategoryIds().length;
  document.getElementById('pipeline-summary').textContent = activeItem.title;
  const pill = document.getElementById('pipeline-cats');
  pill.textContent = `${count} categor${count === 1 ? 'y' : 'ies'}`;
  pill.classList.toggle('has-value', count > 0);
  document.getElementById('pipeline-generate').href = `/?context_media=${activeItem.id}`;
  document.getElementById('pipeline-media-link').href = `/media-detail.html?id=${activeItem.id}`;
}

async function init() {
  StudioNav.render('workbench');
  await WorkbenchTaxonomy.loadTaxonomy();
  WorkbenchTaxonomy.init(updatePipeline);
  await loadQueue();
  setupDragAndDrop();
  setEditorOpen(false);

  const mediaId = queryMediaId();
  if (mediaId) await focusMedia(mediaId);

  editorForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    await saveAssignments({ advance: true, markReviewed: false });
  });

  document.getElementById('skip-btn').addEventListener('click', () => {
    advanceQueue(activeItem?.id, { remove: false });
  });

  document.getElementById('done-btn').addEventListener('click', () => {
    saveAssignments({ advance: true, markReviewed: true });
  });
}

async function focusMedia(mediaId) {
  const existing = queue.find((item) => item.id === mediaId);
  if (existing) {
    await selectItem(existing);
    return;
  }
  const media = await StudioApi.getMedia(mediaId);
  queue = [media, ...queue.filter((item) => item.id !== mediaId)];
  renderQueue();
  await selectItem(media);
}

async function loadQueue() {
  try {
    queue = await StudioApi.getInbox();
    renderQueue();
    if (queue.length > 0 && !activeItem && !queryMediaId()) await selectItem(queue[0]);
  } catch (error) {
    console.error('Failed to load inbox', error);
  }
}

function renderQueue() {
  queueCount.textContent = queue.length;
  if (!queue.length) {
    queueList.innerHTML = '';
    return;
  }
  queueList.innerHTML = queue.map((item) => {
    const count = categoryCount(item);
    const metaClass = count > 0 ? 'queue-item-meta has-cats' : 'queue-item-meta';
    return `
      <div class="queue-item ${activeItem?.id === item.id ? 'active' : ''}" data-id="${item.id}">
        <span class="queue-item-name">${item.title}</span>
        <span class="${metaClass}">${count}</span>
      </div>
    `;
  }).join('');
  queueList.querySelectorAll('.queue-item').forEach((el) => {
    el.addEventListener('click', () => selectItemById(el.dataset.id));
  });
}

async function selectItemById(id) {
  const item = queue.find((entry) => entry.id === id);
  if (item) await selectItem(item);
}

async function selectItem(item) {
  activeItem = await StudioApi.getMedia(item.id);
  syncQueueItem(activeItem);
  renderQueue();

  const first = activeItem.category_assignments?.[0] || {};
  document.getElementById('quality-score').value = first.quality_score ?? '';
  document.getElementById('fit-score').value = first.fit_score ?? '';
  document.getElementById('role-select').value = first.role || activeItem.primary_role || 'REFERENCE';
  document.getElementById('notes-input').value = first.notes || '';

  WorkbenchTaxonomy.setSelectionFromMedia(activeItem);
  setEditorOpen(true);
  activeFilename.textContent = activeItem.title;
  mediaPlayer.src = `/api/media/${activeItem.id}/audio`;
  updatePipeline();
}

function advanceQueue(currentId, { remove }) {
  if (remove && currentId) queue = queue.filter((item) => item.id !== currentId);
  renderQueue();
  if (queue.length > 0) {
    selectItem(queue[0]);
    return;
  }
  activeItem = null;
  setEditorOpen(false);
  mediaPlayer.removeAttribute('src');
  mediaPlayer.load();
}

function setupDragAndDrop() {
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach((name) => {
    dropzone.addEventListener(name, (e) => { e.preventDefault(); e.stopPropagation(); });
  });
  ['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, () => dropzone.classList.add('dragover')));
  ['dragleave', 'drop'].forEach((name) => dropzone.addEventListener(name, () => dropzone.classList.remove('dragover')));
  dropzone.addEventListener('drop', (e) => uploadFiles(e.dataTransfer.files));
  fileInput.addEventListener('change', (e) => uploadFiles(e.target.files));
}

async function uploadFiles(files) {
  if (!files.length) return;
  const formData = new FormData();
  for (const file of files) formData.append('files', file);
  try {
    const imported = await StudioApi.importMedia(formData);
    queue = [...queue, ...imported];
    renderQueue();
    if (!activeItem && queue.length) await selectItem(queue[0]);
  } catch (error) {
    console.error('Upload failed', error);
    alert('Upload failed.');
  }
}

function parseOptionalScore(value) {
  if (value === '' || value == null) return null;
  const parsed = parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

function buildAssignmentPayload(markReviewed) {
  const qualityScore = parseOptionalScore(document.getElementById('quality-score').value);
  const fitScore = parseOptionalScore(document.getElementById('fit-score').value);
  const role = document.getElementById('role-select').value || 'REFERENCE';
  const notes = document.getElementById('notes-input').value.trim() || null;
  const categoryIds = WorkbenchTaxonomy.getSelectedCategoryIds();
  return {
    mark_reviewed: markReviewed,
    categories: categoryIds.map((categoryId) => ({
      category_id: categoryId,
      quality_score: qualityScore,
      fit_score: fitScore,
      role,
      notes,
      reviewed: markReviewed,
    })),
    concepts: [],
  };
}

async function saveAssignments({ advance, markReviewed }) {
  if (!activeItem) return;
  const submitBtn = document.getElementById('save-next-btn');
  submitBtn.disabled = true;
  document.getElementById('done-btn').disabled = true;

  try {
    const saved = await StudioApi.saveAssignments(activeItem.id, buildAssignmentPayload(markReviewed));
    WorkbenchTaxonomy.rememberSavedCategories();
    activeItem = saved;
    if (markReviewed) {
      advanceQueue(activeItem.id, { remove: true });
    } else {
      syncQueueItem(saved);
      if (advance) advanceQueue(activeItem.id, { remove: false });
      else renderQueue();
    }
  } catch (error) {
    console.error('Save failed', error);
    alert('Failed to save.');
  } finally {
    submitBtn.disabled = false;
    document.getElementById('done-btn').disabled = false;
  }
}

init();
