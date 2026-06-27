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
  createCategory(name, dimension) {
    return this.request('/api/categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, dimension }),
    });
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
