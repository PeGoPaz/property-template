/**
 * Contact page
 * Reads URL parameters from the booking flow and auto-fills the inquiry form.
 */

(function () {
  'use strict';

  // ──────────────────────────────────────────────
  // PARSE URL PARAMETERS
  // ──────────────────────────────────────────────

  const params = new URLSearchParams(window.location.search);

  // i18n: dictionaries provided by js/i18n.js (must load first).
  // Falls back to English if i18n.js is missing.
  const I18N = window.SITE_I18N || null;
  const T = I18N ? I18N.t : function (key) { return key; };
  const LOCALE = I18N ? I18N.locale : 'en-US';
  // Set by js/property.js, which scripts/build.py generates from property.json.
  const EMAIL = (window.PROPERTY && window.PROPERTY.email) || '';
  const PRICING = window.SITE_PRICING;

  // ──────────────────────────────────────────────
  // VALIDATE URL PARAMETERS
  // These values come from the URL and are fully attacker-controlled
  // (anyone can craft a link). Only accept values in the exact shape we
  // produced, and reject anything else so a malicious link cannot inject
  // arbitrary content into the auto-filled inquiry.
  // ──────────────────────────────────────────────

  /** Return the value only if it matches YYYY-MM-DD and is a real date. */
  function validIsoDate(v) {
    if (!v || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return null;
    const [y, m, d] = v.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== d) return null;
    return v;
  }

  /** Return a bounded positive integer string, or null. */
  function validInt(v, min, max) {
    if (!v || !/^\d{1,7}$/.test(v)) return null;
    const n = Number(v);
    if (n < min || n > max) return null;
    return String(n);
  }

  const checkin    = validIsoDate(params.get('checkin'));
  const checkout   = validIsoDate(params.get('checkout'));
  const guests     = validInt(params.get('guests'), 1, PRICING.maxGuests);
  const price      = validInt(params.get('price'), 0, 1000000);
  const nights     = validInt(params.get('nights'), 1, 365);

  // ──────────────────────────────────────────────
  // DATE FORMATTING
  // ──────────────────────────────────────────────

  function formatHumanDate(isoStr) {
    if (!isoStr) return '';
    const parts = isoStr.split('-');
    const d = new Date(+parts[0], +parts[1] - 1, +parts[2]);
    return d.toLocaleDateString(LOCALE, {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  }

  // ──────────────────────────────────────────────
  // AUTO-FILL FORM & POPULATE HIDDEN FIELDS
  // ──────────────────────────────────────────────

  const $form     = document.getElementById('contact-form');
  const $name     = document.getElementById('form-name');
  const $email    = document.getElementById('form-email');
  const $message  = document.getElementById('form-message');
  const $feedback = document.getElementById('form-feedback');
  
  // Hidden booking data fields
  const $checkin  = document.getElementById('form-checkin');
  const $checkout = document.getElementById('form-checkout');
  const $guestsField = document.getElementById('form-guests');
  const $nightsField = document.getElementById('form-nights');
  const $priceField = document.getElementById('form-price');
  
  // Booking summary display
  const $summarySect = document.getElementById('booking-details-summary');
  const $summaryDates = document.getElementById('summary-dates');
  const $summaryGuests = document.getElementById('summary-guests');
  const $summaryNights = document.getElementById('summary-nights');
  const $summaryPrice = document.getElementById('summary-price');

  // If we have booking params, populate everything
  if (checkin && checkout && guests && price) {
    const checkinFormatted  = formatHumanDate(checkin);
    const checkoutFormatted = formatHumanDate(checkout);
    const priceFormatted    = PRICING.formatPrice(Number(price), LOCALE);

    // Populate hidden fields (for form submission)
    $checkin.value = checkin;
    $checkout.value = checkout;
    $guestsField.value = guests;
    $nightsField.value = nights;
    $priceField.value = price;

    // Show booking summary
    $summarySect.style.display = 'block';
    $summaryDates.textContent = `${checkinFormatted} → ${checkoutFormatted}`;
    $summaryGuests.textContent = `${guests} ${I18N ? I18N.plural(guests, 'guest', 'guests') : (guests === '1' ? 'guest' : 'guests')}`;
    $summaryNights.textContent = `${nights} ${I18N ? I18N.plural(nights, 'night', 'nights') : (nights === '1' ? 'night' : 'nights')}`;
    $summaryPrice.textContent = priceFormatted;

    // Populate message with booking details
    const messageText = T('msgTemplate', {
      checkin: checkinFormatted,
      checkout: checkoutFormatted,
      guests: guests,
      nights: nights,
      nightsWord: I18N ? I18N.plural(nights, 'night', 'nights') : (nights === '1' ? 'night' : 'nights'),
      price: priceFormatted,
    });

    $message.value = messageText;
  }

  // ──────────────────────────────────────────────
  // FORM SUBMISSION (Formspree / Web3Forms)
  // ──────────────────────────────────────────────

  function showFeedback(text, type) {
    $feedback.textContent = text;
    $feedback.className = `form-feedback visible ${type}`;
  }

  $form.addEventListener('submit', function (e) {
    e.preventDefault();

    const formData = new FormData($form);

    // ── Basic validation ──
    const name = formData.get('name');
    const email = formData.get('email');
    const message = formData.get('message');

    if (!name || name.trim().length < 2) {
      showFeedback(T('errName'), 'error');
      return;
    }

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      showFeedback(T('errEmail'), 'error');
      return;
    }

    if (!message || message.trim().length < 10) {
      showFeedback(T('errMessage'), 'error');
      return;
    }

    if (message.length > 5000) {
      showFeedback(T('errTooLong'), 'error');
      return;
    }

    // ── Honeypot anti-spam check ──
    // Bots fill every field; humans never see this one. If it's populated,
    // silently drop the submission.
    const honeypot = formData.get('company');
    if (honeypot) {
      showFeedback(T('sent'), 'success');
      $form.reset();
      return;
    }

    // ── Submit to Formspree ──
    const action = $form.getAttribute('action');

    // Check if Formspree is configured
    if (!action || action.includes('YOUR_FORM_ID')) {
      // Fallback: open mailto link
      const subject = encodeURIComponent(T('mailSubject'));
      const body = encodeURIComponent(
        `From: ${name} (${email})\n\n${message}`
      );
      window.location.href = `mailto:${EMAIL}?subject=${subject}&body=${body}`;
      showFeedback(T('openingMail'), 'success');
      return;
    }

    // Real Formspree submission
    const submitBtn = $form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = T('sending');

    fetch(action, {
      method: 'POST',
      body: formData,
      headers: { 'Accept': 'application/json' },
    })
      .then(function (response) {
        if (response.ok) {
          showFeedback(
            T('sentFull'),
            'success'
          );
          $form.reset();
        } else {
          return response.json().then(function (data) {
            showFeedback(
              data.errors ? data.errors.map(function (e) { return e.message; }).join(', ') : T('genericError'),
              'error'
            );
          });
        }
      })
      .catch(function () {
        showFeedback(T('networkError'), 'error');
      })
      .finally(function () {
        submitBtn.disabled = false;
        submitBtn.textContent = T('sendInquiry');
      });
  });

})();

