#!/usr/bin/env python3
"""
Builds the site into _site/ from:

  property.json         facts about the property: name, contact details, links,
                        photos, prices, and the languages the site is in
  reviews.json          guest reviews, rendered into the pages (see scripts/reviews.py)
  content/<lang>.json   every piece of visible text, one file per language
  templates/            page layouts; files starting with _ are partials

The first language in property.json is the default and is built at the root;
every other one gets the same pages under /<lang>/. Each translation must have
exactly the keys the default language has, so a missing string fails the build
instead of showing up as a hole on the site.

Templates use {{ dotted.path }} placeholders, looked up in
  p.*   property.json
  t.*   content/<lang>.json for the page being built
plus the partials and the fragments built below (gallery, amenities, social
links, language links). Values are HTML-escaped. `| avif` and `| webp` swap a
photo's .jpg for the sibling scripts/build_images.py generates. Paths to the
site's own files start with {{ root }}, which is '../' on translated pages.

Text may say {name}, {minNights} or {maxGuests}; they are filled in from
property.json.

Every link a page makes to the site's own CSS or JavaScript gets ?v=<hash of
the file> appended, so after a deploy browsers fetch the new files instead of
running a cached old script against new pages. A link to a file the site does
not have fails the build.

  python3 scripts/build.py           build into _site/
  python3 scripts/build.py --serve   build, then serve it on http://localhost:8000
"""

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from datetime import date, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from markup import BuildError, Markup, attr, indent
from reviews import check_reviews, reviews_context

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'templates'
OUT = ROOT / '_site'

PAGES = ['index', 'info', 'reviews', 'contact']
PARTIALS = ['head', 'header', 'footer', 'home_reviews']
STATIC = ['css', 'js', 'assets', 'availability.json', '_headers']

REQUIRED = ['name', 'url', 'languages', 'email', 'address', 'booking', 'photos', 'gallery', 'amenities']
REQUIRED_PHOTOS = ['logo', 'favicon', 'appleTouchIcon', 'hero', 'exterior', 'view']

PLACEHOLDER = re.compile(r'\{\{\s*([\w.-]+)\s*(?:\|\s*(\w+)\s*)?\}\}')
# A placeholder alone on its line; if it renders to nothing, the line goes too.
STANDALONE = re.compile(r'^[ \t]*(\{\{[^{}]*\}\})[ \t]*\n', re.M)

# src="js/booking.js", href="../css/styles.css": the site's own scripts and styles.
OWN_ASSET = re.compile(r'\b(src|href)="((?:\.\./)*(?:js|css)/[^"?#]+)"')

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

    def drop_if_empty(match):
        return '' if PLACEHOLDER.sub(replace, match.group(1)) == '' else match.group(0)

    template = STANDALONE.sub(drop_if_empty, template)
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
        raise BuildError(f'content/{text["lang"]}.json has no {section} text for "{key}"') from None


def gallery(prop: dict, text: dict, root: str) -> dict:
    items = [(root + g['src'], text_for(text, 'gallery', g['id'])) for g in prop['gallery']]
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


def amenities(prop: dict, text: dict, root: str) -> Markup:
    cards = []
    for a in prop['amenities']:
        t = text_for(text, 'amenities', a['id'])
        cards.append(f'<div class="amenity-card">\n'
                     f'  <div class="amenity-image">\n'
                     + indent(picture(root + a['image'], t['alt'], 'loading="lazy" decoding="async"'), 4)
                     + f'\n  </div>\n'
                     f'  <div class="amenity-body">\n'
                     f'    <h3>{html.escape(t["title"])}</h3>\n'
                     f'    <p>{html.escape(t["text"])}</p>\n'
                     f'  </div>\n'
                     f'</div>')
    return Markup(indent('\n\n'.join(cards), 10))


def page_path(page: str, lang: str, default: str) -> str:
    """Where a page lives, from the site root: 'info.html', 'it/info.html'."""
    return ('' if lang == default else f'{lang}/') + f'{page}.html'


def page_url(base: str, page: str, lang: str, default: str) -> str:
    """Absolute URL, with the home page as its directory rather than index.html."""
    path = page_path(page, lang, default)
    return f'{base}/' + (path[:-len('index.html')] if path.endswith('index.html') else path)


def alternates(prop: dict, page: str, lang: str) -> Markup:
    """Canonical URL, plus hreflang links so search engines pair up the translations."""
    base, languages = prop['url'].rstrip('/'), prop['languages']
    default = languages[0]
    links = [f'<link rel="canonical" href="{attr(page_url(base, page, lang, default))}">']
    if len(languages) > 1:
        for other in languages:
            links.append(f'<link rel="alternate" hreflang="{other}" href="{attr(page_url(base, page, other, default))}">')
        links.append(f'<link rel="alternate" hreflang="x-default" href="{attr(page_url(base, page, default, default))}">')
    return Markup(indent('\n'.join(links), 2))


def jpeg_size(path: Path) -> tuple:
    """(width, height) from a JPEG's frame header, so og:image sizes cannot go stale."""
    data = path.read_bytes()
    if data[:2] != b'\xff\xd8':
        raise BuildError(f'{path.name} must be a JPEG: it is also the preview image social networks show')
    i = 2
    while i + 9 < len(data):
        marker = data[i + 1]
        if data[i] != 0xFF or marker == 0xFF:  # fill bytes before a marker
            i += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:  # markers without a length
            i += 2
            continue
        # SOF0-SOF15 carry the size; C4 (Huffman), C8 and CC (arithmetic coding) do not.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = int.from_bytes(data[i + 5:i + 7], 'big')
            width = int.from_bytes(data[i + 7:i + 9], 'big')
            return width, height
        i += 2 + int.from_bytes(data[i + 2:i + 4], 'big')
    raise BuildError(f'{path.name}: no image size found in the JPEG')


def og_locale(text: dict) -> str:
    return text['ui']['locale'].replace('-', '_')  # en-US -> en_US


def sharing(prop: dict, texts: dict, page: str, lang: str, image_size: tuple) -> Markup:
    """Open Graph and Twitter tags: the title, text and photo a shared link previews with."""
    base, default = prop['url'].rstrip('/'), prop['languages'][0]
    text = texts[lang]
    page_text = text['pages'][page]
    image = f'{base}/{quote(prop["photos"]["hero"])}'  # the JPEG: not every scraper reads AVIF or WebP
    alt = text['home']['heroAlt']

    tags = [
        ('property', 'og:type', 'website'),
        ('property', 'og:site_name', prop['name']),
        ('property', 'og:title', page_text['title']),
        ('property', 'og:description', page_text['description']),
        ('property', 'og:url', page_url(base, page, lang, default)),
        ('property', 'og:image', image),
        ('property', 'og:image:width', image_size[0]),
        ('property', 'og:image:height', image_size[1]),
        ('property', 'og:image:alt', alt),
        ('property', 'og:locale', og_locale(text)),
    ]
    tags += [('property', 'og:locale:alternate', og_locale(texts[other])) for other in prop['languages'] if other != lang]
    tags += [
        ('name', 'twitter:card', 'summary_large_image'),
        ('name', 'twitter:title', page_text['title']),
        ('name', 'twitter:description', page_text['description']),
        ('name', 'twitter:image', image),
        ('name', 'twitter:image:alt', alt),
    ]
    return Markup(indent('\n'.join(f'<meta {kind}="{name}" content="{attr(str(value))}">'
                                    for kind, name, value in tags), 2))


def price_range(booking: dict) -> str:
    rates = [season['nightly'] for season in booking['seasons']]
    low, high = min(rates), max(rates)
    amounts = f'{low:g}' if low == high else f'{low:g}-{high:g}'
    return f'{amounts} {booking["currency"]}'


def structured_data(prop: dict, text: dict, lang: str, reviews: dict) -> Markup:
    """
    JSON-LD describing the property, for the home page. ld+json is a data block,
    so CSP's script-src 'self' does not stop it.

    Google does not show star ratings for reviews a business publishes about
    itself, wherever they were first written, so aggregateRating will not put
    stars in search results; it still tells search engines what guests think.
    """
    base, default = prop['url'].rstrip('/'), prop['languages'][0]
    data = {
        '@context': 'https://schema.org',
        '@type': 'LodgingBusiness',
        'name': prop['name'],
        'description': text['pages']['index']['description'],
        'url': page_url(base, 'index', lang, default),
        'image': f'{base}/{quote(prop["photos"]["hero"])}',
        'email': prop['email'],
        'address': prop['address'],
        'priceRange': price_range(prop['booking']),
        'availableLanguage': prop['languages'],
    }
    same_as = [url for url in prop.get('social', {}).values() if url]
    if same_as:
        data['sameAs'] = same_as
    if reviews['count']:
        data['aggregateRating'] = {
            '@type': 'AggregateRating',
            'ratingValue': reviews['ratingValue'],
            'reviewCount': reviews['count'],
            'bestRating': 5,
            'worstRating': 1,
        }
    # "</" would end the script element early: a name like "</script><script>..."
    # must stay data. JSON allows "\/" for "/", so the value is unchanged.
    body = json.dumps(data, indent=2, ensure_ascii=False).replace('</', '<\\/')
    return Markup(indent('<script type="application/ld+json">\n' + body + '\n</script>', 2))


def language_switch(prop: dict, text: dict, page: str, lang: str, root: str) -> Markup:
    languages = prop['languages']
    if len(languages) < 2:
        return Markup('')
    links = []
    for other in languages:
        current = ' class="active" aria-current="page"' if other == lang else ''
        links.append(f'<a href="{root}{page_path(page, other, languages[0])}"{current}'
                     f' lang="{other}" hreflang="{other}">{other.upper()}</a>')
    return Markup(f'<div class="lang-switch" role="group" aria-label="{attr(text["language"]["switchLabel"])}">'
                  + ''.join(links) + '</div>')


# ────────────────────────────────────────────────
# Build
# ────────────────────────────────────────────────

def load_json(path: Path, root: Path):
    name = path.relative_to(root)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise BuildError(f'{name} is missing') from None
    except json.JSONDecodeError as e:
        raise BuildError(f'{name}: {e}') from None


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
    if not isinstance(booking.get('sameDayTurnover', False), bool):
        problems.append('sameDayTurnover must be true or false')

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

    if not re.fullmatch(r'https?://[^/\s]+(/\S*)?', prop['url']):
        raise BuildError(f'property.json: url must be the address the site is served at, such as '
                         f'"https://example.com", got {prop["url"]!r}')
    languages = prop['languages']
    if (not isinstance(languages, list) or len(set(languages)) != len(languages)
            or not all(isinstance(lang, str) and re.fullmatch(r'[a-z]{2}', lang) for lang in languages)):
        raise BuildError('property.json: languages must list two-letter codes such as "en", '
                         'each once, the default first')

    problems = check_booking(prop['booking'])
    if problems:
        raise BuildError('property.json booking:\n  ' + '\n  '.join(problems))

    files = list(prop['photos'].values())
    files += [g['src'] for g in prop['gallery']]
    files += [a['image'] for a in prop['amenities']]
    absent = [f for f in files if not (root / f).is_file()]
    if absent:
        raise BuildError('property.json points at photos that do not exist: ' + ', '.join(absent))


def missing_translations(reference, other, path: str = '') -> list:
    """Keys the default language has and a translation lacks (or has extra), as dotted paths."""
    problems = []
    for key, value in reference.items():
        where = path + key
        if key not in other:
            problems.append(f'missing {where}')
        elif isinstance(value, dict) != isinstance(other[key], dict):
            problems.append(f'{where} should be ' + ('a group of texts' if isinstance(value, dict) else 'a text'))
        elif isinstance(value, dict):
            problems += missing_translations(value, other[key], where + '.')
        elif isinstance(value, list) and (not isinstance(other[key], list) or len(other[key]) != len(value)):
            problems.append(f'{where} should list {len(value)} entries')
    problems += [f'unexpected {path}{key}' for key in other if key not in reference]
    return problems


def load_content(root: Path, prop: dict) -> dict:
    """Every language's texts, checked against the default and with {name} etc. filled in."""
    languages = prop['languages']
    raw = {lang: load_json(root / 'content' / f'{lang}.json', root) for lang in languages}
    problems = []
    for lang in languages[1:]:
        problems += [f'content/{lang}.json: {p}' for p in missing_translations(raw[languages[0]], raw[lang])]
    if problems:
        raise BuildError(f'translations do not match content/{languages[0]}.json:\n  ' + '\n  '.join(problems))

    variables = {
        'name': prop['name'],
        'minNights': prop['booking']['minNights'],
        'maxGuests': prop['booking']['maxGuests'],
    }
    return {lang: dict(fill_vars(text, variables), lang=lang) for lang, text in raw.items()}


def context_for(prop: dict, reviews: dict, text: dict, root: str) -> dict:
    form_id = prop.get('formspreeId', '')
    return {
        'p': prop,
        't': text,
        'lang': text['lang'],
        'root': root,
        'photos': {key: root + path for key, path in prop['photos'].items()},
        'year': str(date.today().year),
        'maxChildren': prop['booking']['maxGuests'] - 1,
        # An empty action makes js/contact.js fall back to a mailto: link.
        'formAction': f'https://formspree.io/f/{form_id}' if form_id else '',
        'social': {
            'header': Markup(indent(social_links(prop), 8)),
            'mobile': Markup(indent(social_links(prop, ' width="20" height="20"'), 12)),
            'footer': Markup(indent(social_links(prop), 10)),
        },
        'gallery': gallery(prop, text, root),
        'amenities': amenities(prop, text, root),
        'reviews': reviews_context(reviews, text, text['lang']),
    }


def property_script(prop: dict) -> str:
    """What the browser scripts need to know, as js/property.js."""
    data = {'name': prop['name'], 'email': prop['email'], 'booking': prop['booking']}
    return ('// Generated by scripts/build.py from property.json - do not edit.\n'
            f'window.PROPERTY = {json.dumps(data, ensure_ascii=False, indent=2)};\n')


def strings_script(text: dict) -> str:
    """One language's UI strings for js/i18n.js, as js/strings.<lang>.js."""
    return (f'// Generated by scripts/build.py from content/{text["lang"]}.json - do not edit.\n'
            f'window.SITE_STRINGS = {json.dumps(text["ui"], ensure_ascii=False, indent=2)};\n')


def build(root: Path = ROOT, out: Path = OUT) -> list:
    prop = load_json(root / 'property.json', root)
    check_property(prop, root)
    texts = load_content(root, prop)

    reviews = load_json(root / 'reviews.json', root)
    problems = check_reviews(reviews)
    if problems:
        raise BuildError('reviews.json:\n  ' + '\n  '.join(problems))

    templates = root / 'templates'
    partials = {name: (templates / f'_{name}.html').read_text(encoding='utf-8').rstrip('\n')
                for name in PARTIALS}
    sources = {page: (templates / f'{page}.html').read_text(encoding='utf-8') for page in PAGES}

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

    default = prop['languages'][0]
    hero_size = jpeg_size(root / prop['photos']['hero'])
    written = []
    for lang, text in texts.items():
        root_path = '' if lang == default else '../'
        (out / 'js' / f'strings.{lang}.js').write_text(strings_script(text), encoding='utf-8')
        context = context_for(prop, reviews, text, root_path)

        for page in PAGES:
            page_context = dict(context, page=text['pages'][page],
                                alternates=alternates(prop, page, lang),
                                sharing=sharing(prop, texts, page, lang, hero_size),
                                structuredData=(structured_data(prop, text, lang, context['reviews'])
                                                if page == 'index' else Markup('')),
                                languageSwitch=language_switch(prop, text, page, lang, root_path))
            for name, source in partials.items():
                page_context[name] = Markup(render(source, page_context, f'templates/_{name}.html'))
            if not context['reviews']['count']:
                page_context['home_reviews'] = Markup('')  # no "Loved by our guests" with nothing to show

            path = page_path(page, lang, default)
            (out / path).parent.mkdir(parents=True, exist_ok=True)
            page_html = render(sources[page], page_context, f'templates/{page}.html')
            (out / path).write_text(fingerprint(page_html, (out / path).parent, f'templates/{page}.html'),
                                    encoding='utf-8')
            written.append(path)
    return written


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def fingerprint(page_html: str, page_dir: Path, name: str) -> str:
    """Append ?v=<content hash> to every link to the site's own CSS and JS."""
    def replace(match):
        attribute, url = match.groups()
        target = page_dir / url
        if not target.is_file():
            raise BuildError(f'{name} links to {url}, which the built site does not have')
        return f'{attribute}="{url}?v={file_hash(target)}"'

    return OWN_ASSET.sub(replace, page_html)


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
