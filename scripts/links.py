"""
Checks that every link on the built pages leads somewhere.

build.py runs it once every page is written, so a page may link to one built
after it. For each page it reads the addresses a browser would follow or
fetch: href and src, every entry of a srcset, and the data-src, data-avif and
data-webp the gallery copies into its main photo when a thumbnail is picked.
Addresses on the property's own url count as the site's too, which covers the
canonical and hreflang links and the link-preview image. Each has to name a
file the site has, and a #fragment an element on that page.

It also checks the references from one element to another by id - <label for>,
aria-describedby, aria-labelledby and aria-controls - and that no id is used
twice on a page, where a fragment or label would find the first one only.

Addresses a script puts together while the page runs are not in the HTML, so
they are not checked here.
"""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

URLS = ('href', 'src', 'data-src')
SRCSETS = ('srcset', 'data-avif', 'data-webp')
ID_REFERENCES = ('for', 'aria-describedby', 'aria-labelledby', 'aria-controls')
PREVIEW_IMAGES = ('og:image', 'twitter:image')


class Page(HTMLParser):
    """The ids on one page and the links and id references it makes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.base = None
        self.ids = {}          # id -> line it first appears on
        self.duplicates = []   # (line, id)
        self.links = []        # (line, attribute, address)
        self.references = []   # (line, attribute, id)

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        attrs = {name: value or '' for name, value in attrs}
        if tag == 'base':
            # Not a link but the folder the others start from.
            if self.base is None:
                self.base = attrs.get('href')
            return
        if 'id' in attrs:
            if attrs['id'] in self.ids:
                self.duplicates.append((line, attrs['id']))
            else:
                self.ids[attrs['id']] = line

        for name in URLS:
            if attrs.get(name):
                self.links.append((line, name, attrs[name]))
        for name in SRCSETS:
            for entry in attrs.get(name, '').split(','):
                if entry.strip():
                    self.links.append((line, name, entry.split()[0]))
        if tag == 'meta' and (attrs.get('property') or attrs.get('name')) in PREVIEW_IMAGES:
            self.links.append((line, attrs.get('property') or attrs.get('name'), attrs.get('content', '')))
        for name in ID_REFERENCES:
            for ref in attrs.get(name, '').split():
                self.references.append((line, name, ref))


def site_path(address: str, page_url: str, site_url: str) -> str | None:
    """The file in the built site an address names, '' for one outside the
    site's folder, and None for an address elsewhere (another site, mailto:)."""
    target = urlparse(urljoin(page_url, address))
    site = urlparse(site_url)
    if (target.scheme, target.netloc) != (site.scheme, site.netloc):
        return None
    if not target.path.startswith(site.path):
        return ''
    path = unquote(target.path[len(site.path):])
    return path + 'index.html' if path == '' or path.endswith('/') else path


def check_links(out: Path, site_url: str, pages: list) -> list:
    """Problems with the links on the given pages of the site built in out,
    one line each, naming the page and the line on it."""
    site_url = site_url.rstrip('/') + '/'
    parsed = {}
    for path in pages:
        parsed[path] = Page()
        parsed[path].feed((out / path).read_text(encoding='utf-8'))

    problems = []
    for path, page in parsed.items():
        where = lambda line: f'{out.name}/{path}:{line}'
        page_url = urljoin(site_url, path)
        if page.base is not None:
            page_url = urljoin(page_url, page.base)

        for line, name, address in page.links:
            target = site_path(address, page_url, site_url)
            if target is None:
                continue
            if target == '':
                problems.append(f'{where(line)}: {name} {address} is outside the site at {site_url}')
            elif not (out / target).is_file():
                problems.append(f'{where(line)}: {name} {address} leads to {target}, which the site does not have')
            else:
                fragment = urlparse(address).fragment
                if fragment and target in parsed and fragment not in parsed[target].ids:
                    problems.append(f'{where(line)}: {name} {address}: {target} has no id="{fragment}"')

        for line, name, ref in page.references:
            if ref not in page.ids:
                problems.append(f'{where(line)}: {name}="{ref}" names no element on the page')
        for line, ref in page.duplicates:
            problems.append(f'{where(line)}: id="{ref}" is already used on line {page.ids[ref]}')

    return problems
