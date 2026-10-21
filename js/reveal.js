/**
 * Scroll reveal
 *
 * Elements opt in with [data-reveal]; [data-reveal-group] staggers its children.
 * Nothing is hidden until we know we can reveal it again — see reveal-enabled.
 */
(function () {
  'use strict';

  if (!('IntersectionObserver' in window)) return;
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var targets = [];

  document.querySelectorAll('[data-reveal]').forEach(function (el) {
    targets.push(el);
  });

  document.querySelectorAll('[data-reveal-group]').forEach(function (group) {
    Array.prototype.forEach.call(group.children, function (child, i) {
      child.style.setProperty('--reveal-delay', (i * 90) + 'ms');
      targets.push(child);
    });
  });

  if (!targets.length) return;

  document.documentElement.classList.add('reveal-enabled');

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-revealed');
      observer.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });

  targets.forEach(function (el) {
    el.classList.add('reveal-pending');
    observer.observe(el);
  });
})();
