import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from sync_availability import SyncError, blocked_dates, feed_urls, parse_events, sync  # noqa: E402

TODAY = date(2027, 5, 1)

# Shaped like Booking.com's export: all-day events, CRLF line ends.
BOOKING = (
    'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Booking.com//EN\r\n'
    'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20270514\r\nDTEND;VALUE=DATE:20270518\r\n'
    'SUMMARY:CLOSED - Not available\r\nEND:VEVENT\r\n'
    'END:VCALENDAR\r\n'
)

# Shaped like Airbnb's: a folded DESCRIPTION line, plus an owner block with no DTEND.
AIRBNB = (
    'BEGIN:VCALENDAR\nPRODID:-//Airbnb Inc//Hosting Calendar//EN\n'
    'BEGIN:VEVENT\nDTEND;VALUE=DATE:20270605\nDTSTART;VALUE=DATE:20270601\n'
    'DESCRIPTION:Reservation URL: https://www.airbnb.com/hosting/reservations/de\n'
    ' tails/HMXXXX\nSUMMARY:Reserved\nEND:VEVENT\n'
    'BEGIN:VEVENT\nDTSTART;VALUE=DATE:20270620\nSUMMARY:Airbnb (Not available)\nEND:VEVENT\n'
    'END:VCALENDAR\n'
)


def days(*ranges):
    out = []
    for first, last in ranges:
        d = first
        while d <= last:
            out.append(d.isoformat())
            d = date.fromordinal(d.toordinal() + 1)
    return out


class ParseEventsTest(unittest.TestCase):
    def test_all_day_events(self):
        self.assertEqual(parse_events(BOOKING), [(date(2027, 5, 14), date(2027, 5, 18))])

    def test_folded_lines_and_missing_end(self):
        self.assertEqual(parse_events(AIRBNB), [(date(2027, 6, 1), date(2027, 6, 5)),
                                               (date(2027, 6, 20), None)])

    def test_date_times_keep_their_date(self):
        raw = ('BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;TZID=Europe/Rome:20270710T150000\n'
               'DTEND:20270714T100000Z\nEND:VEVENT\nEND:VCALENDAR\n')
        self.assertEqual(parse_events(raw), [(date(2027, 7, 10), date(2027, 7, 14))])

    def test_cancelled_events_are_skipped(self):
        raw = BOOKING.replace('SUMMARY:', 'STATUS:CANCELLED\r\nSUMMARY:')
        self.assertEqual(parse_events(raw), [])

    def test_not_a_calendar(self):
        with self.assertRaisesRegex(SyncError, 'does not look like an iCal feed'):
            parse_events('<html>Sign in</html>')


class BlockedDatesTest(unittest.TestCase):
    def test_checkout_day_is_kept_free_for_cleaning(self):
        events = [(date(2027, 5, 14), date(2027, 5, 18))]
        self.assertEqual(blocked_dates(events, False, TODAY), days((date(2027, 5, 14), date(2027, 5, 18))))

    def test_same_day_turnover_blocks_only_the_nights(self):
        events = [(date(2027, 5, 14), date(2027, 5, 18))]
        self.assertEqual(blocked_dates(events, True, TODAY), days((date(2027, 5, 14), date(2027, 5, 17))))

    def test_single_day_block(self):
        self.assertEqual(blocked_dates([(date(2027, 6, 20), None)], True, TODAY), ['2027-06-20'])

    def test_past_dates_are_dropped_but_yesterday_stays(self):
        events = [(date(2027, 4, 20), date(2027, 5, 3))]
        self.assertEqual(blocked_dates(events, True, TODAY), days((date(2027, 4, 30), date(2027, 5, 2))))

    def test_overlapping_feeds_merge(self):
        events = [(date(2027, 5, 14), date(2027, 5, 16)), (date(2027, 5, 15), date(2027, 5, 17))]
        self.assertEqual(blocked_dates(events, True, TODAY), days((date(2027, 5, 14), date(2027, 5, 16))))


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.out = self.tmp / 'availability.json'
        self.feeds = {'https://ical.booking.com/v1/export?t=secret': BOOKING,
                      'https://www.airbnb.com/calendar/ical/1.ics?s=secret': AIRBNB}

    def fake_fetch(self, url):
        if url not in self.feeds:
            raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
        return self.feeds[url]

    def test_urls_one_per_line_or_space_separated(self):
        self.assertEqual(feed_urls(' https://a/1\nhttps://b/2  https://c/3\n'),
                         ['https://a/1', 'https://b/2', 'https://c/3'])

    def test_writes_dates_from_every_feed(self):
        result = sync(list(self.feeds), self.out, False, TODAY, self.fake_fetch)
        written = json.loads(self.out.read_text())
        self.assertEqual(written['feeds'], 2)
        self.assertEqual(written['dates'], days((date(2027, 5, 14), date(2027, 5, 18)),
                                                (date(2027, 6, 1), date(2027, 6, 5)),
                                                (date(2027, 6, 20), date(2027, 6, 21))))
        self.assertEqual(result, 'updated (12 blocked days from 2 feeds)')

    def test_one_feed(self):
        url = 'https://ical.booking.com/v1/export?t=secret'
        self.assertEqual(sync([url], self.out, False, TODAY, self.fake_fetch), 'updated (5 blocked days from 1 feed)')

    def test_leaves_the_file_alone_when_nothing_changed(self):
        sync(list(self.feeds), self.out, False, TODAY, self.fake_fetch)
        before = self.out.read_text()
        self.assertEqual(sync(list(self.feeds), self.out, False, TODAY, self.fake_fetch),
                         'unchanged (12 blocked days)')
        self.assertEqual(self.out.read_text(), before)

    def test_one_failing_feed_writes_nothing_and_hides_the_url(self):
        self.out.write_text('{"dates": ["2027-01-01"]}')
        urls = list(self.feeds) + ['https://www.vrbo.com/icalendar/abc123secret.ics']
        with self.assertRaises(SyncError) as raised:
            sync(urls, self.out, False, TODAY, self.fake_fetch)
        self.assertEqual(str(raised.exception), 'feed 3 (www.vrbo.com) could not be fetched: HTTP 404')
        self.assertNotIn('secret', str(raised.exception))
        self.assertEqual(self.out.read_text(), '{"dates": ["2027-01-01"]}')

    def test_feed_that_is_not_a_calendar(self):
        self.feeds['https://www.airbnb.com/calendar/ical/1.ics?s=secret'] = '<html>Sign in</html>'
        with self.assertRaisesRegex(SyncError, r'^feed 2 \(www.airbnb.com\) does not look like an iCal feed$'):
            sync(list(self.feeds), self.out, False, TODAY, self.fake_fetch)

    def test_no_urls(self):
        with self.assertRaisesRegex(SyncError, 'ICAL_URLS is empty'):
            sync([], self.out, False, TODAY, self.fake_fetch)


if __name__ == '__main__':
    unittest.main()
