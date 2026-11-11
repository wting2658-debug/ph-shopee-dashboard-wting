"""Add the livestream page; leave all other page templates and payloads intact."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def inject_live_page(html, data=None):
    if data is None:
        data = json.loads((ROOT / 'live_data.json').read_text(encoding='utf-8'))
    # Idempotence supports patching an existing report as well as normal rebuilds.
    for start, end in [('/* ===== Live Page ===== */', '/* ===== End Live Page ===== */'),
                       ('<!-- ===== Live Page ===== -->', '<!-- ===== End Live Page ===== -->'),
                       ('// ===== Live Page Rendering =====', '// ===== End Live Page Rendering =====')]:
        html = re.sub(r'    ' + re.escape(start) + r'.*?' + re.escape(end) + r'\n?', '', html, flags=re.S)
    html = html.replace('        <button class="dashboard-tab" type="button" data-dashboard-page="live">直播板块</button>\n', '')
    html = html.replace("      document.getElementById('live-page').hidden = state.activePage !== 'live';\n", '')
    html = html.replace("      if (state.activePage === 'live') { renderLivePage(); return; }\n", '')
    nav = '        <button class="dashboard-tab" type="button" data-dashboard-page="shipment">出货分析</button>'
    if html.count(nav) != 1:
        raise ValueError('Expected shipment navigation anchor missing')
    html = html.replace(nav, nav + '\n        <button class="dashboard-tab" type="button" data-dashboard-page="live">直播板块</button>', 1)
    css = '    /* ===== Live Page ===== */\n' + (ROOT / 'assets/live.css').read_text(encoding='utf-8') + '\n    /* ===== End Live Page ===== */\n'
    html = html.replace('  </style>', css + '  </style>', 1)
    anchor = '\n  <script>\n    const PAYLOAD ='
    if anchor not in html:
        raise ValueError('Expected main script anchor missing')
    html = html.replace(anchor, (ROOT / 'assets/live.html').read_text(encoding='utf-8') + anchor, 1)
    literal = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')
    js = '    // ===== Live Page Rendering =====\n    const LIVE_DATA = ' + literal + ';\n' + (ROOT / 'assets/live.js').read_text(encoding='utf-8') + '\n    // ===== End Live Page Rendering =====\n'
    html = html.replace('    // ===== Shipment Page Rendering =====', js + '    // ===== Shipment Page Rendering =====', 1)
    hide = "      document.getElementById('shipment-page').hidden = state.activePage !== 'shipment';"
    html = html.replace(hide, hide + "\n      document.getElementById('live-page').hidden = state.activePage !== 'live';", 1)
    branch = "      if (state.activePage === 'shipment') {"
    html = html.replace(branch, "      if (state.activePage === 'live') { renderLivePage(); return; }\n" + branch, 1)
    if html.count('id="live-page"') != 1 or html.count('data-dashboard-page="live"') != 1:
        raise ValueError('Livestream registration failed')
    return html


if __name__ == '__main__':
    path = ROOT / 'index.html'
    path.write_text(inject_live_page(path.read_text(encoding='utf-8')), encoding='utf-8')
