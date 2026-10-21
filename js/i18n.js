/**
 * UI strings for the page's language.
 * The strings come from the "ui" block of content/<lang>.json, which
 * scripts/build.py writes to js/strings.<lang>.js; each page loads its own.
 * Loaded BEFORE booking.js / calendar.js / contact.js, which read window.SITE_I18N.
 */

(function () {
  'use strict';

  const dict = window.SITE_STRINGS || {};

  /** Translate: t('msgMinStay', { min: 3, n: 2, nightsWord: '…' }) */
  function t(key, vars) {
    let str = dict[key] !== undefined ? dict[key] : key;
    if (vars) {
      for (const k in vars) {
        str = str.split('{' + k + '}').join(String(vars[k]));
      }
    }
    return str;
  }

  window.SITE_I18N = {
    lang: document.documentElement.getAttribute('lang') || 'en',
    locale: dict.locale || 'en-US',
    months: dict.months,
    days: dict.days,
    t: t,
    /** Pluralized word for nights/guests */
    plural: function (n, singularKey, pluralKey) {
      return String(n) === '1' || n === 1 ? dict[singularKey] : dict[pluralKey];
    },
  };
})();
