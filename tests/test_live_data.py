import csv
import json
import tempfile
import unittest
from pathlib import Path

from inject_live_page import inject_live_page
from process_live_data import duration_hours, process, start_datetime


class LiveDataTests(unittest.TestCase):
    def test_precise_hours_and_cross_midnight(self):
        self.assertAlmostEqual(duration_hours('01:53:57'), 1.8991666667)
        self.assertAlmostEqual(duration_hours('26:30:00'), 26.5)
        self.assertIsNone(duration_hours('00:99:00'))

    def test_start_date_is_day_first(self):
        self.assertEqual(start_datetime('9/11/2026 12:03').isoformat(), '2026-11-09T12:03:00')

    def fixture(self, root, duplicate=False):
        daily = root / 'daily.csv'
        sessions = root / 'sessions.csv'
        with daily.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerows([['Date','Shop GMV','Sales(Confirmed Orders)(₱)'],
                              ['2026/11/9','1,000','100'], ['2026/11/10','#N/A','']])
        with sessions.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['Livestream Session ID','Start Date','Total Live Duration','Likes','Buyers','Gross Sales(Local Currency)','日期'])
            writer.writerow(['123','9/11/2026 23:30','02:15:30','1,200','12','130','#VALUE!'])
            if duplicate:
                writer.writerow(['123','9/11/2026 23:30','02:15:30','1,200','12','130','#VALUE!'])
            writer.writerow(['','','','','','','#NUM!'])
        return daily, sessions

    def test_formula_errors_do_not_drop_valid_sessions_or_create_future_zeroes(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = process(*self.fixture(Path(directory)))
        self.assertEqual(len(payload['daily']), 1)
        self.assertEqual(payload['daily'][0]['shop_gmv'], 1000)
        self.assertEqual(payload['sessions'][0]['date'], '2026-11-09')
        self.assertEqual(payload['sessions'][0]['end'], '2026-11-10T01:45:30')
        self.assertEqual(payload['sessions'][0]['likes'], 1200)
        self.assertEqual(payload['quality']['repaired_helper_dates'], 1)

    def test_duplicate_sessions_fail_before_double_counting(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'Duplicate livestream'):
                process(*self.fixture(Path(directory), duplicate=True))

    def test_injection_is_idempotent_and_script_safe(self):
        root = Path(__file__).resolve().parents[1]
        base = (root / 'index.html').read_text(encoding='utf-8')
        payload = json.loads((root / 'live_data.json').read_text(encoding='utf-8'))
        payload['sessions'][0]['name'] = '</script><script>alert(1)</script>'
        once = inject_live_page(base, payload)
        twice = inject_live_page(once, payload)
        self.assertEqual(once, twice)
        self.assertNotIn('</script><script>alert(1)', once)
        self.assertEqual(once.count('id="live-page"'), 1)


if __name__ == '__main__':
    unittest.main()
