#!/usr/bin/env python3
"""Keep the auto-refresh build aligned with the canonical shipment templates."""
from pathlib import Path
import inject_shipment_page as inj

BUILD = Path(__file__).resolve().parent / "build_flagship_onsite_page1.py"


def main():
    original = BUILD.read_text(encoding="utf-8")
    src = inj.update_template(original)
    start = src.index("    const SHIPMENT_DATA = ")
    end = src.index(";\n", start)
    src = src[:start] + "    const SHIPMENT_DATA = __SHIPMENT_JSON__" + src[end:]
    if src.count("<script>") != 1 or src.count("</style>") != 1 or 'id="shipment-dim-row"' in src:
        raise SystemExit("Invalid build template structure")
    if 'html.replace("__SHIPMENT_JSON__", load_shipment_json())' not in src:
        raise SystemExit("Shipment build data binding is missing")
    if src != original:
        BUILD.write_text(src, encoding="utf-8")
        print("Build shipment templates synchronized")
    else:
        print("Build templates already synchronized (idempotent)")


if __name__ == "__main__":
    main()
