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

  let allCategories = [];
  let allConcepts = [];
  let selectedCategoryIds = [];
  let selectedConceptIds = [];
  let activeTitle = '';
  let onChange = () => {};

  function dimensionLabel(value) {
    return DIMENSION_LABELS[value] || value;
  }

  function categoryById(id) {
    return allCategories.find((item) => item.id === id);
  }

  function conceptById(id) {
    return allConcepts.find((item) => item.id === id);
  }

  function categoryLabel(id) {
    const cat = categoryById(id);
    return cat ? `${dimensionLabel(cat.dimension)} / ${cat.name}` : id;
  }

  function conceptLabel(id) {
    return conceptById(id)?.name || id;
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
    localStorage.setItem(RECENT_KEY, JSON.stringify(merged.slice(0, 12)));
  }

  function tokenize(text) {
    return (text || '').toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length > 2);
  }

  function buildCategorySuggestions() {
    const scores = new Map();
    selectedConceptIds.forEach((conceptId) => {
      conceptById(conceptId)?.category_ids?.forEach((catId) => {
        scores.set(catId, (scores.get(catId) || 0) + 4);
      });
    });
    tokenize(activeTitle).forEach((token) => {
      allCategories.forEach((cat) => {
        const hay = `${cat.name} ${cat.slug} ${cat.dimension}`.toLowerCase();
        if (hay.includes(token)) scores.set(cat.id, (scores.get(cat.id) || 0) + 3);
      });
    });
    loadRecent().forEach((catId) => {
      if (categoryById(catId)) scores.set(catId, (scores.get(catId) || 0) + 1);
    });
    return [...scores.entries()]
      .filter(([id]) => !selectedCategoryIds.includes(id))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([id]) => categoryById(id))
      .filter(Boolean);
  }

  function buildConceptSuggestions() {
    const scores = new Map();
    selectedCategoryIds.forEach((catId) => {
      allConcepts.forEach((concept) => {
        if (concept.category_ids?.includes(catId)) {
          scores.set(concept.id, (scores.get(concept.id) || 0) + 2);
        }
      });
    });
    tokenize(activeTitle).forEach((token) => {
      allConcepts.forEach((concept) => {
        if (concept.name.toLowerCase().includes(token) || concept.slug?.includes(token)) {
          scores.set(concept.id, (scores.get(concept.id) || 0) + 2);
        }
      });
    });
    return [...scores.entries()]
      .filter(([id]) => !selectedConceptIds.includes(id))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([id]) => conceptById(id))
      .filter(Boolean);
  }

  function renderSelectedChips(containerId, ids, labelFn, removeFn) {
    const el = document.getElementById(containerId);
    if (!ids.length) {
      el.innerHTML = '<span class="muted small">None selected — browse or tap suggestions below.</span>';
      return;
    }
    el.innerHTML = ids.map((id) => `
      <span class="chip chip-selected">${labelFn(id)}
        <span class="remove" data-id="${id}">×</span>
      </span>
    `).join('');
    el.querySelectorAll('.remove').forEach((btn) => {
      btn.addEventListener('click', () => removeFn(btn.dataset.id));
    });
  }

  function renderSuggestionChips(containerId, items, onPick) {
    const el = document.getElementById(containerId);
    if (!items.length) {
      el.innerHTML = '<span class="muted small">Suggestions appear from filename, concepts, and recent picks.</span>';
      return;
    }
    el.innerHTML = items.map((item) => `
      <button type="button" class="chip chip-suggestion" data-id="${item.id}">${item.dimension ? dimensionLabel(item.dimension) + ' / ' + item.name : item.name}</button>
    `).join('');
    el.querySelectorAll('.chip-suggestion').forEach((btn) => {
      btn.addEventListener('click', () => onPick(btn.dataset.id));
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
      return `<details class="browse-dimension" open><summary>${dimensionLabel(dimension)}</summary><div class="chips-container">${chips}</div></details>`;
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
      onChange();
    }
  }

  function removeCategory(id) {
    selectedCategoryIds = selectedCategoryIds.filter((x) => x !== id);
    refresh();
    onChange();
  }

  function addConcept(id) {
    if (!selectedConceptIds.includes(id)) {
      selectedConceptIds.push(id);
      refresh();
      onChange();
    }
  }

  function removeConcept(id) {
    selectedConceptIds = selectedConceptIds.filter((x) => x !== id);
    refresh();
    onChange();
  }

  function refresh() {
    renderSelectedChips('cat-chips', selectedCategoryIds, categoryLabel, removeCategory);
    renderSelectedChips('con-chips', selectedConceptIds, conceptLabel, removeConcept);
    renderSuggestionChips('cat-suggestions', buildCategorySuggestions(), addCategory);
    renderSuggestionChips('con-suggestions', buildConceptSuggestions(), (id) => addConcept(id));
    renderBrowse();
  }

  function filterCategories(query) {
    const q = query.toLowerCase();
    return allCategories.filter((cat) => {
      const hay = `${cat.name} ${cat.slug} ${cat.dimension} ${dimensionLabel(cat.dimension)}`.toLowerCase();
      return hay.includes(q);
    }).slice(0, 12);
  }

  function filterConcepts(query) {
    const q = query.toLowerCase();
    return allConcepts.filter((concept) => `${concept.name} ${concept.slug}`.toLowerCase().includes(q)).slice(0, 12);
  }

  function renderSearchResults(resultsEl, items, labelFn, onSelect, emptyQuery, onCreate) {
    if (!emptyQuery) {
      resultsEl.classList.add('hidden');
      return;
    }
    let html = items.map((item) => `
      <div class="search-result-item" data-id="${item.id}">${labelFn(item)}</div>
    `).join('');
    if (!items.length && onCreate) {
      html = onCreate(emptyQuery);
    }
    resultsEl.innerHTML = html;
    resultsEl.classList.remove('hidden');
    resultsEl.querySelectorAll('.search-result-item:not(.search-create)').forEach((el) => {
      el.addEventListener('click', () => onSelect(el.dataset.id));
    });
  }

  async function onCreateSubmit(name, dimension) {
    const created = await window.WorkbenchApi.createCategory(name, dimension);
    allCategories.push(created);
    addCategory(created.id);
    document.getElementById('cat-search').value = '';
    document.getElementById('cat-results').classList.add('hidden');
  }

  async function onConceptCreateSubmit(name) {
    if (!selectedCategoryIds.length) {
      alert('Select at least one category before creating a concept.');
      return;
    }
    const created = await window.WorkbenchApi.createConcept(name, selectedCategoryIds);
    allConcepts.push(created);
    addConcept(created.id);
    document.getElementById('con-search').value = '';
    document.getElementById('con-results').classList.add('hidden');
  }

  function setupCategorySearch() {
    const input = document.getElementById('cat-search');
    const results = document.getElementById('cat-results');
    let timeout = null;
    input.addEventListener('input', () => {
      clearTimeout(timeout);
      const query = input.value.trim();
      timeout = setTimeout(() => {
        const matches = filterCategories(query);
        renderSearchResults(
          results,
          matches,
          (item) => `${dimensionLabel(item.dimension)} / ${item.name}`,
          (id) => { addCategory(id); input.value = ''; results.classList.add('hidden'); },
          query,
          (q) => {
            const options = DIMENSION_ORDER.map((d) => `<option value="${d}">${dimensionLabel(d)}</option>`).join('');
            return `<div class="search-result-item search-create">
              Create "<strong>${q}</strong>" in
              <select id="inline-cat-dimension">${options}</select>
              <button type="button" class="ghost small" data-action="create-category" data-name="${q.replace(/"/g, '')}">Create</button>
            </div>`;
          },
        );
        results.querySelectorAll('[data-action="create-category"]').forEach((btn) => {
          btn.addEventListener('click', () => {
            const dim = document.getElementById('inline-cat-dimension')?.value || 'GENRE';
            onCreateSubmit(btn.dataset.name, dim);
          });
        });
      }, 200);
    });
    document.addEventListener('click', (e) => {
      if (!input.contains(e.target) && !results.contains(e.target)) results.classList.add('hidden');
    });
  }

  function setupConceptSearch() {
    const input = document.getElementById('con-search');
    const results = document.getElementById('con-results');
    let timeout = null;
    input.addEventListener('input', () => {
      clearTimeout(timeout);
      const query = input.value.trim();
      timeout = setTimeout(() => {
        const matches = filterConcepts(query);
        renderSearchResults(
          results,
          matches,
          (item) => item.name,
          (id) => { addConcept(id); input.value = ''; results.classList.add('hidden'); },
          query,
          (q) => `<div class="search-result-item search-create">
            Create concept "<strong>${q}</strong>" (uses selected categories)
            <button type="button" class="ghost small" data-action="create-concept" data-name="${q.replace(/"/g, '')}">Create</button>
          </div>`,
        );
        results.querySelectorAll('[data-action="create-concept"]').forEach((btn) => {
          btn.addEventListener('click', () => onConceptCreateSubmit(btn.dataset.name));
        });
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
      const conRes = await window.WorkbenchApi.listConcepts();
      allConcepts = conRes.concepts || [];
    },
    setSelectionFromMedia(media) {
      activeTitle = media?.title || '';
      selectedCategoryIds = (media.category_assignments || []).map((a) => a.category_id);
      selectedConceptIds = (media.concept_assignments || []).map((a) => a.concept_id);
      refresh();
    },
    setActiveTitle(title) {
      activeTitle = title || '';
      refresh();
    },
    getSelectedCategoryIds: () => [...selectedCategoryIds],
    getSelectedConceptIds: () => [...selectedConceptIds],
    rememberSavedCategories() {
      rememberRecent(selectedCategoryIds);
    },
    registerConcept(concept) {
      allConcepts.push(concept);
      refresh();
    },
    registerCategory(category) {
      allCategories.push(category);
      refresh();
    },
    init(onSelectionChange) {
      onChange = onSelectionChange || (() => {});
      setupCategorySearch();
      setupConceptSearch();
      refresh();
    },
  };
})();
