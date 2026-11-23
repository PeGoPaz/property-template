/**
 * Pure calendar logic, extracted from calendar.js so it can be unit-tested
 * without a DOM. calendar.js keeps the rendering and keyboard wiring; this
 * module holds the date arithmetic and the check-in / check-out selection
 * state machine.
 *
 * Loaded before calendar.js, which reads it as window.CALENDAR_CORE.
 */

(function (root) {
  'use strict';

  var MODE_CHECKIN = 'checkin';
  var MODE_CHECKOUT = 'checkout';

  function dateKey(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function sameDay(a, b) {
    return a && b && a.getFullYear() === b.getFullYear()
      && a.getMonth() === b.getMonth()
      && a.getDate() === b.getDate();
  }

  function daysBetween(a, b) {
    return Math.round((b - a) / 86400000);
  }

  function isPast(d, today) {
    return d < today;
  }

  function isClosedSeason(d, pricing) {
    return pricing && pricing.rateFor(d) === null;
  }

  /** True if the date key is present in the blocked-dates set. */
  function isBlocked(d, blockedDates) {
    return blockedDates !== undefined && blockedDates.has(dateKey(d));
  }

  /**
   * Returns Date for the Monday-based month grid start, the top-left cell of
   * the 6x7 grid rendered for the given year/month (Monday = first weekday).
   */
  function monthGridStart(year, month) {
    const first = new Date(year, month, 1);
    const dow = (first.getDay() + 6) % 7; // Monday = 0
    const start = new Date(first);
    start.setDate(first.getDate() - dow);
    return start;
  }

  /**
   * A check-out day is not a night, so booked and off-season days are still
   * valid to leave on — but only if every night up to it is free, otherwise
   * the stay would span someone else's booking.
   *
   * ctx: { mode, checkinDate, pricing, blockedDates, today }
   */
  function isCheckoutCandidate(d, ctx) {
    const { mode, checkinDate, pricing, blockedDates, today } = ctx;
    if (mode !== MODE_CHECKOUT || checkinDate === null) return false;
    if (d < today || d <= checkinDate) return false;

    const night = new Date(checkinDate);
    while (night < d) {
      if (isBlocked(night, blockedDates) || isClosedSeason(night, pricing)) return false;
      night.setDate(night.getDate() + 1);
    }
    return true;
  }

  /**
   * Arrow-key month navigation must clamp to the target month's last day:
   * 31 March goes to 28 February, where Date.setMonth alone would land on
   * 3 March. Positive delta = forward.
   */
  function monthDelta(d, delta) {
    const day = d.getDate();
    const res = new Date(d);
    res.setDate(1);
    res.setMonth(res.getMonth() + delta);
    res.setDate(Math.min(day, new Date(res.getFullYear(), res.getMonth() + 1, 0).getDate()));
    return res;
  }

  /**
   * The check-in / check-out selection state machine. `click(date)` returns
   * the next state: { mode, checkinDate, checkoutDate }. A Date at or before
   * the check-in while picking a check-out restarts as a new check-in.
   */
  function createSelection() {
    let mode = MODE_CHECKIN;
    let checkinDate = null;
    let checkoutDate = null;

    function click(d) {
      if (mode === MODE_CHECKIN) {
        checkinDate = d;
        checkoutDate = null;
        mode = MODE_CHECKOUT;
      } else {
        // User clicked the check-out date.
        if (checkinDate !== null && d <= checkinDate) {
          // Clicked at or before check-in: treat as a new check-in.
          checkinDate = d;
          checkoutDate = null;
          mode = MODE_CHECKOUT;
        } else {
          checkoutDate = d;
          mode = MODE_CHECKIN; // ready for a new selection if they re-click
        }
      }
      return { mode: mode, checkinDate: checkinDate, checkoutDate: checkoutDate };
    }

    function getState() {
      return { mode: mode, checkinDate: checkinDate, checkoutDate: checkoutDate };
    }

    return { click: click, getState: getState };
  }

  const api = {
    MODE_CHECKIN: MODE_CHECKIN,
    MODE_CHECKOUT: MODE_CHECKOUT,
    dateKey: dateKey,
    sameDay: sameDay,
    daysBetween: daysBetween,
    isPast: isPast,
    isClosedSeason: isClosedSeason,
    isBlocked: isBlocked,
    monthGridStart: monthGridStart,
    monthDelta: monthDelta,
    isCheckoutCandidate: isCheckoutCandidate,
    createSelection: createSelection,
  };

  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.CALENDAR_CORE = api;
  }
})(this);