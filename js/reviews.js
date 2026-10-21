/**
 * Reviews
 * Renders guest reviews grouped by platform (Booking.com, Airbnb, Google Maps).
 *
 * Each review carries:
 *   date         — 'YYYY-MM'; rendered in the page language via I18N.months
 *   originalLang — the language the guest actually wrote in ('en', 'de', …)
 *   translations — { <lang>: { title, text } } human translations into other
 *                  site languages. `title`/`text` always hold the ORIGINAL text.
 *
 * Display rules (per page language, from <html lang> via js/i18n.js):
 *   - review written in the page language        → show original, no button
 *   - translation available for the page language → show translation plus a
 *     "Show original" toggle that reveals the original text in place
 *   - otherwise                                   → show original (fallback)
 */

(function () {
  'use strict';

  // ── Sample reviews: replace with your own ──

  // Booking.com (scores out of 10)
  const bookingReviews = [
    {
      reviewer: 'Marta, PL',
      date: '2026-08',
      score: 10,
      featured: true,
      originalLang: 'en',
      title: 'Exactly as pictured.',
      text: 'Bright rooms, a well-equipped kitchen and a terrace we never wanted to leave. The host answered every message within the hour.'
    },
    {
      reviewer: 'Jonas, DE',
      date: '2026-07',
      score: 9,
      originalLang: 'de',
      title: 'Ideal, um den See zu erkunden.',
      text: 'Ruhige Straße, einfaches Parken und nur ein kurzer Spaziergang zur Fähre. Die Betten könnten etwas fester sein.',
      translations: {
        en: {
          title: 'A great base for exploring the lake.',
          text: 'Quiet street, easy parking and only a short walk to the ferry. The beds could be a little firmer.'
        }
      }
    },
    {
      reviewer: 'Claire, FR',
      date: '2026-06',
      score: 10,
      featured: true,
      originalLang: 'en',
      title: 'A wonderful family holiday.',
      text: 'Plenty of room for two families, and the children spent every afternoon in the garden.'
    }
  ];

  // Google Maps (stars out of 5)
  const googleReviews = [
    {
      reviewer: 'Peter K.',
      date: '2026-08',
      score: 5,
      originalLang: 'en',
      title: '',
      text: 'Beautiful house and a very kind host.'
    }
  ];

  // Airbnb (stars out of 5)
  const airbnbReviews = [
    {
      reviewer: 'Daniel',
      date: '2026-09',
      score: 5,
      featured: true,
      originalLang: 'en',
      title: '',
      text: 'Spotless, comfortable and in a lovely spot. We would stay again.'
    },
    {
      reviewer: 'Sofia',
      date: '2026-05',
      score: 4,
      originalLang: 'en',
      title: '',
      text: 'Lovely home with a great view. The road up is steep, so a small car helps.'
    }
  ];

  // ── i18n ──
  // Dictionaries provided by js/i18n.js (must load first).
  // Falls back to English labels if i18n.js is missing.
  var I18N = window.SITE_I18N || null;
  var PAGE_LANG = I18N ? I18N.lang : 'en';

  var FALLBACK_LANG_NAMES = {
    en: 'English', it: 'Italian', de: 'German', fr: 'French',
    pl: 'Polish', da: 'Danish', uk: 'Ukrainian', ru: 'Russian'
  };

  var FALLBACK_MONTHS = ['January','February','March','April','May','June',
                         'July','August','September','October','November','December'];

  function langName(code) {
    if (I18N && I18N.langNames && I18N.langNames[code]) return I18N.langNames[code];
    return FALLBACK_LANG_NAMES[code] || code;
  }

  function toggleLabel(key, langCode) {
    if (I18N) return I18N.t(key, { lang: langName(langCode) });
    var base = key === 'showOriginal' ? 'Show original' : 'Show translation';
    return base + ' (' + langName(langCode) + ')';
  }

  // ── Helpers ──

  var STAR_SVG = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"></path></svg>';

  function starsHTML(count) {
    var html = '';
    for (var i = 0; i < count; i++) html += '<span>' + STAR_SVG + '</span>';
    return html;
  }

  function scoreToStars(score) {
    // Booking.com score is out of 10 → convert to 5-star scale
    return Math.round(score / 2);
  }

  /** '2026-07' -> 'July 2026', in the page language. */
  function formatReviewDate(ym) {
    var parts = String(ym).split('-');
    var months = (I18N && I18N.months) ? I18N.months : FALLBACK_MONTHS;
    var name = months[parseInt(parts[1], 10) - 1];
    return name ? name + ' ' + parts[0] : String(ym);
  }

  /** Combine title + text the way the card displays them. */
  function combinedText(title, body) {
    var out = '';
    if (title) out += '"' + title + '" ';
    if (body) out += body;
    return out;
  }

  /**
   * Pick what to display for this review on the current page language.
   * Returns { title, text, showToggle, originalLang }.
   */
  function displayFor(review) {
    var original = { title: review.title || '', text: review.text || '' };

    // Written in the page language → original, no toggle.
    if (!review.originalLang || review.originalLang === PAGE_LANG) {
      return { title: original.title, text: original.text, showToggle: false };
    }

    // Translation available for the page language → show it with a toggle.
    var trans = review.translations && review.translations[PAGE_LANG];
    if (trans) {
      return {
        title: trans.title || '',
        text: trans.text || '',
        showToggle: true,
        originalLang: review.originalLang,
        original: original
      };
    }

    // No translation for this page language yet → original, no toggle
    // (same behaviour as before translations were introduced).
    return { title: original.title, text: original.text, showToggle: false };
  }

  function createCard(review, isBooking, platformName) {
    var card = document.createElement('article');
    card.className = 'review-card';

    var stars = document.createElement('div');
    stars.className = 'review-stars';
    stars.innerHTML = starsHTML(isBooking ? scoreToStars(review.score) : review.score);

    if (platformName) {
      var badge = document.createElement('span');
      badge.className = 'review-platform';
      badge.textContent = platformName;
      stars.appendChild(badge);
    }

    var view = displayFor(review);

    var text = document.createElement('p');
    text.className = 'review-text';
    text.textContent = combinedText(view.title, view.text);

    card.appendChild(stars);
    card.appendChild(text);

    if (view.showToggle) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'review-toggle';
      btn.setAttribute('aria-pressed', 'false');
      btn.textContent = toggleLabel('showOriginal', view.originalLang);

      var showingOriginal = false;
      btn.addEventListener('click', function () {
        showingOriginal = !showingOriginal;
        if (showingOriginal) {
          text.textContent = combinedText(view.original.title, view.original.text);
          btn.textContent = toggleLabel('showTranslation', PAGE_LANG);
        } else {
          text.textContent = combinedText(view.title, view.text);
          btn.textContent = toggleLabel('showOriginal', view.originalLang);
        }
        btn.setAttribute('aria-pressed', String(showingOriginal));
      });

      card.appendChild(btn);
    }

    var footer = document.createElement('footer');
    footer.className = 'review-footer';

    var name = document.createElement('strong');
    name.textContent = review.reviewer;

    var date = document.createElement('span');
    date.textContent = formatReviewDate(review.date);

    footer.appendChild(name);
    footer.appendChild(date);

    card.appendChild(footer);

    return card;
  }

  /** Newest first — 'YYYY-MM' sorts as a plain string. */
  function renderReviews(gridEl, reviews, isBooking) {
    reviews.slice()
      .sort(function (a, b) { return String(b.date).localeCompare(String(a.date)); })
      .forEach(function (r) {
        gridEl.appendChild(createCard(r, isBooking));
      });
  }

  /** Mean score, formatted for the page language (German reads '9,8'). */
  function averageScore(reviews, decimals) {
    if (!reviews.length) return '';
    var sum = reviews.reduce(function (acc, r) { return acc + r.score; }, 0);
    var avg = sum / reviews.length;
    var locale = I18N ? I18N.locale : 'en-US';
    return avg.toLocaleString(locale, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
  }

  /** `decimals` follows each platform's own convention. */
  var PLATFORMS = [
    { name: 'Booking.com', reviews: bookingReviews, isBooking: true,
      gridId: 'reviews-booking', scoreId: 'booking-score', decimals: 1 },
    { name: 'Airbnb', reviews: airbnbReviews, isBooking: false,
      gridId: 'reviews-airbnb', scoreId: 'airbnb-score', decimals: 2 },
    { name: 'Google Maps', reviews: googleReviews, isBooking: false,
      gridId: 'reviews-google', scoreId: 'google-score', decimals: 1 }
  ];

  /** All platforms, normalised onto the 5-point scale. */
  function overallRating() {
    var total = 0, count = 0;
    PLATFORMS.forEach(function (p) {
      p.reviews.forEach(function (r) {
        total += p.isBooking ? r.score / 2 : r.score;
        count++;
      });
    });
    return { rating: count ? total / count : 0, count: count };
  }

  // ── Mount ──

  /** The score is computed here; the HTML value is the no-JS fallback. */
  function mountPlatform(p) {
    var grid = document.getElementById(p.gridId);
    if (!grid) return;
    renderReviews(grid, p.reviews, p.isBooking);
    var score = document.getElementById(p.scoreId);
    if (score) score.textContent = averageScore(p.reviews, p.decimals);
  }

  /** Home page: reviews marked `featured`, plus the overall rating. */
  function mountFeatured() {
    var grid = document.getElementById('reviews-featured');
    if (!grid) return;

    var picks = [];
    PLATFORMS.forEach(function (p) {
      p.reviews.forEach(function (r) {
        if (r.featured) picks.push({ review: r, platform: p });
      });
    });
    picks.sort(function (a, b) {
      return String(b.review.date).localeCompare(String(a.review.date));
    });
    picks.forEach(function (pick) {
      grid.appendChild(createCard(pick.review, pick.platform.isBooking, pick.platform.name));
    });

    var summary = overallRating();
    var locale = I18N ? I18N.locale : 'en-US';

    var ratingEl = document.getElementById('home-rating');
    if (ratingEl) {
      ratingEl.textContent = summary.rating.toLocaleString(locale, {
        minimumFractionDigits: 1, maximumFractionDigits: 1
      });
    }

    var countEl = document.getElementById('home-review-count');
    if (countEl) {
      countEl.textContent = I18N
        ? I18N.t('reviewsFrom', { n: summary.count })
        : 'from ' + summary.count + ' guest reviews';
    }
  }

  PLATFORMS.forEach(mountPlatform);
  mountFeatured();

})();
