/**
 * Booking engine
 * Handles: date validation, pricing, iCal availability, redirect flow.
 * Rates and stay rules come from js/pricing.js (property.json → booking).
 * Pure date/pricing/validation logic lives in js/booking-core.js.
 */

(function () {
  'use strict';

  // ──────────────────────────────────────────────
  // CONFIG
  // ──────────────────────────────────────────────

  const PRICING = window.SITE_PRICING;
  const CORE = window.BOOKING_CORE;

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
  // DATE UTILITIES
  // ──────────────────────────────────────────────

  // Pure date/pricing logic is unit-tested in js/booking-core.js.
  const parseDate = CORE.parseDate;
  const nightCount = CORE.nightCount;

  // i18n: dictionaries provided by js/i18n.js (must load first).
  // Falls back to English if i18n.js is missing.
  const I18N = window.SITE_I18N || null;
  const T = I18N ? I18N.t : function (key) { return key; };
  const LOCALE = I18N ? I18N.locale : 'en-US';
  const nightsWord = n => I18N ? I18N.plural(n, 'night', 'nights') : (String(n) === '1' ? 'night' : 'nights');

  function formatDateHuman(d) {
    return d.toLocaleDateString(LOCALE, { month: 'long', day: 'numeric', year: 'numeric' });
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
    if (!document.hidden && !$priceDisplay.hidden) {
      setPriceText(prevPrice);
    }
  });

  /**
   * Core validation & pricing logic.
   * Called when calendar selection changes or guest count changes.
   * The decision tree lives in booking-core.js; this maps its result to the DOM.
   */
  function validate() {
    clearMessage();

    const checkInStr = selectedCheckin;
    const checkOutStr = selectedCheckout;
    const adults = parseInt($adults.value, 10) || 0;
    const children = parseInt($children.value, 10) || 0;

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const result = CORE.validateBooking(PRICING, {
      checkInStr: checkInStr,
      checkOutStr: checkOutStr,
      adults: adults,
      children: children,
      today: today,
      blockedDates: blockedDates,
    });

    if (!result.ok) {
      $btn.disabled = true;
      $priceDisplay.hidden = true;

      switch (result.reason) {
        case 'no-dates':
          $btn.textContent = T('btnSelectDates');
          return;
        case 'past-date':
          showMessage(T('msgFutureDate'), 'error');
          $btn.textContent = T('btnInvalidDates');
          return;
        case 'bad-order':
          showMessage(T('msgOrder'), 'error');
          $btn.textContent = T('btnInvalidDates');
          return;
        case 'min-stay':
          showMessage(T('msgMinStay', { min: PRICING.minNights, n: result.nights, nightsWord: nightsWord(result.nights) }), 'error');
          $btn.textContent = T('btnTooShort');
          return;
        case 'closed-season':
          showMessage(T('msgOpenSeason'), 'warning');
          $btn.textContent = T('btnClosedSeason');
          return;
        case 'cross-season':
          showMessage(T('msgCrossSeason'), 'warning');
          $btn.textContent = T('btnClosedSeason');
          return;
        case 'min-guests':
          showMessage(T('msgMinGuest'), 'error');
          $btn.textContent = T('btnInvalid');
          return;
        case 'max-guests':
          showMessage(T('msgMaxGuests', { max: PRICING.maxGuests }), 'error');
          $btn.textContent = T('btnTooManyGuests');
          return;
        case 'adult-required':
          showMessage(T('msgAdultRequired'), 'error');
          $btn.textContent = T('btnInvalid');
          return;
        case 'closed-nights':
          showMessage(T('msgClosedNights'), 'warning');
          $btn.textContent = T('btnClosedSeason');
          return;
        case 'conflict':
          showMessage(T('msgConflict', { date: formatDateHuman(result.conflictDate) }), 'error');
          $btn.textContent = T('btnUnavailable');
          return;
        default:
          return;
      }
    }

    // ── Show price & enable button ──
    // Only animate price if the value actually changed (prevents flicker on guest count change)
    const pricing = result.pricing;
    const newPrice = pricing.total;
    if (newPrice !== prevPrice) {
      animatePrice(newPrice);
      prevPrice = newPrice;
    }
    $priceDisplay.hidden = false;
    $priceBreakdown.textContent = T('breakdown', { nights: pricing.nights, from: formatDateHuman(result.checkIn), to: formatDateHuman(result.checkOut) });

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
    $btn.dataset.guests = String(result.totalGuests);
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
