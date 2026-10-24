/**
 * Shared mobile nav toggle.
 * Loaded on every page; handles the hamburger <-> close button swap.
 */
(function () {
  'use strict';

  const btn = document.querySelector('.mobile-toggle');
  const menu = document.querySelector('.mobile-nav');
  const menuIcon = btn && btn.querySelector('.menu-icon');
  const closeIcon = btn && btn.querySelector('.close-icon');

  if (!btn || !menu) return;

  btn.addEventListener('click', function () {
    const isOpen = menu.classList.toggle('open');
    btn.setAttribute('aria-expanded', String(isOpen));
    if (menuIcon && closeIcon) {
      // toggleAttribute, not .hidden: these are SVG elements.
      menuIcon.toggleAttribute('hidden', isOpen);
      closeIcon.toggleAttribute('hidden', !isOpen);
    }
  });

  // Close menu when a link inside it is clicked
  menu.querySelectorAll('a').forEach(function (a) {
    a.addEventListener('click', function () {
      menu.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
      if (menuIcon && closeIcon) {
        menuIcon.removeAttribute('hidden');
        closeIcon.setAttribute('hidden', '');
      }
    });
  });
})();