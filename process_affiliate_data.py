"""Build the affiliate asset from the existing Google Sheets export.

Money is recomputed from raw PHP and the row/month FX rate. Never sum the
repeated Shop GMV column, or use product orders as unique shop orders.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHEET = 'https://docs.google.com/spreadsheets/d/1zDffbrbBkPn5oTnOD2xy1MwEFwXczXyLUeRkH7bPeng/edit'


def number(value):
    text = str('' if value is None else value).strip().replace(',', '').replace('₱', '').replace('¥', '')
    try:
        result = float(text)
    except ValueError:
        raise ValueError(f'Invalid numeric value: {value!r}') from None
    if not math.isfinite(result):
        raise ValueError(f'Non-finite numeric value: {value!r}')
    return result


def day(value):
    text = str(value).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f'Invalid date: {value!r}')


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as source:
        return list(csv.reader(source))


def shop_gmv_rows_from_daily_shop(rows):
    """Reconstruct the former F:G GMV export from the same confirmed-sales source.

    The old affiliate GMV worksheet was removed. Its daily CNY values match
    Sales Confirmed / FX in the shop-day source at Google CSV's ten significant
    digits; that source's Sales-￥ column is rounded to whole yuan instead.
    """
    if not rows:
        raise ValueError('Daily shop export is empty')
    header = [cell.strip() for cell in rows[0]]
    required = ('Date', 'Sales Confirmed', '汇率', 'Units (Add to Cart)')
    missing = [name for name in required if name not in header]
    if missing:
        raise ValueError(f'Daily shop export missing GMV columns: {missing}')
    indices = {name: header.index(name) for name in required}
    result = [['', '', '', '', '', 'Sales-￥', 'Date']]
    for row in rows[1:]:
        cell = lambda name: row[indices[name]].strip() if len(row) > indices[name] else ''
        # Monthly totals reuse the first date of the month, and future template
        # rows have no confirmed sales. Neither is a daily GMV observation.
        if cell('Units (Add to Cart)') == '/' or not cell('Sales Confirmed'):
            continue
        d = day(cell('Date'))
        try:
            sales = Decimal(cell('Sales Confirmed').replace(',', ''))
            fx = Decimal(cell('汇率').replace(',', ''))
        except InvalidOperation:
            raise ValueError(f'Invalid daily shop sales/FX at {d}') from None
        if not sales.is_finite() or not fx.is_finite() or fx <= 0:
            raise ValueError(f'Invalid daily shop sales/FX at {d}')
        result.append(['', '', '', '', '', format(sales / fx, '.10g'), d])
    if len(result) == 1:
        raise ValueError('Daily shop export contains no daily GMV records')
    return result


def build_data(product_rows, shop_rows, rate_rows, gmv_rows):
    rates = {}
    for row in rate_rows[1:]:
        if len(row) >= 3 and row[0].strip() and row[1].strip():
            rates[f'{int(number(row[0])):04d}-{int(number(row[1])):02d}'] = number(row[2])
    # F:G is the daily CNY source. First match deliberately excludes the later
    # monthly subtotal which reuses the month's first date in this source.
    shop_gmv = {}
    for row in gmv_rows[1:]:
        if len(row) >= 7 and row[5].strip() and row[6].strip():
            shop_gmv.setdefault(day(row[6]), number(row[5]))

    records, products, channels, dates, daily_local = {}, {}, set(), set(), defaultdict(lambda: [0., 0., 0.])
    duplicates = 0
    for row in product_rows[1:]:
        if len(row) < 29 or not row[12].strip():
            continue
        d = day(row[12]); raw = row[12:29]
        if raw[1] != 'PH' or raw[3] != '612831390' or raw[7] != 'Confirmed Orders':
            raise ValueError(f'Unexpected affiliate scope at {d}: {raw[1:8]}')
        key = (d, raw[3], raw[5], raw[6], raw[7])
        fx = number(row[4]) if row[4].strip() else rates.get(d[:7])
        if not fx or fx <= 0:
            raise ValueError(f'Missing PHP/CNY FX at {d}')
        sales, cost, units, orders = map(number, (raw[11], raw[13], raw[8], raw[9]))
        value = (sales, cost, units, orders, fx)
        if key in records:
            if records[key] != value:
                raise ValueError(f'Conflicting duplicate affiliate key: {key}')
            duplicates += 1
            continue
        records[key] = value
        category = row[10].strip() or '未匹配类目'
        name = row[11].strip() or raw[4]
        products[raw[5]] = [raw[5], category, name, raw[4]]
        channels.add(raw[6]); dates.add(d)
        daily_local[d][0] += sales; daily_local[d][1] += cost; daily_local[d][2] += units

    if not records:
        raise ValueError('Affiliate product export contains no records')
    product_list = sorted(products.values(), key=lambda p: p[0])
    product_index = {p[0]: i for i, p in enumerate(product_list)}
    channel_list, date_list = sorted(channels), sorted(dates)
    channel_index = {c: i for i, c in enumerate(channel_list)}
    date_index = {d: i for i, d in enumerate(date_list)}
    rows = []
    for (d, _, pid, channel, _), (sales, cost, units, orders, fx) in sorted(records.items()):
        rows.append([date_index[d], product_index[pid], channel_index[channel], round(sales/fx, 6), round(cost/fx, 6), units, orders])

    shop = {}
    for row in shop_rows[1:]:
        if len(row) < 24 or not row[10].strip():
            continue
        r = row[10:24]; d = day(r[0])
        if r[1] != 'PH' or r[3] != '612831390' or r[4] != 'Confirmed Orders':
            raise ValueError(f'Unexpected shop scope at {d}')
        fx = rates.get(d[:7])
        if not fx or fx <= 0:
            raise ValueError(f'Missing shop FX at {d}')
        value = [round(number(r[6])/fx, 6), round(number(r[10])/fx, 6), number(r[7]), number(r[8])]
        if d in shop and shop[d] != value:
            raise ValueError(f'Conflicting shop day: {d}')
        shop[d] = value

    reconciliations = []
    for d, values in shop.items():
        if d not in daily_local:
            continue
        local = daily_local[d]; fx = rates[d[:7]]
        diff = [values[0]*fx-local[0], values[1]*fx-local[1], values[2]-local[2]]
        if max(abs(diff[0]), abs(diff[1])) > 1 or abs(diff[2]) > .01:
            reconciliations.append({'date': d, 'sales_php_diff': round(diff[0], 4), 'commission_php_diff': round(diff[1], 4), 'units_diff': diff[2]})
    start, end = date.fromisoformat(date_list[0]), date.fromisoformat(date_list[-1])
    missing = []
    while start <= end:
        if start.isoformat() not in dates:
            missing.append(start.isoformat())
        start += timedelta(days=1)
    return {
        'schema': 1, 'order_type': 'Confirmed Orders', 'currency': 'CNY',
        'source': SHEET+'?gid=1684158147', 'shop_source': SHEET+'?gid=1971481596',
        'coverage': {'start': date_list[0], 'end': date_list[-1], 'days': len(dates), 'missing': missing},
        'products': product_list, 'channels': channel_list, 'dates': date_list,
        'columns': ['date_index', 'product_index', 'channel_index', 'gmv_cny', 'commission_cny', 'units', 'product_orders'],
        'rows': rows, 'shop': shop, 'shop_gmv': shop_gmv,
        'audit': {'rows': len(rows), 'duplicates_removed': duplicates, 'sales_php': sum(v[0] for v in daily_local.values()), 'commission_php': sum(v[1] for v in daily_local.values()), 'shop_reconciliation_differences': reconciliations},
    }


def main():
    data = ROOT / 'data'
    result = build_data(
        *(read_csv(data / f'affiliate_{name}.csv') for name in ('products', 'shop', 'rates')),
        shop_gmv_rows_from_daily_shop(read_csv(data / 'daily_shop.csv')),
    )
    output = ROOT / 'assets/affiliate-data.json'
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'coverage': result['coverage'], 'rows': len(result['rows']), 'products': len(result['products']), 'bytes': output.stat().st_size, 'reconciliation_warnings': len(result['audit']['shop_reconciliation_differences'])}))


if __name__ == '__main__':
    main()
