#!/usr/bin/env python3
"""
Writes availability.json from the iCal feeds booking platforms export
(Booking.com, Airbnb, Vrbo, Google Calendar...): every date a guest cannot
stay the night, merged across all of them.

The feed URLs come from the ICAL_URLS environment variable, one per line.
Keep it in a repository secret: anyone holding a feed URL can read the
calendar, so this script never prints one, only its host.

For every event in every feed:
  - each night from DTSTART up to, not including, DTEND is blocked
  - the DTEND day is blocked too, so nobody arrives the day someone else
    leaves, unless booking.sameDayTurnover is true in property.json
  - cancelled events are skipped
Dates before yesterday are dropped; the calendar never offers them anyway.

If any feed fails, nothing is written: a calendar missing one platform's
bookings would offer those dates again.

  ICAL_URLS="https://... https://..." python3 scripts/sync_availability.py
"""

import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / 'availability.json'
PROPERTY_FILE = ROOT / 'property.json'


class SyncError(Exception):
    pass


def feed_urls(value: str) -> list:
    return value.split()


def host(url: str) -> str:
    return urlsplit(url).hostname or 'an invalid URL'


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': 'property-template-availability-sync/1.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8', errors='replace')


def ical_date(value: str):
    """The date part of 20270514 or 20270514T140000Z; None if it has none."""
    digits = re.sub(r'[^0-9]', '', value)[:8]
    if len(digits) < 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def parse_events(raw: str) -> list:
    """(start, end) for every event that is not cancelled; end is None when the feed gives none."""
    if 'BEGIN:VCALENDAR' not in raw:
        raise SyncError('does not look like an iCal feed')

    # RFC 5545 folds long lines: a line starting with a space or tab continues the one before.
    lines = re.sub(r'\r?\n[ \t]', '', raw).splitlines()

    events, event = [], None
    for line in lines:
        if line == 'BEGIN:VEVENT':
            event = {}
        elif line == 'END:VEVENT' and event is not None:
            if event.get('STATUS', '').upper() != 'CANCELLED' and event.get('DTSTART'):
                events.append((event['DTSTART'], event.get('DTEND')))
            event = None
        elif event is not None and ':' in line:
            # DTSTART;VALUE=DATE:20270514 -> name DTSTART, value 20270514
            name, value = line.split(':', 1)
            name = name.split(';', 1)[0].upper()
            if name in ('DTSTART', 'DTEND'):
                event[name] = ical_date(value)
            elif name == 'STATUS':
                event[name] = value.strip()
    return events


def blocked_dates(events: list, same_day_turnover: bool, today: date) -> list:
    earliest = today - timedelta(days=1)
    blocked = set()
    for start, end in events:
        if end is None or end <= start:
            end = start + timedelta(days=1)  # a single-day block
        last = end if not same_day_turnover else end - timedelta(days=1)
        day = max(start, earliest)
        while day <= last:
            blocked.add(day.isoformat())
            day += timedelta(days=1)
    return sorted(blocked)


def sync(urls: list, out_file: Path, same_day_turnover: bool, today: date, fetch=fetch) -> str:
    if not urls:
        raise SyncError('ICAL_URLS is empty: give it one iCal feed URL per line')

    events = []
    for n, url in enumerate(urls, 1):
        try:
            events += parse_events(fetch(url))
        except SyncError as e:
            raise SyncError(f'feed {n} ({host(url)}) {e}') from None
        except Exception as e:  # network errors, HTTP errors, timeouts
            # The class and status code only: some error messages quote the URL.
            reason = getattr(e, 'reason', e)  # URLError wraps the real cause, e.g. an SSL failure
            detail = f'HTTP {e.code}' if hasattr(e, 'code') else type(reason).__name__
            raise SyncError(f'feed {n} ({host(url)}) could not be fetched: {detail}') from None

    dates = blocked_dates(events, same_day_turnover, today)

    if out_file.exists():
        try:
            if json.loads(out_file.read_text()).get('dates') == dates:
                return f'unchanged ({len(dates)} blocked days)'
        except (json.JSONDecodeError, OSError):
            pass  # rewrite it

    payload = {
        'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source': 'ical',
        'feeds': len(urls),
        'dates': dates,
    }
    out_file.write_text(json.dumps(payload, indent=2) + '\n')
    feeds = f'{len(urls)} feed' + ('' if len(urls) == 1 else 's')
    return f'updated ({len(dates)} blocked days from {feeds})'


def main() -> int:
    same_day_turnover = json.loads(PROPERTY_FILE.read_text())['booking'].get('sameDayTurnover', False)
    try:
        print(sync(feed_urls(os.environ.get('ICAL_URLS', '')), OUT_FILE, same_day_turnover, date.today()))
    except SyncError as e:
        print(f'availability sync failed: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
