import json
import csv
import re
import subprocess
import sys
import unittest
from decimal import Decimal
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from process_affiliate_data import build_data
from inject_affiliate_page import inject_affiliate_page


class AffiliateDataTest(unittest.TestCase):
    def setUp(self):
        self.rates = [['Year','Month','汇率'], ['2026','1','10']]
        self.product = ['2026','1','1','1','10','99999','99999','999%','999%','500','护肤','面霜',
                        '2026-1-1','PH','SKINTIFIC Official Shop','612831390','Cream','123456789012','Facebook','Confirmed Orders', '3','2','10','100','1','10','99','2','1']
        self.shop = ['']*10+['01/01/2026','PH','SKINTIFIC Official Shop','612831390','Confirmed Orders','10','100','3','1','1','10','99','1','1']
        self.gmv = [['','','','','','Sales-￥','Date'], ['','','','','','500','2026-1-1'], ['','','','','','9000','2026-1-1']]

    def build(self, products=None, shops=None):
        return build_data([['header']*29]+(products or [self.product]), [['header']*24]+(shops or [self.shop]), self.rates, self.gmv)

    def test_recompute_money_and_do_not_sum_repeated_store_gmv(self):
        data = self.build([self.product, self.product.copy()])
        self.assertEqual(data['rows'], [[0,0,0,10.,1.,3.,2.]])
        self.assertEqual(data['shop']['2026-01-01'], [10.,1.,3.,1.])
        self.assertEqual(data['shop_gmv']['2026-01-01'], 500)
        self.assertEqual(data['products'][0][0], '123456789012')
        self.assertEqual(data['audit']['duplicates_removed'], 1)

    def test_different_channels_retained_conflicting_duplicate_rejected(self):
        other = self.product.copy(); other[18] = 'Shopee Video'
        self.assertEqual(len(self.build([self.product, other])['rows']), 2)
        other[18] = 'Facebook'; other[23] = '101'
        with self.assertRaisesRegex(ValueError, 'Conflicting duplicate'):
            self.build([self.product, other])

    def test_missing_days_and_source_discrepancy_explicit(self):
        other = self.product.copy(); other[12] = '2026-1-3'
        shop = self.shop.copy(); shop[16] = '200'
        data = self.build([self.product, other], [shop])
        self.assertEqual(data['coverage']['missing'], ['2026-01-02'])
        self.assertEqual(data['audit']['shop_reconciliation_differences'][0]['sales_php_diff'], 100)

    def test_bad_fx_and_wrong_order_type_fail_before_asset_write(self):
        product = self.product.copy(); product[4] = '0'
        with self.assertRaisesRegex(ValueError, 'FX'):
            self.build([product])
        product[4] = '10'; product[19] = 'Placed Orders'
        with self.assertRaisesRegex(ValueError, 'scope'):
            self.build([product])

    def test_injection_is_idempotent_and_preserves_original_data(self):
        base = subprocess.check_output(['git','show','HEAD:index.html'], cwd=ROOT).decode('utf8')
        first = inject_affiliate_page(base)
        self.assertEqual(first, inject_affiliate_page(first))
        for name in ['PAYLOAD','SHIPMENT_DATA','SUBSIDY_DATA','LIVE_DATA']:
            pattern = 'const '+name+r' = (.*?);\n'
            self.assertEqual(re.search(pattern,base).group(1), re.search(pattern,first).group(1))
        for page in ['store','meta','onsite','shipment','subsidy','live','competitor']:
            pattern = r'<main[^>]*id="'+page+r'-page".*?</main>'
            self.assertEqual(re.search(pattern,base,re.S).group(), re.search(pattern,first,re.S).group())
        self.assertLess(first.index('data-dashboard-page="live"'), first.index('data-dashboard-page="affiliate"'))
        self.assertLess(first.index('data-dashboard-page="affiliate"'), first.index('data-dashboard-page="competitor"'))

    def test_live_asset_verified_control_totals(self):
        data = json.loads((ROOT/'assets/affiliate-data.json').read_text('utf8'))
        self.assertEqual(data['coverage']['start'], '2025-06-01')
        self.assertGreaterEqual(data['coverage']['end'], '2026-11-13')
        self.assertEqual(data['coverage']['missing'], [])
        checkpoint = [r for r in data['rows'] if data['dates'][r[0]] <= '2026-11-13']
        self.assertEqual(len(checkpoint), 86733)
        if data['coverage']['end'] == '2026-11-13':
            self.assertAlmostEqual(data['audit']['sales_php'], 177119063.99842, places=4)
            self.assertAlmostEqual(data['audit']['commission_php'], 4792362.23534, places=4)
        self.assertEqual(len({tuple(r[:3]) for r in data['rows']}), len(data['rows']))

    def test_every_product_record_against_raw_export(self):
        """Independent Decimal check of raw PHP/FX, units and orders, for all dates."""
        data = json.loads((ROOT/'assets/affiliate-data.json').read_text('utf8'))
        with (ROOT/'data/affiliate_rates.csv').open(encoding='utf-8-sig', newline='') as source:
            rates = {(int(r['Year']), int(r['Month'])): Decimal(r['汇率'].replace(',', ''))
                     for r in csv.DictReader(source) if r['Year'] and r['Month']}
        actual = {(data['dates'][r[0]], data['products'][r[1]][0], data['channels'][r[2]]): r[3:]
                  for r in data['rows']}
        checked = set()
        with (ROOT/'data/affiliate_products.csv').open(encoding='utf-8-sig', newline='') as source:
            for r in csv.DictReader(source):
                if not r['Date']:
                    continue
                d = datetime.strptime(r['Date'], '%Y-%m-%d').date()
                key = (d.isoformat(), r['Product ID'], r['Channel'])
                self.assertEqual((r['Region'], r['Shop ID'], r['Order Type']),
                                 ('PH', '612831390', 'Confirmed Orders'))
                fx = Decimal(r['汇率']) if r['汇率'] else rates[d.year, d.month]
                expected = [Decimal(r['Sales (Local Currency)'].replace(',', ''))/fx,
                            Decimal(r['Estimated Commission (Local Currency)'].replace(',', ''))/fx,
                            Decimal(r['Units Sold'].replace(',', '')), Decimal(r['Orders'].replace(',', ''))]
                for value, control in zip(actual[key], expected):
                    self.assertLessEqual(abs(Decimal(str(value))-control), Decimal('0.000001'), str(key))
                checked.add(key)
        self.assertEqual(checked, set(actual))


if __name__ == '__main__':
    unittest.main()
