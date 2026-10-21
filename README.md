# property-template

A template for building a direct-booking website for a holiday rental, based on
the site behind [villacaterina.casa](https://villacaterina.casa).

The example property, Casa Esempio, is made up: its text, reviews, availability
and photos are placeholders to replace with your own.

Zero-dependency static site: vanilla HTML, CSS and JavaScript, no build step
needed to view it.

- Home page with a booking calendar and seasonal pricing
- Availability from a static `availability.json`
- Gallery, amenities, guest reviews from several platforms, and a contact form
  that arrives pre-filled from the booking flow
- Light and dark theme
- Photos served as AVIF and WebP with a JPEG fallback

## Preview

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000.

## Photos

Each placeholder in `assets/` is labelled with its file name and size. Replace
the JPEGs with your own photos, then regenerate the AVIF and WebP versions
(needs `cwebp` and the Xcode command line tools):

```bash
python3 scripts/build_images.py
```
