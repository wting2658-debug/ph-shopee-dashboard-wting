"""Build an isolated, Product-ID keyed dataset for the new-products dashboard."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from process_shipment_data import parse_shipment_date, normalize_platform

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUTPUT = ROOT / 'assets/new-products-data.json'
USD_TO_RMB = 6.8  # Same conversion as the existing Meta dashboard.
SOURCES = {
    'mapping': 'https://docs.google.com/spreadsheets/d/1dwWGTlSeO9cL8NsYQBu3JUmB-H7t02pK16gSIpetl2Y/edit?gid=911602533#gid=911602533',
    'performance': 'https://docs.google.com/spreadsheets/d/1l0nGfEPMqBVThzLVBBTZk7ydnRXwvjUaKjagLTEcnIA/edit?gid=0#gid=0',
    'onsite': 'https://docs.google.com/spreadsheets/d/1I_Q-Rx6QklML2023EUG8U1hb4MPN8shyeTyShiXrcYY/edit?gid=1711647547#gid=1711647547',
    'meta': 'https://docs.google.com/spreadsheets/d/1I_Q-Rx6QklML2023EUG8U1hb4MPN8shyeTyShiXrcYY/edit?gid=1292217820#gid=1292217820',
    'shipment': 'https://docs.google.com/spreadsheets/d/1dwWGTlSeO9cL8NsYQBu3JUmB-H7t02pK16gSIpetl2Y/edit?gid=374772985#gid=374772985',
}
PERFORMANCE_FIELDS = {
    'sales': 'Sales-￥', 'units': 'Units (Confirmed Order)',
    'orders': 'Confirmed Order', 'impressions': 'Product Impression',
    'clicks': 'Product Clicks', 'atc': 'Product Visitors (Add to Cart)',
    'atcUnits': 'Units (Add to Cart)',
}
ON_FIELDS = {'onSpend':'Ads Spend(rmb)', 'onGmv':'Ads GMV(rmb)',
             'onImpressions':'Impression', 'onClicks':'Clicks', 'onOrders':'Order'}
META_FIELDS = {'metaSpend':'花费金额 (USD)', 'metaGmv':'购物转化价值（仅共享商品）',
               'metaImpressions':'展示次数', 'metaClicks':'链接点击量', 'metaOrders':'购物次数（共享商品）'}
SHIPMENT_FIELDS = {'Tiktok':'ttQty', 'Shopee':'shopeeQty', 'Lazada':'lazadaQty'}


def number(value):
    text = str(value or '').strip().replace(',', '')
    if text in {'', '-', 'null', 'nan', '#N/A', '#VALUE!', '#DIV/0!'}:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError(f'Invalid numeric source value: {value!r}')


def iso(value):
    text = str(value or '').strip()
    if not text:
        return None
    parts = re.split(r'[-/]', text.split(' ')[0])
    if len(parts) != 3:
        raise ValueError(f'Invalid date: {text!r}')
    return date(*map(int, parts)).isoformat()


def normalized(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or '')).lower())


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as source:
        yield from csv.DictReader(source)


def load_products(rows):
    products, names, launches = {}, defaultdict(set), defaultdict(set)
    for row in rows:
        pid = row.get('Product ID', '').strip()
        if not pid or not pid.isdigit():
            continue
        name = row.get('链接名称', '').strip()
        if name:
            names[normalized(name)].add(pid)
        p = products.setdefault(pid, {'id':pid, 'name':name or row.get('Product Name', pid),
            'url':'', 'category':row.get('类目', '').strip(), 'launch':None})
        url = row.get('Link', '').strip()
        if url.startswith('https://shopee.ph/'):
            p['url'] = url
        if row.get('上新时间', '').strip():
            launches[pid].add(iso(row['上新时间']))
    for pid, dates in launches.items():
        if len(dates) != 1:
            raise ValueError(f'Conflicting launch dates for Product ID {pid}: {dates}')
        products[pid]['launch'] = next(iter(dates))
    return products, names


def merge_product_day(rows):
    """Prefer the product total. Never add variant totals to the product total.

    Conflicting repeated totals remain missing for the conflicting field only.
    Without a total, additive sales/units/orders can use unique variant rows;
    product-level traffic cannot be reconstructed from variants.
    """
    totals = [r for r in rows if r.get('Variation ID', '').strip() in {'', '-'}]
    result, conflicts = {}, []
    if totals:
        for key, col in PERFORMANCE_FIELDS.items():
            values = {number(r.get(col)) for r in totals}
            if len(values) == 1:
                result[key] = next(iter(values))
            else:
                result[key] = None
                conflicts.append(key)
        return result, conflicts
    variants = defaultdict(list)
    for row in rows:
        variants[row['Variation ID']].append(row)
    for key, col in PERFORMANCE_FIELDS.items():
        if key not in {'sales', 'units', 'orders'}:
            result[key] = None
            continue
        values = []
        for group in variants.values():
            candidates = {number(r.get(col)) for r in group}
            values.append(next(iter(candidates)) if len(candidates) == 1 else None)
        result[key] = sum(values) if values and all(v is not None for v in values) else None
    return result, ['missing_product_total']


def window(launch, mode='cumulative', year='', month=''):
    start, end = launch, '9999-12-31'
    if mode in {'year', 'month'}:
        first = f'{year}-{month if mode == "month" else "01"}-01'
        y, m, _ = map(int, first.split('-'))
        following = date(y+1, 1, 1) if mode == 'year' or m == 12 else date(y, m+1, 1)
        start, end = max(start, first), (following-timedelta(days=1)).isoformat()
    return start, end


def load_shipments(rows, cutoff):
    daily = defaultdict(float)
    skus = {platform:set() for platform in SHIPMENT_FIELDS}
    coverage = {platform:set() for platform in SHIPMENT_FIELDS}
    for row in rows:
        platform = normalize_platform(row.get('Platform'))
        if platform not in SHIPMENT_FIELDS:
            continue
        qty = number(row.get('销量'))
        try:
            d = parse_shipment_date(row.get('日期'), row.get('年份')).isoformat()
        except ValueError:
            if qty:
                raise
            continue
        if d > cutoff:
            continue
        coverage[platform].add(d)
        sku = row.get('SKU', '').strip().upper()
        if sku:
            skus[platform].add(sku)
            daily[(platform,sku,d)] += qty or 0
    return daily, skus, coverage


def shipment_day(product_skus, day, daily, platform_skus, coverage):
    values = {}
    for platform, field in SHIPMENT_FIELDS.items():
        matched = product_skus & platform_skus[platform]
        values[field] = sum(daily.get((platform,sku,day),0) for sku in matched) if matched and day in coverage[platform] else None
    return values


def build_dataset():
    products, names = load_products(read_csv(DATA/'new_products_mapping.csv'))
    selected = {pid:p for pid,p in products.items() if p['launch']}
    if not selected:
        raise ValueError('No launch dates found in mapping column L')
    cutoff = (datetime.now(timezone(timedelta(hours=8))).date()-timedelta(days=1)).isoformat()
    groups, sku_ids, product_skus = defaultdict(list), defaultdict(set), defaultdict(set)
    coverage = {key:set() for key in ['performance', 'onsite', 'meta', 'shipment']}
    for row in read_csv(DATA/'new_products_daily.csv'):
        d, pid = iso(row['Date']), row['Item ID'].strip()
        if not d or d > cutoff:
            continue
        coverage['performance'].add(d)
        sku = row.get('SKU', '').strip().upper()
        if sku and sku != '-':
            sku_ids[sku].add(pid)
            product_skus[pid].add(sku)
        if pid in selected:
            groups[(pid,d)].append(row)
    if not coverage['performance'] or not groups:
        raise ValueError('No product-day performance data matched the launch mapping')
    records, issues = defaultdict(dict), []
    for (pid,d), rows in groups.items():
        values, conflicts = merge_product_day(rows)
        records[pid][d] = {'date':d, **values}
        if conflicts:
            issues.append({'id':pid,'date':d,'fields':conflicts})
    ad_rows = list(read_csv(DATA/'onsite_ads_sheet_1711647547.csv'))
    for row in ad_rows:
        pid, name = row['产品ID'].strip(), normalized(row['站内产品命名'])
        if pid.isdigit() and name:
            names[name].add(pid)
    on, meta, meta_names, meta_ambiguous = defaultdict(lambda:defaultdict(float)), defaultdict(lambda:defaultdict(float)), defaultdict(set), set()
    for row in ad_rows:
        d, pid = iso(row['date']), row['产品ID'].strip()
        if not d or d > cutoff:
            continue
        coverage['onsite'].add(d)
        if pid in selected:
            for key,col in ON_FIELDS.items():
                on[(pid,d)][key] += number(row[col]) or 0
    for row in read_csv(DATA/'raw_data_sheet_1292217820.csv'):
        d = iso(row['单日'])
        if not d or d > cutoff:
            continue
        coverage['meta'].add(d)
        name = normalized(row.get('站内产品名') or row.get('产品'))
        candidates = names.get(name, set())
        if len(candidates) != 1:
            meta_ambiguous.update(candidates & selected.keys())
            continue
        pid = next(iter(candidates))
        if pid not in selected:
            continue
        meta_names[pid].add(row.get('站内产品名') or row.get('产品'))
        for key,col in META_FIELDS.items():
            amount = number(row.get(col)) or 0
            if key in {'metaSpend','metaGmv'}:
                amount *= USD_TO_RMB
            meta[(pid,d)][key] += amount
    shipment_file = DATA/'shipment_raw.csv'
    if not shipment_file.exists():
        shipment_file = ROOT/'shipment_raw.csv'
    sku_daily, platform_skus, shipment_coverage = load_shipments(read_csv(shipment_file), cutoff)
    shipment_skus = set().union(*platform_skus.values())
    coverage['shipment'] = set().union(*shipment_coverage.values())
    for pid,p in selected.items():
        skus = sorted(product_skus[pid] & shipment_skus)
        p['shipmentSkus'] = skus
        p['sharedSkus'] = [s for s in skus if len(sku_ids[s]) > 1]
        p['metaNames'] = sorted(meta_names[pid])
        p['metaAmbiguous'] = pid in meta_ambiguous
        p['preStart'] = (date.fromisoformat(p['launch'])-timedelta(days=7)).isoformat()
        p['preEnd'] = (date.fromisoformat(p['launch'])-timedelta(days=1)).isoformat()
        dates = set(records[pid]) | {d for x,d in on if x==pid} | {d for x,d in meta if x==pid}
        # Include shipment-only dates after launch and the prelaunch observation window.
        dates |= {d for d in coverage['shipment'] if p['preStart'] <= d <= cutoff}
        for d in sorted(dates):
            if d < p['preStart']:
                continue
            record = records[pid].setdefault(d, {'date':d, **dict.fromkeys(PERFORMANCE_FIELDS)})
            for key in ON_FIELDS:
                record[key] = round(on[(pid,d)].get(key,0),6) if d in coverage['onsite'] else None
            for key in META_FIELDS:
                record[key] = round(meta[(pid,d)].get(key,0),6) if d in coverage['meta'] and meta_names[pid] and pid not in meta_ambiguous else None
            record.update(shipment_day(product_skus[pid], d, sku_daily, platform_skus, shipment_coverage))
            for key in PERFORMANCE_FIELDS:
                if record[key] is not None:
                    record[key] = round(record[key],6)
        p['rows'] = [records[pid][d] for d in sorted(records[pid]) if d >= p['preStart']]
    return {'generatedAt':datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
            'cutoff':cutoff, 'currency':'CNY', 'usdToRmb':USD_TO_RMB, 'sources':SOURCES,
            'coverage':{key:{'start':min(ds) if ds else None,'end':max(ds) if ds else None,'dates':sorted(ds)} for key,ds in coverage.items()},
            'shipmentCoverage':{platform:sorted(ds) for platform,ds in shipment_coverage.items()},
            'products':sorted(selected.values(),key=lambda p:(p['launch'],p['id']),reverse=True),
            'issues':issues, 'undatedLinks':sum(not p['launch'] for p in products.values())}


def main():
    dataset = build_dataset()
    OUTPUT.write_text(json.dumps(dataset,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    print(f'New products: {len(dataset["products"])}; field conflicts: {len(dataset["issues"])}; output: {OUTPUT.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
