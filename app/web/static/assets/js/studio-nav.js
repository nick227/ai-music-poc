window.StudioNav = {
  tabs: [
    { id: 'categories', label: 'Categories', href: StudioRoutes.categories },
    { id: 'media', label: 'Media', href: StudioRoutes.media },
    { id: 'workbench', label: 'Workbench', href: StudioRoutes.workbench },
    { id: 'generate', label: 'Songs', href: StudioRoutes.home },
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
