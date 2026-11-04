#!/usr/bin/env python3
"""
Sync the updated "出货分析" (shipment) section into
build_flagship_onsite_page1.py so the daily auto-refresh build keeps the
new layout / linkage features.

It reads the canonical shipment CSS / HTML / JS from inject_shipment_page.py
and rewrites the corresponding blocks inside the build script template.

Run:  python sync_build_script.py
"""
import re
from pathlib import Path

import inject_shipment_page as inj

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build_flagship_onsite_page1.py"


def replace_once(text, start_marker, end_marker, new_block, label, include_end=True):
    start = text.find(start_marker)
    if start == -1:
        raise SystemExit(f"[!] start marker not found for {label}: {start_marker!r}")
    end = text.find(end_marker, start)
    if end == -1:
        raise SystemExit(f"[!] end marker not found for {label}: {end_marker!r}")
    if include_end:
        return text[:start] + new_block + text[end + len(end_marker):]
    return text[:start] + new_block + text[end:]


def replace_span(text, start_marker, end_marker, new_block, label):
    """Replace [start_marker, end_marker) with new_block.

    Works both for a legacy build script and an already-synced one, because
    `start_marker` is unique to the shipped section and `end_marker` is a
    stable boundary that follows it.
    """
    start = text.find(start_marker)
    if start == -1:
        raise SystemExit(f"[!] start marker not found for {label}: {start_marker!r}")
    end = text.find(end_marker, start)
    if end == -1:
        raise SystemExit(f"[!] end marker not found for {label}: {end_marker!r}")
    return text[:start] + new_block + text[end:]


def main():
    src = BUILD.read_text(encoding="utf-8")
    original = src

    # ---- 1. CSS block inside the template --------------------------------
    # Start marker is unique to the shipment CSS; end marker is the stable
    # boundary that follows it (the closing brace of the media query).
    src = replace_span(
        src,
        "    /* ===== Shipment Page ===== */",
        "\n  </style>",
        inj.CSS + "\n  </style>",
        "shipment CSS",
    )
    # ---- 2. HTML block ----------------------------------------------------
    # The build script template ends the shipment <main> right before the
    # <script> tag. We replace up to (not including) the "<script>" marker
    # and re-emit it ourselves, so the closing </main> stays unique.
    html_body = inj.HTML.rstrip("\n")
    src = replace_span(
        src,
        '    <main class="dashboard-page" id="shipment-page" hidden>',
        "\n  <script>",
        html_body + "\n\n",
        "shipment HTML",
    )

    # ---- 3. SHIPMENT_DATA placeholder ------------------------------------
    # Replace the hardcoded JSON with a runtime placeholder that is filled
    # from shipment_data.json at build time.
    old_data_start = "    const SHIPMENT_DATA = "
    idx = src.find(old_data_start)
    if idx == -1:
        raise SystemExit("[!] SHIPMENT_DATA declaration not found in build script")
    semi = src.find(";\n", idx)
    placeholder = "    const SHIPMENT_DATA = __SHIPMENT_JSON__;\n"
    if src[idx:semi + 1] != placeholder.rstrip("\n"):
        src = (src[:idx] + placeholder.rstrip("\n") + src[semi:])
    else:
        print("[=] SHIPMENT_DATA already uses the placeholder")

    # ---- 4. JS logic block -----------------------------------------------
    src = replace_span(
        src,
        "    // ===== Shipment Page Rendering =====",
        "    syncDateInputs();",
        inj.JS + "    syncDateInputs();",
        "shipment JS",
    )

    # ---- 5. Date-control dim row (below the time inputs) -----------------
    ctrl_old = """          <div class="field">
            <label for="compare-end-date">对比结束</label>
            <input id="compare-end-date" type="date">
          </div>
        </div>
      </div>
    </section>"""
    ctrl_new = """          <div class="field">
            <label for="compare-end-date">对比结束</label>
            <input id="compare-end-date" type="date">
          </div>
        </div>
        <div class="shipment-dim-row" id="shipment-dim-row" hidden>
          <span class="shipment-dim-row-label">明细维度</span>
          <div class="shipment-dim-switch" id="shipment-dim-switch-top" role="group" aria-label="明细维度">
            <button type="button" data-dim="sku" class="is-active">SKU货号</button>
            <button type="button" data-dim="category">品类</button>
            <button type="button" data-dim="name">产品名</button>
          </div>
        </div>
      </div>
    </section>"""
    if ctrl_old in src:
        src = src.replace(ctrl_old, ctrl_new, 1)
    elif ctrl_new in src:
        print("[=] date-control dim row already present")
    else:
        raise SystemExit("[!] date-control block not found in build script")

    # ---- 6. Wire the placeholder replacement in render_html --------------
    old_return = '    return html.replace("__PAYLOAD_JSON__", payload_json)'
    new_return = '''    html = html.replace("__PAYLOAD_JSON__", payload_json)
    html = html.replace("__SHIPMENT_JSON__", load_shipment_json())
    return html'''
    if old_return in src:
        src = src.replace(old_return, new_return, 1)
    elif new_return not in src:
        raise SystemExit("[!] render_html return statement not found")
    else:
        print("[=] render_html already wired")

    # ---- 7. Add load_shipment_json helper --------------------------------
    helper = '''
SHIPMENT_JSON_PATH = REPORT_DIR / "shipment_data.json"


def load_shipment_json() -> str:
    """Return the shipment dataset as a compact JSON literal.

    Falls back to an empty dataset so the build never breaks when the
    shipment source is unavailable.
    """
    if SHIPMENT_JSON_PATH.exists():
        raw = SHIPMENT_JSON_PATH.read_text(encoding="utf-8").strip()
        if raw:
            return raw
    return json.dumps(
        {
            "channel_cards": {"current_ym": "", "prev_ym": "", "cards": []},
            "category_table": [],
            "monthly_trend": [],
            "daily_trend": {"tiktok": [], "shopee": [], "lazada": []},
            "product_rows": [],
            "all_skus": [],
            "current_ym": "",
            "prev_ym": "",
            "all_yms": [],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


'''
    anchor = "def render_html(payload: dict[str, Any]) -> str:"
    if anchor not in src:
        raise SystemExit("[!] render_html definition not found")
    if "def load_shipment_json()" not in src:
        src = src.replace(anchor, helper.lstrip("\n") + anchor, 1)
    else:
        print("[=] load_shipment_json already present")

    # ---- 8. Make sure `json` is imported ---------------------------------
    if not re.search(r"^import json$", src, flags=re.M):
        src = re.sub(r"^import csv$", "import csv\nimport json", src, count=1, flags=re.M)

    if src == original:
        print("[=] build script already up to date - nothing changed")
        return

    # ---- 9. Sanity checks ------------------------------------------------
    problems = []
    if "<script>    </main>" in src:
        problems.append("stray </main> after <script>")
    if "<script>\n  <script>" in src:
        problems.append("duplicate <script> tag")
    if src.count("<script>") != 1:
        problems.append(f"expected exactly 1 inline <script>, found {src.count('<script>')}")
    if not re.search(r"</main>\n+\s*<script>", src):
        problems.append("shipment <main> is not properly closed before <script>")
    if problems:
        raise SystemExit("[!] build script structure broken: " + "; ".join(problems))

    BUILD.write_text(src, encoding="utf-8")
    print(f"[OK] build_flagship_onsite_page1.py updated ({len(src):,} chars)")


if __name__ == "__main__":
    main()
