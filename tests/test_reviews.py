import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from reviews import check_reviews, reviews_context, round_half_up, stars  # noqa: E402

SAMPLE = json.loads((ROOT / 'reviews.json').read_text())
TEXT = json.loads((ROOT / 'content' / 'en.json').read_text())


def sample(change=None):
    data = copy.deepcopy(SAMPLE)
    if change:
        change(data)
    return data


class RoundingTest(unittest.TestCase):
    def test_half_up(self):
        self.assertEqual(str(round_half_up(2.25, 1)), '2.3')
        self.assertEqual(str(round_half_up(4.75, 1)), '4.8')
        self.assertEqual(str(round_half_up(4.5, 2)), '4.50')

    def test_stars_on_a_ten_point_scale(self):
        self.assertEqual(stars(10, 10), 5)
        self.assertEqual(stars(9, 10), 5)   # 4.5 rounds up, as Booking.com shows it
        self.assertEqual(stars(7, 10), 4)
        self.assertEqual(stars(4, 5), 4)


class CheckReviewsTest(unittest.TestCase):
    def test_sample_passes(self):
        self.assertEqual(check_reviews(SAMPLE), [])

    def test_needs_both_lists(self):
        self.assertEqual(check_reviews({'reviews': []}),
                         ['reviews.json needs a "platforms" list and a "reviews" list'])

    def test_no_reviews_yet_is_fine(self):
        self.assertEqual(check_reviews(sample(lambda d: d.update(reviews=[]))), [])

    def test_review_problems(self):
        def break_it(d):
            d['reviews'][0].update(platform='tripadvisor')
            d['reviews'][1].update(score=11, date='2026-13', lang='German')
            d['reviews'][2].update(text='  ', featured='yes')
            d['reviews'][3]['translations'] = {'it': {'title': 'Solo titolo'}}
        self.assertEqual(check_reviews(sample(break_it)), [
            "review 1 (Marta, PL): platform 'tripadvisor' is not in the platforms list",
            'review 2 (Jonas, DE): score must be above 0 and at most 10, got 11',
            "review 2 (Jonas, DE): date must be written YYYY-MM, got '2026-13'",
            'review 2 (Jonas, DE): lang must be a two-letter code such as "en"',
            'review 3 (Claire, FR): text is missing',
            'review 3 (Claire, FR): featured must be true or false',
            'review 4 (Daniel): translation "it" needs a two-letter code and a text',
        ])

    def test_platform_problems(self):
        def break_it(d):
            d['platforms'][1].update(id='booking')
            d['platforms'][2].update(scale=0)
        problems = check_reviews(sample(break_it))
        self.assertIn('platform 2: id "booking" is used twice', problems)
        self.assertIn('platform 3: scale must be the top score, such as 5 or 10', problems)


class ReviewsContextTest(unittest.TestCase):
    def setUp(self):
        self.context = reviews_context(SAMPLE, TEXT)

    def test_overall_rating_on_five_points(self):
        # (10 + 9 + 10) / 2 and 5, 4, 5 -> 28.5 / 6 = 4.75
        self.assertEqual(self.context['rating'], '4.8')
        self.assertEqual(self.context['count'], 6)
        self.assertEqual(self.context['countText'], 'from 6 guest reviews')

    def test_sections_follow_platform_order_with_their_own_scale(self):
        sections = self.context['sections']
        self.assertLess(sections.index('Booking.com'), sections.index('Airbnb'))
        self.assertLess(sections.index('Airbnb'), sections.index('Google Maps'))
        self.assertIn('<span>9.7</span> / 10', sections)
        self.assertIn('<span>4.50</span> / 5', sections)
        self.assertIn('<span>5.0</span> / 5', sections)

    def test_platform_without_reviews_gets_no_section(self):
        context = reviews_context(sample(lambda d: d.update(reviews=[r for r in d['reviews'] if r['platform'] != 'google'])), TEXT)
        self.assertNotIn('Google Maps', context['sections'])

    def test_featured_reviews_newest_first_with_badges(self):
        featured = self.context['featured']
        order = [featured.index(name) for name in ('Daniel', 'Marta, PL', 'Claire, FR')]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('Jonas', featured)
        self.assertIn('<span class="review-platform">Airbnb</span>', featured)

    def test_translated_review_keeps_the_original_behind_a_toggle(self):
        sections = self.context['sections']
        self.assertIn('<p class="review-text">&quot;A great base for exploring the lake.&quot; Quiet street', sections)
        self.assertIn('<p class="review-text" lang="de" hidden>&quot;Ideal, um den See zu erkunden.&quot;', sections)
        self.assertIn('data-label-original="Show original (German)"', sections)
        self.assertIn('data-label-translation="Show translation (English)" hidden>Show original (German)</button>', sections)

    def test_untranslated_foreign_review_is_marked_with_its_language(self):
        def add(d):
            d['reviews'].append({'platform': 'google', 'reviewer': 'Lukas', 'date': '2026-04',
                                 'score': 5, 'lang': 'de', 'text': 'Sehr schön.'})
        context = reviews_context(sample(add), TEXT)
        self.assertIn('<p class="review-text" lang="de">Sehr schön.</p>', context['sections'])
        self.assertNotIn('Show original (German)">Sehr', context['sections'])

    def test_month_names_and_escaping(self):
        def add(d):
            d['reviews'].append({'platform': 'google', 'reviewer': '<script>x</script>', 'date': '2026-01',
                                 'score': 5, 'lang': 'en', 'text': 'Fine & dandy'})
        sections = reviews_context(sample(add), TEXT)['sections']
        self.assertIn('<strong>&lt;script&gt;x&lt;/script&gt;</strong><span>January 2026</span>', sections)
        self.assertIn('Fine &amp; dandy', sections)

    def test_no_reviews(self):
        context = reviews_context(sample(lambda d: d.update(reviews=[])), TEXT)
        self.assertEqual((context['count'], context['rating'], context['sections'], context['featured']),
                         (0, '', '', ''))


if __name__ == '__main__':
    unittest.main()
