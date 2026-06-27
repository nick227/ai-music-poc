window.WorkbenchTaxonomy = (() => {
  const DIMENSION_ORDER = [
    'GENRE', 'MOOD', 'INSTRUMENT', 'VOCALS', 'ENERGY', 'RHYTHM', 'TECHNIQUE',
    'PRODUCTION', 'MIX', 'ARRANGEMENT', 'QUALITY_ISSUE', 'TRAINING_ROLE',
  ];
  const DIMENSION_LABELS = {
    GENRE: 'Genre', MOOD: 'Mood', INSTRUMENT: 'Instrument', TECHNIQUE: 'Technique',
    PRODUCTION: 'Production', MIX: 'Mix', RHYTHM: 'Rhythm', VOCALS: 'Vocals',
    ARRANGEMENT: 'Arrangement', ENERGY: 'Energy', QUALITY_ISSUE: 'Quality Issue',
    TRAINING_ROLE: 'Training Role',
  };
  const RECENT_KEY = 'workbench_recent_categories';
  const RECENT_MAX = 6;
  const SUGGESTION_MAX = 6;

  let allCategories = [];
  let selectedCategoryIds = [];
  let activeTitle = '';
  let onChange = null;

  function dimensionLabel(value) {
    return DIMENSION_LABELS[value] || value;
  }

  function categoryById(id) {
    return allCategories.find((item) => item.id === id);
  }

  function categoryLabel(id) {
    const cat = categoryById(id);
    return cat ? `${dimensionLabel(cat.dimension)} / ${cat.name}` : id;
  }

  function loadRecent() {
    try {
      return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
    } catch {
      return [];
    }
  }

  function rememberRecent(categoryIds) {
    const merged = [...categoryIds, ...loadRecent()].filter((id, index, arr) => arr.indexOf(id) === index);
    localStorage.setItem(RECENT_KEY, JSON.stringify(merged.slice(0, RECENT_MAX)));
  }

  function tokenize(text) {
    return (text || '').toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length > 2);
  }

  function buildTitleSuggestions() {
    const scores = new Map();
    const recentIds = new Set(loadRecent());
    tokenize(activeTitle).forEach((token) => {
      allCategories.forEach((cat) => {
        const hay = `${cat.name} ${cat.slug} ${cat.dimension}`.toLowerCase();
        if (hay.includes(token)) scores.set(cat.id, (scores.get(cat.id) || 0) + 3);
      });
    });
    return [...scores.entries()]
      .filter(([id]) => !selectedCategoryIds.includes(id) && !recentIds.has(id))
      .sort((a, b) => b[1] - a[1])
      .slice(0, SUGGESTION_MAX)
      .map(([id]) => categoryById(id))
      .filter(Boolean);
  }

  function buildRecentItems() {
    return loadRecent()
      .filter((id) => categoryById(id) && !selectedCategoryIds.includes(id))
      .slice(0, RECENT_MAX)
      .map((id) => categoryById(id));
  }

  function toggleEmpty(id, hasItems) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('hidden', hasItems);
  }

  function renderSelectedChips() {
    const el = document.getElementById('cat-chips');
    if (!selectedCategoryIds.length) {
      el.innerHTML = '';
      toggleEmpty('cat-chips-empty', false);
      return;
    }
    toggleEmpty('cat-chips-empty', true);
    el.innerHTML = selectedCategoryIds.map((id) => `
      <span class="chip chip-selected">${categoryLabel(id)}
        <span class="remove" data-id="${id}">×</span>
      </span>
    `).join('');
    el.querySelectorAll('.remove').forEach((btn) => {
      btn.addEventListener('click', () => removeCategory(btn.dataset.id));
    });
  }

  function renderRecentChips() {
    const el = document.getElementById('cat-recent');
    if (!el) return;
    const items = buildRecentItems();
    toggleEmpty('cat-recent-empty', items.length > 0);
    if (!items.length) {
      el.innerHTML = '';
      return;
    }
    el.innerHTML = items.map((item) => `
      <button type="button" class="chip chip-recent" data-id="${item.id}">${dimensionLabel(item.dimension)} / ${item.name}</button>
    `).join('');
    el.querySelectorAll('.chip-recent').forEach((btn) => {
      btn.addEventListener('click', () => addCategory(btn.dataset.id));
    });
  }

  function renderSuggestionChips() {
    const el = document.getElementById('cat-suggestions');
    const items = buildTitleSuggestions();
    toggleEmpty('cat-suggestions-empty', items.length > 0);
    if (!items.length) {
      el.innerHTML = '';
      return;
    }
    el.innerHTML = items.map((item) => `
      <button type="button" class="chip chip-suggestion" data-id="${item.id}">${dimensionLabel(item.dimension)} / ${item.name}</button>
    `).join('');
    el.querySelectorAll('.chip-suggestion').forEach((btn) => {
      btn.addEventListener('click', () => addCategory(btn.dataset.id));
    });
  }

  function renderBrowse() {
    const browse = document.getElementById('cat-browse');
    const grouped = new Map();
    allCategories.forEach((cat) => {
      if (!grouped.has(cat.dimension)) grouped.set(cat.dimension, []);
      grouped.get(cat.dimension).push(cat);
    });
    browse.innerHTML = DIMENSION_ORDER.filter((d) => grouped.has(d)).map((dimension) => {
      const items = grouped.get(dimension).sort((a, b) => a.name.localeCompare(b.name));
      const chips = items.map((cat) => {
        const selected = selectedCategoryIds.includes(cat.id) ? ' chip-active' : '';
        return `<button type="button" class="chip chip-browse${selected}" data-id="${cat.id}">${cat.name}</button>`;
      }).join('');
      return `<details class="browse-dimension"><summary>${dimensionLabel(dimension)}</summary><div class="chips-container">${chips}</div></details>`;
    }).join('');
    browse.querySelectorAll('.chip-browse').forEach((btn) => {
      btn.addEventListener('click', () => toggleCategory(btn.dataset.id));
    });
  }

  function toggleCategory(id) {
    if (selectedCategoryIds.includes(id)) removeCategory(id);
    else addCategory(id);
  }

  function addCategory(id) {
    if (!selectedCategoryIds.includes(id)) {
      selectedCategoryIds.push(id);
      rememberRecent([id]);
      refresh();
    }
  }

  function removeCategory(id) {
    selectedCategoryIds = selectedCategoryIds.filter((x) => x !== id);
    refresh();
  }

  function refresh() {
    renderSelectedChips();
    renderRecentChips();
    renderSuggestionChips();
    renderBrowse();
    if (onChange) onChange();
  }

  function filterCategories(query) {
    const q = query.toLowerCase();
    return allCategories.filter((cat) => {
      const hay = `${cat.name} ${cat.slug} ${cat.dimension} ${dimensionLabel(cat.dimension)}`.toLowerCase();
      return hay.includes(q);
    }).slice(0, 10);
  }

  async function onCreateSubmit(name, dimension) {
    const created = await window.WorkbenchApi.createCategory(name, dimension);
    allCategories.push(created);
    addCategory(created.id);
    document.getElementById('cat-search').value = '';
    document.getElementById('cat-results').classList.add('hidden');
  }

  function setupCategorySearch() {
    const input = document.getElementById('cat-search');
    const results = document.getElementById('cat-results');
    let timeout = null;
    input.addEventListener('input', () => {
      clearTimeout(timeout);
      const query = input.value.trim();
      timeout = setTimeout(() => {
        if (!query) {
          results.classList.add('hidden');
          return;
        }
        const matches = filterCategories(query);
        if (matches.length) {
          results.innerHTML = matches.map((item) => `
            <div class="search-result-item" data-id="${item.id}">${dimensionLabel(item.dimension)} / ${item.name}</div>
          `).join('');
          results.querySelectorAll('.search-result-item').forEach((el) => {
            el.addEventListener('click', () => {
              addCategory(el.dataset.id);
              input.value = '';
              results.classList.add('hidden');
            });
          });
        } else {
          const options = DIMENSION_ORDER.map((d) => `<option value="${d}">${dimensionLabel(d)}</option>`).join('');
          results.innerHTML = `<div class="search-result-item search-create">
            <span>${query}</span>
            <select id="inline-cat-dimension">${options}</select>
            <button type="button" class="ghost small" data-action="create-category" data-name="${query.replace(/"/g, '')}">Create</button>
          </div>`;
          results.querySelector('[data-action="create-category"]')?.addEventListener('click', (e) => {
            const dim = document.getElementById('inline-cat-dimension')?.value || 'GENRE';
            onCreateSubmit(e.target.dataset.name, dim);
          });
        }
        results.classList.remove('hidden');
      }, 200);
    });
    document.addEventListener('click', (e) => {
      if (!input.contains(e.target) && !results.contains(e.target)) results.classList.add('hidden');
    });
  }

  return {
    async loadTaxonomy() {
      const catRes = await window.WorkbenchApi.listCategories();
      allCategories = catRes.categories || [];
    },
    setSelectionFromMedia(media) {
      activeTitle = media?.title || '';
      selectedCategoryIds = (media.category_assignments || []).map((a) => a.category_id);
      refresh();
    },
    getSelectedCategoryIds: () => [...selectedCategoryIds],
    rememberSavedCategories() {
      rememberRecent(selectedCategoryIds);
    },
    init(changeHandler) {
      onChange = changeHandler || null;
      setupCategorySearch();
      refresh();
    },
  };
})();
