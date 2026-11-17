"""Register the flash dashboard in generated HTML."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAV = '        <button class="dashboard-tab" type="button" data-dashboard-page="affiliate">联盟板块</button>'
PAGE_ANCHOR = '    <!-- ===== Affiliate Page ===== -->'
HIDE_ANCHOR = "      document.getElementById('affiliate-page').hidden = state.activePage !== 'affiliate';"
RENDER_ANCHOR = "      if (state.activePage === 'affiliate') { renderAffiliatePage(); return; }"
FOOTER_ANCHOR = '  </script>\n</body>'


def inject_flash_page(html):
    if 'id="flash-page"' in html:
        return html
    for anchor in (NAV, PAGE_ANCHOR, HIDE_ANCHOR, RENDER_ANCHOR, FOOTER_ANCHOR):
        if html.count(anchor) != 1:
            raise ValueError(f"Flash dashboard anchor missing or duplicated: {anchor}")
    page = (ROOT / "assets/flash-page.html").read_text(encoding="utf-8").rstrip()
    html = html.replace(NAV, NAV + '\n        <button class="dashboard-tab" type="button" data-dashboard-page="flash">闪购板块</button>', 1)
    html = html.replace(PAGE_ANCHOR, page + '\n' + PAGE_ANCHOR, 1)
    html = html.replace(HIDE_ANCHOR, HIDE_ANCHOR + "\n      document.getElementById('flash-page').hidden = state.activePage !== 'flash';", 1)
    html = html.replace(RENDER_ANCHOR, RENDER_ANCHOR + "\n      if (state.activePage === 'flash') { window.renderFlashPage?.(); return; }", 1)
    assets = (
        '  <link rel="stylesheet" href="assets/flash.css">\n'
        '  <link rel="stylesheet" href="assets/flash-charts.css">\n'
        '  <link rel="stylesheet" href="assets/flash-products.css">\n'
        '  <link rel="stylesheet" href="assets/flash-kpi.css">\n'
        '  <script src="assets/flash.js"></script>\n'
        '  <script src="assets/flash-charts.js"></script>\n'
        '  <script src="assets/flash-products.js"></script>\n'
    )
    return html.replace(FOOTER_ANCHOR, '  </script>\n' + assets + '</body>', 1)
