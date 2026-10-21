/**
 * UI string dictionaries.
 * Language is selected from the page's <html lang="…"> attribute.
 * Loaded BEFORE booking.js / calendar.js / contact.js, which read window.SITE_I18N.
 * {property} in any string becomes the property's name from js/property.js.
 *
 * Review texts carry their own translations in js/reviews.js.
 */

(function () {
  'use strict';

  const DICTS = {

    en: {
      locale: 'en-US',
      months: ['January','February','March','April','May','June',
               'July','August','September','October','November','December'],
      days: ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],
      night: 'night', nights: 'nights',
      guest: 'guest', guests: 'guests',

      // Calendar widget
      legendAvailable: 'Available',
      legendSelected: 'Selected',
      legendInRange: 'In Range',
      legendBooked: 'Booked',
      legendClosed: 'Closed Season',
      prevMonth: 'Previous month',
      nextMonth: 'Next month',
      loading: 'Loading availability...',
      calLoadFailed: '⚠ Live availability could not be loaded. Some dates shown as available may already be booked.',
      alreadyBooked: 'Already booked',
      checkoutOnly: 'Available as a check-out date only',
      closedTooltip: 'Closed on this date',

      // Booking engine
      btnSelectDates: 'Select Dates',
      btnInvalidDates: 'Invalid Dates',
      btnTooShort: 'Too Short',
      btnClosedSeason: 'Closed Season',
      btnInvalid: 'Invalid',
      btnTooManyGuests: 'Too Many Guests',
      btnUnavailable: 'Unavailable',
      btnRequestStay: 'Request This Stay',
      msgFutureDate: 'Check-in date must be in the future.',
      msgOrder: 'Check-out must be after check-in.',
      msgMinStay: 'Minimum stay is {min} nights. Your selection: {n} {nightsWord}.',
      msgOpenSeason: 'The property is closed on your check-in date.',
      msgCrossSeason: 'Your stay includes nights when the property is closed. Please adjust dates.',
      msgClosedNights: 'Your stay includes nights in the closed season.',
      msgMinGuest: 'Please enter at least 1 guest.',
      msgMaxGuests: 'Maximum {max} guests total (adults + children).',
      msgAdultRequired: 'At least 1 adult is required.',
      msgConflict: 'These dates conflict with an existing booking ({date}). Please choose different dates.',
      msgStillLoading: '⚠ Availability data is still loading. Your selected dates may already be booked.',
      msgLoadFailed: '⚠ Live availability could not be loaded. Your selected dates may already be booked — we will confirm by email.',
      breakdown: '{nights} nights · {from} → {to}',
      hintCheckin: 'Click a check-in date.',
      hintCheckout: 'Check-in: {date}. Now click check-out.',
      hintRange: '{from} → {to} ({nights} nights)',

      // Contact form
      errName: 'Please enter your name.',
      errEmail: 'Please enter a valid email address.',
      errMessage: 'Please include a message with your inquiry.',
      errTooLong: 'Your message is too long. Please shorten it.',
      sent: 'Thank you! Your inquiry has been sent.',
      sentFull: 'Thank you! Your inquiry has been sent. We will reply to your email shortly.',
      sending: 'Sending...',
      sendInquiry: 'Send Inquiry',
      openingMail: 'Opening your email client...',
      genericError: 'Something went wrong. Please try again.',
      networkError: 'Network error. Please check your connection and try again.',
      mailSubject: 'Booking Inquiry - {property}',
      msgTemplate: 'Hello,\n\nI would like to request a booking at {property}:\n\n  Check-in:  {checkin}\n  Check-out: {checkout}\n  Guests:    {guests}\n  Duration:  {nights} {nightsWord}\n\n  Estimated Total Price: {price}\n\nPlease confirm availability and let me know the next steps.\n\nThank you,',

      // Reviews page
      reviewsFrom: 'from {n} guest reviews',
      showOriginal: 'Show original ({lang})',
      showTranslation: 'Show translation ({lang})',
      langNames: { en: 'English', it: 'Italian', de: 'German', fr: 'French', pl: 'Polish', da: 'Danish', uk: 'Ukrainian', ru: 'Russian' },
    },

  };

  const lang = (document.documentElement.getAttribute('lang') || 'en').slice(0, 2).toLowerCase();
  const dict = DICTS[lang] || DICTS.en;

  const PROPERTY_NAME = (window.PROPERTY && window.PROPERTY.name) || '';

  /** Translate: t('msgMinStay', { min: 3, n: 2, nightsWord: '…' }) */
  function t(key, vars) {
    let str = dict[key] !== undefined ? dict[key] : (DICTS.en[key] !== undefined ? DICTS.en[key] : key);
    if (typeof str === 'string') str = str.split('{property}').join(PROPERTY_NAME);
    if (vars) {
      for (const k in vars) {
        str = str.split('{' + k + '}').join(String(vars[k]));
      }
    }
    return str;
  }

  window.SITE_I18N = {
    lang: lang,
    locale: dict.locale,
    months: dict.months,
    days: dict.days,
    langNames: dict.langNames || DICTS.en.langNames,
    t: t,
    /** Pluralized word for nights/guests */
    plural: function (n, singularKey, pluralKey) {
      return String(n) === '1' || n === 1 ? dict[singularKey] : dict[pluralKey];
    },
  };
})();
