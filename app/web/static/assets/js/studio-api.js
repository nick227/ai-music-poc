window.StudioApi = {
  async request(url, options = {}) {
    const res = await fetch(url, options);
    if (!res.ok) throw new Error(await res.text() || 'API request failed');
    return res.json();
  },
  importMedia(formData) {
    return this.request('/api/media/import', { method: 'POST', body: formData }).then((r) => r.media || []);
  },
  getInbox() {
    return this.listMedia({ review_status: 'NEEDS_REVIEW', kind: 'UPLOAD' });
  },
  listMedia(params = {}) {
    const query = new URLSearchParams();
    if (params.review_status) query.set('review_status', params.review_status);
    if (params.kind) query.set('kind', params.kind);
    query.set('limit', String(params.limit || 200));
    const suffix = query.toString() ? `?${query}` : '';
    return this.request(`/api/media${suffix}`).then((r) => r.media || []);
  },
  getMedia(id) {
    return this.request(`/api/media/${id}`);
  },
  listCategories() {
    return this.request('/api/categories');
  },
  listConcepts() {
    return this.request('/api/concepts').then((r) => r.concepts || []);
  },
  previewSlices(filter = {}) {
    const query = new URLSearchParams();
    if (filter.concept_id) query.append('concept_id', filter.concept_id);
    (filter.category_ids || []).forEach((id) => query.append('category_ids', id));
    (filter.roles || []).forEach((role) => query.append('roles', role));
    if (filter.min_quality != null && filter.min_quality !== '') query.set('min_quality', String(filter.min_quality));
    if (filter.min_fit != null && filter.min_fit !== '') query.set('min_fit', String(filter.min_fit));
    if (filter.review_status) query.set('review_status', filter.review_status);
    if (filter.rights_status) query.set('rights_status', filter.rights_status);
    return this.request(`/api/slices/preview?${query}`);
  },
  listSlices() {
    return this.request('/api/slices').then((r) => r.slices || []);
  },
  getSlice(id) {
    return this.request(`/api/slices/${id}`);
  },
  createSlice(payload) {
    return this.request('/api/slices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },
  updateSlice(id, payload) {
    return this.request(`/api/slices/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },
  freezeSlice(id) {
    return this.request(`/api/slices/${id}/freeze`, { method: 'POST' });
  },
  slicePackageUrl(id) {
    return `/api/slices/${id}/package`;
  },
  listTrainingRuns() {
    return this.request('/api/training/runs').then((r) => r.runs || []);
  },
  getTrainingRun(id) {
    return this.request(`/api/training/runs/${id}`);
  },
  createTrainingRun(payload) {
    return this.request('/api/training/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },
  cancelTrainingRun(id) {
    return this.request(`/api/training/runs/${id}/cancel`, { method: 'POST' });
  },
  getTrainingRunLogs(id, maxChars = 4000) {
    return this.request(`/api/training/runs/${id}/logs?max_chars=${maxChars}`);
  },
  createCategory(name, dimension, description = '') {
    return this.request('/api/categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, dimension, description: description || null }),
    });
  },
  bulkCreateCategories(categories) {
    return this.request('/api/categories/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ categories }),
    });
  },
  deleteCategory(id) {
    return this.request(`/api/categories/${encodeURIComponent(id)}`, { method: 'DELETE' });
  },
  saveAssignments(id, payload) {
    return this.request(`/api/media/${id}/assignments`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },
  listSongs(params = {}) {
    const query = new URLSearchParams();
    query.set('limit', String(params.limit || 100));
    if (params.review_status) query.set('review_status', params.review_status);
    if (params.review_decision) query.set('review_decision', params.review_decision);
    return this.request(`/api/songs?${query}`).then((r) => r.songs || []);
  },
  getSong(id) {
    return this.request(`/api/songs/${id}`);
  },
  reviewSong(id, payload) {
    return this.request(`/api/songs/${id}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },
  modelStatus() {
    return this.request('/api/model-status');
  },
};

window.WorkbenchApi = window.StudioApi;
