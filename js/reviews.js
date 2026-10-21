/**
 * Reviews
 * The cards are rendered into the page from reviews.json by scripts/reviews.py.
 * This only wires up "Show original" on reviews shown in translation: the
 * button ships hidden, because without JavaScript it would do nothing.
 */

(function () {
  'use strict';

  document.querySelectorAll('.review-toggle').forEach(function (btn) {
    const texts = btn.closest('.review-card').querySelectorAll('.review-text');
    const translation = texts[0];
    const original = texts[1];
    if (!translation || !original) return;

    btn.hidden = false;
    btn.addEventListener('click', function () {
      const showOriginal = btn.getAttribute('aria-pressed') !== 'true';
      translation.hidden = showOriginal;
      original.hidden = !showOriginal;
      btn.setAttribute('aria-pressed', String(showOriginal));
      btn.textContent = showOriginal ? btn.dataset.labelTranslation : btn.dataset.labelOriginal;
    });
  });
})();
