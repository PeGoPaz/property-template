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
- Light and dark theme
- Photos served as AVIF and WebP with a JPEG fallback

## Making it yours

| File | What goes in it |
|---|---|
| `property.json` | Name, email, address, Formspree form ID, social links, photos, gallery and amenities |
| `content/en.json` | Every piece of text on the site. `{name}` becomes the property's name |
| `templates/` | Page layouts. Files starting with `_` are shared between pages |

Leave `formspreeId` empty and the contact form opens the guest's email client
instead.

## Build and preview

```bash
python3 scripts/build.py --serve
```

builds the site into `_site/` and serves it on http://localhost:8000. A typo in
a template placeholder, a photo that does not exist or a gallery photo without
a caption stops the build with a message saying which.

```bash
python3 -m unittest discover -s tests
```

## Photos

Each placeholder in `assets/` is labelled with its file name and size. Replace
the JPEGs with your own photos, then regenerate the AVIF and WebP versions
(needs `cwebp` and the Xcode command line tools):

```bash
python3 scripts/build_images.py
```
