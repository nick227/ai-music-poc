window.WorkbenchSessions = (() => {
  const STORAGE_KEY = 'studio_training_workspace';

  function load() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    } catch {
      return null;
    }
  }

  function save(workspace) {
    workspace.updated_at = new Date().toISOString();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace));
    return workspace;
  }

  function getOrCreate() {
    const existing = load();
    if (existing) return existing;
    return save({ media_ids: [], updated_at: new Date().toISOString() });
  }

  function setMediaIds(mediaIds) {
    const workspace = getOrCreate();
    workspace.media_ids = [...mediaIds];
    return save(workspace);
  }

  function toggleMedia(mediaId, included) {
    const workspace = getOrCreate();
    const set = new Set(workspace.media_ids);
    if (included) set.add(mediaId);
    else set.delete(mediaId);
    workspace.media_ids = [...set];
    return save(workspace);
  }

  return { getOrCreate, setMediaIds, toggleMedia };
})();
