window.StudioNav = {
  tabs: [
    { id: 'media', label: 'Media', href: StudioRoutes.media },
    { id: 'workbench', label: 'Workbench', href: StudioRoutes.workbench },
    { id: 'generate', label: 'Generate', href: StudioRoutes.home },
    { id: 'songs', label: 'Songs', href: StudioRoutes.songs },
    { id: 'settings', label: 'Settings', href: StudioRoutes.settings },
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
