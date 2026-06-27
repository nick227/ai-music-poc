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
  return new Date(value).toLocaleString();
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
  StudioNav.render('media');
  allRows = await StudioApi.listMedia({ limit: 200 });
  render();
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
    tbody.innerHTML = '<tr><td colspan="9" class="table-meta">No media</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map((row) => {
    const count = row.category_assignment_count ?? 0;
    const countClass = count > 0 ? 'count-pill has-value' : 'count-pill';
    const reviewClass = row.review_status === 'NEEDS_REVIEW' ? 'status-pill needs-review' : 'status-pill reviewed';
    return `
      <tr data-id="${row.id}">
        <td><button type="button" class="ghost small play-btn" data-id="${row.id}">▶</button></td>
        <td class="table-title"><a href="/media-detail.html?id=${row.id}">${row.title}</a></td>
        <td>${formatDuration(row.duration_seconds)}</td>
        <td><span class="${countClass}">${count}</span></td>
        <td class="table-meta">${roleLabel(row)}</td>
        <td><span class="${reviewClass}">${row.review_status.replace(/_/g, ' ').toLowerCase()}</span></td>
        <td class="table-meta">${row.kind.replace(/_/g, ' ').toLowerCase()}</td>
        <td class="table-meta">${formatDate(row.created_at)}</td>
        <td class="table-actions">
          <a class="button ghost small" href="/media-detail.html?id=${row.id}">Open</a>
          <a class="button ghost small" href="/workbench.html?media_id=${row.id}">Workbench</a>
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
  const files = e.target.files;
  if (!files?.length) return;
  const formData = new FormData();
  for (const file of files) formData.append('files', file);
  await StudioApi.importMedia(formData);
  e.target.value = '';
  allRows = await StudioApi.listMedia({ limit: 200 });
  render();
});

load();
