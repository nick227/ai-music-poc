window.WorkbenchApi = {
  async request(url, options = {}) {
    const res = await fetch(url, options);
    if (!res.ok) throw new Error(await res.text() || 'API request failed');
    return res.json();
  },
  importMedia(formData) {
    return this.request('/api/media/import', { method: 'POST', body: formData }).then((r) => r.media || []);
  },
  getInbox() {
    return this.request('/api/media?review_status=NEEDS_REVIEW&kind=UPLOAD').then((r) => r.media || []);
  },
  getMedia(id) {
    return this.request(`/api/media/${id}`);
  },
  listCategories() {
    return this.request('/api/categories');
  },
  createCategory(name, dimension) {
    return this.request('/api/categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, dimension }),
    });
  },
  saveAssignments(id, payload) {
    return this.request(`/api/media/${id}/assignments`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },
};

let queue = [];
let activeItem = null;

const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-upload');
const queueList = document.getElementById('queue-list');
const queueCount = document.getElementById('queue-count');
const editorForm = document.getElementById('editor-form');
const emptyState = document.getElementById('empty-editor-state');
const activeFilename = document.getElementById('active-filename');
const mediaPlayer = document.getElementById('media-player');

async function init() {
  await WorkbenchTaxonomy.loadTaxonomy();
  WorkbenchTaxonomy.init();
  await loadQueue();
  setupDragAndDrop();

  editorForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    await saveAndNext();
  });

  document.getElementById('skip-btn').addEventListener('click', () => {
    queue = queue.filter((item) => item.id !== activeItem?.id);
    renderQueue();
    selectNext();
  });
}

async function loadQueue() {
  try {
    queue = await WorkbenchApi.getInbox();
    renderQueue();
    if (queue.length > 0 && !activeItem) await selectItem(queue[0]);
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
  queueList.innerHTML = queue.map((item) => `
    <div class="queue-item ${activeItem?.id === item.id ? 'active' : ''}" data-id="${item.id}">
      <span class="queue-item-name">${item.title}</span>
    </div>
  `).join('');
  queueList.querySelectorAll('.queue-item').forEach((el) => {
    el.addEventListener('click', () => selectItemById(el.dataset.id));
  });
}

async function selectItemById(id) {
  const item = queue.find((entry) => entry.id === id);
  if (item) await selectItem(item);
}

async function selectItem(item) {
  activeItem = await WorkbenchApi.getMedia(item.id);
  renderQueue();

  const first = activeItem.category_assignments?.[0] || {};
  document.getElementById('quality-score').value = first.quality_score ?? '';
  document.getElementById('fit-score').value = first.fit_score ?? '';
  document.getElementById('role-select').value = first.role || 'REFERENCE';
  document.getElementById('notes-input').value = first.notes || '';

  WorkbenchTaxonomy.setSelectionFromMedia(activeItem);

  emptyState.hidden = true;
  editorForm.hidden = false;
  activeFilename.textContent = activeItem.title;
  mediaPlayer.src = `/api/media/${activeItem.id}/audio`;
}

function selectNext() {
  if (queue.length > 0) {
    selectItem(queue[0]);
    return;
  }
  activeItem = null;
  editorForm.hidden = true;
  emptyState.hidden = false;
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
    const imported = await WorkbenchApi.importMedia(formData);
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

async function saveAndNext() {
  if (!activeItem) return;
  const submitBtn = document.getElementById('save-next-btn');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Saving...';

  const qualityScore = parseOptionalScore(document.getElementById('quality-score').value);
  const fitScore = parseOptionalScore(document.getElementById('fit-score').value);
  const role = document.getElementById('role-select').value || 'REFERENCE';
  const notes = document.getElementById('notes-input').value.trim() || null;
  const categoryIds = WorkbenchTaxonomy.getSelectedCategoryIds();

  const payload = {
    mark_reviewed: true,
    categories: categoryIds.map((categoryId) => ({
      category_id: categoryId,
      quality_score: qualityScore,
      fit_score: fitScore,
      role,
      notes,
      reviewed: true,
    })),
    concepts: [],
  };

  try {
    await WorkbenchApi.saveAssignments(activeItem.id, payload);
    WorkbenchTaxonomy.rememberSavedCategories();
    queue = queue.filter((item) => item.id !== activeItem.id);
    renderQueue();
    selectNext();
  } catch (error) {
    console.error('Save failed', error);
    alert('Failed to save.');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Save + Next';
  }
}

init();
