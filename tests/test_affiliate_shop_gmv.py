import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from process_affiliate_data import day, read_csv, shop_gmv_rows_from_daily_shop


class AffiliateShopGmvTests(unittest.TestCase):
    header = ['Date', 'Sales Confirmed', '汇率', 'Units (Add to Cart)', 'Sales-￥']

    def test_uses_confirmed_sales_and_retains_original_export_precision(self):
        rows = [self.header,
                ['2026-11-13', '766,165', '9.55', '8,301', '80227']]
        result = shop_gmv_rows_from_daily_shop(rows)
        self.assertEqual(Decimal(result[1][5]), Decimal('80226.70157'))
        self.assertEqual(result[1][6], '2026-11-13')

    def test_monthly_summary_and_future_template_are_excluded(self):
        rows = [self.header,
                ['2026-11-1', '999,999', '9.55', '/', '104712'],
                ['2026-11-1', '955', '9.55', '2', '100'],
                ['2026-11-16', '', '#N/A', '', '#N/A']]
        result = shop_gmv_rows_from_daily_shop(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1][6], '2026-11-01')
        self.assertEqual(Decimal(result[1][5]), Decimal('100'))

    def test_invalid_fx_fails_for_actual_sales(self):
        for fx in ('', '0', '-1', '#N/A', 'NaN', 'Infinity'):
            with self.subTest(fx=fx), self.assertRaisesRegex(ValueError, 'sales/FX'):
                shop_gmv_rows_from_daily_shop(
                    [self.header, ['2026-11-13', '766165', fx, '8301', '80227']])

    def test_missing_columns_and_no_actual_days_fail(self):
        with self.assertRaisesRegex(ValueError, 'missing GMV columns'):
            shop_gmv_rows_from_daily_shop([['Date', 'Sales-￥']])
        with self.assertRaisesRegex(ValueError, 'no daily GMV records'):
            shop_gmv_rows_from_daily_shop([self.header, ['2026-11-16', '', '#N/A', '', '#N/A']])

    @unittest.skipUnless((ROOT / 'data/affiliate_gmv.csv').exists() and
                         (ROOT / 'data/daily_shop.csv').exists(),
                         'Historical local exports are not checked into Git')
    def test_every_historical_day_matches_removed_gmv_source_exactly(self):
        original = {}
        for row in read_csv(ROOT / 'data/affiliate_gmv.csv')[1:]:
            if len(row) >= 7 and row[5].strip() and row[6].strip():
                original.setdefault(day(row[6]), Decimal(row[5].replace(',', '')))
        rebuilt = {}
        for row in shop_gmv_rows_from_daily_shop(read_csv(ROOT / 'data/daily_shop.csv'))[1:]:
            rebuilt.setdefault(row[6], Decimal(row[5]))
        self.assertGreaterEqual(len(original), 531)
        self.assertTrue(set(original) <= set(rebuilt))
        self.assertEqual({d: rebuilt[d] for d in original}, original)


if __name__ == '__main__':
    unittest.main()
