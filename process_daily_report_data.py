"""Prepare the daily report's supplemental shop and affiliate metrics."""
from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHOP_SOURCE = 'https://docs.google.com/spreadsheets/d/1dwWGTlSeO9cL8NsYQBu3JUmB-H7t02pK16gSIpetl2Y/edit?gid=1222028246'


def number(value):
    try:
        result = float(str(value).strip().replace(',', ''))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def shop_days(rows):
    result = {}
    for row in rows:
        # The source interleaves monthly totals dated on the first day with
        # daily records. Monthly summary rows mark the cart fields with '/'.
        if row.get('Units (Add to Cart)', '').strip() == '/':
            continue
        raw_date = row.get('Date', '').strip()
        new_buyers, buyers = number(row.get('# of new buyers')), number(row.get('# of buyers'))
        if new_buyers is None and buyers is None:
            continue  # Ignore future formula/template rows.
        y, m, d = map(int, raw_date.replace('/', '-').split('-'))
        key = date(y, m, d).isoformat()
        value = {'newBuyers': new_buyers, 'buyers': buyers}
        if key in result and result[key] != value:
            raise ValueError(f'Conflicting daily shop records: {key}')
        result[key] = value
    return result


def build():
    with (ROOT / 'data/daily_shop.csv').open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'Date', '# of new buyers', '# of buyers', 'Units (Add to Cart)'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Daily shop source headers changed')
        shop = shop_days(reader)
    affiliate = json.loads((ROOT / 'assets/affiliate-data.json').read_text('utf-8'))
    costs = {day: 0 for day in affiliate['dates']}
    for row in affiliate['rows']:
        costs[affiliate['dates'][row[0]]] += row[4]
    return {'schema': 1, 'shop': shop, 'affiliateCost': costs,
            'sources': {'shop': SHOP_SOURCE, 'affiliate': affiliate['source']}}


if __name__ == '__main__':
    data = build()
    (ROOT / 'assets/daily-report-data.json').write_text(
        json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    print(f"Daily report: {len(data['shop'])} shop days, {len(data['affiliateCost'])} affiliate days")
