/**
 * Theme initialisation (FOUC prevention)
 *
 * Loaded synchronously before the CSS link so the correct data-theme
 * attribute is already on <html> when the browser paints the first frame.
 * This replaces the former inline <script> which was silently blocked
 * by the Content-Security-Policy (script-src 'self').
 */
(function () {
  try {
    var k = 'site-theme';
    var s = localStorage.getItem(k);
    var t = s || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', t);
  } catch (e) {
    document.documentElement.setAttribute('data-theme', 'light');
  }
})();
