/**
 * Pure booking logic, extracted from booking.js so it can be unit-tested
 * without a DOM. booking.js keeps the DOM wiring (messages, button state,
 * price animation); this module holds the date, pricing and validation
 * decisions.
 *
 * Loaded before booking.js, which reads it as window.BOOKING_CORE.
 */

(function (root) {
  'use strict';

  function formatDateISO(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function parseDate(str) {
    if (!str) return null;
    const parts = str.split('-');
    return new Date(+parts[0], +parts[1] - 1, +parts[2]);
  }

  /** Count nights between two dates (whole days, DST-safe via rounding). */
  function nightCount(from, to) {
    return Math.round((to - from) / (1000 * 60 * 60 * 24));
  }

  /** True if the night starting on this date falls in a season. */
  function isOperationalDate(pricing, date) {
    return pricing.rateFor(date) !== null;
  }

  /**
   * Calculate total price by iterating each individual night.
   * A "night" is from check-in date D to D+1, priced by D's season.
   * Returns { total, nights, rateBreakdown[], closedSeason }.
   */
  function calculatePrice(pricing, checkIn, checkOut) {
    let total = 0;
    let nights = 0;
    const breakdown = [];

    const cursor = new Date(checkIn);
    while (cursor < checkOut) {
      const rate = pricing.rateFor(cursor);
      if (rate === null) {
        // Night falls in closed season — invalidate
        return { total: 0, nights: 0, breakdown: [], closedSeason: true };
      }
      total += rate;
      breakdown.push({ date: formatDateISO(cursor), rate: rate });
      nights++;
      cursor.setDate(cursor.getDate() + 1);
    }

    return { total, nights, breakdown, closedSeason: false };
  }

  /**
   * Run the full validation + pricing decision for a booking, returning a
   * structured result instead of touching the DOM. booking.js maps each
   * `reason` to a message and button label.
   *
   * opts: { checkInStr, checkOutStr, adults, children, today, blockedDates }
   *   today         a Date at local midnight (the earliest allowed check-in)
   *   blockedDates  a Set of 'YYYY-MM-DD' strings the guest cannot stay
   *
   * Returns { ok: false, reason } on failure, or
   *         { ok: true, checkIn, checkOut, nights, totalGuests, pricing }.
   */
  function validateBooking(pricing, opts) {
    const checkInStr = opts.checkInStr;
    const checkOutStr = opts.checkOutStr;
    const adults = opts.adults;
    const children = opts.children;
    const today = opts.today;
    const blockedDates = opts.blockedDates;

    const totalGuests = adults + children;

    if (!checkInStr || !checkOutStr) {
      return { ok: false, reason: 'no-dates' };
    }

    const checkIn = parseDate(checkInStr);
    const checkOut = parseDate(checkOutStr);

    if (checkIn < today) {
      return { ok: false, reason: 'past-date' };
    }

    if (checkOut <= checkIn) {
      return { ok: false, reason: 'bad-order' };
    }

    const nights = nightCount(checkIn, checkOut);

    if (nights < pricing.minNights) {
      return { ok: false, reason: 'min-stay', nights };
    }

    if (!isOperationalDate(pricing, checkIn)) {
      return { ok: false, reason: 'closed-season' };
    }

    // Every night must fall in a season.
    const cursor = new Date(checkIn);
    let inClosedSeason = false;
    while (cursor < checkOut) {
      if (!isOperationalDate(pricing, cursor)) {
        inClosedSeason = true;
        break;
      }
      cursor.setDate(cursor.getDate() + 1);
    }
    if (inClosedSeason) {
      return { ok: false, reason: 'cross-season' };
    }

    if (totalGuests < 1) {
      return { ok: false, reason: 'min-guests' };
    }

    if (totalGuests > pricing.maxGuests) {
      return { ok: false, reason: 'max-guests' };
    }

    if (adults < 1) {
      return { ok: false, reason: 'adult-required' };
    }

    const pricingResult = calculatePrice(pricing, checkIn, checkOut);

    if (pricingResult.closedSeason) {
      return { ok: false, reason: 'closed-nights' };
    }

    // Availability check (iCal blocked dates).
    const availCursor = new Date(checkIn);
    let conflictDate = null;
    while (availCursor < checkOut) {
      if (blockedDates.has(formatDateISO(availCursor))) {
        conflictDate = new Date(availCursor);
        break;
      }
      availCursor.setDate(availCursor.getDate() + 1);
    }
    // Check-in day itself is blocked for incoming guests.
    if (blockedDates.has(formatDateISO(checkIn))) {
      conflictDate = new Date(checkIn);
    }

    if (conflictDate) {
      return { ok: false, reason: 'conflict', conflictDate };
    }

    return {
      ok: true,
      checkIn: checkIn,
      checkOut: checkOut,
      nights: nights,
      totalGuests: totalGuests,
      pricing: pricingResult,
    };
  }

  const api = {
    formatDateISO: formatDateISO,
    parseDate: parseDate,
    nightCount: nightCount,
    isOperationalDate: isOperationalDate,
    calculatePrice: calculatePrice,
    validateBooking: validateBooking,
  };

  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.BOOKING_CORE = api;
  }
})(this);
