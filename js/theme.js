/**
 * Light/dark theme toggle
 *
 * Persists the user's choice in localStorage.
 * Respects OS-level prefers-color-scheme when no explicit choice is stored.
 *
 * The FOUC-prevention inline script in each HTML page must run before CSS
 * loads; this file just wires up the toggle button and handles clicks.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'site-theme';

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (_) {}
  }

  function toggle() {
    var current = document.documentElement.getAttribute('data-theme') || 'light';
    apply(current === 'dark' ? 'light' : 'dark');
  }

  // Attach to every .theme-toggle button on the page
  function bind() {
    var buttons = document.querySelectorAll('.theme-toggle');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener('click', toggle);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
