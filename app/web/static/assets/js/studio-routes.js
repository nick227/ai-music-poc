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
  settings: '/settings/',
};
