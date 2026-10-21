import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import build  # noqa: E402
from build import BuildError, Markup, fill_name, render  # noqa: E402


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


class FillNameTest(unittest.TestCase):
    def test_fills_nested_strings(self):
        content = {'a': 'Stay at {name}', 'b': {'c': ['{name}!', 3]}}
        self.assertEqual(fill_name(content, 'Casa'), {'a': 'Stay at Casa', 'b': {'c': ['Casa!', 3]}})


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

    def test_builds_every_page_with_nothing_left_unfilled(self):
        self.assertEqual(build.build(self.root, self.out),
                         ['index.html', 'info.html', 'reviews.html', 'contact.html'])
        for page in ('index', 'info', 'reviews', 'contact'):
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
