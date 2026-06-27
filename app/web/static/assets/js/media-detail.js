let mediaId = null;
let media = null;

function queryId() {
  return new URLSearchParams(window.location.search).get('id');
}

function parseOptionalScore(value) {
  if (value === '' || value == null) return null;
  const parsed = parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

function buildPayload(markReviewed) {
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

function formatReviewStatus(value) {
  return (value || '').replace(/_/g, ' ').toLowerCase();
}

function renderMeta() {
  const list = document.getElementById('meta-list');
  const rows = [
    ['Review', formatReviewStatus(media.review_status)],
    ['Duration', media.duration_seconds != null ? `${Math.round(media.duration_seconds)}s` : '—'],
    ['Tags', media.category_assignment_count ?? media.category_assignments?.length ?? 0],
    ['Kind', (media.kind || '').replace(/_/g, ' ').toLowerCase()],
    ['Added', new Date(media.created_at).toLocaleString()],
  ];
  list.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}

function setPipelineLinks() {
  document.getElementById('workbench-link').href = StudioRoutes.workbench;
  document.getElementById('generate-link').href = StudioRoutes.generateWithContext(mediaId);
}

async function load() {
  mediaId = queryId();
  if (!mediaId) {
    window.location.href = StudioRoutes.media;
    return;
  }
  await WorkbenchTaxonomy.loadTaxonomy();
  WorkbenchTaxonomy.init();
  media = await StudioApi.getMedia(mediaId);

  document.getElementById('page-title').textContent = media.title;
  document.title = `${media.title} - Media`;
  document.getElementById('media-player').src = `/api/media/${mediaId}/audio`;

  const first = media.category_assignments?.[0] || {};
  document.getElementById('quality-score').value = first.quality_score ?? '';
  document.getElementById('fit-score').value = first.fit_score ?? '';
  document.getElementById('role-select').value = first.role || media.primary_role || 'REFERENCE';
  document.getElementById('notes-input').value = first.notes || '';

  WorkbenchTaxonomy.setSelectionFromMedia(media);
  renderMeta();
  setPipelineLinks();
}

document.getElementById('editor-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  media = await StudioApi.saveAssignments(mediaId, buildPayload(false));
  WorkbenchTaxonomy.rememberSavedCategories();
  WorkbenchTaxonomy.setSelectionFromMedia(media);
  renderMeta();
});

document.getElementById('done-btn').addEventListener('click', async () => {
  media = await StudioApi.saveAssignments(mediaId, buildPayload(true));
  window.location.href = StudioRoutes.media;
});

load();
