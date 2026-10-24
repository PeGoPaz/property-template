import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import build  # noqa: E402
from build import BuildError, Markup, check_booking, fill_vars, jpeg_size, render  # noqa: E402


class RenderTest(unittest.TestCase):
    def test_escapes_values(self):
        self.assertEqual(render('<p>{{ p.name }}</p>', {'p': {'name': 'Tom & "Jerry" <b>'}}),
                         '<p>Tom &amp; &quot;Jerry&quot; &lt;b&gt;</p>')

    def test_inserts_markup_as_is(self):
        self.assertEqual(render('{{ x }}', {'x': Markup('<b>ok</b>')}), '<b>ok</b>')

    def test_line_with_only_an_empty_placeholder_is_dropped(self):
        template = '<head>\n  {{ a }}\n  {{ b }}\n</head>\n<p>{{ b }}</p>\n'
        self.assertEqual(render(template, {'a': Markup(''), 'b': ''}), '<head>\n</head>\n<p></p>\n')
        self.assertEqual(render(template, {'a': Markup('<x>'), 'b': ''}), '<head>\n  <x>\n</head>\n<p></p>\n')

    def test_tolerates_spacing(self):
        self.assertEqual(render('{{x}}|{{   x   }}', {'x': 'a'}), 'a|a')

    def test_photo_filters(self):
        context = {'src': 'assets/inside/kitchen.jpg'}
        self.assertEqual(render('{{ src | avif }} {{ src|webp }}', context),
                         'assets/inside/kitchen.avif assets/inside/kitchen.webp')

    def test_unknown_placeholder_names_the_template(self):
        with self.assertRaisesRegex(BuildError, r'templates/x\.html: unknown placeholder \{\{ t\.missing \}\}'):
            render('{{ t.missing }}', {'t': {}}, 'templates/x.html')

    def test_group_is_not_a_value(self):
        with self.assertRaisesRegex(BuildError, 'is a group'):
            render('{{ t }}', {'t': {'a': 'b'}})

    def test_unknown_filter(self):
        with self.assertRaisesRegex(BuildError, 'unknown filter'):
            render('{{ x | upper }}', {'x': 'a'})


class FillVarsTest(unittest.TestCase):
    def test_fills_nested_strings(self):
        content = {'a': 'Stay at {name}', 'b': {'c': ['{name}, {minNights} nights', 3]}}
        self.assertEqual(fill_vars(content, {'name': 'Casa', 'minNights': 3}),
                         {'a': 'Stay at Casa', 'b': {'c': ['Casa, 3 nights', 3]}})

    def test_leaves_unknown_braces_alone(self):
        self.assertEqual(fill_vars('{price}', {'name': 'Casa'}), '{price}')


def booking(**changes):
    rules = {
        'currency': 'EUR',
        'minNights': 3,
        'maxGuests': 8,
        'seasons': [{'from': '04-01', 'to': '06-30', 'nightly': 180},
                    {'from': '07-01', 'to': '08-31', 'nightly': 250}],
    }
    rules.update(changes)
    return rules


class CheckBookingTest(unittest.TestCase):
    def test_example_rules_pass(self):
        self.assertEqual(check_booking(booking()), [])
        prop = json.loads((ROOT / 'property.json').read_text())
        self.assertEqual(check_booking(prop['booking']), [])

    def test_season_over_new_year(self):
        self.assertEqual(check_booking(booking(seasons=[{'from': '12-15', 'to': '01-10', 'nightly': 300}])), [])

    def test_leap_day(self):
        self.assertEqual(check_booking(booking(seasons=[{'from': '02-29', 'to': '02-29', 'nightly': 99}])), [])

    def test_overlapping_seasons(self):
        problems = check_booking(booking(seasons=[{'from': '06-01', 'to': '06-30', 'nightly': 200},
                                                  {'from': '06-15', 'to': '07-15', 'nightly': 250}]))
        self.assertEqual(problems, ['seasons 1 and 2 both cover 06-15'])

    def test_overlap_across_new_year(self):
        problems = check_booking(booking(seasons=[{'from': '12-20', 'to': '01-05', 'nightly': 300},
                                                  {'from': '01-01', 'to': '01-31', 'nightly': 200}]))
        self.assertEqual(problems, ['seasons 1 and 2 both cover 01-01'])

    def test_bad_dates_and_prices(self):
        problems = check_booking(booking(seasons=[{'from': '02-30', 'to': '2026-03-01', 'nightly': 0},
                                                  {'from': '05-01', 'to': '05-31', 'nightly': '200'}]))
        self.assertEqual(problems, [
            'season 1: "from" must be a date written MM-DD, got \'02-30\'',
            'season 1: "to" must be a date written MM-DD, got \'2026-03-01\'',
            'season 1: nightly must be a price above 0, got 0',
            "season 2: nightly must be a price above 0, got '200'",
        ])

    def test_limits_and_currency(self):
        problems = check_booking(booking(currency='euro', minNights=0, maxGuests=True, sameDayTurnover='no'))
        self.assertEqual(problems, [
            'currency must be a three-letter code such as "EUR"',
            'minNights must be a whole number of at least 1',
            'maxGuests must be a whole number of at least 1',
            'sameDayTurnover must be true or false',
        ])

    def test_no_seasons(self):
        self.assertEqual(check_booking(booking(seasons=[])), ['seasons must list at least one season'])


class JpegSizeTest(unittest.TestCase):
    def test_reads_the_frame_header(self):
        self.assertEqual(jpeg_size(ROOT / 'assets' / 'hero.jpg'), (1920, 1080))
        self.assertEqual(jpeg_size(ROOT / 'assets' / 'exterior.jpg'), (1600, 1067))
        self.assertEqual(jpeg_size(ROOT / 'assets' / 'logo.jpg'), (100, 100))

    def test_rejects_other_formats(self):
        with self.assertRaisesRegex(BuildError, 'favicon-32.png must be a JPEG'):
            jpeg_size(ROOT / 'assets' / 'favicon-32.png')

    def test_truncated_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cut.jpg'
            path.write_bytes((ROOT / 'assets' / 'hero.jpg').read_bytes()[:12])
            with self.assertRaisesRegex(BuildError, 'cut.jpg: no image size found'):
                jpeg_size(path)


class BuildTest(unittest.TestCase):
    """Builds a copy of the repository, so each test can change its config."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / 'site'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('.git', '_site', '__pycache__'))
        self.out = self.root / '_site'

    def edit_property(self, change):
        path = self.root / 'property.json'
        prop = json.loads(path.read_text())
        change(prop)
        path.write_text(json.dumps(prop))

    def page(self, name):
        return (self.out / f'{name}.html').read_text()

    def test_builds_every_page_in_every_language_with_nothing_left_unfilled(self):
        self.assertEqual(build.build(self.root, self.out),
                         ['index.html', 'info.html', 'reviews.html', 'contact.html',
                          'it/index.html', 'it/info.html', 'it/reviews.html', 'it/contact.html'])
        for page in ('index', 'info', 'reviews', 'contact', 'it/index', 'it/info', 'it/reviews', 'it/contact'):
            html = self.page(page)
            self.assertNotIn('{{', html, page)
            self.assertNotIn('{name}', html, page)
            self.assertIn('<title>', html)
            self.assertIn('Casa Esempio', html)

    def test_copies_static_files_and_writes_property_script(self):
        build.build(self.root, self.out)
        for path in ('css/styles.css', 'js/booking.js', 'assets/hero.avif', 'availability.json'):
            self.assertTrue((self.out / path).is_file(), path)
        script = (self.out / 'js' / 'property.js').read_text()
        self.assertIn('"name": "Casa Esempio"', script)
        self.assertIn('"email": "hello@example.com"', script)
        self.assertIn('"minNights": 3', script)

    def test_name_comes_from_property_json(self):
        self.edit_property(lambda p: p.update(name='Villa <Nova>'))
        build.build(self.root, self.out)
        self.assertIn('<title>Villa &lt;Nova&gt; - Holiday Home on Lake Garda</title>', self.page('index'))
        self.assertIn('<h3>Villa &lt;Nova&gt;</h3>', self.page('info'))

    def test_gallery_follows_property_json(self):
        self.edit_property(lambda p: p.update(gallery=p['gallery'][1:3]))
        build.build(self.root, self.out)
        html = self.page('info')
        self.assertEqual(html.count(' data-src='), 2)
        self.assertIn('id="gallery-main-img" src="assets/inside/kitchen.jpg" alt="Kitchen"', html)
        self.assertIn('<button type="button" class="gallery-thumb active" aria-current="true" '
                      'data-src="assets/inside/kitchen.jpg"', html)
        self.assertEqual(html.count('aria-current="true"'), 1)

    def test_pages_carry_no_inline_styles(self):
        # The CSP (in each page's <meta> and in _headers) allows styles from
        # the stylesheet only, so a style="" attribute would be ignored.
        build.build(self.root, self.out)
        for page in self.out.rglob('*.html'):
            html = page.read_text()
            name = page.relative_to(self.out)
            self.assertFalse(' style="' in html, f'{name} has a style attribute')
            self.assertFalse("'unsafe-inline'" in html, f'{name} allows inline styles')

    def test_contact_form_messages_reach_screen_readers(self):
        build.build(self.root, self.out)
        html = self.page('contact')
        self.assertIn('id="form-feedback" class="form-feedback" role="status" aria-live="polite"', html)
        self.assertIn('name="name" autocomplete="name"', html)
        self.assertIn('name="email" autocomplete="email"', html)

    def test_contact_form_without_formspree_falls_back_to_email(self):
        build.build(self.root, self.out)
        self.assertIn('<form id="contact-form" action="" method="POST">', self.page('contact'))

    def test_contact_form_posts_to_formspree_when_configured(self):
        self.edit_property(lambda p: p.update(formspreeId='abcd1234'))
        build.build(self.root, self.out)
        self.assertIn('action="https://formspree.io/f/abcd1234"', self.page('contact'))

    def test_social_link_without_url_is_left_out(self):
        self.edit_property(lambda p: p['social'].update(facebook=''))
        build.build(self.root, self.out)
        html = self.page('index')
        self.assertNotIn('aria-label="Facebook"', html)
        self.assertEqual(html.count('aria-label="Instagram"'), 3)

    def test_stay_rules_reach_the_page(self):
        self.edit_property(lambda p: p['booking'].update(minNights=5, maxGuests=4))
        build.build(self.root, self.out)
        html = self.page('index')
        self.assertIn('(min. 5 nights)', html)
        self.assertIn('id="adults" min="1" max="4"', html)
        self.assertIn('id="children" min="0" max="3"', html)

    def test_invalid_booking_rules_stop_the_build(self):
        self.edit_property(lambda p: p['booking'].update(minNights=0))
        with self.assertRaisesRegex(BuildError, 'booking:\n  minNights must be'):
            build.build(self.root, self.out)

    def edit_content(self, lang, change):
        path = self.root / 'content' / f'{lang}.json'
        text = json.loads(path.read_text())
        change(text)
        path.write_text(json.dumps(text))

    def test_translated_pages_point_back_up_for_shared_files(self):
        build.build(self.root, self.out)
        html = self.page('it/info')
        self.assertIn('<html lang="it">', html)
        self.assertIn('<link rel="stylesheet" href="../css/styles.css?v=', html)
        self.assertIn('<script src="../js/strings.it.js?v=', html)
        self.assertIn('<img src="../assets/exterior.jpg" alt="La casa vista dal giardino"', html)
        self.assertIn('data-src="../assets/inside/kitchen.jpg" data-alt="Cucina"', html)
        self.assertIn('<h1>La casa</h1>', html)
        self.assertNotIn('src="assets/', html)

    def test_language_links(self):
        build.build(self.root, self.out)
        english, italian = self.page('index'), self.page('it/index')
        self.assertIn('<link rel="canonical" href="https://example.com/">', english)
        self.assertIn('<link rel="canonical" href="https://example.com/it/">', italian)
        for html in (english, italian):
            self.assertIn('<link rel="alternate" hreflang="en" href="https://example.com/">', html)
            self.assertIn('<link rel="alternate" hreflang="it" href="https://example.com/it/">', html)
            self.assertIn('<link rel="alternate" hreflang="x-default" href="https://example.com/">', html)
        self.assertIn('<a href="index.html" class="active" aria-current="page" lang="en" hreflang="en">EN</a>'
                      '<a href="it/index.html" lang="it" hreflang="it">IT</a>', english)
        self.assertIn('<a href="../index.html" lang="en" hreflang="en">EN</a>', italian)

    def test_link_previews(self):
        build.build(self.root, self.out)
        english, italian = self.page('reviews'), self.page('it/reviews')
        for html in (english, italian):
            self.assertIn('<meta property="og:image" content="https://example.com/assets/hero.jpg">', html)
            self.assertIn('<meta property="og:image:width" content="1920">', html)
            self.assertIn('<meta property="og:image:height" content="1080">', html)
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', html)
        self.assertIn('<meta property="og:title" content="Reviews - Casa Esempio">', english)
        self.assertIn('<meta property="og:url" content="https://example.com/reviews.html">', english)
        self.assertIn('<meta property="og:locale" content="en_US">', english)
        self.assertIn('<meta property="og:locale:alternate" content="it_IT">', english)
        self.assertIn('<meta property="og:title" content="Recensioni - Casa Esempio">', italian)
        self.assertIn('<meta property="og:locale" content="it_IT">', italian)
        self.assertIn('<meta name="twitter:image:alt" content="Casa Esempio sopra il Lago di Garda">', italian)

    def test_link_preview_text_is_escaped(self):
        self.edit_property(lambda p: p.update(name='Casa "Sole"'))
        build.build(self.root, self.out)
        self.assertIn('<meta property="og:site_name" content="Casa &quot;Sole&quot;">', self.page('index'))

    def test_hero_photo_must_be_a_jpeg(self):
        self.edit_property(lambda p: p['photos'].update(hero='assets/apple-touch-icon.png'))
        with self.assertRaisesRegex(BuildError, 'apple-touch-icon.png must be a JPEG'):
            build.build(self.root, self.out)

    def structured_data(self, page):
        found = re.findall(r'<script type="application/ld\+json">(.*?)</script>', self.page(page), re.S)
        return [json.loads(block) for block in found]

    def test_structured_data_on_the_home_page_only(self):
        build.build(self.root, self.out)
        [english] = self.structured_data('index')
        [italian] = self.structured_data('it/index')
        self.assertEqual(english['@type'], 'LodgingBusiness')
        self.assertEqual(english['url'], 'https://example.com/')
        self.assertEqual(italian['url'], 'https://example.com/it/')
        self.assertTrue(italian['description'].startswith('Casa Esempio - una casa vacanze'))
        self.assertEqual(english['priceRange'], '180-280 EUR')
        self.assertEqual(english['availableLanguage'], ['en', 'it'])
        self.assertEqual(english['aggregateRating']['ratingValue'], 4.75)
        self.assertEqual(english['aggregateRating']['reviewCount'], 6)
        for page in ('info', 'reviews', 'contact', 'it/info'):
            self.assertEqual(self.structured_data(page), [], page)

    def test_structured_data_cannot_close_its_script_tag(self):
        name = 'Casa </script><script>alert(1)</script>'
        self.edit_property(lambda p: p.update(name=name))
        build.build(self.root, self.out)
        [data] = self.structured_data('index')
        self.assertEqual(data['name'], name)  # the block ends where it should and keeps the text
        self.assertNotIn('</script><script>alert(1)', self.page('index'))

    def test_structured_data_without_reviews_or_social_links(self):
        def change(p):
            p['social'] = {'facebook': '', 'instagram': ''}
            p['booking']['seasons'] = [{'from': '01-01', 'to': '12-31', 'nightly': 95}]
        self.edit_property(change)
        path = self.root / 'reviews.json'
        data = json.loads(path.read_text())
        data['reviews'] = []
        path.write_text(json.dumps(data))
        build.build(self.root, self.out)
        [data] = self.structured_data('index')
        self.assertNotIn('aggregateRating', data)
        self.assertNotIn('sameAs', data)
        self.assertEqual(data['priceRange'], '95 EUR')

    def sitemap(self):
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9', 'x': 'http://www.w3.org/1999/xhtml'}
        root = ET.parse(self.out / 'sitemap.xml').getroot()
        return {url.find('s:loc', ns).text: {link.get('hreflang'): link.get('href') for link in url.findall('x:link', ns)}
                for url in root.findall('s:url', ns)}

    def test_sitemap_lists_every_page_with_its_translations(self):
        build.build(self.root, self.out)
        entries = self.sitemap()
        self.assertEqual(sorted(entries), sorted([
            'https://example.com/', 'https://example.com/it/',
            'https://example.com/info.html', 'https://example.com/it/info.html',
            'https://example.com/reviews.html', 'https://example.com/it/reviews.html',
            'https://example.com/contact.html', 'https://example.com/it/contact.html',
        ]))
        self.assertEqual(entries['https://example.com/it/info.html'], {
            'en': 'https://example.com/info.html',
            'it': 'https://example.com/it/info.html',
            'x-default': 'https://example.com/info.html',
        })

    def test_sitemap_for_one_language_has_no_alternates(self):
        self.edit_property(lambda p: p.update(languages=['en'], url='https://villa.example/'))
        build.build(self.root, self.out)
        entries = self.sitemap()
        self.assertEqual(len(entries), 4)
        self.assertEqual(set(map(len, entries.values())), {0})
        self.assertNotIn('xhtml', (self.out / 'sitemap.xml').read_text())
        self.assertIn('https://villa.example/info.html', entries)  # no double slash from the trailing one

    def test_robots_points_at_the_sitemap(self):
        build.build(self.root, self.out)
        self.assertEqual((self.out / 'robots.txt').read_text(),
                         'User-agent: *\nAllow: /\n\nSitemap: https://example.com/sitemap.xml\n')

    def test_ui_strings_are_written_per_language(self):
        build.build(self.root, self.out)
        italian = (self.out / 'js' / 'strings.it.js').read_text()
        self.assertIn('"locale": "it-IT"', italian)
        self.assertIn('"mailSubject": "Richiesta di prenotazione - Casa Esempio"', italian)
        self.assertIn('Check-in date must be in the future.', (self.out / 'js' / 'strings.en.js').read_text())

    def test_numbers_follow_the_language(self):
        build.build(self.root, self.out)
        self.assertIn('<span id="home-rating">4.8</span>', self.page('index'))
        self.assertIn('<span id="home-rating">4,8</span>', self.page('it/index'))

    def test_one_language_means_no_switch_and_no_hreflang(self):
        self.edit_property(lambda p: p.update(languages=['en']))
        build.build(self.root, self.out)
        html = self.page('index')
        self.assertNotIn('lang-switch', html)
        self.assertNotIn('hreflang', html)
        self.assertIn('<link rel="canonical" href="https://example.com/">', html)
        self.assertFalse((self.out / 'it').exists())

    def test_default_language_is_the_first_listed(self):
        self.edit_property(lambda p: p.update(languages=['it', 'en']))
        build.build(self.root, self.out)
        self.assertIn('<html lang="it">', self.page('index'))
        self.assertIn('<html lang="en">', self.page('en/index'))

    def test_incomplete_translation_stops_the_build(self):
        def change(text):
            del text['home']['heroHeading']
            text['ui']['months'] = text['ui']['months'][:11]
            text['nav']['extra'] = 'Extra'
        self.edit_content('it', change)
        with self.assertRaises(BuildError) as raised:
            build.build(self.root, self.out)
        # In the order the keys appear in the file.
        self.assertEqual(str(raised.exception), 'translations do not match content/en.json:\n'
                         '  content/it.json: unexpected nav.extra\n'
                         '  content/it.json: missing home.heroHeading\n'
                         '  content/it.json: ui.months should list 12 entries')

    def test_language_without_a_content_file(self):
        self.edit_property(lambda p: p.update(languages=['en', 'it', 'fr']))
        with self.assertRaisesRegex(BuildError, 'content/fr.json is missing'):
            build.build(self.root, self.out)

    def test_bad_languages_and_url(self):
        self.edit_property(lambda p: p.update(languages=['en', 'EN']))
        with self.assertRaisesRegex(BuildError, 'languages must list two-letter codes'):
            build.build(self.root, self.out)
        self.edit_property(lambda p: p.update(languages=['en'], url='example.com'))
        with self.assertRaisesRegex(BuildError, 'url must be the address'):
            build.build(self.root, self.out)

    def test_own_scripts_and_styles_carry_a_content_hash(self):
        build.build(self.root, self.out)
        html = self.page('index')
        booking = hashlib.sha256((self.out / 'js' / 'booking.js').read_bytes()).hexdigest()[:10]
        self.assertIn(f'<script src="js/booking.js?v={booking}"></script>', html)
        self.assertIn(f'<script src="../js/booking.js?v={booking}"></script>', self.page('it/index'))
        self.assertRegex(html, r'<link rel="stylesheet" href="css/styles.css\?v=[0-9a-f]{10}">')
        for page in ('index', 'info', 'reviews', 'contact', 'it/contact'):
            self.assertNotRegex(self.page(page), r'(src|href)="(\.\./)*(js|css)/[^"?]+"', page)

    def test_changing_a_script_changes_only_its_hash(self):
        def versions():
            return dict(re.findall(r'js/([\w.-]+\.js)\?v=(\w+)', self.page('index')))

        build.build(self.root, self.out)
        before = versions()
        with open(self.root / 'js' / 'booking.js', 'a') as f:
            f.write('\n// changed\n')
        build.build(self.root, self.out)
        after = versions()
        self.assertNotEqual(before.pop('booking.js'), after.pop('booking.js'))
        self.assertEqual(before, after)

    def test_link_to_a_missing_script_stops_the_build(self):
        path = self.root / 'templates' / 'info.html'
        path.write_text(path.read_text().replace('</body>', '  <script src="{{ root }}js/missing.js"></script>\n</body>'))
        with self.assertRaisesRegex(BuildError, 'templates/info.html links to js/missing.js, which the built site does not have'):
            build.build(self.root, self.out)

    def test_reviews_are_in_the_html(self):
        build.build(self.root, self.out)
        home = self.page('index')
        self.assertIn('<span id="home-rating">4.8</span> / 5', home)
        self.assertEqual(home.count('<article class="review-card">'), 3)
        self.assertEqual(self.page('reviews').count('<article class="review-card">'), 6)

    def test_home_page_drops_the_reviews_section_without_reviews(self):
        path = self.root / 'reviews.json'
        data = json.loads(path.read_text())
        data['reviews'] = []
        path.write_text(json.dumps(data))
        build.build(self.root, self.out)
        self.assertNotIn('home-reviews', self.page('index'))

    def test_invalid_reviews_stop_the_build(self):
        path = self.root / 'reviews.json'
        data = json.loads(path.read_text())
        data['reviews'][0]['score'] = 12
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(BuildError, r'reviews.json:\n  review 1 \(Marta, PL\): score must be'):
            build.build(self.root, self.out)

    def test_missing_required_field(self):
        self.edit_property(lambda p: (p.pop('email'), p['photos'].pop('hero')))
        with self.assertRaisesRegex(BuildError, 'missing email, photos.hero'):
            build.build(self.root, self.out)

    def test_missing_photo_file(self):
        self.edit_property(lambda p: p['gallery'].append({'id': 'garden', 'src': 'assets/inside/garden.jpg'}))
        with self.assertRaisesRegex(BuildError, 'do not exist: assets/inside/garden.jpg'):
            build.build(self.root, self.out)

    def test_gallery_photo_without_text(self):
        (self.root / 'assets' / 'inside' / 'garden.jpg').write_bytes(b'')
        self.edit_property(lambda p: p['gallery'].append({'id': 'garden', 'src': 'assets/inside/garden.jpg'}))
        with self.assertRaisesRegex(BuildError, 'no gallery text for "garden"'):
            build.build(self.root, self.out)


if __name__ == '__main__':
    unittest.main()
