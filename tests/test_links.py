import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from links import check_links  # noqa: E402


class CheckLinksTest(unittest.TestCase):
    """Each test builds a tiny site by hand: {path: content} for the pages,
    and files that only need to exist."""

    def site(self, pages, files=(), url='https://example.com'):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        out = tmp / '_site'
        for path, content in pages.items():
            (out / path).parent.mkdir(parents=True, exist_ok=True)
            (out / path).write_text(content)
        for path in files:
            (out / path).parent.mkdir(parents=True, exist_ok=True)
            (out / path).write_bytes(b'')
        return check_links(out, url, list(pages))

    def test_links_that_resolve(self):
        self.assertEqual(self.site({
            'index.html': '<a href="info.html#rates">Rates</a> <a href="it/">IT</a> <a href="#top" id="top">Up</a>\n'
                          '<link rel="stylesheet" href="css/styles.css?v=1234567890">\n'
                          '<img src="assets/a.jpg" srcset="assets/a-640.jpg 640w, assets/a.jpg 1600w">',
            'info.html': '<h2 id="rates">Rates</h2>',
            'it/index.html': '<a href="../index.html">EN</a> <img src="../assets/a.jpg">',
        }, files=['css/styles.css', 'assets/a.jpg', 'assets/a-640.jpg']), [])

    def test_every_srcset_entry_is_checked(self):
        # A translated page whose second entry lost its ../ asks for it/assets/,
        # and browsers that pick that width get no photo.
        problems = self.site({
            'it/info.html': '<p>\n<source srcset="../assets/a-640.avif 640w, assets/a.avif 1600w">',
        }, files=['assets/a-640.avif', 'assets/a.avif'])
        self.assertEqual(problems, ['_site/it/info.html:2: srcset assets/a.avif leads to it/assets/a.avif, '
                                    'which the site does not have'])

    def test_gallery_data_attributes(self):
        problems = self.site({
            'info.html': '<button data-src="assets/b.jpg" data-avif="assets/b-640.avif 640w" '
                         'data-webp="assets/b.webp 1600w">',
        }, files=['assets/b.jpg', 'assets/b.webp'])
        self.assertEqual(problems, ['_site/info.html:1: data-avif assets/b-640.avif leads to assets/b-640.avif, '
                                    'which the site does not have'])

    def test_missing_page_and_missing_fragment(self):
        problems = self.site({
            'index.html': '<a href="rates.html">Rates</a>\n<a href="info.html#prices">Prices</a>\n<a href="#book">Book</a>',
            'info.html': '<h2 id="rates">Rates</h2>',
        })
        self.assertEqual(problems, [
            '_site/index.html:1: href rates.html leads to rates.html, which the site does not have',
            '_site/index.html:2: href info.html#prices: info.html has no id="prices"',
            '_site/index.html:3: href #book: index.html has no id="book"',
        ])

    def test_addresses_elsewhere_are_not_checked(self):
        self.assertEqual(self.site({
            'index.html': '<a href="https://www.instagram.com/casa">Instagram</a> <a href="mailto:a@b.c">Mail</a> '
                          '<a href="tel:+390000">Call</a> <img src="data:image/gif;base64,R0lGOD==">',
        }), [])

    def test_own_url_counts_as_the_site(self):
        problems = self.site({
            'index.html': '<link rel="canonical" href="https://example.com/">\n'
                          '<link rel="alternate" hreflang="de" href="https://example.com/de/">\n'
                          '<meta property="og:image" content="https://example.com/assets/hero.jpg">',
        })
        self.assertEqual(problems, [
            '_site/index.html:2: href https://example.com/de/ leads to de/index.html, which the site does not have',
            '_site/index.html:3: og:image https://example.com/assets/hero.jpg leads to assets/hero.jpg, '
            'which the site does not have',
        ])

    def test_base_on_a_project_site(self):
        # The 404 page is served from any folder; <base> sends its links to the
        # site's root, and an address from the domain's root misses the site.
        problems = self.site({
            '404.html': '<base href="/casa/">\n<img src="assets/logo.jpg">\n<a href="it/index.html">IT</a>\n'
                        '<img src="/assets/logo.jpg">',
            'it/index.html': '',
        }, files=['assets/logo.jpg'], url='https://someone.github.io/casa')
        self.assertEqual(problems, ['_site/404.html:4: src /assets/logo.jpg is outside the site at '
                                    'https://someone.github.io/casa/'])

    def test_references_by_id(self):
        problems = self.site({
            'contact.html': '<label for="email">Email</label>\n<input id="mail" aria-describedby="hint error">\n'
                            '<p id="hint">We reply within a day.</p>\n<button aria-controls="menu">',
        })
        self.assertEqual(problems, [
            '_site/contact.html:1: for="email" names no element on the page',
            '_site/contact.html:2: aria-describedby="error" names no element on the page',
            '_site/contact.html:4: aria-controls="menu" names no element on the page',
        ])

    def test_id_used_twice(self):
        problems = self.site({'index.html': '<input id="adults">\n<label for="children">\n<input id="adults">'})
        self.assertEqual(problems, ['_site/index.html:2: for="children" names no element on the page',
                                    '_site/index.html:3: id="adults" is already used on line 1'])


if __name__ == '__main__':
    unittest.main()
