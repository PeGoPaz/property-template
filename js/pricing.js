/**
 * Seasonal pricing and stay rules, shared by booking.js, calendar.js and
 * contact.js. Reads the `booking` block of property.json via js/property.js.
 *
 *   seasons: [{ from: 'MM-DD', to: 'MM-DD', nightly: 180 }, …]
 *
 * Both ends of a season are inclusive and repeat every year. A season whose
 * `from` is later than its `to` runs over New Year (e.g. '12-15' to '01-10').
 * The night starting on 14 May is priced by the season that contains 14 May;
 * a night in no season is closed. scripts/build.py rejects overlapping seasons.
 */

(function (root) {
  'use strict';

  function monthDay(date) {
    return String(date.getMonth() + 1).padStart(2, '0') + '-' +
           String(date.getDate()).padStart(2, '0');
  }

  // 'MM-DD' strings sort the same way as the dates they name.
  function inSeason(md, season) {
    return season.from <= season.to
      ? md >= season.from && md <= season.to
      : md >= season.from || md <= season.to;
  }

  function createPricing(booking) {
    const seasons = booking.seasons || [];

    return {
      minNights: booking.minNights,
      maxGuests: booking.maxGuests,
      currency: booking.currency,

      /** Rate for the night starting on `date`, or null when the property is closed. */
      rateFor: function (date) {
        const md = monthDay(date);
        for (let i = 0; i < seasons.length; i++) {
          if (inSeason(md, seasons[i])) return seasons[i].nightly;
        }
        return null;
      },

      /** Whole amounts in the property's currency, written the page language's way. */
      formatPrice: function (amount, locale) {
        return new Intl.NumberFormat(locale, {
          style: 'currency',
          currency: booking.currency,
          minimumFractionDigits: 0,
          maximumFractionDigits: 0,
        }).format(amount);
      },
    };
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = { createPricing: createPricing };
  } else {
    root.SITE_PRICING = createPricing((root.PROPERTY && root.PROPERTY.booking) || {});
  }
})(this);
