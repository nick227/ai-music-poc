let queue = [];
let activeItem = null;
let selectedCategories = [];
let selectedConcepts = [];

// Elements
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-upload');
const queueList = document.getElementById('queue-list');
const queueCount = document.getElementById('queue-count');
const editorForm = document.getElementById('editor-form');
const emptyState = document.getElementById('empty-editor-state');
const activeFilename = document.getElementById('active-filename');
const mediaPlayer = document.getElementById('media-player');

const catSearch = document.getElementById('cat-search');
const catResults = document.getElementById('cat-results');
const catChips = document.getElementById('cat-chips');

const conSearch = document.getElementById('con-search');
const conResults = document.getElementById('con-results');
const conChips = document.getElementById('con-chips');

// API Client - Centralized canonical endpoints
const ApiClient = {
    async request(url, options = {}) {
        const res = await fetch(url, options);
        if (!res.ok) {
            const err = await res.text();
            throw new Error(err || 'API request failed');
        }
        return res.json();
    },
    importMedia: async (formData) => {
        const res = await ApiClient.request('/api/media/import', { method: 'POST', body: formData });
        return res.media || [];
    },
    getInbox: async () => {
        const res = await ApiClient.request('/api/media?review_status=NEEDS_REVIEW');
        return res.media || [];
    },
    searchCategories: async (query) => {
        const res = await ApiClient.request(`/api/categories?q=${encodeURIComponent(query)}`);
        return res.categories || [];
    },
    searchConcepts: async (query) => {
        const res = await ApiClient.request(`/api/concepts?q=${encodeURIComponent(query)}`);
        return res.concepts || [];
    },
    saveAssignments: (id, payload) => ApiClient.request(`/api/media/${id}/assignments`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
};

// Initialization
async function init() {
    await loadQueue();
    setupDragAndDrop();
    setupSearch(catSearch, catResults, ApiClient.searchCategories, addCategory);
    setupSearch(conSearch, conResults, ApiClient.searchConcepts, addConcept);
    
    editorForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveAndNext();
    });
    
    document.getElementById('skip-btn').addEventListener('click', () => {
        // Just load next without saving for MVP skip
        queue = queue.filter(item => item.id !== activeItem.id);
        renderQueue();
        selectNext();
    });
}

// Queue Management
async function loadQueue() {
    try {
        queue = await ApiClient.getInbox();
        renderQueue();
        if (queue.length > 0 && !activeItem) {
            selectItem(queue[0]);
        }
    } catch (e) {
        console.error("Failed to load inbox", e);
    }
}

function renderQueue() {
    queueCount.textContent = queue.length;
    if (queue.length === 0) {
        queueList.innerHTML = '<p>Inbox is empty.</p>';
        return;
    }
    
    queueList.innerHTML = queue.map(item => `
        <div class="queue-item ${activeItem && activeItem.id === item.id ? 'active' : ''}" onclick="window.selectItemById('${item.id}')">
            <span class="queue-item-name">${item.title || item.id}</span>
        </div>
    `).join('');
}

window.selectItemById = (id) => {
    const item = queue.find(i => i.id === id);
    if (item) selectItem(item);
};

function selectItem(item) {
    activeItem = item;
    renderQueue(); // update active class
    
    const firstCat = (item.category_assignments || [])[0] || {};
    const firstCon = (item.concept_assignments || [])[0] || {};
    
    selectedCategories = (item.category_assignments || []).map(a => a.category_id);
    selectedConcepts = (item.concept_assignments || []).map(a => a.concept_id);
    
    const qs = firstCat.quality_score || firstCon.quality_score || '';
    const fs = firstCat.fit_score || firstCon.fit_score || '';
    const r = firstCat.role || firstCon.role || '';
    const n = firstCat.notes || firstCon.notes || '';

    document.getElementById('quality-score').value = qs;
    document.getElementById('fit-score').value = fs;
    document.getElementById('role-select').value = r;
    document.getElementById('notes-input').value = n;
    
    renderChips();
    
    // Update UI
    emptyState.hidden = true;
    editorForm.hidden = false;
    activeFilename.textContent = item.title || item.id;
    mediaPlayer.src = `/api/media/${item.id}/audio`;
}

function selectNext() {
    if (queue.length > 0) {
        selectItem(queue[0]);
    } else {
        activeItem = null;
        editorForm.hidden = true;
        emptyState.hidden = false;
        mediaPlayer.src = '';
    }
}

// Upload Handling
function setupDragAndDrop() {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.remove('dragover'), false);
    });

    dropzone.addEventListener('drop', handleDrop, false);
    fileInput.addEventListener('change', (e) => uploadFiles(e.target.files));
}

function handleDrop(e) {
    const dt = e.dataTransfer;
    uploadFiles(dt.files);
}

async function uploadFiles(files) {
    if (!files.length) return;
    
    const formData = new FormData();
    for (const file of files) {
        formData.append('files', file);
    }
    
    try {
        const newItems = await ApiClient.importMedia(formData);
        queue = [...queue, ...newItems];
        renderQueue();
        if (!activeItem) selectItem(queue[0]);
    } catch (e) {
        console.error("Upload failed", e);
        alert("Upload failed. Make sure backend is running.");
    }
}

// Taxonomy Search and Chips
function setupSearch(inputEl, resultsEl, searchFn, onSelect) {
    let timeout = null;
    
    inputEl.addEventListener('input', (e) => {
        clearTimeout(timeout);
        const query = e.target.value.trim();
        
        if (query.length < 1) {
            resultsEl.classList.add('hidden');
            return;
        }
        
        timeout = setTimeout(async () => {
            try {
                const results = await searchFn(query);
                if (results.length > 0) {
                    resultsEl.innerHTML = results.map(r => `
                        <div class="search-result-item" data-id="${r.id}" data-name="${r.name}">
                            ${r.name}
                        </div>
                    `).join('');
                    resultsEl.classList.remove('hidden');
                    
                    // Bind clicks
                    resultsEl.querySelectorAll('.search-result-item').forEach(el => {
                        el.addEventListener('click', () => {
                            onSelect({ id: el.dataset.id, name: el.dataset.name });
                            inputEl.value = '';
                            resultsEl.classList.add('hidden');
                        });
                    });
                } else {
                    resultsEl.classList.add('hidden');
                }
            } catch (err) {
                console.error("Search failed", err);
            }
        }, 300);
    });

    // Close on click outside
    document.addEventListener('click', (e) => {
        if (!inputEl.contains(e.target) && !resultsEl.contains(e.target)) {
            resultsEl.classList.add('hidden');
        }
    });
}

function addCategory(cat) {
    if (!selectedCategories.includes(cat.id)) {
        selectedCategories.push(cat.id);
        renderChips();
    }
}

function addConcept(con) {
    if (!selectedConcepts.includes(con.id)) {
        selectedConcepts.push(con.id);
        renderChips();
    }
}

window.removeCategory = (id) => {
    selectedCategories = selectedCategories.filter(x => x !== id);
    renderChips();
};

window.removeConcept = (id) => {
    selectedConcepts = selectedConcepts.filter(x => x !== id);
    renderChips();
};

function renderChips() {
    catChips.innerHTML = selectedCategories.map(id => `
        <span class="chip">${id} <span class="remove" onclick="window.removeCategory('${id}')">×</span></span>
    `).join('');
    
    conChips.innerHTML = selectedConcepts.map(id => `
        <span class="chip">${id} <span class="remove" onclick="window.removeConcept('${id}')">×</span></span>
    `).join('');
}

// Save + Next
async function saveAndNext() {
    if (!activeItem) return;
    
    const submitBtn = document.getElementById('save-next-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';
    
    const qs = parseInt(document.getElementById('quality-score').value) || null;
    const fs = parseInt(document.getElementById('fit-score').value) || null;
    let role = document.getElementById('role-select').value || null;
    
    // Mapping default empty role to REFERENCE to satisfy canonical API requirements
    if (!role) role = 'REFERENCE';
    
    const notes = document.getElementById('notes-input').value || null;

    const payload = {
        categories: selectedCategories.map(id => ({ category_id: id, quality_score: qs, fit_score: fs, role, notes, reviewed: true })),
        concepts: selectedConcepts.map(id => ({ concept_id: id, quality_score: qs, fit_score: fs, role, notes, reviewed: true })),
        mark_reviewed: true
    };
    
    try {
        await ApiClient.saveAssignments(activeItem.id, payload);
        
        // Remove from queue
        queue = queue.filter(item => item.id !== activeItem.id);
        renderQueue();
        
        // Next
        selectNext();
    } catch (e) {
        console.error("Save failed", e);
        alert("Failed to save media.");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Save + Next';
    }
}

// Run
init();
