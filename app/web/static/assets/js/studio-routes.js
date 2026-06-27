window.StudioRoutes = {
  home: '/',
  media: '/media/',
  categories: '/categories/',
  mediaDetail(id) {
    return `/media/detail.html?id=${encodeURIComponent(id)}`;
  },
  workbench: '/workbench/',
  generateWithContext(id) {
    return `/?context_media=${encodeURIComponent(id)}`;
  },
  songs: '/songs/',
  songCompare(baselineId, styledId) {
    const query = new URLSearchParams({ baseline_id: baselineId, styled_id: styledId });
    return `/songs/compare.html?${query}`;
  },
  settings: '/settings/',
};
