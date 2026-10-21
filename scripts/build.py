#!/usr/bin/env python3
"""
Builds the site into _site/ from three sources:

  property.json     facts about the property: name, contact details, links, photos
  reviews.json      guest reviews, rendered into the pages (see scripts/reviews.py)
  content/en.json   every piece of visible text
  templates/        page layouts; files starting with _ are partials

Templates use {{ dotted.path }} placeholders, looked up in
  p.*   property.json
  t.*   content/en.json
plus the partials and the fragments built below (gallery, amenities, social
links). Values are HTML-escaped. `| avif` and `| webp` swap a photo's .jpg for
the sibling scripts/build_images.py generates. An unknown placeholder fails the
build rather than shipping a page with a hole in it.

Text in content/en.json may say {name}, {minNights} or {maxGuests}; they are
filled in from property.json.

  python3 scripts/build.py           build into _site/
  python3 scripts/build.py --serve   build, then serve it on http://localhost:8000
"""

import argparse
import html
import json
import re
import shutil
import sys
from datetime import date, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from markup import BuildError, Markup, attr, indent
from reviews import check_reviews, reviews_context

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'templates'
OUT = ROOT / '_site'

PAGES = ['index', 'info', 'reviews', 'contact']
PARTIALS = ['head', 'header', 'footer', 'home_reviews']
STATIC = ['css', 'js', 'assets', 'availability.json', '_headers']

REQUIRED = ['name', 'email', 'address', 'booking', 'photos', 'gallery', 'amenities']
REQUIRED_PHOTOS = ['logo', 'favicon', 'appleTouchIcon', 'hero', 'exterior', 'view']

PLACEHOLDER = re.compile(r'\{\{\s*([\w.-]+)\s*(?:\|\s*(\w+)\s*)?\}\}')

FILTERS = {
    'avif': lambda v: re.sub(r'\.jpg$', '.avif', v),
    'webp': lambda v: re.sub(r'\.jpg$', '.webp', v),
}


# ────────────────────────────────────────────────
# Templating
# ────────────────────────────────────────────────

def lookup(context: dict, path: str):
    value = context
    for part in path.split('.'):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(path)
        value = value[part]
    return value


def render(template: str, context: dict, name: str = 'template') -> str:
    def replace(match):
        path, filter_name = match.group(1), match.group(2)
        try:
            value = lookup(context, path)
        except KeyError:
            raise BuildError(f'{name}: unknown placeholder {{{{ {path} }}}}') from None
        if isinstance(value, (dict, list)):
            raise BuildError(f'{name}: {{{{ {path} }}}} is a group, not a value')
        if filter_name:
            if filter_name not in FILTERS:
                raise BuildError(f'{name}: unknown filter | {filter_name}')
            value = FILTERS[filter_name](str(value))
        if isinstance(value, Markup):
            return value
        return html.escape(str(value))

    return PLACEHOLDER.sub(replace, template)


def fill_vars(value, variables: dict):
    """Replace {key} with variables[key] in every string of the content tree."""
    if isinstance(value, dict):
        return {k: fill_vars(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [fill_vars(v, variables) for v in value]
    if isinstance(value, str):
        for key, replacement in variables.items():
            value = value.replace('{' + key + '}', str(replacement))
        return value
    return value


# ────────────────────────────────────────────────
# Fragments
# ────────────────────────────────────────────────

def picture(src: str, alt: str, extra: str = '') -> str:
    extra = f' {extra}' if extra else ''
    return (f'<picture>\n'
            f'  <source type="image/avif" srcset="{attr(FILTERS["avif"](src))}">\n'
            f'  <source type="image/webp" srcset="{attr(FILTERS["webp"](src))}">\n'
            f'  <img src="{attr(src)}" alt="{attr(alt)}"{extra}>\n'
            f'</picture>')


SOCIAL_ICONS = {
    'facebook': ('Facebook', 'fill="currentColor"',
                 '<path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"></path>'),
    'instagram': ('Instagram', 'fill="none" stroke="currentColor" stroke-width="2"',
                  '<rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>'
                  '<path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>'
                  '<line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>'),
}


def social_links(prop: dict, size: str = '') -> str:
    """Links for every network with a URL in property.json, in a fixed order."""
    links = []
    for key, (label, paint, shape) in SOCIAL_ICONS.items():
        url = prop.get('social', {}).get(key)
        if not url:
            continue
        links.append(f'<a href="{attr(url)}" target="_blank" rel="noopener noreferrer" aria-label="{label}">\n'
                     f'  <svg viewBox="0 0 24 24" {paint}{size}>{shape}</svg>\n'
                     f'</a>')
    return '\n'.join(links)


def text_for(text: dict, section: str, key: str):
    try:
        return text[section][key]
    except KeyError:
        raise BuildError(f'content/en.json has no {section} text for "{key}"') from None


def gallery(prop: dict, text: dict) -> dict:
    items = [(g['src'], text_for(text, 'gallery', g['id'])) for g in prop['gallery']]
    thumbs = []
    for i, (src, alt) in enumerate(items):
        cls = 'gallery-thumb active' if i == 0 else 'gallery-thumb'
        thumbs.append(f'<div class="{cls}" data-src="{attr(src)}" data-alt="{attr(alt)}">\n'
                      + indent(picture(src, alt, 'loading="lazy" decoding="async"'), 2)
                      + '\n</div>')
    first_src, first_alt = items[0]
    return {
        'first': {'src': first_src, 'alt': first_alt},
        'thumbs': Markup(indent('\n'.join(thumbs), 12)),
    }


def amenities(prop: dict, text: dict) -> Markup:
    cards = []
    for a in prop['amenities']:
        t = text_for(text, 'amenities', a['id'])
        cards.append(f'<div class="amenity-card">\n'
                     f'  <div class="amenity-image">\n'
                     + indent(picture(a['image'], t['alt'], 'loading="lazy" decoding="async"'), 4)
                     + f'\n  </div>\n'
                     f'  <div class="amenity-body">\n'
                     f'    <h3>{html.escape(t["title"])}</h3>\n'
                     f'    <p>{html.escape(t["text"])}</p>\n'
                     f'  </div>\n'
                     f'</div>')
    return Markup(indent('\n\n'.join(cards), 10))


# ────────────────────────────────────────────────
# Build
# ────────────────────────────────────────────────

def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise BuildError(f'{path.relative_to(ROOT)} is missing') from None
    except json.JSONDecodeError as e:
        raise BuildError(f'{path.relative_to(ROOT)}: {e}') from None


MONTH_DAY = re.compile(r'^(\d{2})-(\d{2})$')


def season_days(season: dict) -> set:
    """The 'MM-DD' days a season covers, counted on a leap year so 02-29 exists."""
    first = date(2024, *map(int, season['from'].split('-')))
    last = date(2024, *map(int, season['to'].split('-')))
    if last < first:  # runs over New Year
        last = last.replace(year=2025)
    days, day = set(), first
    while day <= last:
        days.add(day.strftime('%m-%d'))
        day += timedelta(days=1)
    return days


def is_whole(value, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def check_booking(booking: dict) -> list:
    """Everything wrong with the booking block, so one build reports it all."""
    problems = []
    if not (isinstance(booking.get('currency'), str) and re.fullmatch(r'[A-Z]{3}', booking['currency'])):
        problems.append('currency must be a three-letter code such as "EUR"')
    if not is_whole(booking.get('minNights'), 1):
        problems.append('minNights must be a whole number of at least 1')
    if not is_whole(booking.get('maxGuests'), 1):
        problems.append('maxGuests must be a whole number of at least 1')

    seasons = booking.get('seasons')
    if not isinstance(seasons, list) or not seasons:
        return problems + ['seasons must list at least one season']

    covered = {}
    for n, season in enumerate(seasons, 1):
        ends_ok = True
        for end in ('from', 'to'):
            match = MONTH_DAY.match(str(season.get(end, '')))
            try:
                if not match:
                    raise ValueError
                date(2024, int(match[1]), int(match[2]))
            except ValueError:
                problems.append(f'season {n}: "{end}" must be a date written MM-DD, got {season.get(end)!r}')
                ends_ok = False
        nightly = season.get('nightly')
        if isinstance(nightly, bool) or not isinstance(nightly, (int, float)) or nightly <= 0:
            problems.append(f'season {n}: nightly must be a price above 0, got {nightly!r}')
        if not ends_ok:
            continue
        for day in sorted(season_days(season)):
            if day in covered:
                problems.append(f'seasons {covered[day]} and {n} both cover {day}')
                break
            covered[day] = n
    return problems


def check_property(prop: dict, root: Path) -> None:
    missing = [key for key in REQUIRED if not prop.get(key)]
    missing += [f'photos.{key}' for key in REQUIRED_PHOTOS if not prop.get('photos', {}).get(key)]
    if missing:
        raise BuildError('property.json is missing ' + ', '.join(missing))

    problems = check_booking(prop['booking'])
    if problems:
        raise BuildError('property.json booking:\n  ' + '\n  '.join(problems))

    files = list(prop['photos'].values())
    files += [g['src'] for g in prop['gallery']]
    files += [a['image'] for a in prop['amenities']]
    absent = [f for f in files if not (root / f).is_file()]
    if absent:
        raise BuildError('property.json points at photos that do not exist: ' + ', '.join(absent))


def context_for(prop: dict, reviews: dict, text: dict) -> dict:
    form_id = prop.get('formspreeId', '')
    return {
        'p': prop,
        't': text,
        'year': str(date.today().year),
        'maxChildren': prop['booking']['maxGuests'] - 1,
        # An empty action makes js/contact.js fall back to a mailto: link.
        'formAction': f'https://formspree.io/f/{form_id}' if form_id else '',
        'social': {
            'header': Markup(indent(social_links(prop), 8)),
            'mobile': Markup(indent(social_links(prop, ' width="20" height="20"'), 12)),
            'footer': Markup(indent(social_links(prop), 10)),
        },
        'gallery': gallery(prop, text),
        'amenities': amenities(prop, text),
        'reviews': reviews_context(reviews, text),
    }


def property_script(prop: dict) -> str:
    """What the browser scripts need to know, as js/property.js."""
    data = {'name': prop['name'], 'email': prop['email'], 'booking': prop['booking']}
    return ('// Generated by scripts/build.py from property.json - do not edit.\n'
            f'window.PROPERTY = {json.dumps(data, ensure_ascii=False, indent=2)};\n')


def build(root: Path = ROOT, out: Path = OUT) -> list:
    prop = load_json(root / 'property.json')
    check_property(prop, root)
    text = fill_vars(load_json(root / 'content' / 'en.json'), {
        'name': prop['name'],
        'minNights': prop['booking']['minNights'],
        'maxGuests': prop['booking']['maxGuests'],
    })

    reviews = load_json(root / 'reviews.json')
    problems = check_reviews(reviews)
    if problems:
        raise BuildError('reviews.json:\n  ' + '\n  '.join(problems))

    context = context_for(prop, reviews, text)

    templates = root / 'templates'
    partials = {name: (templates / f'_{name}.html').read_text(encoding='utf-8').rstrip('\n')
                for name in PARTIALS}

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for item in STATIC:
        src = root / item
        if src.is_dir():
            shutil.copytree(src, out / item)
        elif src.is_file():
            shutil.copy2(src, out / item)
    (out / 'js' / 'property.js').write_text(property_script(prop), encoding='utf-8')

    written = []
    for page in PAGES:
        page_context = dict(context, page=text['pages'][page])
        for name, source in partials.items():
            page_context[name] = Markup(render(source, page_context, f'templates/_{name}.html'))
        if not context['reviews']['count']:
            page_context['home_reviews'] = Markup('')  # no "Loved by our guests" with nothing to show
        source = (templates / f'{page}.html').read_text(encoding='utf-8')
        (out / f'{page}.html').write_text(render(source, page_context, f'templates/{page}.html'),
                                          encoding='utf-8')
        written.append(f'{page}.html')
    return written


def serve(port: int) -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(OUT))
    with ThreadingHTTPServer(('127.0.0.1', port), handler) as server:
        print(f'Serving {OUT.relative_to(ROOT)}/ on http://localhost:{port} (Ctrl+C to stop)')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--serve', action='store_true', help='serve _site/ after building')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()

    try:
        pages = build()
    except BuildError as e:
        print(f'build failed: {e}', file=sys.stderr)
        return 1
    print(f'Built {len(pages)} pages into {OUT.relative_to(ROOT)}/')

    if args.serve:
        serve(args.port)
    return 0


if __name__ == '__main__':
    sys.exit(main())
