let mediaId = null;
let media = null;

function queryId() {
  return new URLSearchParams(window.location.search).get('id');
}

function buildPayload() {
  const notes = document.getElementById('notes-input').value.trim() || null;
  const categoryIds = WorkbenchTaxonomy.getSelectedCategoryIds();
  return {
    mark_reviewed: true,
    categories: categoryIds.map((categoryId) => ({
      category_id: categoryId,
      quality_score: null,
      fit_score: null,
      role: 'REFERENCE',
      notes,
      reviewed: true,
    })),
    concepts: [],
  };
}

function formatReviewStatus(value) {
  return (value || '').replace(/_/g, ' ').toLowerCase();
}

function renderMeta() {
  const list = document.getElementById('meta-list');
  const count = media.category_assignment_count ?? media.category_assignments?.length ?? 0;
  const rows = [
    ['Review', formatReviewStatus(media.review_status)],
    ['Duration', media.duration_seconds != null ? `${Math.round(media.duration_seconds)}s` : '—'],
    ['Categories', count],
    ['Kind', (media.kind || '').replace(/_/g, ' ').toLowerCase()],
    ['Added', new Date(media.created_at).toLocaleString()],
  ];
  list.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
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
  document.getElementById('notes-input').value = first.notes || '';

  WorkbenchTaxonomy.setSelectionFromMedia(media);
  renderMeta();
}

document.getElementById('editor-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const button = document.getElementById('save-categories-btn');
  const count = WorkbenchTaxonomy.getSelectedCategoryIds().length;
  await StudioSave.run(
    button,
    async () => {
      media = await StudioApi.saveAssignments(mediaId, buildPayload());
      WorkbenchTaxonomy.rememberSavedCategories();
      WorkbenchTaxonomy.setSelectionFromMedia(media);
      renderMeta();
      return media;
    },
    {
      savingLabel: 'Saving categories…',
      successMessage: count
        ? `Saved ${count} categor${count === 1 ? 'y' : 'ies'}.`
        : 'Saved — no categories selected.',
      feedbackEl: 'save-feedback',
    },
  );
});

load();
