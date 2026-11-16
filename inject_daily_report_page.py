"""Register an isolated daily report without rewriting existing modules."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKERS = [
    ('/* ===== Daily Report Page ===== */', '/* ===== End Daily Report Page ===== */'),
    ('<!-- ===== Daily Report Page ===== -->', '<!-- ===== End Daily Report Page ===== -->'),
    ('// ===== Daily Report Page Rendering =====', '// ===== End Daily Report Page Rendering ====='),
]
NAV = '        <button class="dashboard-tab daily-report-tab" type="button" data-dashboard-page="daily-report">日报</button>'
LINES = [
    "      document.getElementById('daily-report-page').hidden = state.activePage !== 'daily-report';",
    "      document.body.classList.toggle('daily-report-mode', state.activePage === 'daily-report');",
    "      if (state.activePage === 'daily-report') { renderDailyReportPage(); return; }",
]


def remove_daily_report_page(html):
    for start, end in MARKERS:
        html = re.sub(r'    ' + re.escape(start) + r'.*?' + re.escape(end) + r'\n?', '', html, flags=re.S)
    html = html.replace(NAV + '\n', '')
    for line in LINES:
        html = html.replace(line + '\n', '')
    return html


def inject_daily_report_page(html):
    html = remove_daily_report_page(html)
    anchor = '        <button class="dashboard-tab competitor-tab" type="button" data-dashboard-page="competitor">竞品监控</button>'
    if html.count(anchor) != 1:
        raise ValueError('Competitor navigation anchor missing')
    html = html.replace(anchor, NAV + '\n' + anchor, 1)
    css = '    ' + MARKERS[0][0] + '\n' + (ROOT/'assets/daily-report.css').read_text('utf-8') + '\n    ' + MARKERS[0][1] + '\n'
    html = html.replace('  </style>', css + '  </style>', 1)
    anchor = '\n  <script>\n    const PAYLOAD ='
    html = html.replace(anchor, (ROOT/'assets/daily-report.html').read_text('utf-8') + anchor, 1)
    js = '    ' + MARKERS[2][0] + '\n' + (ROOT/'assets/daily-report.js').read_text('utf-8') + '\n    ' + MARKERS[2][1] + '\n'
    html = html.replace('    // ===== Shipment Page Rendering =====', js + '    // ===== Shipment Page Rendering =====', 1)
    anchor = "      document.getElementById('subsidy-page').hidden = state.activePage !== 'subsidy';"
    html = html.replace(anchor, anchor + '\n' + LINES[0] + '\n' + LINES[1], 1)
    anchor = "      if (state.activePage === 'meta') {"
    html = html.replace(anchor, LINES[2] + '\n' + anchor, 1)
    if html.count('id="daily-report-page"') != 1 or html.count('data-dashboard-page="daily-report"') != 1:
        raise ValueError('Daily report registration failed')
    return html


if __name__ == '__main__':
    path = ROOT/'index.html'
    original = path.read_text('utf-8')
    updated = inject_daily_report_page(original)
    if remove_daily_report_page(updated) != remove_daily_report_page(original):
        raise ValueError('An existing module changed')
    path.write_text(updated, encoding='utf-8')
