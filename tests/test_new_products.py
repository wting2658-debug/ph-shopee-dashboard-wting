import json
import subprocess
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from process_new_products_data import load_products, merge_product_day, load_shipments, shipment_day, PERFORMANCE_FIELDS
from inject_new_products_page import inject_new_products_page, remove_new_products_page


def source_row(variation, **values):
    return {'Variation ID':variation, **{column:str(values.get(key,0)) for key,column in PERFORMANCE_FIELDS.items()}}


class NewProductsTests(unittest.TestCase):
    def test_variant_rows_do_not_duplicate_product_total(self):
        rows=[source_row('-',sales=100,units=5,impressions=1000,clicks=80),source_row('11',sales=60,units=3),source_row('12',sales=40,units=2)]
        result,issues=merge_product_day(rows)
        self.assertEqual(result['sales'],100)
        self.assertEqual(result['units'],5)
        self.assertEqual(result['impressions'],1000)
        self.assertEqual(issues,[])

    def test_missing_totals_do_not_invent_traffic(self):
        one=source_row('11',sales=60,units=3)
        result,_=merge_product_day([one,one,source_row('12',sales=40,units=2)])
        self.assertEqual(result['sales'],100)
        self.assertEqual(result['units'],5)
        self.assertIsNone(result['impressions'])

    def test_conflicting_totals_keep_unknown_fields_missing(self):
        result,issues=merge_product_day([source_row('-',sales=100,impressions=90),source_row('-',sales=100,impressions=80)])
        self.assertEqual(result['sales'],100)
        self.assertIsNone(result['impressions'])
        self.assertEqual(issues,['impressions'])

    def test_mapping_is_per_id_and_launch_conflicts_fail(self):
        rows=[{'Product ID':'123','Variation ID':'1','上新时间':'2026/5/1','链接名称':'新品'}, {'Product ID':'123','Variation ID':'2','上新时间':'2026/5/1','链接名称':'新品'}]
        products,_=load_products(rows)
        self.assertEqual(len(products),1)
        self.assertEqual(products['123']['launch'],'2026-05-01')
        rows[1]['上新时间']='2026/5/2'
        with self.assertRaises(ValueError):
            load_products(rows)

    def test_shipments_keep_platforms_separate_and_missing_distinct_from_zero(self):
        rows = [
            {'SKU':'sku-a','销量':'3','Platform':'TikTok','日期':'2026-11-14','年份':'2026'},
            {'SKU':'SKU-A','销量':'2','Platform':'Tiktok','日期':'2026-11-14','年份':'2026'},
            {'SKU':'SKU-A','销量':'8','Platform':'SHopee','日期':'2026-11-14','年份':'2026'},
            {'SKU':'SKU-A','销量':'4','Platform':'Lazada','日期':'2026-11-14','年份':'2026'},
            {'SKU':'OTHER','销量':'9','Platform':'Tiktok','日期':'2026-11-15','年份':'2026'},
            {'SKU':'SKU-A','销量':'999','Platform':'Lazada','日期':'2026-11-16','年份':'2026'},
            {'SKU':'SKU-A','销量':'999','Platform':'Other','日期':'2026-11-14','年份':'2026'},
        ]
        daily, skus, coverage = load_shipments(rows, '2026-11-15')
        self.assertEqual(shipment_day({'SKU-A'},'2026-11-14',daily,skus,coverage),
                         {'ttQty':5,'shopeeQty':8,'lazadaQty':4})
        self.assertEqual(shipment_day({'SKU-A'},'2026-11-15',daily,skus,coverage),
                         {'ttQty':0,'shopeeQty':None,'lazadaQty':None})
        self.assertEqual(shipment_day({'UNKNOWN'},'2026-11-14',daily,skus,coverage),
                         {'ttQty':None,'shopeeQty':None,'lazadaQty':None})
        self.assertNotIn('2026-11-16',coverage['Lazada'])

    def test_existing_sections_identical_and_injection_idempotent(self):
        baseline=subprocess.run(['git','show','HEAD:index.html'],cwd=ROOT,capture_output=True,check=True).stdout.decode('utf-8').replace('\r\n','\n')
        current=(ROOT/'index.html').read_text('utf-8')
        self.assertEqual(remove_new_products_page(current),remove_new_products_page(baseline))
        self.assertEqual(inject_new_products_page(current),current)

    def test_output_is_unique_and_sources_are_exposed(self):
        data=json.loads((ROOT/'assets/new-products-data.json').read_text('utf-8'))
        ids=[p['id'] for p in data['products']]
        self.assertEqual(len(ids),len(set(ids)))
        for p in data['products']:
            dates=[r['date'] for r in p['rows']]
            self.assertEqual(len(dates),len(set(dates)))
            self.assertTrue(all(d<=data['cutoff'] for d in dates))
            self.assertTrue(set(p['sharedSkus'])<=set(p['shipmentSkus']))
        self.assertEqual(data['currency'],'CNY')
        self.assertEqual(len(data['sources']),5)


if __name__=='__main__':
    unittest.main()
