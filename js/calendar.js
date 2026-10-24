/**
 * Availability calendar widget
 * Renders months with availability from the iCal feed.
 * Dispatches a CustomEvent when selection changes.
 *
 * Usage: container div must have id="availability-calendar".
 * Fires: 'dateselected' on the container with detail: { checkin, checkout }
 * Reads: window.blockedDates, window.availabilityLoaded (set by booking.js)
 */

(function () {
  'use strict';

  const $container = document.getElementById('availability-calendar');
  if (!$container) return;

  // ──────────────────────────────────────────────
  // STATE
  // ──────────────────────────────────────────────

  let viewMonth = new Date();         // first month displayed
  viewMonth.setDate(1);

  const MODE_CHECKIN  = 'checkin';
  const MODE_CHECKOUT = 'checkout';

  let selectionState = MODE_CHECKIN;  // what the next click selects
  let focusAfterRender = null;        // dateKey to re-focus after render()
  let activeKey = null;               // dateKey of the calendar's one tab stop
  let checkinDate  = null;            // Date objects (local midnight)
  let checkoutDate = null;

  // i18n: dictionaries provided by js/i18n.js (must load first).
  // Falls back to English if i18n.js is missing.
  const I18N = window.SITE_I18N || null;
  const T = I18N ? I18N.t : function (key) { return key; };

  const MONTHS = I18N ? I18N.months :
                 ['January','February','March','April','May','June',
                  'July','August','September','October','November','December'];
  const DAYS   = I18N ? I18N.days : ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  // Seasons come from js/pricing.js (property.json → booking.seasons).
  const PRICING = window.SITE_PRICING;

  // ──────────────────────────────────────────────
  // DATE HELPERS
  // ──────────────────────────────────────────────

  const today = (() => { const d = new Date(); d.setHours(0,0,0,0); return d; })();

  function dateKey(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function isPast(d) { return d < today; }

  function isClosedSeason(d) {
    return PRICING.rateFor(d) === null;
  }

  function isBlocked(d) {
    // window.blockedDates is a Set maintained by booking.js
    return window.blockedDates !== undefined && window.blockedDates.has(dateKey(d));
  }

  /**
   * A check-out day is not a night, so booked and off-season days are still
   * valid to leave on — but only if every night up to it is free, otherwise the
   * stay would span someone else's booking.
   */
  function isCheckoutCandidate(d) {
    if (selectionState !== MODE_CHECKOUT || checkinDate === null) return false;
    if (isPast(d) || d <= checkinDate) return false;

    const night = new Date(checkinDate);
    while (night < d) {
      if (isBlocked(night) || isClosedSeason(night)) return false;
      night.setDate(night.getDate() + 1);
    }
    return true;
  }

  function sameDay(a, b) {
    return a && b && a.getFullYear() === b.getFullYear()
      && a.getMonth() === b.getMonth()
      && a.getDate() === b.getDate();
  }

  function daysBetween(a, b) {
    return Math.round((b - a) / 86400000);
  }

  /** Returns Date for the Monday-based month grid start. */
  function monthGridStart(year, month) {
    const first = new Date(year, month, 1);
    const dow = (first.getDay() + 6) % 7; // Monday = 0
    const start = new Date(first);
    start.setDate(first.getDate() - dow);
    return start;
  }

  // ──────────────────────────────────────────────
  // RENDERING
  // ──────────────────────────────────────────────

  function render() {
    $container.innerHTML = '';

    // Header with navigation
    const header = document.createElement('div');
    header.className = 'cal-header';

    const prevBtn = document.createElement('button');
    prevBtn.className = 'cal-nav-btn';
    prevBtn.innerHTML = '&lsaquo;';
    prevBtn.setAttribute('aria-label', T('prevMonth'));

    const title = document.createElement('div');
    title.className = 'cal-title';
    const m2Month = (viewMonth.getMonth() + 1) % 12;
    const m2Year  = viewMonth.getMonth() === 11 ? viewMonth.getFullYear() + 1 : viewMonth.getFullYear();
    title.textContent = `${MONTHS[viewMonth.getMonth()]} ${viewMonth.getFullYear()} — ${MONTHS[m2Month]} ${m2Year}`;

    const nextBtn = document.createElement('button');
    nextBtn.className = 'cal-nav-btn';
    nextBtn.innerHTML = '&rsaquo;';
    nextBtn.setAttribute('aria-label', T('nextMonth'));

    header.appendChild(prevBtn);
    header.appendChild(title);
    header.appendChild(nextBtn);
    $container.appendChild(header);

    prevBtn.onclick = () => { viewMonth.setMonth(viewMonth.getMonth() - 1); render(); };
    nextBtn.onclick = () => { viewMonth.setMonth(viewMonth.getMonth() + 1); render(); };

    // Two-month grid
    const monthsWrap = document.createElement('div');
    monthsWrap.className = 'cal-months';

    for (let offset = 0; offset < 2; offset++) {
      const ym = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + offset, 1);
      monthsWrap.appendChild(renderMonth(ym.getFullYear(), ym.getMonth()));
    }

    $container.appendChild(monthsWrap);

    // Legend
    const legend = document.createElement('div');
    legend.className = 'cal-legend';
    legend.innerHTML = `
      <span><i class="dot dot-available"></i> ${T('legendAvailable')}</span>
      <span><i class="dot dot-selected"></i> ${T('legendSelected')}</span>
      <span><i class="dot dot-range"></i> ${T('legendInRange')}</span>
      <span><i class="dot dot-blocked"></i> ${T('legendBooked')}</span>
      <span><i class="dot dot-closed"></i> ${T('legendClosed')}</span>
    `;
    $container.appendChild(legend);

    if (!window.availabilityLoaded) {
      const note = document.createElement('div');
      note.className = 'cal-loading';
      note.textContent = T('loading');
      $container.appendChild(note);
    } else if (!window.availabilityHasData) {
      const warn = document.createElement('div');
      warn.className = 'cal-warning';
      warn.setAttribute('role', 'alert');
      warn.textContent = T('calLoadFailed');
      $container.appendChild(warn);
    }

    // One tab stop for the whole calendar (roving tabindex): the day last
    // moved to, else the check-in, else the first day that can be picked.
    // Arrow keys move between days, so Tab steps past the calendar in one
    // press instead of one per day.
    const stop = (activeKey && $container.querySelector(`[data-date="${activeKey}"]`))
      || $container.querySelector('.cal-cell.selected')
      || $container.querySelector('.cal-cell[data-date]:not([aria-disabled])')
      || $container.querySelector('.cal-cell[data-date]');
    if (stop) {
      stop.tabIndex = 0;
      activeKey = stop.dataset.date;
    }

    // Restore focus after the rebuild.
    if (focusAfterRender) {
      const target = $container.querySelector(`[data-date="${focusAfterRender}"]`);
      focusAfterRender = null;
      if (target) target.focus();
    }
  }

  function renderMonth(year, month) {
    const wrap = document.createElement('div');
    wrap.className = 'cal-month';

    const label = document.createElement('div');
    label.className = 'cal-month-label';
    label.textContent = `${MONTHS[month]} ${year}`;
    wrap.appendChild(label);

    // Day names
    const dayNames = document.createElement('div');
    dayNames.className = 'cal-week';
    DAYS.forEach(d => {
      const dn = document.createElement('div');
      dn.className = 'cal-dayname';
      dn.textContent = d;
      dayNames.appendChild(dn);
    });
    wrap.appendChild(dayNames);

    // Cell grid (6 weeks × 7 days covers any month)
    const days = document.createElement('div');
    days.className = 'cal-days';

    const start = monthGridStart(year, month);
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    for (let i = 0; i < 42; i++) {
      const cellDate = new Date(start);
      cellDate.setDate(start.getDate() + i);

      const cell = document.createElement('div');
      cell.className = 'cal-cell';

      if (cellDate.getMonth() !== month) {
        cell.classList.add('out-of-month');
      } else {
        cell.innerHTML = `<span class="cal-daynum">${cellDate.getDate()}</span>`;

        let selectable = false;

        if (isPast(cellDate)) {
          cell.classList.add('past');
        } else if (isBlocked(cellDate) || isClosedSeason(cellDate)) {
          const reason = isBlocked(cellDate) ? 'alreadyBooked' : 'closedTooltip';
          cell.classList.add(isBlocked(cellDate) ? 'blocked' : 'closed');
          cell.title = T(reason);
          cell.setAttribute('aria-label', dayLabel(cellDate) + ' — ' + T(reason));

          // Recomputed each render, so these go inert once a range is set.
          if (isCheckoutCandidate(cellDate)) {
            cell.classList.add('checkout-eligible');
            cell.title = T('checkoutOnly');
            selectable = true;
          }
        } else {
          cell.classList.add('available');
          selectable = true;

          // Highlight selected range
          if (sameDay(cellDate, checkinDate) || sameDay(cellDate, checkoutDate)) {
            cell.classList.add('selected');
          } else if (checkinDate && checkoutDate
            && cellDate > checkinDate && cellDate < checkoutDate) {
            cell.classList.add('in-range');
          }
        }

        if (selectable) {
          makeSelectable(cell, cellDate);
        } else if (!isPast(cellDate)) {
          // Booked and closed days can be reached with the arrow keys, so
          // their reason is read out, but not picked.
          cell.setAttribute('role', 'button');
          cell.setAttribute('aria-disabled', 'true');
          cell.tabIndex = -1;
          cell.dataset.date = dateKey(cellDate);
        }
      }

      days.appendChild(cell);
    }

    wrap.appendChild(days);
    return wrap;
  }

  // ──────────────────────────────────────────────
  // INTERACTION
  // ──────────────────────────────────────────────

  /** Cells are <div>s, so the button role and key handling are explicit. */
  function makeSelectable(cell, cellDate) {
    const picked = new Date(cellDate);

    cell.setAttribute('role', 'button');
    cell.tabIndex = -1; // render() makes one day the tab stop
    cell.setAttribute('aria-label', describeDate(picked));
    cell.dataset.date = dateKey(picked);

    function activate() {
      focusAfterRender = activeKey = dateKey(picked); // render() rebuilds every cell
      handleDateClick(new Date(picked));
    }

    cell.addEventListener('click', activate);
    cell.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
        e.preventDefault();
        activate();
      }
    });
  }

  // Arrow keys move a day or a week, Home and End to the ends of the week,
  // Page Up and Page Down a month. The two-month view follows the focus.
  function moveFocus(from, key) {
    const d = new Date(from);
    const weekday = (d.getDay() + 6) % 7; // Monday = 0
    switch (key) {
      case 'ArrowLeft':  d.setDate(d.getDate() - 1); break;
      case 'ArrowRight': d.setDate(d.getDate() + 1); break;
      case 'ArrowUp':    d.setDate(d.getDate() - 7); break;
      case 'ArrowDown':  d.setDate(d.getDate() + 7); break;
      case 'Home':       d.setDate(d.getDate() - weekday); break;
      case 'End':        d.setDate(d.getDate() + 6 - weekday); break;
      case 'PageUp':
      case 'PageDown': {
        // The same day a month away, or that month's last day: 31 March goes
        // to 28 February, where setMonth alone would land on 3 March.
        const day = d.getDate();
        d.setDate(1);
        d.setMonth(d.getMonth() + (key === 'PageUp' ? -1 : 1));
        d.setDate(Math.min(day, new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()));
        break;
      }
      default: return false;
    }
    const target = isPast(d) ? new Date(today) : d;
    activeKey = focusAfterRender = dateKey(target);

    const first = new Date(viewMonth.getFullYear(), viewMonth.getMonth(), 1);
    const afterLast = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 2, 1);
    if (target < first) viewMonth = new Date(target.getFullYear(), target.getMonth(), 1);
    else if (target >= afterLast) viewMonth = new Date(target.getFullYear(), target.getMonth() - 1, 1);
    render();
    return true;
  }

  $container.addEventListener('keydown', function (e) {
    const cell = e.target.closest('.cal-cell[data-date]');
    if (!cell || e.altKey || e.ctrlKey || e.metaKey) return;
    const [y, m, d] = cell.dataset.date.split('-').map(Number);
    if (moveFocus(new Date(y, m - 1, d), e.key)) e.preventDefault();
  });

  function dayLabel(d) {
    return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  }

  function describeDate(d) {
    if (isBlocked(d) || isClosedSeason(d)) return `${dayLabel(d)} — ${T('checkoutOnly')}`;
    return dayLabel(d);
  }

  function handleDateClick(d) {
    if (selectionState === MODE_CHECKIN) {
      checkinDate = d;
      checkoutDate = null;
      selectionState = MODE_CHECKOUT;
    } else {
      // User clicked checkout date
      if (d <= checkinDate) {
        // Clicked before check-in: treat as new check-in
        checkinDate = d;
        checkoutDate = null;
        selectionState = MODE_CHECKOUT;
      } else {
        checkoutDate = d;
        selectionState = MODE_CHECKIN; // ready for new selection if they re-click
      }
    }
    render();
    emitSelection();
  }

  function emitSelection() {
    const detail = {
      checkin:  checkinDate  ? dateKey(checkinDate)  : null,
      checkout: checkoutDate ? dateKey(checkoutDate) : null,
    };
    $container.dispatchEvent(new CustomEvent('dateselected', { detail, bubbles: true }));
  }

  // ──────────────────────────────────────────────
  // REFRESH HOOK: re-render when booking.js updates blockedDates
  // ──────────────────────────────────────────────

  window.calendarRefresh = function () { render(); };

  // Initial render
  render();
})();
