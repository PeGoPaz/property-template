const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { createPricing } = require('../js/pricing.js');
const CAL = require('../js/calendar-core.js');

const property = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'property.json'), 'utf8'));
const pricing = createPricing(property.booking);

const day = (y, m, d) => new Date(y, m - 1, d);
const iso = (y, m, d) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

// A fixed "today" so calendar tests don't depend on the wall clock.
const TODAY = day(2027, 5, 1);

function candidateCtx(d, overrides) {
  return {
    mode: CAL.MODE_CHECKIN,
    checkinDate: TODAY,
    pricing: pricing,
    blockedDates: new Set(),
    today: TODAY,
    ...overrides,
  };
}

// ── Date helpers ──

test('dateKey zero-pads month and day', () => {
  assert.equal(CAL.dateKey(day(2027, 1, 5)), '2027-01-05');
  assert.equal(CAL.dateKey(day(2027, 12, 31)), '2027-12-31');
});

test('sameDay ignores time of day', () => {
  assert.equal(CAL.sameDay(day(2027, 5, 1), day(2027, 5, 1)), true);
  assert.equal(CAL.sameDay(day(2027, 5, 1), day(2027, 5, 2)), false);
  // Falsy inputs are not a day, so it returns null rather than crashing.
  assert.equal(CAL.sameDay(null, day(2027, 5, 1)), null);
  assert.equal(CAL.sameDay(day(2027, 5, 1), null), null);
});

test('monthGridStart lands on the Monday on or before the 1st', () => {
  // 1 Oct 2026 is a Thursday, so the grid starts Monday 28 Sep 2026.
  const start = CAL.monthGridStart(2026, 9);
  assert.equal(CAL.dateKey(start), '2026-09-28');
  // 1 Feb 2027 is a Monday, so the grid starts on the 1st itself.
  assert.equal(CAL.dateKey(CAL.monthGridStart(2027, 1)), '2027-02-01');
});

// ── Month navigation (Page Up / Page Down) ──

test('monthDelta clamps to the target month last day', () => {
  // 31 March back one month lands on 28 February, not 3 March.
  const feb = CAL.monthDelta(day(2027, 3, 31), -1);
  assert.equal(CAL.dateKey(feb), '2027-02-28');
  // 15 Jul forward one month stays in August.
  const aug = CAL.monthDelta(day(2027, 7, 15), 1);
  assert.equal(CAL.dateKey(aug), '2027-08-15');
  // Year boundary: December forward lands in January of the next year.
  const jan = CAL.monthDelta(day(2026, 12, 20), 1);
  assert.equal(CAL.dateKey(jan), '2027-01-20');
});

// ── Checkout eligibility ──

test('isCheckoutCandidate is false while picking check-in', () => {
  assert.equal(CAL.isCheckoutCandidate(day(2027, 5, 3), candidateCtx()), false);
});

test('isCheckoutCandidate allows a closed (off-season) departure day', () => {
  // 30 Oct is the last in-season night; 1 Nov is off-season but is not a night.
  const ctx = candidateCtx(day(2027, 11, 1), {
    mode: CAL.MODE_CHECKOUT,
    checkinDate: day(2027, 10, 28),
  });
  assert.equal(CAL.isCheckoutCandidate(day(2027, 11, 1), ctx), true);
});

test('isCheckoutCandidate is false when a night in the range is closed', () => {
  // Check-in 30 Oct, check-out 2 Nov: the night of 1 Nov is closed.
  const ctx = candidateCtx(day(2027, 11, 2), {
    mode: CAL.MODE_CHECKOUT,
    checkinDate: day(2027, 10, 30),
  });
  assert.equal(CAL.isCheckoutCandidate(day(2027, 11, 2), ctx), false);
});

test('isCheckoutCandidate is false when a night in the range is blocked', () => {
  const ctx = candidateCtx(day(2027, 5, 5), {
    mode: CAL.MODE_CHECKOUT,
    checkinDate: day(2027, 5, 1),
    blockedDates: new Set([iso(2027, 5, 3)]),
  });
  assert.equal(CAL.isCheckoutCandidate(day(2027, 5, 5), ctx), false);
});

test('isCheckoutCandidate is false at or before check-in and in the past', () => {
  const checkoutCtx = { mode: CAL.MODE_CHECKOUT, checkinDate: day(2027, 5, 3) };
  assert.equal(CAL.isCheckoutCandidate(day(2027, 5, 3), candidateCtx(null, checkoutCtx)), false);
  assert.equal(CAL.isCheckoutCandidate(day(2027, 5, 2), candidateCtx(null, checkoutCtx)), false);
  assert.equal(CAL.isCheckoutCandidate(day(2027, 4, 30), candidateCtx(null, checkoutCtx)), false);
});

// ── Selection state machine ──

test('first click selects check-in and waits for a check-out', () => {
  const sel = CAL.createSelection();
  const s1 = sel.click(day(2027, 5, 3));
  assert.equal(s1.mode, CAL.MODE_CHECKOUT);
  assert.equal(CAL.dateKey(s1.checkinDate), '2027-05-03');
  assert.equal(s1.checkoutDate, null);
});

test('a later click completes the range and returns to check-in mode', () => {
  const sel = CAL.createSelection();
  sel.click(day(2027, 5, 3));
  const s2 = sel.click(day(2027, 5, 8));
  assert.equal(s2.mode, CAL.MODE_CHECKIN);
  assert.equal(CAL.dateKey(s2.checkinDate), '2027-05-03');
  assert.equal(CAL.dateKey(s2.checkoutDate), '2027-05-08');
});

test('clicking at or before check-in restarts as a new check-in', () => {
  const sel = CAL.createSelection();
  sel.click(day(2027, 5, 3));
  const s2 = sel.click(day(2027, 5, 3)); // the check-in day itself
  assert.equal(s2.mode, CAL.MODE_CHECKOUT);
  assert.equal(CAL.dateKey(s2.checkinDate), '2027-05-03');
  assert.equal(s2.checkoutDate, null);

  const s3 = sel.click(day(2027, 5, 1)); // before the current check-in
  assert.equal(s3.mode, CAL.MODE_CHECKOUT);
  assert.equal(CAL.dateKey(s3.checkinDate), '2027-05-01');
  assert.equal(s3.checkoutDate, null);
});

test('after a completed range the next click starts a fresh check-in', () => {
  const sel = CAL.createSelection();
  sel.click(day(2027, 5, 3));
  sel.click(day(2027, 5, 8));   // completes the range, back to check-in
  const s3 = sel.click(day(2027, 6, 1));
  assert.equal(s3.mode, CAL.MODE_CHECKOUT);
  assert.equal(CAL.dateKey(s3.checkinDate), '2027-06-01');
  assert.equal(s3.checkoutDate, null);
});