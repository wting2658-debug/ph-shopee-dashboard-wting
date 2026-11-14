"""Check rebuild persistence, unchanged original pages, and every published ranking."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_flagship_onsite_page1 import render_html
from inject_competitor_page import inject_competitor_page
from scripts.package_competitor import unpack_rows


def verify(source_data=None):
    baseline = subprocess.check_output(['git', 'show', 'origin/main:index.html'], cwd=ROOT).decode('utf-8')
    updated = (ROOT / 'index.html').read_text('utf-8')
    for page in ('store', 'meta', 'onsite', 'shipment', 'subsidy', 'live'):
        pattern = r'<main[^>]*id="' + page + r'-page".*?</main>'
        assert re.search(pattern, baseline, re.S).group() == re.search(pattern, updated, re.S).group(), page
    for key in ('PAYLOAD', 'SHIPMENT_DATA', 'SUBSIDY_DATA', 'LIVE_DATA'):
        pattern = r'const ' + key + r' = (.*?);\n'
        assert re.search(pattern, baseline).group(1) == re.search(pattern, updated).group(1), key
    assert inject_competitor_page(updated) == updated, 'Injection is not idempotent'
    payload = json.loads(re.search(r'const PAYLOAD = (.*?);\n', baseline).group(1))
    subsidy = re.search(r'const SUBSIDY_DATA = (.*?);\n', baseline).group(1)
    # Reuse the online baseline source snapshot; local raw daily CSVs are not required.
    with patch('build_flagship_onsite_page1.load_subsidy_json', return_value=subsidy):
        rebuilt = render_html(payload)
    assert rebuilt.count('id="competitor-page"') == 1
    assert rebuilt.count('data-dashboard-page="competitor"') == 1
    assert rebuilt.index('data-dashboard-page="live"') < rebuilt.index('data-dashboard-page="competitor"')
    # A second refresh must preserve all six old modules and a single competitor tab.
    assert inject_competitor_page(rebuilt) == rebuilt
    published = ROOT / 'assets/competitor'
    manifest = json.loads((published / 'manifest.json').read_text('utf-8'))
    rows = []
    for entry in manifest['chunks']:
        blob = (published / entry['file']).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == entry['sha256']
        assert len(blob) == entry['bytes'] < 25 * 1024 * 1024
        decoded = unpack_rows(json.loads(blob))
        assert len(decoded) == entry['count']
        assert all(row['country'] == 'PH' and row['month'] == entry['month'] for row in decoded)
        rows.extend(decoded)
    assert len(rows) == manifest['row_count'] == 108326
    assert len(manifest['chunks']) == 22
    if source_data:
        content = source_data.read_text('utf-8')
        original = json.loads(content[len('window.RANKING_DATA='):-1])
        assert rows == original['rows'], 'Packing changed original row values or order'
        assert manifest['metadata'] == {k: v for k, v in original.items() if k != 'rows'}
    own = [r for r in rows if r['kind'] == 'shop' and r['skintific'] and r['metric'] in ('sales', 'units', 'views')]
    assert len(own) == 1885 and all(r['rank'] is not None for r in own)
    for category, expected in [('Beauty', 14), ('Beauty >> Makeup', 16), ('Beauty >> Skincare', 10)]:
        matches = [r for r in own if r['shop_name'] == 'SKINTIFIC Official Shop' and r['month'] == '2026-10' and r['metric'] == 'sales' and r['category'] == category]
        assert len(matches) == 1 and matches[0]['rank'] == expected, category
    for path in published.rglob('*'):
        assert path.name not in ('state.json', 'service_account.json')
        assert path.suffix not in ('.xlsx', '.sqlite', '.db', '.csv')
    script = re.findall(r'<script>(.*?)</script>', updated, re.S)[0]
    syntax = subprocess.run(['node', '--check'], input=script, text=True, encoding='utf-8', capture_output=True)
    assert syntax.returncode == 0, syntax.stderr
    print(json.dumps({'original_pages_unchanged': 6, 'original_datasets_unchanged': 4,
        'rebuild_preserves_competitor': True, 'packing_row_differences': 0,
        'rows_verified': len(rows), 'months': len(manifest['chunks']),
        'skintific_records_verified': len(own), 'skintific_missing': 0}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-data', type=Path)
    verify(parser.parse_args().source_data)
