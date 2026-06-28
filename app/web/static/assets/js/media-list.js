let allRows = [];
let allCategories = [];
let selectedIds = new Set();

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
  const [mediaRes, catRes] = await Promise.all([
    StudioApi.listMedia({ limit: 200 }),
    StudioApi.listCategories()
  ]);
  allRows = mediaRes;
  allCategories = catRes.categories || [];
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

function trainingStatus(row) {
  return StudioTrainingStatus.mediaLabel(row);
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
    const training = trainingStatus(row);
    
    const chipsHtml = (row.category_assignments || [])
      .map(a => {
        const name = a.category ? a.category.name : (a.category_id || '').replace('cat_', '');
        return `<span class="chip" style="font-size: 10px; padding: 2px 6px; line-height: 1; border-color: rgba(255,255,255,0.1); background: rgba(255,255,255,0.05); color: #d4d4d8;">${name}</span>`;
      }).join('');

    const reviewStatusMap = { 'NEEDS_REVIEW': 'Needs review', 'REVIEWED': 'Reviewed', 'REJECTED': 'Rejected' };
    const reviewStatus = reviewStatusMap[row.review_status] || '';
    const kindLabel = row.kind === 'GENERATED_SONG' ? 'Generated' : (row.kind === 'UPLOAD' ? 'Upload' : '');

    const meta = [
      formatDuration(row.duration_seconds),
      training,
      reviewStatus,
      kindLabel,
      formatDate(row.created_at),
    ].filter(val => val && val !== '—').join(' · ');
    
    const editBtnHtml = `<button type="button" class="ghost small edit-cats-btn" data-id="${row.id}" style="padding: 2px 6px; font-size: 10px;" aria-label="Edit Categories">✏️</button>`;

    return `
      <tr data-id="${row.id}" class="${selectedIds.has(row.id) ? 'selected' : ''}">
        <td style="text-align: center;">
          <input type="checkbox" class="row-select" data-id="${row.id}" ${selectedIds.has(row.id) ? 'checked' : ''} />
        </td>
        <td>
          <div class="media-row-main">
            <button type="button" class="ghost small play-btn" data-id="${row.id}" aria-label="Play">▶</button>
            <a class="media-row-title" href="${StudioRoutes.mediaDetail(row.id)}">${row.title}</a>
          </div>
          <div class="media-row-meta" style="display: flex; align-items: center; gap: 8px;">
            <span>${meta}</span>
            <div style="display: flex; gap: 4px; flex-wrap: wrap;">${chipsHtml}${editBtnHtml}</div>
          </div>
        </td>
        <td class="media-row-actions">
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

  tbody.querySelectorAll('.row-select').forEach(cb => {
    cb.addEventListener('change', (e) => {
      const id = e.target.dataset.id;
      if (e.target.checked) selectedIds.add(id);
      else selectedIds.delete(id);
      render();
    });
  });

  tbody.querySelectorAll('.edit-cats-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      openCategoryPicker(new Set([btn.dataset.id]));
    });
  });

  updateBulkToolbar();

  if (typeof updatePlayButtons === 'function') updatePlayButtons();
}

let activeAudio = null;
let activeAudioId = null;

function updatePlayButtons() {
  document.querySelectorAll('.play-btn').forEach((b) => {
    if (activeAudioId === b.dataset.id && activeAudio && !activeAudio.paused) {
      b.textContent = '⏸';
      b.setAttribute('aria-label', 'Pause');
    } else {
      b.textContent = '▶';
      b.setAttribute('aria-label', 'Play');
    }
  });
}

function playRow(id) {
  if (activeAudioId === id && activeAudio) {
    if (activeAudio.paused) {
      activeAudio.play();
    } else {
      activeAudio.pause();
    }
    return;
  }

  if (activeAudio) {
    activeAudio.pause();
  }
  
  activeAudioId = id;
  activeAudio = new Audio(`/api/media/${id}/audio`);
  activeAudio.addEventListener('play', updatePlayButtons);
  activeAudio.addEventListener('pause', updatePlayButtons);
  activeAudio.addEventListener('ended', () => {
    activeAudioId = null;
    updatePlayButtons();
  });
  activeAudio.play();
}

document.getElementById('search').addEventListener('input', render);
document.getElementById('filter-review').addEventListener('change', render);
document.getElementById('filter-kind').addEventListener('change', render);

function updateBulkToolbar() {
  const bulkBar = document.getElementById('bulk-action-bar');
  const countEl = document.getElementById('bulk-count');
  const selectAll = document.getElementById('bulk-select-all');
  
  if (selectedIds.size > 0) {
    bulkBar.hidden = false;
    countEl.textContent = `${selectedIds.size} item${selectedIds.size > 1 ? 's' : ''} selected`;
  } else {
    bulkBar.hidden = true;
  }
  
  const rows = filteredRows();
  if (rows.length && selectedIds.size === rows.length) {
    selectAll.checked = true;
    selectAll.indeterminate = false;
  } else if (selectedIds.size > 0) {
    selectAll.checked = false;
    selectAll.indeterminate = true;
  } else {
    selectAll.checked = false;
    selectAll.indeterminate = false;
  }
}

document.getElementById('bulk-select-all').addEventListener('change', (e) => {
  const rows = filteredRows();
  if (e.target.checked) {
    rows.forEach(r => selectedIds.add(r.id));
  } else {
    rows.forEach(r => selectedIds.delete(r.id));
  }
  render();
});

document.getElementById('bulk-clear-btn').addEventListener('click', () => {
  selectedIds.clear();
  render();
});

document.getElementById('bulk-assign-btn').addEventListener('click', () => {
  openCategoryPicker(selectedIds);
});

let targetMediaIds = new Set();
let selectedCategoryIds = new Set();

function openCategoryPicker(mediaIds) {
  targetMediaIds = new Set(mediaIds);
  selectedCategoryIds = new Set();
  
  if (targetMediaIds.size === 1) {
    const id = Array.from(targetMediaIds)[0];
    const media = allRows.find(r => r.id === id);
    if (media && media.category_assignments) {
      media.category_assignments.forEach(a => selectedCategoryIds.add(a.category_id));
    }
  }

  renderCategoryGrid();
  document.getElementById('category-picker-modal').showModal();
}

function renderCategoryGrid() {
  const q = document.getElementById('category-search').value.trim().toLowerCase();
  const grid = document.getElementById('category-grid');
  const selectedSection = document.getElementById('category-selected-section');
  
  if (selectedCategoryIds.size === 0) {
    selectedSection.innerHTML = '<span class="muted" style="font-size: 13px; margin: auto;">No categories selected</span>';
  } else {
    selectedSection.innerHTML = Array.from(selectedCategoryIds).map(id => {
      const c = allCategories.find(cat => cat.id === id);
      const name = c ? c.name : id;
      return `<button type="button" class="chip selected-chip" data-id="${id}" style="padding: 4px 10px; font-size: 12px; border-radius: 16px; border: 1px solid var(--primary); background: rgba(139, 92, 246, 0.15); color: #fafafa; cursor: pointer; display: flex; align-items: center; gap: 6px;">${name} <span style="opacity: 0.5; font-size: 10px;">✕</span></button>`;
    }).join('');
  }

  selectedSection.querySelectorAll('.selected-chip').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      selectedCategoryIds.delete(btn.dataset.id);
      renderCategoryGrid();
    });
  });
  
  const dims = {};
  allCategories.forEach(c => {
    if (q && !c.name.toLowerCase().includes(q)) return;
    const d = c.dimension || 'uncategorized';
    if (!dims[d]) dims[d] = [];
    dims[d].push(c);
  });
  
  grid.innerHTML = Object.keys(dims).sort().map(dim => {
    const title = dim.charAt(0).toUpperCase() + dim.slice(1);
    const chips = dims[dim].map(c => {
      const active = selectedCategoryIds.has(c.id);
      return `<button type="button" class="chip grid-chip ${active ? 'active' : ''}" data-id="${c.id}" style="padding: 4px 12px; font-size: 13px; border-radius: 16px; border: 1px solid ${active ? 'var(--primary)' : 'rgba(255,255,255,0.1)'}; background: ${active ? 'var(--primary)' : 'rgba(255,255,255,0.05)'}; cursor: pointer; color: ${active ? '#ffffff' : '#d4d4d8'}; transition: all 0.2s;">${c.name}</button>`;
    }).join('');
    return `<div><h3 style="font-size: 13px; margin-bottom: 10px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">${title}</h3><div style="display: flex; flex-wrap: wrap; gap: 8px;">${chips}</div></div>`;
  }).join('');
  
  grid.querySelectorAll('.grid-chip').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      if (selectedCategoryIds.has(id)) selectedCategoryIds.delete(id);
      else selectedCategoryIds.add(id);
      renderCategoryGrid();
    });
  });
}

document.getElementById('category-search').addEventListener('input', renderCategoryGrid);

document.getElementById('close-category-picker').addEventListener('click', () => {
  document.getElementById('category-picker-modal').close();
});

document.getElementById('apply-categories-btn').addEventListener('click', async () => {
  const btn = document.getElementById('apply-categories-btn');
  const status = document.getElementById('category-picker-status');
  btn.disabled = true;
  status.hidden = false;
  
  const payload = { category_assignments: Array.from(selectedCategoryIds).map(id => ({ category_id: id })) };
  
  for (const mediaId of targetMediaIds) {
    try {
      await StudioApi.saveAssignments(mediaId, payload);
    } catch (e) {
      console.error('Failed to save assignments for', mediaId, e);
    }
  }
  
  selectedIds.clear();
  document.getElementById('category-picker-modal').close();
  btn.disabled = false;
  status.hidden = true;
  
  allRows = await StudioApi.listMedia({ limit: 200 });
  render();
});

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
