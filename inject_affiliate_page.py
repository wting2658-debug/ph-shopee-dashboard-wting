"""Register the affiliate view without replacing existing report data."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def inject_affiliate_page(html):
    for start, end in [
        ('/* ===== Affiliate Page ===== */', '/* ===== End Affiliate Page ===== */'),
        ('<!-- ===== Affiliate Page ===== -->', '<!-- ===== End Affiliate Page ===== -->'),
        ('// ===== Affiliate Page Rendering =====', '// ===== End Affiliate Page Rendering ====='),
    ]:
        html = re.sub(r'    '+re.escape(start)+r'.*?'+re.escape(end)+r'\n?', '', html, flags=re.S)
    nav = '        <button class="dashboard-tab" type="button" data-dashboard-page="affiliate">联盟板块</button>'
    html = html.replace(nav+'\n', '')
    for line in [
        "      document.getElementById('affiliate-page').hidden = state.activePage !== 'affiliate';",
        "      if (state.activePage === 'affiliate') { renderAffiliatePage(); return; }",
        "      document.body.classList.toggle('affiliate-mode', state.activePage === 'affiliate');",
    ]:
        html = html.replace(line+'\n', '')
    anchor = '        <button class="dashboard-tab" type="button" data-dashboard-page="live">直播板块</button>'
    if html.count(anchor) != 1:
        raise ValueError('Expected livestream navigation anchor missing')
    html = html.replace(anchor, anchor+'\n'+nav, 1)
    css = '    /* ===== Affiliate Page ===== */\n'+(ROOT/'assets/affiliate.css').read_text('utf-8')+'\n    /* ===== End Affiliate Page ===== */\n'
    html = html.replace('  </style>', css+'  </style>', 1)
    anchor = '\n  <script>\n    const PAYLOAD ='
    if html.count(anchor) != 1:
        raise ValueError('Expected main script anchor missing')
    html = html.replace(anchor, (ROOT/'assets/affiliate.html').read_text('utf-8')+anchor, 1)
    js = '    // ===== Affiliate Page Rendering =====\n'+(ROOT/'assets/affiliate.js').read_text('utf-8')+'\n    // ===== End Affiliate Page Rendering =====\n'
    html = html.replace('    // ===== Shipment Page Rendering =====', js+'    // ===== Shipment Page Rendering =====', 1)
    anchor = "      document.getElementById('subsidy-page').hidden = state.activePage !== 'subsidy';"
    html = html.replace(anchor, anchor+"\n      document.getElementById('affiliate-page').hidden = state.activePage !== 'affiliate';\n      document.body.classList.toggle('affiliate-mode', state.activePage === 'affiliate');", 1)
    anchor = "      if (state.activePage === 'meta') {"
    html = html.replace(anchor, "      if (state.activePage === 'affiliate') { renderAffiliatePage(); return; }\n"+anchor, 1)
    if html.count('id="affiliate-page"') != 1 or html.count('data-dashboard-page="affiliate"') != 1:
        raise ValueError('Affiliate registration failed')
    return html


if __name__ == '__main__':
    path = ROOT/'index.html'
    path.write_text(inject_affiliate_page(path.read_text('utf-8')), encoding='utf-8')
