"""Run before committing, comparing the site with its current Git baseline."""
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from build_flagship_onsite_page1 import render_html

root = Path(__file__).resolve().parents[1]
baseline = sys.argv[1] if len(sys.argv) > 1 else 'HEAD'
base = subprocess.check_output(['git', 'show', f'{baseline}:index.html'], cwd=root).decode('utf-8')
updated = (root / 'index.html').read_text(encoding='utf-8')
payload = json.loads(re.search(r'const PAYLOAD = (.*?);\n', base).group(1))
subsidy_literal = re.search(r'const SUBSIDY_DATA = (.*?);\n', base).group(1)
with patch('build_flagship_onsite_page1.load_subsidy_json', return_value=subsidy_literal):
    rebuilt = render_html(payload)
assert rebuilt.count('id="live-page"') == 1
print('Builder integration: OK')
for page in ['store', 'meta', 'onsite', 'shipment', 'subsidy']:
    pattern = r'<main[^>]*id="' + page + r'-page".*?</main>'
    assert re.search(pattern, base, re.S).group() == re.search(pattern, updated, re.S).group(), page
    print(f'{page} page: unchanged')
for key in ['PAYLOAD', 'SHIPMENT_DATA', 'SUBSIDY_DATA']:
    pattern = 'const ' + key + r' = (.*?);\n'
    assert re.search(pattern, base).group(1) == re.search(pattern, updated).group(1), key
print('All three original datasets: unchanged')
(root.parent / 'validation-script.js').write_text(re.findall(r'<script>(.*?)</script>', updated, re.S)[0], encoding='utf-8')
