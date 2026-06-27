let allRows = [];

function formatDuration(seconds) {
  if (seconds == null) return '—';
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatDate(value) {
  if (!value) return '—';
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function roleLabel(item) {
  if (item.primary_role) return item.primary_role.replace(/_/g, ' ').toLowerCase();
  const assignments = item.category_assignments || [];
  if (assignments.length && assignments[0].role) {
    return assignments[0].role.replace(/_/g, ' ').toLowerCase();
  }
  return '—';
}

async function load() {
  allRows = await StudioApi.listMedia({ limit: 200 });
  render();
  setupDropzone();
}

function filteredRows() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const review = document.getElementById('filter-review').value;
  const kind = document.getElementById('filter-kind').value;
  return allRows.filter((row) => {
    if (review && row.review_status !== review) return false;
    if (kind && row.kind !== kind) return false;
    if (q && !row.title.toLowerCase().includes(q)) return false;
    return true;
  });
}

function render() {
  const rows = filteredRows();
  document.getElementById('table-count').textContent = `${rows.length} items`;
  const tbody = document.getElementById('media-rows');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="2" class="table-meta">No media</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map((row) => {
    const count = row.category_assignment_count ?? 0;
    const reviewLabel = row.review_status.replace(/_/g, ' ').toLowerCase();
    const ingestion = (row.ingestion_status || 'pending').replace(/_/g, ' ').toLowerCase();
    const meta = [
      formatDuration(row.duration_seconds),
      `${count} tag${count === 1 ? '' : 's'}`,
      ingestion,
      reviewLabel,
      formatDate(row.created_at),
    ].join(' · ');
    return `
      <tr data-id="${row.id}">
        <td>
          <div class="media-row-main">
            <button type="button" class="ghost small play-btn" data-id="${row.id}" aria-label="Play">▶</button>
            <a class="media-row-title" href="${StudioRoutes.mediaDetail(row.id)}">${row.title}</a>
          </div>
          <div class="media-row-meta">${meta}</div>
        </td>
        <td class="media-row-actions">
          <a class="button ghost small" href="${StudioRoutes.mediaDetail(row.id)}">Open</a>
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.play-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      playRow(btn.dataset.id);
    });
  });
}

let activeAudio = null;

function playRow(id) {
  if (activeAudio) {
    activeAudio.pause();
    activeAudio = null;
  }
  activeAudio = new Audio(`/api/media/${id}/audio`);
  activeAudio.play();
}

document.getElementById('search').addEventListener('input', render);
document.getElementById('filter-review').addEventListener('change', render);
document.getElementById('filter-kind').addEventListener('change', render);

document.getElementById('import-btn').addEventListener('click', () => {
  document.getElementById('import-files').click();
});

document.getElementById('import-files').addEventListener('change', async (e) => {
  await importFiles(e.target.files);
  e.target.value = '';
});

async function importFiles(files) {
  if (!files?.length) return;
  const formData = new FormData();
  for (const file of files) formData.append('files', file);
  await StudioApi.importMedia(formData);
  allRows = await StudioApi.listMedia({ limit: 200 });
  render();
}

function setupDropzone() {
  const zone = document.getElementById('dropzone');
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach((name) => {
    zone.addEventListener(name, (e) => { e.preventDefault(); e.stopPropagation(); });
  });
  ['dragenter', 'dragover'].forEach((name) => zone.addEventListener(name, () => zone.classList.add('dragover')));
  ['dragleave', 'drop'].forEach((name) => zone.addEventListener(name, () => zone.classList.remove('dragover')));
  zone.addEventListener('drop', (e) => importFiles(e.dataTransfer.files));
}

load();
