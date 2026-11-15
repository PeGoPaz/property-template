const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { createPricing } = require('../js/pricing.js');
const bookingCore = require('../js/booking-core.js');

const property = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'property.json'), 'utf8'));
const pricing = createPricing(property.booking);

const day = (y, m, d) => new Date(y, m - 1, d);
const iso = (y, m, d) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

// A fixed "today" so validation tests don't depend on the wall clock.
const TODAY = day(2027, 5, 1);

function validate(opts) {
  return bookingCore.validateBooking(pricing, {
    checkInStr: null,
    checkOutStr: null,
    adults: 2,
    children: 0,
    today: TODAY,
    blockedDates: new Set(),
    ...opts,
  });
}

// ── Date utilities ──

test('formatDateISO zero-pads month and day', () => {
  assert.equal(bookingCore.formatDateISO(day(2027, 1, 5)), '2027-01-05');
  assert.equal(bookingCore.formatDateISO(day(2027, 12, 31)), '2027-12-31');
});

test('parseDate builds a local-midnight Date', () => {
  const d = bookingCore.parseDate('2027-05-14');
  assert.equal(d.getFullYear(), 2027);
  assert.equal(d.getMonth(), 4);
  assert.equal(d.getDate(), 14);
  assert.equal(bookingCore.parseDate(''), null);
  assert.equal(bookingCore.parseDate(null), null);
});

test('nightCount counts whole nights between two dates', () => {
  assert.equal(bookingCore.nightCount(day(2027, 5, 1), day(2027, 5, 4)), 3);
  assert.equal(bookingCore.nightCount(day(2027, 5, 1), day(2027, 5, 1)), 0);
});

// ── Pricing ──

test('calculatePrice sums each night by its own season', () => {
  // 30 Apr (180) + 1 May (200) + 2 May (200) = 580 across a season boundary.
  const r = bookingCore.calculatePrice(pricing, day(2027, 4, 30), day(2027, 5, 3));
  assert.equal(r.closedSeason, false);
  assert.equal(r.nights, 3);
  assert.equal(r.total, 580);
  assert.deepEqual(r.breakdown, [
    { date: '2027-04-30', rate: 180 },
    { date: '2027-05-01', rate: 200 },
    { date: '2027-05-02', rate: 200 },
  ]);
});

test('calculatePrice flags a night in a closed season', () => {
  // 31 Oct (180) then 1 Nov (closed) — the whole stay is invalid.
  const r = bookingCore.calculatePrice(pricing, day(2027, 10, 31), day(2027, 11, 2));
  assert.equal(r.closedSeason, true);
  assert.equal(r.total, 0);
  assert.equal(r.nights, 0);
});

test('isOperationalDate is true only inside a season', () => {
  assert.equal(bookingCore.isOperationalDate(pricing, day(2027, 5, 1)), true);
  assert.equal(bookingCore.isOperationalDate(pricing, day(2027, 11, 1)), false);
});

// ── Validation ──

test('missing dates are rejected before anything else', () => {
  assert.deepEqual(validate({ checkInStr: null, checkOutStr: null }), { ok: false, reason: 'no-dates' });
  assert.deepEqual(validate({ checkInStr: '2027-05-01', checkOutStr: null }), { ok: false, reason: 'no-dates' });
});

test('a check-in before today is rejected', () => {
  const r = validate({ checkInStr: iso(2027, 4, 30), checkOutStr: iso(2027, 5, 3) });
  assert.equal(r.ok, false);
  assert.equal(r.reason, 'past-date');
});

test('check-out must be after check-in', () => {
  const r = validate({ checkInStr: iso(2027, 5, 3), checkOutStr: iso(2027, 5, 3) });
  assert.equal(r.reason, 'bad-order');
});

test('a stay shorter than minNights is rejected', () => {
  const r = validate({ checkInStr: iso(2027, 5, 1), checkOutStr: iso(2027, 5, 3) });
  assert.equal(r.reason, 'min-stay');
  assert.equal(r.nights, 2);
});

test('a check-in in a closed season is rejected', () => {
  const r = validate({ checkInStr: iso(2027, 11, 1), checkOutStr: iso(2027, 11, 4) });
  assert.equal(r.reason, 'closed-season');
});

test('a stay crossing into a closed season is rejected', () => {
  // 30 Oct is in season, 1 Nov is not.
  const r = validate({ checkInStr: iso(2027, 10, 30), checkOutStr: iso(2027, 11, 2) });
  assert.equal(r.reason, 'cross-season');
});

test('zero guests are rejected', () => {
  const r = validate({ adults: 0, children: 0, checkInStr: iso(2027, 5, 1), checkOutStr: iso(2027, 5, 4) });
  assert.equal(r.reason, 'min-guests');
});

test('more guests than maxGuests are rejected', () => {
  const r = validate({ adults: 9, children: 0, checkInStr: iso(2027, 5, 1), checkOutStr: iso(2027, 5, 4) });
  assert.equal(r.reason, 'max-guests');
});

test('children without an adult are rejected', () => {
  const r = validate({ adults: 0, children: 2, checkInStr: iso(2027, 5, 1), checkOutStr: iso(2027, 5, 4) });
  assert.equal(r.reason, 'adult-required');
});

test('a blocked date in the stay is a conflict', () => {
  const r = validate({
    checkInStr: iso(2027, 5, 1),
    checkOutStr: iso(2027, 5, 4),
    blockedDates: new Set(['2027-05-02']),
  });
  assert.equal(r.reason, 'conflict');
  assert.equal(bookingCore.formatDateISO(r.conflictDate), '2027-05-02');
});

test('a blocked check-in day is a conflict', () => {
  const r = validate({
    checkInStr: iso(2027, 5, 1),
    checkOutStr: iso(2027, 5, 4),
    blockedDates: new Set(['2027-05-01']),
  });
  assert.equal(r.reason, 'conflict');
  assert.equal(bookingCore.formatDateISO(r.conflictDate), '2027-05-01');
});

test('a valid booking returns the price and guest totals', () => {
  const r = validate({ checkInStr: iso(2027, 5, 1), checkOutStr: iso(2027, 5, 4), adults: 2, children: 1 });
  assert.equal(r.ok, true);
  assert.equal(r.nights, 3);
  assert.equal(r.totalGuests, 3);
  assert.equal(r.pricing.total, 600); // 3 nights in May at 200
  assert.equal(r.pricing.closedSeason, false);
});
