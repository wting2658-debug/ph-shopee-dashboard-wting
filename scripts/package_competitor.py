"""Package verified public competitor assets; never read crawler credentials/exports."""
import argparse
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_FILES = (
    'style.css', 'app.js', 'rank-history.js', 'rank-history-view.js',
    'rising-competitors.js', 'rising-competitors-view.js',
    'product-opportunities.js', 'product-opportunities-view.js',
    'self-ranking.js', 'self-ranking-view.js', 'category-picker.js',
)


def encode_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def pack_rows(rows):
    # Source rows have a common schema plus optional trailing UI evidence fields.
    # Keep each row's original field count, so absent fields remain absent.
    columns = list(max(rows, key=len))
    for row in rows:
        if list(row) != columns[:len(row)]:
            raise ValueError('Unexpected source schema; update the packer before publishing')
    dictionaries = {}
    for key in columns:
        values = [r[key] for r in rows if key in r]
        if all(value is None or isinstance(value, str) for value in values):
            dictionaries[key] = list(dict.fromkeys(value for value in values if value is not None))
    lookups = {key: {value: index for index, value in enumerate(values)} for key, values in dictionaries.items()}
    cells = [
        [lookups[key][value] if key in lookups and value is not None else value for key, value in row.items()]
        for row in rows
    ]
    return {'format': 'ph-ranking-columns-v1', 'columns': columns, 'dictionaries': dictionaries, 'rows': cells}


def unpack_rows(chunk):
    return [
        {key: chunk['dictionaries'][key][value] if key in chunk['dictionaries'] and value is not None else value
         for key, value in zip(chunk['columns'], cells)}
        for cells in chunk['rows']
    ]


def package(source, output):
    source = source.resolve()
    content = (source / 'data.js').read_text('utf-8')
    prefix = 'window.RANKING_DATA='
    if not content.startswith(prefix) or not content.endswith(';'):
        raise ValueError('Expected verified dashboard data.js')
    data = json.loads(content[len(prefix):-1])
    if not data['rows'] or any(row['country'] != 'PH' for row in data['rows']):
        raise ValueError('Expected Philippines ranking rows')
    if data.get('rank_recheck', {}).get('remaining_shop_ui') != 0:
        raise ValueError('Ranking verification is not complete')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'data').mkdir(exist_ok=True)
    for name in STATIC_FILES:
        shutil.copyfile(source / name, output / name)
    grouped = defaultdict(list)
    for row in data['rows']:
        if not re.fullmatch(r'\d{4}-\d{2}', row['month']):
            raise ValueError('Invalid month')
        grouped[row['month']].append(row)
    chunks = []
    reconstructed = []
    for month, rows in grouped.items():
        packed = pack_rows(rows)
        restored = unpack_rows(packed)
        if restored != rows:
            raise ValueError(f'Packing changed source rows: {month}')
        reconstructed.extend(restored)
        blob = encode_json(packed)
        if len(blob) >= 25 * 1024 * 1024:
            raise ValueError(f'Month exceeds Cloudflare asset limit: {month}')
        digest = hashlib.sha256(blob).hexdigest()
        filename = f'data/{month}.{digest[:12]}.json'
        (output / filename).write_bytes(blob)
        chunks.append({'month': month, 'file': filename, 'sha256': digest, 'count': len(rows), 'bytes': len(blob)})
    if reconstructed != data['rows']:
        raise ValueError('Source order changed during packing')
    version = hashlib.sha256(encode_json(chunks)).hexdigest()[:16]
    manifest = {
        'format': 'ph-competitor-manifest-v1', 'version': version,
        'row_count': len(data['rows']), 'chunks': chunks,
        'metadata': {key: value for key, value in data.items() if key != 'rows'},
    }
    (output / 'manifest.json').write_bytes(encode_json(manifest))
    html = (source / 'index.html').read_text('utf-8')
    html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S)
    html = html.replace('<body>', '<body data-loading>')
    loading = '<section id="competitor-loading" role="status" aria-live="polite"><p id="competitor-loading-text">正在加载菲律宾历史排名…</p><noscript>请开启 JavaScript 以查看竞品监控。</noscript></section>'
    html = html.replace('<div id="notice"', loading + '<div id="notice"', 1)
    styles = '<style>.embedded main{max-width:none;padding:0}.embedded header{display:none}.embedded body{background:transparent}[data-loading] .controls,[data-loading] #notice,[data-loading] #content{display:none}#competitor-loading{padding:48px;text-align:center;background:white;border-radius:12px;margin:12px 0}#competitor-loading p{color:#16748d}</style>'
    html = html.replace('</head>', styles + '</head>')
    html = html.replace('</body>', '<script src="../competitor-loader.js?v=' + version + '"></script></body>')
    (output / 'index.html').write_text(html, 'utf-8')
    return {
        'rows': len(data['rows']), 'months': len(chunks), 'row_differences': 0,
        'source_bytes': len(content.encode('utf-8')), 'packed_bytes': sum(c['bytes'] for c in chunks),
        'largest_chunk_bytes': max(c['bytes'] for c in chunks), 'version': version,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True, help='Verified market-intelligence/public folder')
    parser.add_argument('--output', type=Path, default=ROOT / 'assets/competitor')
    args = parser.parse_args()
    print(json.dumps(package(args.source, args.output), ensure_ascii=False))
