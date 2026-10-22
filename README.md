# property-template

A template for building a direct-booking website for a holiday rental, based on
the site behind [villacaterina.casa](https://villacaterina.casa).

The example property, Casa Esempio, is made up: its text, reviews, availability
and photos are placeholders to replace with your own.

Zero-dependency static site: vanilla HTML, CSS and JavaScript, built by one
standard-library Python script.

- Home page with a booking calendar and seasonal pricing
- Availability from a static `availability.json`
- Gallery, amenities, guest reviews from several platforms, and a contact form
  that arrives pre-filled from the booking flow
- Any number of languages, with a language switch and hreflang links
- Link previews for social networks and messengers, from the hero photo
- Structured data (schema.org `LodgingBusiness`) with the price range and
  rating worked out from the seasons and reviews
- Light and dark theme
- Photos served as AVIF and WebP with a JPEG fallback

## Making it yours

| File | What goes in it |
|---|---|
| `property.json` | Name, address the site is served at, languages, email, postal address, Formspree form ID, prices and stay rules, social links, photos, gallery and amenities |
| `reviews.json` | Guest reviews and the platforms they came from |
| `content/<lang>.json` | Every piece of text on the site, one file per language. `{name}` becomes the property's name |
| `templates/` | Page layouts. Files starting with `_` are shared between pages |

Leave `formspreeId` empty and the contact form opens the guest's email client
instead.

`photos.hero` must be a JPEG: besides opening the home page, it is the image a
link to the site previews with on Facebook, WhatsApp, Slack and the like. Its
size goes into the preview tags straight from the file.

### Prices

`booking` in `property.json` sets the currency, the minimum stay, the most
guests allowed and the nightly rate for each season:

```json
"seasons": [
  { "from": "06-01", "to": "06-15", "nightly": 600 },
  { "from": "06-16", "to": "06-30", "nightly": 650 },
  { "from": "12-20", "to": "01-06", "nightly": 400 }
]
```

Dates are `MM-DD`, both ends included, and repeat every year. A season whose
start is later than its end runs over New Year. Any night outside every season
is closed and shown as such in the calendar. Overlapping seasons stop the build.

### Languages

`languages` in `property.json` lists the languages the site is built in. The
first is the default and lives at the root; each other one gets the same pages
under `/<lang>/`. The example ships English and Italian.

To add one, copy `content/en.json` to `content/<lang>.json`, translate every
value (including the `ui` block the booking calendar and contact form use,
and its `locale`), and add the code to `languages`. A translation with a
missing or extra key stops the build and lists them:

```
build failed: translations do not match content/en.json:
  content/de.json: missing home.heroHeading
  content/de.json: ui.months should list 12 entries
```

Reviews are shown in the guest's own language unless they carry a translation
for the page's language, in which case the original is one click away.

### Availability

The calendar greys out every date in `availability.json`. The one in the
repository is a made-up sample; `scripts/sync_availability.py` replaces it
with the real bookings from the iCal feeds your platforms export. Booking.com,
Airbnb and Vrbo each offer an export link in their calendar sync settings.

```bash
ICAL_URLS="https://ical.booking.com/v1/export?t=...
https://www.airbnb.com/calendar/ical/....ics?s=..." python3 scripts/sync_availability.py
```

Bookings from every feed are merged. The day a stay ends stays closed to new
arrivals, to leave time for cleaning, unless `booking.sameDayTurnover` is
`true`. If any feed cannot be fetched nothing is written, because a calendar
missing one platform's bookings would offer those dates again.

Treat the feed URLs like passwords: anyone holding one can read your bookings.
Keep them out of the repository; the script never prints them. Once the site
is deployed (below), the URLs live in a repository secret and the calendar
refreshes itself every 6 hours.

### Reviews

Each review names its platform, the guest's score on that platform's scale
(10 on Booking.com, 5 on Airbnb and Google), the month, and the language the
guest wrote in. Add `translations` to show it in the page's language with a
"Show original" button, and `"featured": true` to put it on the home page.

Reviews are rendered into the HTML at build time, so search engines and
visitors without JavaScript see them too. Averages per platform and the
overall rating out of 5 are worked out from the reviews themselves.

## Build and preview

```bash
python3 scripts/build.py --serve
```

builds the site into `_site/` and serves it on http://localhost:8000. A typo in
a template placeholder, a photo that does not exist or a gallery photo without
a caption stops the build with a message saying which.

Links to the site's own CSS and JavaScript get a hash of the file appended
(`js/booking.js?v=cccefb6a23`). When a file changes, so does its link, and
browsers fetch the new version straight after a deploy instead of running a
cached old script against the new pages.

```bash
python3 -m unittest discover -s tests
node --test tests/*.test.js
```

## Deploy

The CI workflow tests and builds every push. Once deploying is switched on, runs
on `main` also deploy `_site/` to GitHub Pages, and every 6 hours it fetches the
iCal feeds and rebuilds, so new bookings reach the calendar without anyone
committing anything. A failing test, translation or feed stops the run and
leaves the live site as it was.

1. **Settings → Pages → Source:** GitHub Actions.
2. **Settings → Secrets and variables → Actions:**
   - variable `PAGES_ENABLED` set to `true`; until then CI only tests and builds
   - secret `ICAL_URLS`, one feed URL per line. Without it the calendar shows
     the sample `availability.json`, and each run says so in a warning.
3. Set `url` in `property.json` to the address the site is served at, for
   example `https://<user>.github.io/<repository>` or your own domain.

GitHub pauses scheduled workflows after 60 days without activity in the
repository; re-enable it from the Actions tab if the calendar stops updating.

## Photos

Each placeholder in `assets/` is labelled with its file name and size. Replace
the JPEGs with your own photos, then regenerate the AVIF and WebP versions
(needs `cwebp` and the Xcode command line tools):

```bash
python3 scripts/build_images.py
```
