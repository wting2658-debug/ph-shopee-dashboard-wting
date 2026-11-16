import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from process_daily_report_data import shop_days
from inject_daily_report_page import inject_daily_report_page, remove_daily_report_page


class DailyReportTests(unittest.TestCase):
    def test_monthly_summary_and_future_templates_do_not_inflate_buyers(self):
        base = {'Date': '2026/1/1', '# of buyers': '2541', '# of new buyers': '1668', 'Units (Add to Cart)': '100'}
        summary = {**base, '# of buyers': '54693', '# of new buyers': '39075', 'Units (Add to Cart)': '/'}
        future = {**base, 'Date': '2026/11/16', '# of buyers': '', '# of new buyers': ''}
        self.assertEqual(shop_days([base, summary, base, future]), {'2026-01-01': {'buyers': 2541, 'newBuyers': 1668}})

    def test_zero_buyers_are_valid_and_conflicts_fail(self):
        row = {'Date': '2026/11/1', '# of buyers': '0', '# of new buyers': '0'}
        self.assertEqual(shop_days([row])['2026-11-01']['newBuyers'], 0)
        with self.assertRaises(ValueError):
            shop_days([row, {**row, '# of new buyers': '1'}])

    def test_real_daily_buyer_values_and_source(self):
        data = json.loads((ROOT/'assets/daily-report-data.json').read_text('utf-8'))
        self.assertEqual(data['shop']['2026-01-01']['newBuyers'], 1668)
        self.assertEqual(data['shop']['2026-11-15']['newBuyers'], 863)
        self.assertEqual(sum(v['newBuyers'] for d,v in data['shop'].items() if '2026-11-01' <= d <= '2026-11-15'), 12308)
        self.assertNotIn('2026-11-16', data['shop'])
        self.assertIn('gid=1222028246', data['sources']['shop'])

    def test_only_daily_report_is_added_and_injection_is_idempotent(self):
        baseline = subprocess.run(['git','show','HEAD:index.html'], cwd=ROOT, capture_output=True, check=True).stdout.decode('utf-8').replace('\r\n','\n')
        current = (ROOT/'index.html').read_text('utf-8')
        self.assertEqual(remove_daily_report_page(current), remove_daily_report_page(baseline))
        self.assertEqual(inject_daily_report_page(current), current)


if __name__ == '__main__':
    unittest.main()
