/*
 * context7-init.js
 * Adds a lightweight Context7 chat button next to `#reto-theme-toggle` and
 * lazy-loads the Context7 widget script on first click. Derives color from
 * the site's CSS variables so it matches light/dark themes.
 */
(function () {
  const WIDGET_SRC = 'https://context7.com/widget.js';
  const LIBRARY = '/anselmoo/repo-release-tools';
  const POSITION = 'bottom-right'; // 'bottom-right' or 'bottom-left'
  const PLACEHOLDER = ''; // empty = provider default
  const BUTTON_ID = 'context7-chat-button';
  const TOGGLE_ID = 'reto-theme-toggle';

  function getTheme() {
    const root = document.documentElement;
    if (root && root.dataset && (root.dataset.theme === 'dark' || root.dataset.theme === 'light')) {
      return root.dataset.theme;
    }
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
    return 'light';
  }

  function getAccentColor() {
    try {
      const s = getComputedStyle(document.documentElement);
      let c = (s.getPropertyValue('--reto-accent') || '').trim();
      if (!c) c = (s.getPropertyValue('--reto-accent-strong') || '').trim();
      if (!c) return '#b65e13';
      // Normalize rgb(...) -> #rrggbb
      const rgb = c.match(/rgb\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)/i);
      if (rgb) {
        const r = parseInt(rgb[1], 10); const g = parseInt(rgb[2], 10); const b = parseInt(rgb[3], 10);
        return '#' + [r,g,b].map(n => ('0' + n.toString(16)).slice(-2)).join('');
      }
      return c;
    } catch (e) {
      return '#b65e13';
    }
  }

  function createButton() {
    if (document.getElementById(BUTTON_ID)) return;
    const btn = document.createElement('button');
    btn.id = BUTTON_ID;
    btn.type = 'button';
    btn.title = 'Open chat';
    btn.setAttribute('aria-label', 'Open chat');
    btn.innerHTML = '💬';
    btn.className = 'context7-chat-btn';

    // Inline fallback styles so the button appears even if CSS is slow to load
    btn.style.position = 'fixed';
    btn.style.right = 'calc(2rem + 64px)';
    btn.style.bottom = '2rem';
    btn.style.width = '48px';
    btn.style.height = '48px';
    btn.style.zIndex = '61';
    btn.style.display = 'flex';
    btn.style.alignItems = 'center';
    btn.style.justifyContent = 'center';
    btn.style.cursor = 'pointer';
    btn.style.fontSize = '1.25rem';
    btn.style.border = '2px solid var(--reto-border)';
    btn.style.borderRadius = '4px';
    btn.style.boxShadow = 'var(--reto-glow)';
    btn.style.background = 'var(--reto-bg-elevated)';
    const color = getAccentColor();
    if (color) btn.style.color = color;

    btn.addEventListener('click', onButtonClick);
    document.body.appendChild(btn);
  }

  function injectWidgetScript(color) {
    if (window.__context7_script_added) return;
    window.__context7_script_added = true;
    const s = document.createElement('script');
    s.src = WIDGET_SRC;
    s.async = true;
    s.setAttribute('data-library', LIBRARY);
    if (color) s.setAttribute('data-color', color);
    if (POSITION) s.setAttribute('data-position', POSITION);
    if (PLACEHOLDER) s.setAttribute('data-placeholder', PLACEHOLDER);

    s.onload = function () {
      // Try to open the widget via common provider APIs after it loads
      tryOpenWidget();
      // Heuristic: if the provider created its own UI, hide our anchor to avoid duplication
      setTimeout(() => {
        const ours = document.getElementById(BUTTON_ID);
        // Try to detect a widget root element commonly used by widgets
        const created = document.querySelector('[data-context7], .context7-widget, .c7-widget, .context7, [data-widget="context7"]');
        if (created && ours) ours.style.display = 'none';
      }, 700);
    };

    s.onerror = function () {
      console.warn('Context7 widget failed to load:', WIDGET_SRC);
      const btn = document.getElementById(BUTTON_ID);
      if (btn) { btn.disabled = false; btn.classList.remove('loading'); }
    };

    document.head.appendChild(s);
  }

  function tryOpenWidget() {
    const candidates = ['Context7', 'Context7Widget', 'context7', 'context7Widget', 'C7', 'c7'];
    for (const name of candidates) {
      const obj = window[name];
      if (!obj) continue;
      if (typeof obj.open === 'function') { try { obj.open(); return true; } catch(e){} }
      if (typeof obj.show === 'function') { try { obj.show(); return true; } catch(e){} }
      if (typeof obj.toggle === 'function') { try { obj.toggle(); return true; } catch(e){} }
    }
    if (typeof window.__context7_open === 'function') { try { window.__context7_open(); return true; } catch(e){} }
    return false;
  }

  function onButtonClick() {
    const btn = document.getElementById(BUTTON_ID);
    if (!btn) return;
    if (!window.__context7_loaded) {
      btn.disabled = true;
      btn.classList.add('loading');
      const color = getAccentColor();
      injectWidgetScript(color);
      window.__context7_loaded = true;
    } else {
      tryOpenWidget();
    }
  }

  function waitForToggleOrTimeout() {
    if (document.getElementById(TOGGLE_ID)) { createButton(); return; }
    const mo = new MutationObserver((_, observer) => {
      if (document.getElementById(TOGGLE_ID)) {
        createButton();
        observer.disconnect();
      }
    });
    mo.observe(document.body, { childList: true, subtree: true });
    // Fallback: create after 3s if the toggle never appears
    setTimeout(() => { if (!document.getElementById(BUTTON_ID)) createButton(); mo.disconnect(); }, 3000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', waitForToggleOrTimeout);
  else waitForToggleOrTimeout();

  // Observe theme attribute changes and update button color
  const root = document.documentElement;
  const attrObserver = new MutationObserver(() => {
    const btn = document.getElementById(BUTTON_ID);
    if (!btn) return;
    const color = getAccentColor();
    if (color) btn.style.color = color;
    try {
      const widget = window.Context7 || window.Context7Widget || window.context7 || window.c7;
      if (widget && typeof widget.update === 'function') widget.update({ color });
    } catch (e) {}
  });
  attrObserver.observe(root, { attributes: true, attributeFilter: ['data-theme'] });

})();
