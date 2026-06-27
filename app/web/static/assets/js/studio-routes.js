window.StudioRoutes = {
  home: '/',
  media: '/media/',
  mediaDetail(id) {
    return `/media/detail.html?id=${encodeURIComponent(id)}`;
  },
  workbench: '/workbench/',
  workbenchWithMedia(id) {
    return `/workbench/?media_id=${encodeURIComponent(id)}`;
  },
  generateWithContext(id) {
    return `/?context_media=${encodeURIComponent(id)}`;
  },
  songs: '/songs/',
  settings: '/settings/',
};
