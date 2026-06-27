window.StudioNav = {
  tabs: [
    { id: 'media', label: 'Media', href: '/media.html' },
    { id: 'workbench', label: 'Workbench', href: '/workbench.html' },
    { id: 'generate', label: 'Generate', href: '/' },
    { id: 'songs', label: 'Songs', href: '/songs.html' },
    { id: 'settings', label: 'Settings', href: '/settings.html' },
  ],
  render(activeId) {
    const root = document.getElementById('studio-nav');
    if (!root) return;
    root.innerHTML = this.tabs.map((tab) => `
      <a href="${tab.href}" class="studio-tab ${tab.id === activeId ? 'active' : ''}">${tab.label}</a>
    `).join('');
  },
  boot() {
    const tab = document.body?.dataset?.studioTab;
    if (tab) this.render(tab);
  },
};

document.addEventListener('DOMContentLoaded', () => StudioNav.boot());
