"""Add the new-products module while preserving all existing report sections."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKERS = [
    ('/* ===== New Products Page ===== */','/* ===== End New Products Page ===== */'),
    ('<!-- ===== New Products Page ===== -->','<!-- ===== End New Products Page ===== -->'),
    ('// ===== New Products Page Rendering =====','// ===== End New Products Page Rendering ====='),
]
NAV = '        <button class="dashboard-tab" type="button" data-dashboard-page="new-products">新品专区</button>'
LINES = [
    "      document.getElementById('new-products-page').hidden = state.activePage !== 'new-products';",
    "      document.body.classList.toggle('new-products-mode', state.activePage === 'new-products');",
    "      if (state.activePage === 'new-products') { renderNewProductsPage(); return; }",
]


def remove_new_products_page(html):
    for start,end in MARKERS:
        html = re.sub(r'    '+re.escape(start)+r'.*?'+re.escape(end)+r'\n?', '', html, flags=re.S)
    html = html.replace(NAV+'\n','')
    for line in LINES:
        html = html.replace(line+'\n','')
    return html


def inject_new_products_page(html):
    html = remove_new_products_page(html)
    anchor = '        <button class="dashboard-tab" type="button" data-dashboard-page="affiliate">联盟板块</button>'
    if html.count(anchor) != 1:
        raise ValueError('Affiliate navigation anchor missing')
    html = html.replace(anchor,anchor+'\n'+NAV,1)
    css = '    '+MARKERS[0][0]+'\n'+(ROOT/'assets/new-products.css').read_text('utf-8')+'\n    '+MARKERS[0][1]+'\n'
    html = html.replace('  </style>',css+'  </style>',1)
    anchor = '\n  <script>\n    const PAYLOAD ='
    if html.count(anchor) != 1:
        raise ValueError('Main script anchor missing')
    html = html.replace(anchor,(ROOT/'assets/new-products.html').read_text('utf-8')+anchor,1)
    js = '    '+MARKERS[2][0]+'\n'+(ROOT/'assets/new-products.js').read_text('utf-8')+'\n    '+MARKERS[2][1]+'\n'
    html = html.replace('    // ===== Shipment Page Rendering =====',js+'    // ===== Shipment Page Rendering =====',1)
    anchor = "      document.getElementById('subsidy-page').hidden = state.activePage !== 'subsidy';"
    html = html.replace(anchor,anchor+'\n'+LINES[0]+'\n'+LINES[1],1)
    anchor = "      if (state.activePage === 'meta') {"
    html = html.replace(anchor,LINES[2]+'\n'+anchor,1)
    if html.count('id="new-products-page"') != 1 or html.count('data-dashboard-page="new-products"') != 1:
        raise ValueError('New products registration failed')
    return html


if __name__ == '__main__':
    path = ROOT/'index.html'
    existing = path.read_text('utf-8')
    result = inject_new_products_page(existing)
    if remove_new_products_page(result) != remove_new_products_page(existing):
        raise ValueError('An existing section changed')
    path.write_text(result,encoding='utf-8')
