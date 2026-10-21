/**
 * Booking engine
 * Handles: date validation, pricing, iCal availability, redirect flow.
 * Rates and stay rules come from js/pricing.js (property.json → booking).
 */

(function () {
  'use strict';

  // ──────────────────────────────────────────────
  // CONFIG
  // ──────────────────────────────────────────────

  const PRICING = window.SITE_PRICING;

  const CONFIG = {
    /**
     * Availability data: a same-origin JSON list of blocked dates.
     * Resolved against this script rather than the page, so it works from
     * any page depth and when the site is served from a sub-path
     * (e.g. a GitHub Pages project site).
     */
    AVAILABILITY_URL: new URL('../availability.json', document.currentScript.src).href,
  };

  // ──────────────────────────────────────────────
  // PRICING
  // ──────────────────────────────────────────────

  /**
   * Calculate total price by iterating each individual night.
   * A "night" is from check-in date D to D+1, priced by D's season.
   * Returns { total, nights, rateBreakdown[] }
   */
  function calculatePrice(checkIn, checkOut) {
    let total = 0;
    let nights = 0;
    const breakdown = [];

    const cursor = new Date(checkIn);
    while (cursor < checkOut) {
      const rate = PRICING.rateFor(cursor);
      if (rate === null) {
        // Night falls in closed season — invalidate
        return { total: 0, nights: 0, breakdown: [], closedSeason: true };
      }
      total += rate;
      breakdown.push({
        date: formatDateISO(cursor),
        rate: rate,
      });
      nights++;
      cursor.setDate(cursor.getDate() + 1);
    }

    return { total, nights, breakdown, closedSeason: false };
  }

  // ──────────────────────────────────────────────
  // DATE UTILITIES
  // ──────────────────────────────────────────────

  function formatDateISO(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  // i18n: dictionaries provided by js/i18n.js (must load first).
  // Falls back to English if i18n.js is missing.
  const I18N = window.SITE_I18N || null;
  const T = I18N ? I18N.t : function (key) { return key; };
  const LOCALE = I18N ? I18N.locale : 'en-US';
  const nightsWord = n => I18N ? I18N.plural(n, 'night', 'nights') : (String(n) === '1' ? 'night' : 'nights');

  function formatDateHuman(d) {
    return d.toLocaleDateString(LOCALE, { month: 'long', day: 'numeric', year: 'numeric' });
  }

  function parseDate(str) {
    if (!str) return null;
    const parts = str.split('-');
    return new Date(+parts[0], +parts[1] - 1, +parts[2]);
  }

  /** True if the night starting on this date falls in a season */
  function isOperationalDate(date) {
    return PRICING.rateFor(date) !== null;
  }

  /** Count nights between two dates */
  function nightCount(from, to) {
    return Math.round((to - from) / (1000 * 60 * 60 * 24));
  }

  // ──────────────────────────────────────────────
  // AVAILABILITY DATA
  // Reads availability.json: { generated, source, dates: ['YYYY-MM-DD', …] },
  // every date a guest cannot stay the night. The template ships a sample.
  // ──────────────────────────────────────────────

  let blockedDates = new Set();
  // availabilityLoaded = fetch finished (success OR failure)
  // availabilityHasData = fetch succeeded (file parsed, even if 0 bookings)
  window.blockedDates = blockedDates;
  window.availabilityLoaded = false;
  window.availabilityHasData = false;

  async function fetchAvailability() {
    try {
      const resp = await fetch(CONFIG.AVAILABILITY_URL, { cache: 'no-cache' });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      if (!data || !Array.isArray(data.dates)) throw new Error('Malformed availability.json');
      applyBlockedDates(new Set(data.dates));
      console.log(`[availability] Availability loaded: ${blockedDates.size} blocked days (generated ${data.generated})`);
    } catch (err) {
      console.error('[availability] Failed to load availability data:', err);
    }
    window.availabilityLoaded = true;
    finishAvailability();
  }

  function finishAvailability() {
    if (window.calendarRefresh) window.calendarRefresh();
    if (window.revalidateBooking) window.revalidateBooking();
  }

  /** Central place to swap the blocked-dates set and sync globals. */
  function applyBlockedDates(set) {
    blockedDates = set;
    window.blockedDates = blockedDates;
    window.availabilityHasData = true;
  }

  /** Check if a date is blocked (already booked) */
  function isBlocked(date) {
    return blockedDates.has(formatDateISO(date));
  }

  // ──────────────────────────────────────────────
  // UI CONTROLLER
  // ──────────────────────────────────────────────

  const $calendar = document.getElementById('availability-calendar');
  const $hint = document.getElementById('calendar-hint');
  const $adults = document.getElementById('adults');
  const $children = document.getElementById('children');
  const $priceDisplay = document.getElementById('price-display');
  const $priceAmount = document.getElementById('price-amount');
  const $priceBreakdown = document.getElementById('price-breakdown');
  const $btn = document.getElementById('check-availability-btn');
  const $message = document.getElementById('booking-message');

  // Date selection state (managed by calendar.js)
  let selectedCheckin = null;
  let selectedCheckout = null;

  // Track previous price to avoid re-animating on guest count change
  let prevPrice = 0;

  function showMessage(text, type) {
    $message.textContent = text;
    $message.className = `booking-message visible ${type}`;
  }

  function clearMessage() {
    $message.className = 'booking-message';
    $message.textContent = '';
  }

  function setPriceText(value) {
    $priceAmount.textContent = PRICING.formatPrice(value, LOCALE);
  }

  /** Animate price counter from previous value to target value */
  function animatePrice(targetValue, duration = 600) {
    // rAF never fires in a hidden tab, which would strand the price at €0.
    const reduceMotion = window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (document.hidden || reduceMotion) {
      setPriceText(targetValue);
      return;
    }

    const start = performance.now();
    const startValue = prevPrice;

    function update(currentTime) {
      const elapsed = currentTime - start;
      // rAF reports the frame's start, which can predate `start` — without the
      // lower clamp the eased value overshoots and flashes a negative price.
      const progress = Math.min(Math.max(elapsed / duration, 0), 1);

      if (progress >= 1) {
        setPriceText(targetValue);
        return;
      }

      // Ease-out cubic: decelerating to zero velocity
      const easeOut = 1 - Math.pow(1 - progress, 3);
      setPriceText(Math.floor(startValue + (targetValue - startValue) * easeOut));
      requestAnimationFrame(update);
    }

    requestAnimationFrame(update);
  }

  // Backgrounding mid-animation stops the counter; snap it on return.
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && $priceDisplay.style.display === 'block') {
      setPriceText(prevPrice);
    }
  });

  /**
   * Core validation & pricing logic.
   * Called when calendar selection changes or guest count changes.
   */
  function validate() {
    clearMessage();

    const checkInStr = selectedCheckin;
    const checkOutStr = selectedCheckout;
    const adults = parseInt($adults.value, 10) || 0;
    const children = parseInt($children.value, 10) || 0;
    const totalGuests = adults + children;

    if (!checkInStr || !checkOutStr) {
      $btn.disabled = true;
      $btn.textContent = T('btnSelectDates');
      $priceDisplay.style.display = 'none';
      return;
    }

    const checkIn = parseDate(checkInStr);
    const checkOut = parseDate(checkOutStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // ── Validation checks ──

    if (checkIn < today) {
      showMessage(T('msgFutureDate'), 'error');
      $btn.disabled = true;
      $btn.textContent = T('btnInvalidDates');
      $priceDisplay.style.display = 'none';
      return;
    }

    if (checkOut <= checkIn) {
      showMessage(T('msgOrder'), 'error');
      $btn.disabled = true;
      $btn.textContent = T('btnInvalidDates');
      $priceDisplay.style.display = 'none';
      return;
    }

    const nights = nightCount(checkIn, checkOut);

    if (nights < PRICING.minNights) {
      showMessage(T('msgMinStay', { min: PRICING.minNights, n: nights, nightsWord: nightsWord(nights) }), 'error');
      $btn.disabled = true;
      $btn.textContent = T('btnTooShort');
      $priceDisplay.style.display = 'none';
      return;
    }

    // ── Season check: every night must fall in a season ──
    if (!isOperationalDate(checkIn)) {
      showMessage(T('msgOpenSeason'), 'warning');
      $btn.disabled = true;
      $btn.textContent = T('btnClosedSeason');
      $priceDisplay.style.display = 'none';
      return;
    }

    // Check each night's date for closed season
    const cursor = new Date(checkIn);
    let inClosedSeason = false;
    while (cursor < checkOut) {
      if (!isOperationalDate(cursor)) {
        inClosedSeason = true;
        break;
      }
      cursor.setDate(cursor.getDate() + 1);
    }
    if (inClosedSeason) {
      showMessage(T('msgCrossSeason'), 'warning');
      $btn.disabled = true;
      $btn.textContent = T('btnClosedSeason');
      $priceDisplay.style.display = 'none';
      return;
    }

    // ── Guest count ──
    if (totalGuests < 1) {
      showMessage(T('msgMinGuest'), 'error');
      $btn.disabled = true;
      $btn.textContent = T('btnInvalid');
      $priceDisplay.style.display = 'none';
      return;
    }

    if (totalGuests > PRICING.maxGuests) {
      showMessage(T('msgMaxGuests', { max: PRICING.maxGuests }), 'error');
      $btn.disabled = true;
      $btn.textContent = T('btnTooManyGuests');
      $priceDisplay.style.display = 'none';
      return;
    }

    if (adults < 1) {
      showMessage(T('msgAdultRequired'), 'error');
      $btn.disabled = true;
      $btn.textContent = T('btnInvalid');
      $priceDisplay.style.display = 'none';
      return;
    }

    // ── Calculate price ──
    const pricing = calculatePrice(checkIn, checkOut);

    if (pricing.closedSeason) {
      showMessage(T('msgClosedNights'), 'warning');
      $btn.disabled = true;
      $btn.textContent = T('btnClosedSeason');
      $priceDisplay.style.display = 'none';
      return;
    }

    // ── Availability check (iCal blocked dates) ──
    const availCursor = new Date(checkIn);
    let conflictDate = null;
    while (availCursor < checkOut) {
      if (isBlocked(availCursor)) {
        conflictDate = new Date(availCursor);
        break;
      }
      availCursor.setDate(availCursor.getDate() + 1);
    }
    // Also check checkout day (turn-over rule: it's blocked for incoming,
    // meaning the current booking's checkout day is fine for THIS booking
    // but the day itself is blocked for incoming guests — which is us checking in)
    if (isBlocked(checkIn)) {
      conflictDate = new Date(checkIn);
    }

    if (conflictDate) {
      showMessage(
        T('msgConflict', { date: formatDateHuman(conflictDate) }),
        'error'
      );
      $btn.disabled = true;
      $btn.textContent = T('btnUnavailable');
      $priceDisplay.style.display = 'none';
      return;
    }

    // ── Show price & enable button ──
    // Only animate price if the value actually changed (prevents flicker on guest count change)
    const newPrice = pricing.total;
    if (newPrice !== prevPrice) {
      animatePrice(newPrice);
      prevPrice = newPrice;
    }
    $priceDisplay.style.display = 'block';
    $priceBreakdown.textContent = T('breakdown', { nights: pricing.nights, from: formatDateHuman(checkIn), to: formatDateHuman(checkOut) });

    // ── Warn if availability data is missing ──
    if (!window.availabilityLoaded) {
      showMessage(
        T('msgStillLoading'),
        'warning'
      );
    } else if (!window.availabilityHasData) {
      showMessage(
        T('msgLoadFailed'),
        'warning'
      );
    }

    $btn.disabled = false;
    $btn.textContent = T('btnRequestStay');

    // Store for redirect
    $btn.dataset.checkin = checkInStr;
    $btn.dataset.checkout = checkOutStr;
    $btn.dataset.guests = String(totalGuests);
    $btn.dataset.price = String(pricing.total);
    $btn.dataset.nights = String(pricing.nights);
  }

  // ──────────────────────────────────────────────
  // SET MIN DATE ON CALENDAR (handled by calendar.js)
  // ──────────────────────────────────────────────

  function setMinDates() {
    // Calendar.js handles this internally
  }

  // ──────────────────────────────────────────────
  // CALENDAR EVENT LISTENER
  // ──────────────────────────────────────────────

  if ($calendar) {
    $calendar.addEventListener('dateselected', function (e) {
      selectedCheckin = e.detail.checkin;
      selectedCheckout = e.detail.checkout;
      
      // Update hint text
      if ($hint) {
        if (!selectedCheckin) {
          $hint.textContent = T('hintCheckin');
        } else if (!selectedCheckout) {
          $hint.textContent = T('hintCheckout', { date: formatDateHuman(parseDate(selectedCheckin)) });
        } else {
          const nights = nightCount(parseDate(selectedCheckin), parseDate(selectedCheckout));
          $hint.textContent = T('hintRange', { from: formatDateHuman(parseDate(selectedCheckin)), to: formatDateHuman(parseDate(selectedCheckout)), nights: nights });
        }
      }
      
      validate();
    });
  }

  // ──────────────────────────────────────────────
  // REDIRECT TO CONTACT PAGE
  // ──────────────────────────────────────────────

  function redirectToContact() {
    const params = new URLSearchParams({
      checkin: $btn.dataset.checkin,
      checkout: $btn.dataset.checkout,
      guests: $btn.dataset.guests,
      price: $btn.dataset.price,
      nights: $btn.dataset.nights,
    });
    window.location.href = `contact.html?${params.toString()}`;
  }

  // ──────────────────────────────────────────────
  // EVENT LISTENERS
  // ──────────────────────────────────────────────

  $adults.addEventListener('input', validate);
  $children.addEventListener('input', validate);
  $btn.addEventListener('click', redirectToContact);

  // Allow booking.js availability updates to re-run validation
  window.revalidateBooking = validate;

  // ──────────────────────────────────────────────
  // INIT
  // ──────────────────────────────────────────────

  setMinDates();
  fetchAvailability(); // fire-and-forget

})();
