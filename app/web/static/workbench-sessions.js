window.WorkbenchSessions = (() => {
  const STORAGE_KEY = 'studio_training_sessions';

  function loadAll() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch {
      return [];
    }
  }

  function saveAll(sessions) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  }

  function newId() {
    return `sess_${Date.now().toString(36)}`;
  }

  function now() {
    return new Date().toISOString();
  }

  function create(name) {
    const session = {
      id: newId(),
      name: name || `Session ${loadAll().length + 1}`,
      status: 'draft',
      created_at: now(),
      updated_at: now(),
      media_ids: [],
      notes: '',
      base_model_version: '',
      history: [{ at: now(), action: 'created', detail: 'Training session created' }],
    };
    const sessions = [session, ...loadAll()];
    saveAll(sessions);
    return session;
  }

  function update(session) {
    session.updated_at = now();
    const sessions = loadAll().map((item) => (item.id === session.id ? session : item));
    saveAll(sessions);
    return session;
  }

  function log(session, action, detail) {
    session.history = [{ at: now(), action, detail }, ...(session.history || [])].slice(0, 50);
    return update(session);
  }

  function addMedia(session, mediaId) {
    if (session.media_ids.includes(mediaId)) return session;
    session.media_ids.push(mediaId);
    return log(session, 'media_added', `Added ${mediaId}`);
  }

  function removeMedia(session, mediaId) {
    session.media_ids = session.media_ids.filter((id) => id !== mediaId);
    return log(session, 'media_removed', `Removed ${mediaId}`);
  }

  function setStatus(session, status) {
    session.status = status;
    return log(session, 'status_changed', `Status → ${status}`);
  }

  function get(id) {
    return loadAll().find((item) => item.id === id) || null;
  }

  return { loadAll, create, update, get, addMedia, removeMedia, setStatus, log };
})();
