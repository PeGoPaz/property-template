import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import build  # noqa: E402
from build import BuildError, Markup, check_booking, fill_vars, render  # noqa: E402


class RenderTest(unittest.TestCase):
    def test_escapes_values(self):
        self.assertEqual(render('<p>{{ p.name }}</p>', {'p': {'name': 'Tom & "Jerry" <b>'}}),
                         '<p>Tom &amp; &quot;Jerry&quot; &lt;b&gt;</p>')

    def test_inserts_markup_as_is(self):
        self.assertEqual(render('{{ x }}', {'x': Markup('<b>ok</b>')}), '<b>ok</b>')

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
        problems = check_booking(booking(currency='euro', minNights=0, maxGuests=True))
        self.assertEqual(problems, [
            'currency must be a three-letter code such as "EUR"',
            'minNights must be a whole number of at least 1',
            'maxGuests must be a whole number of at least 1',
        ])

    def test_no_seasons(self):
        self.assertEqual(check_booking(booking(seasons=[])), ['seasons must list at least one season'])


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
        self.assertIn('class="gallery-thumb active" data-src="assets/inside/kitchen.jpg"', html)

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
        self.assertIn('<link rel="stylesheet" href="../css/styles.css">', html)
        self.assertIn('<script src="../js/strings.it.js"></script>', html)
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
