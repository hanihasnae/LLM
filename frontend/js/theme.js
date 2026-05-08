/* ══════════════════════════════════════════
   THEME MANAGER — Light/Dark Mode
══════════════════════════════════════════ */

class ThemeManager {
  constructor() {
    this.storageKey = 'carboniq-theme';
    this.html = document.documentElement;
    this.toggleBtn = document.getElementById('theme-toggle');
    
    // Initialiser le thème au chargement
    this.init();
  }

  init() {
    // Récupérer le thème sauvegardé ou la préférence système
    const savedTheme = localStorage.getItem(this.storageKey);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    const theme = savedTheme || (prefersDark ? 'dark' : 'light');
    
    // Appliquer le thème
    this.setTheme(theme);
    
    // Ajouter le listener au bouton
    if (this.toggleBtn) {
      this.toggleBtn.addEventListener('click', () => this.toggle());
    }
    
    // Écouter les changements de préférence système
    window.matchMedia('(prefers-color-scheme: dark)').addListener((e) => {
      if (!localStorage.getItem(this.storageKey)) {
        this.setTheme(e.matches ? 'dark' : 'light');
      }
    });
  }

  setTheme(theme) {
    const validTheme = ['light', 'dark'].includes(theme) ? theme : 'dark';
    
    // Appliquer l'attribut data-theme
    this.html.setAttribute('data-theme', validTheme);
    
    // Sauvegarder dans localStorage
    localStorage.setItem(this.storageKey, validTheme);
    
    // Mettre à jour meta theme-color (optionnel)
    this.updateMetaThemeColor(validTheme);
    
    console.log(`✅ Thème changé : ${validTheme}`);
  }

  toggle() {
    const currentTheme = this.html.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    this.setTheme(newTheme);
  }

  updateMetaThemeColor(theme) {
    let metaThemeColor = document.querySelector('meta[name="theme-color"]');
    
    if (!metaThemeColor) {
      metaThemeColor = document.createElement('meta');
      metaThemeColor.name = 'theme-color';
      document.head.appendChild(metaThemeColor);
    }
    
    metaThemeColor.content = theme === 'dark' ? '#091413' : '#f8fafb';
  }

  getCurrentTheme() {
    return this.html.getAttribute('data-theme') || 'dark';
  }
}

// Initialiser au chargement
document.addEventListener('DOMContentLoaded', () => {
  new ThemeManager();
});