"""Calendar-aligned comparisons must ignore future zero placeholders."""
import calendar
import unittest
from datetime import date

from process_subsidy_data import _monthly_rollup


def month_rows(month, through, value=100):
    year, number = map(int, month.split('-'))
    return [dict(date=f'{month}-{day:02d}', tt_gmv=value if day <= through else 0,
                 sp_gmv=value * 2 if day <= through else 0,
                 tt_subsidy=10 if day <= through else 0,
                 sp_subsidy=30 if day <= through else 0)
            for day in range(1, calendar.monthrange(year, number)[1] + 1)]


class RollupTests(unittest.TestCase):
    def test_prefilled_month_is_compared_through_15_not_30(self):
        daily = month_rows('2026-10', 31) + month_rows('2026-11', 15, 200)
        latest = _monthly_rollup(daily, as_of=date(2026, 11, 16))[-1]
        self.assertEqual((latest['start'], latest['end'], latest['days']),
                         ('2026-11-01', '2026-11-15', 15))
        self.assertEqual(latest['tt_gmv'], 3000)
        self.assertEqual(latest['previous_same_tt_gmv'], 1500)
        self.assertEqual(latest['previous_same_sp_subsidy'], 450)
        self.assertEqual(latest['previous_same_sp_rate'], 450 / 3000)
        self.assertEqual(latest['previous_tt_gmv'], 3100)
        self.assertEqual(latest['previous_same_end'], '2026-10-15')
        self.assertEqual(len(daily), 61)  # Chart data stays intact.

    def test_late_data_and_today_are_not_counted(self):
        daily = month_rows('2026-10', 31) + month_rows('2026-11', 14)
        self.assertEqual(_monthly_rollup(daily, as_of=date(2026, 11, 16))[-1]['end'], '2026-11-14')
        daily = month_rows('2026-10', 31) + month_rows('2026-11', 16)
        self.assertEqual(_monthly_rollup(daily, as_of=date(2026, 11, 16))[-1]['end'], '2026-11-15')

    def test_short_month_and_year_boundary(self):
        latest = _monthly_rollup(month_rows('2026-02', 28) + month_rows('2026-03', 31),
                                 as_of=date(2026, 4, 1))[-1]
        self.assertEqual(latest['previous_same_end'], '2026-02-28')
        self.assertEqual(latest['previous_same_tt_gmv'], 2800)
        latest = _monthly_rollup(month_rows('2025-12', 31) + month_rows('2026-01', 15),
                                 as_of=date(2026, 1, 16))[-1]
        self.assertEqual(latest['previous_same_end'], '2025-12-15')

    def test_missing_calendar_dates_do_not_shift_comparison(self):
        daily = month_rows('2026-10', 31) + month_rows('2026-11', 15)
        daily = [r for r in daily if r['date'] != '2026-10-02']
        latest = _monthly_rollup(daily, as_of=date(2026, 11, 16))[-1]
        self.assertIsNone(latest['previous_same_tt_gmv'])
        self.assertEqual(latest['previous_same_end'], '2026-10-15')
        latest = _monthly_rollup(month_rows('2026-09', 30) + month_rows('2026-11', 15),
                                 as_of=date(2026, 11, 16))[-1]
        self.assertIsNone(latest['previous_month'])


if __name__ == '__main__':
    unittest.main()
