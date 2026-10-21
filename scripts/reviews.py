"""
Guest reviews from reviews.json, rendered into the pages at build time so they
are in the HTML for search engines and for visitors without JavaScript.
js/reviews.js only adds the "Show original" toggle to translated reviews.

reviews.json:
  platforms  [{ id, name, scale, decimals }], in the order the reviews page
             shows them. scale is the platform's top score (10 on Booking.com,
             5 on most others); decimals is how many places it shows the
             average with.
  reviews    [{ platform, reviewer, date: 'YYYY-MM', score, lang, title?, text,
               featured?, translations?: { <lang>: { title?, text } } }]
             `lang` is the language the guest wrote in. `featured` reviews
             also appear on the home page.
"""

import html
import re
from decimal import ROUND_HALF_UP, Decimal

from markup import Markup, attr, indent

STAR = ('<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 '
        '1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"></path></svg>')

YEAR_MONTH = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
LANG = re.compile(r'^[a-z]{2}$')


def round_half_up(value, places: int) -> Decimal:
    """Half up, the way the platforms show averages: 2.25 -> 2.3, where round() gives 2.2."""
    return Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_text(value) -> bool:
    return isinstance(value, str) and value.strip() != ''


# ────────────────────────────────────────────────
# Validation
# ────────────────────────────────────────────────

def check_reviews(data: dict) -> list:
    """Everything wrong with reviews.json, so one build reports it all."""
    problems = []
    platforms = data.get('platforms')
    reviews = data.get('reviews')
    if not isinstance(platforms, list) or not isinstance(reviews, list):
        return ['reviews.json needs a "platforms" list and a "reviews" list']

    known = {}
    for n, p in enumerate(platforms, 1):
        where = f'platform {n}'
        if not is_text(p.get('id')):
            problems.append(f'{where}: id is missing')
            continue
        if p['id'] in known:
            problems.append(f'{where}: id "{p["id"]}" is used twice')
        if not is_text(p.get('name')):
            problems.append(f'{where}: name is missing')
        if not (isinstance(p.get('scale'), int) and is_number(p['scale']) and p['scale'] >= 1):
            problems.append(f'{where}: scale must be the top score, such as 5 or 10')
            continue
        if not (isinstance(p.get('decimals'), int) and is_number(p['decimals']) and p['decimals'] >= 0):
            problems.append(f'{where}: decimals must be a whole number, such as 1')
        known[p['id']] = p

    for n, r in enumerate(reviews, 1):
        where = f'review {n}' + (f' ({r["reviewer"]})' if is_text(r.get('reviewer')) else '')
        if not is_text(r.get('reviewer')):
            problems.append(f'{where}: reviewer is missing')
        platform = known.get(r.get('platform'))
        if platform is None:
            problems.append(f'{where}: platform {r.get("platform")!r} is not in the platforms list')
        elif not is_number(r.get('score')) or not 0 < r['score'] <= platform['scale']:
            problems.append(f'{where}: score must be above 0 and at most {platform["scale"]}, got {r.get("score")!r}')
        if not YEAR_MONTH.match(str(r.get('date', ''))):
            problems.append(f'{where}: date must be written YYYY-MM, got {r.get("date")!r}')
        if not LANG.match(str(r.get('lang', ''))):
            problems.append(f'{where}: lang must be a two-letter code such as "en"')
        if not is_text(r.get('text')):
            problems.append(f'{where}: text is missing')
        if 'title' in r and not isinstance(r['title'], str):
            problems.append(f'{where}: title must be text')
        if 'featured' in r and not isinstance(r['featured'], bool):
            problems.append(f'{where}: featured must be true or false')
        translations = r.get('translations', {})
        if not isinstance(translations, dict):
            problems.append(f'{where}: translations must map a language code to a title and text')
            continue
        for lang, t in translations.items():
            if not LANG.match(lang) or not isinstance(t, dict) or not is_text(t.get('text')):
                problems.append(f'{where}: translation "{lang}" needs a two-letter code and a text')
    return problems


# ────────────────────────────────────────────────
# Rendering
# ────────────────────────────────────────────────

def stars(score, scale: int) -> int:
    """Booking.com's 9/10 shows as five stars, as the platform itself does."""
    return int(round_half_up(score * 5 / scale, 0))


def quoted(title: str, body: str) -> str:
    return (f'"{title}" ' if title else '') + body


def month_label(year_month: str, text: dict) -> str:
    year, month = year_month.split('-')
    return f'{text["ui"]["months"][int(month) - 1]} {year}'


def language_name(code: str, text: dict) -> str:
    return text['reviews']['languages'].get(code, code)


def card(review: dict, platform: dict, text: dict, page_lang: str, badge: bool = False) -> str:
    original = quoted(review.get('title', ''), review['text'])
    translation = review.get('translations', {}).get(page_lang) if review['lang'] != page_lang else None

    badge_html = f'<span class="review-platform">{html.escape(platform["name"])}</span>' if badge else ''
    lines = [
        '<article class="review-card">',
        '  <div class="review-stars">'
        + ''.join(f'<span>{STAR}</span>' for _ in range(stars(review['score'], platform['scale'])))
        + badge_html + '</div>',
    ]
    if translation:
        show_original = text['reviews']['showOriginal'].replace('{lang}', language_name(review['lang'], text))
        show_translation = text['reviews']['showTranslation'].replace('{lang}', language_name(page_lang, text))
        lines += [
            f'  <p class="review-text">{html.escape(quoted(translation.get("title", ""), translation["text"]))}</p>',
            f'  <p class="review-text" lang="{attr(review["lang"])}" hidden>{html.escape(original)}</p>',
            f'  <button type="button" class="review-toggle" aria-pressed="false"'
            f' data-label-original="{attr(show_original)}"'
            f' data-label-translation="{attr(show_translation)}" hidden>{html.escape(show_original)}</button>',
        ]
    else:
        lang_attr = f' lang="{attr(review["lang"])}"' if review['lang'] != page_lang else ''
        lines.append(f'  <p class="review-text"{lang_attr}>{html.escape(original)}</p>')
    lines += [
        f'  <footer class="review-footer"><strong>{html.escape(review["reviewer"])}</strong>'
        f'<span>{html.escape(month_label(review["date"], text))}</span></footer>',
        '</article>',
    ]
    return '\n'.join(lines)


def newest_first(reviews: list) -> list:
    # 'YYYY-MM' sorts as a plain string; sorted() keeps equal dates in file order.
    return sorted(reviews, key=lambda r: r['date'], reverse=True)


def average(scores: list, places: int, text: dict) -> str:
    """Mean score, written the page language's way: 4.8 in English, 4,8 in Italian."""
    return str(round_half_up(sum(scores) / len(scores), places)).replace('.', text['ui']['decimalSeparator'])


def reviews_context(data: dict, text: dict, page_lang: str = 'en') -> dict:
    platforms = data['platforms']
    by_id = {p['id']: p for p in platforms}
    reviews = data['reviews']

    sections = []
    for p in platforms:
        mine = [r for r in reviews if r['platform'] == p['id']]
        if not mine:
            continue
        cards = '\n'.join(card(r, p, text, page_lang) for r in newest_first(mine))
        sections.append(
            f'<section class="reviews-section" data-reveal>\n'
            f'  <div class="container">\n'
            f'    <div class="platform-header">\n'
            f'      <h2>{html.escape(p["name"])}</h2>\n'
            f'      <span class="platform-score">'
            f'<span>{average([r["score"] for r in mine], p["decimals"], text)}</span> / {p["scale"]}</span>\n'
            f'    </div>\n'
            f'    <div class="reviews-masonry">\n'
            + indent(cards, 6) + '\n'
            f'    </div>\n'
            f'  </div>\n'
            f'</section>')

    # Home page: featured reviews from every platform, newest first, with a badge.
    featured = newest_first([r for p in platforms for r in reviews if r['platform'] == p['id'] and r.get('featured')])
    featured_cards = '\n'.join(card(r, by_id[r['platform']], text, page_lang, badge=True) for r in featured)

    out_of_five = [r['score'] * 5 / by_id[r['platform']]['scale'] for r in reviews]
    count = len(reviews)
    return {
        'count': count,
        'rating': average(out_of_five, 1, text) if count else '',
        'countText': text['reviews']['countText'].replace('{n}', str(count)),
        'featured': Markup(indent(featured_cards, 10)),
        'sections': Markup(indent('\n\n'.join(sections), 4)),
    }
