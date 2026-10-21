const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { createPricing } = require('../js/pricing.js');

const property = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'property.json'), 'utf8'));
const day = (y, m, d) => new Date(y, m - 1, d);

test('season ends are inclusive', () => {
  const pricing = createPricing(property.booking);
  assert.equal(pricing.rateFor(day(2027, 3, 31)), null);
  assert.equal(pricing.rateFor(day(2027, 4, 1)), 180);
  assert.equal(pricing.rateFor(day(2027, 6, 30)), 240);
  assert.equal(pricing.rateFor(day(2027, 7, 1)), 280);
  assert.equal(pricing.rateFor(day(2027, 8, 31)), 280);
  assert.equal(pricing.rateFor(day(2027, 10, 31)), 180);
  assert.equal(pricing.rateFor(day(2027, 11, 1)), null);
});

test('a season can run over New Year', () => {
  const pricing = createPricing({
    currency: 'EUR',
    seasons: [{ from: '12-15', to: '01-10', nightly: 300 }],
  });
  assert.equal(pricing.rateFor(day(2026, 12, 14)), null);
  assert.equal(pricing.rateFor(day(2026, 12, 15)), 300);
  assert.equal(pricing.rateFor(day(2026, 12, 31)), 300);
  assert.equal(pricing.rateFor(day(2027, 1, 1)), 300);
  assert.equal(pricing.rateFor(day(2027, 1, 10)), 300);
  assert.equal(pricing.rateFor(day(2027, 1, 11)), null);
});

test('half-month seasons, as Villa Caterina prices June', () => {
  const pricing = createPricing({
    currency: 'EUR',
    seasons: [
      { from: '06-01', to: '06-15', nightly: 600 },
      { from: '06-16', to: '06-30', nightly: 650 },
    ],
  });
  assert.equal(pricing.rateFor(day(2027, 6, 15)), 600);
  assert.equal(pricing.rateFor(day(2027, 6, 16)), 650);
});

test('leap day falls in the season around it', () => {
  const pricing = createPricing({ currency: 'EUR', seasons: [{ from: '02-01', to: '02-29', nightly: 90 }] });
  assert.equal(pricing.rateFor(day(2028, 2, 29)), 90);
  assert.equal(pricing.rateFor(day(2027, 3, 1)), null);
});

test('stay limits pass through', () => {
  const pricing = createPricing(property.booking);
  assert.equal(pricing.minNights, property.booking.minNights);
  assert.equal(pricing.maxGuests, property.booking.maxGuests);
});

test('prices are whole amounts in the property currency', () => {
  assert.equal(createPricing({ currency: 'EUR' }).formatPrice(1720, 'en-US'), '€1,720');
  assert.equal(createPricing({ currency: 'GBP' }).formatPrice(950, 'en-GB'), '£950');
  // German puts the sign after the amount, with a non-breaking space.
  assert.equal(createPricing({ currency: 'EUR' }).formatPrice(1720, 'de-DE'), '1.720 €');
});
