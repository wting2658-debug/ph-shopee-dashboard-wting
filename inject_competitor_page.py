"""Register the isolated monthly competitor module in every dashboard rebuild."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def inject_competitor_page(html):
    for start, end in [
        ('/* ===== Competitor Page ===== */', '/* ===== End Competitor Page ===== */'),
        ('<!-- ===== Competitor Page ===== -->', '<!-- ===== End Competitor Page ===== -->'),
        ('// ===== Competitor Page Rendering =====', '// ===== End Competitor Page Rendering ====='),
    ]:
        html = re.sub(r'    ' + re.escape(start) + r'.*?' + re.escape(end) + r'\n?', '', html, flags=re.S)
    nav = '        <button class="dashboard-tab competitor-tab" type="button" data-dashboard-page="competitor">竞品监控</button>'
    html = html.replace(nav + '\n', '')
    for line in (
        "      document.getElementById('competitor-page').hidden = state.activePage !== 'competitor';",
        '      syncCompetitorShell();',
        "      if (state.activePage === 'competitor') { renderCompetitorPage(); return; }",
    ):
        html = html.replace(line + '\n', '')
    anchor = '        <button class="dashboard-tab" type="button" data-dashboard-page="live">直播板块</button>'
    if html.count(anchor) != 1:
        raise ValueError('Expected livestream navigation anchor missing')
    html = html.replace(anchor, anchor + '\n' + nav, 1)
    css = '    /* ===== Competitor Page ===== */\n' + (ROOT / 'assets/competitor-shell.css').read_text('utf-8') + '\n    /* ===== End Competitor Page ===== */\n'
    html = html.replace('  </style>', css + '  </style>', 1)
    anchor = '\n  <script>\n    const PAYLOAD ='
    if html.count(anchor) != 1:
        raise ValueError('Expected main script anchor missing')
    html = html.replace(anchor, (ROOT / 'assets/competitor-shell.html').read_text('utf-8') + anchor, 1)
    js = '    // ===== Competitor Page Rendering =====\n' + (ROOT / 'assets/competitor-shell.js').read_text('utf-8') + '\n    // ===== End Competitor Page Rendering =====\n'
    html = html.replace('    // ===== Shipment Page Rendering =====', js + '    // ===== Shipment Page Rendering =====', 1)
    anchor = "      document.getElementById('subsidy-page').hidden = state.activePage !== 'subsidy';"
    html = html.replace(anchor, anchor + "\n      document.getElementById('competitor-page').hidden = state.activePage !== 'competitor';\n      syncCompetitorShell();", 1)
    anchor = "      if (state.activePage === 'meta') {"
    html = html.replace(anchor, "      if (state.activePage === 'competitor') { renderCompetitorPage(); return; }\n" + anchor, 1)
    if html.count('id="competitor-page"') != 1 or html.count('data-dashboard-page="competitor"') != 1:
        raise ValueError('Competitor registration failed')
    return html


if __name__ == '__main__':
    path = ROOT / 'index.html'
    path.write_text(inject_competitor_page(path.read_text('utf-8')), 'utf-8')
