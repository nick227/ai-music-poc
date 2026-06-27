const CATEGORY_DIMENSIONS = [
  'GENRE',
  'MOOD',
  'INSTRUMENT',
  'TECHNIQUE',
  'PRODUCTION',
  'MIX',
  'RHYTHM',
  'VOCALS',
  'ARRANGEMENT',
  'ENERGY',
  'QUALITY_ISSUE',
  'TRAINING_ROLE',
];

const DIMENSION_ALIASES = new Map(
  CATEGORY_DIMENSIONS.flatMap((dimension) => {
    const label = formatDimension(dimension);
    return [
      [dimension, dimension],
      [dimension.toLowerCase(), dimension],
      [label.toLowerCase(), dimension],
    ];
  })
);

let categories = [];

function formatDimension(value) {
  return value.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fillDimensionSelect(select, { includeAll = false } = {}) {
  select.innerHTML = [
    includeAll ? '<option value="">All dimensions</option>' : '',
    ...CATEGORY_DIMENSIONS.map((dimension) => `<option value="${dimension}">${formatDimension(dimension)}</option>`),
  ].join('');
}

function filteredCategories() {
  const query = document.getElementById('category-search').value.trim().toLowerCase();
  const dimension = document.getElementById('dimension-filter').value;
  return categories.filter((category) => {
    if (dimension && category.dimension !== dimension) return false;
    if (!query) return true;
    const haystack = `${category.name} ${category.slug} ${category.description || ''}`.toLowerCase();
    return haystack.includes(query);
  });
}

function renderCategories() {
  const rows = filteredCategories();
  document.getElementById('category-count').textContent = `${rows.length} categories`;
  const tbody = document.getElementById('category-rows');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="table-meta">No categories</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map((category) => `
    <tr>
      <td class="table-title">${escapeHtml(category.name)}</td>
      <td><span class="dimension-pill">${formatDimension(category.dimension)}</span></td>
      <td class="table-meta">${escapeHtml(category.slug)}</td>
      <td class="table-meta description-cell" title="${escapeHtml(category.description || '')}">${escapeHtml(category.description || '—')}</td>
      <td class="table-actions">
        <button type="button" class="ghost small danger" data-delete="${escapeHtml(category.id)}">Delete</button>
      </td>
    </tr>
  `).join('');

  tbody.querySelectorAll('[data-delete]').forEach((button) => {
    button.addEventListener('click', () => deleteCategory(button.dataset.delete));
  });
}

async function loadCategories() {
  categories = (await StudioApi.listCategories()).categories || [];
  renderCategories();
}

function setFeedback(message, isError = false) {
  const el = document.getElementById('category-feedback');
  el.hidden = false;
  el.classList.remove('saving', 'saved', 'error');
  el.classList.add(isError ? 'error' : 'saved');
  el.textContent = message;
}

async function createSingleCategory() {
  const name = document.getElementById('single-name').value.trim();
  const dimension = document.getElementById('single-dimension').value;
  const description = document.getElementById('single-description').value.trim();
  if (!name) {
    const el = document.getElementById('single-feedback');
    el.hidden = false;
    el.classList.remove('saving', 'saved');
    el.classList.add('error');
    el.textContent = 'Name is required.';
    return;
  }
  const button = document.getElementById('single-create');
  await StudioSave.run(
    button,
    async () => {
      await StudioApi.createCategory(name, dimension, description);
      document.getElementById('single-name').value = '';
      document.getElementById('single-description').value = '';
      await loadCategories();
    },
    {
      savingLabel: 'Adding…',
      successMessage: `Added ${name}.`,
      feedbackEl: 'single-feedback',
    },
  );
}

function parseBulkCategories() {
  const defaultDimension = document.getElementById('bulk-dimension').value;
  const lines = document.getElementById('bulk-text').value.split(/\r?\n/);
  return lines
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^([^:]+):\s*(.+)$/);
      if (!match) return { name: line, dimension: defaultDimension };
      const candidate = match[1].trim();
      const dimension = DIMENSION_ALIASES.get(candidate) || DIMENSION_ALIASES.get(candidate.toLowerCase());
      if (!dimension) return { name: line, dimension: defaultDimension };
      return { name: match[2].trim(), dimension };
    })
    .filter((item) => item.name);
}

async function createBulkCategories() {
  const items = parseBulkCategories();
  if (!items.length) {
    setFeedback('Add at least one category line.', true);
    return;
  }
  const button = document.getElementById('bulk-create');
  await StudioSave.run(
    button,
    async () => {
      const response = await StudioApi.bulkCreateCategories(items);
      document.getElementById('bulk-text').value = '';
      await loadCategories();
      return response;
    },
    {
      savingLabel: 'Adding categories…',
      successMessage: (response) => `Added ${response.categories.length} categor${response.categories.length === 1 ? 'y' : 'ies'}.`,
      feedbackEl: 'category-feedback',
    },
  );
}

async function deleteCategory(id) {
  const category = categories.find((item) => item.id === id);
  if (!category) return;
  if (!confirm(`Delete ${category.name}?`)) return;
  await StudioApi.deleteCategory(id);
  setFeedback(`Deleted ${category.name}.`);
  await loadCategories();
}

function boot() {
  fillDimensionSelect(document.getElementById('dimension-filter'), { includeAll: true });
  fillDimensionSelect(document.getElementById('single-dimension'));
  fillDimensionSelect(document.getElementById('bulk-dimension'));
  document.getElementById('category-search').addEventListener('input', renderCategories);
  document.getElementById('dimension-filter').addEventListener('change', renderCategories);
  document.getElementById('single-create').addEventListener('click', () => createSingleCategory().catch(() => {}));
  document.getElementById('bulk-create').addEventListener('click', () => createBulkCategories().catch(() => {}));
  loadCategories().catch((error) => setFeedback(error.message, true));
}

boot();
