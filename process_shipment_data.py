#!/usr/bin/env python3
"""
Process shipment_raw.csv and generate JSON data for the shipment dashboard page.
Outputs: shipment_data.json (embedded into index.html)

Data model supports:
  - Channel metric cards (total / Tiktok / Shopee / Lazada), current vs prev month
  - DMS category table with per-platform detail (clickable for page-wide linkage)
  - Daily trend per channel (3 separate charts)
  - Monthly trend per channel (3 channels, placed at page bottom)
  - Product-level detail rows carrying category / sku / name, used by the
    "By 品" detail table whose dimension can be switched via
    SKU货号 / 品类 / 产品名 buttons.
"""
import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent
# The downloader writes the shipment CSV into data/; keep a root-level copy
# working too so the script can be run manually from either location.
RAW_CANDIDATES = [
    REPORT_DIR / "data" / "shipment_raw.csv",
    REPORT_DIR / "shipment_raw.csv",
]
RAW_FILE = "shipment_raw.csv"
OUTPUT_FILE = REPORT_DIR / "shipment_data.json"


def resolve_raw_file() -> Path:
    for candidate in RAW_CANDIDATES:
        if candidate.exists():
            return candidate
    raise SystemExit(
        "shipment_raw.csv not found. Expected one of: "
        + ", ".join(str(c) for c in RAW_CANDIDATES)
    )

PLATFORMS = ["Tiktok", "Shopee", "Lazada"]
PLATFORM_KEY = {"Tiktok": "tiktok", "Shopee": "shopee", "Lazada": "lazada"}


def parse_qty(raw):
    """销量 may contain thousands separators, e.g. '2,030'."""
    text = (raw or "").strip().replace(",", "").replace("，", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def parse_shipment_date(raw, year):
    """解析真实出货日期；Excel 序号使用默认的 1900 日期系统。"""
    text = (raw or "").strip()
    if not text:
        raise ValueError("日期为空")

    if re.fullmatch(r"\d{1,2}/\d{1,2}", text):
        month, day = map(int, text.split("/"))
        return date(int((year or "").strip()), month, day)
    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", text):
        return date(*map(int, text.split("/")))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T].+)?", text):
        return datetime.fromisoformat(text).date()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        serial_day = int(text.split(".", 1)[0])
        if serial_day < 1 or serial_day == 60:
            raise ValueError("无效 Excel 日期序号（序号 60 对应不存在的 1900-02-29）")
        origin = date(1899, 12, 31) if serial_day < 60 else date(1899, 12, 30)
        try:
            return origin + timedelta(days=serial_day)
        except OverflowError as exc:
            raise ValueError("Excel 日期序号超出真实日期范围") from exc
    raise ValueError(f"不支持的日期格式: {text!r}")


def normalize_platform(p):
    if not p:
        return "Unknown"
    p = p.strip().lower()
    if "shopee" in p or "shop" in p:
        return "Shopee"
    if "tiktok" in p or "tik" in p:
        return "Tiktok"
    if "lazada" in p or "laza" in p:
        return "Lazada"
    return p.capitalize()


def normalize_category(c):
    if not c:
        return "未分类"
    return c.strip()


def calc_delta(curr, prev):
    if not prev:
        return 0
    return round((curr - prev) / prev * 100, 1)


def main():
    raw_path = resolve_raw_file()
    rows = []
    source_row_count = 0
    date_parse_error_count = 0
    nonzero_date_error_count = 0
    date_error_examples = []
    with raw_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_row_count += 1
            qty = parse_qty(row.get("销量"))
            try:
                shipment_date = parse_shipment_date(row.get("日期"), row.get("年份"))
            except ValueError as exc:
                date_parse_error_count += 1
                nonzero_date_error_count += qty != 0
                if len(date_error_examples) < 5:
                    date_error_examples.append(
                        f"CSV 行 {reader.line_num}: 日期={row.get('日期')!r}, "
                        f"年份={row.get('年份')!r}, 销量={qty}, 原因={exc}"
                    )
                continue
            if qty == 0:
                continue
            platform = normalize_platform(row.get("Platform", ""))
            if platform not in PLATFORM_KEY:
                continue
            category = normalize_category(row.get("品类", ""))

            rows.append({
                "qty": qty,
                "platform": platform,
                "category": category,
                "date": shipment_date.isoformat(),
                "ym": f"{shipment_date.year:04d}-{shipment_date.month:02d}",
                "day": shipment_date.day,
                "sku": (row.get("SKU") or "").strip(),
                "name": (row.get("产品名") or "").strip(),
            })

    print(f"Source: {raw_path}")
    print(f"Source rows: {source_row_count}; date parse errors: {date_parse_error_count}; "
          f"nonzero date errors: {nonzero_date_error_count}")
    for example in date_error_examples:
        print(example)
    if nonzero_date_error_count:
        raise SystemExit(
            f"{nonzero_date_error_count} 行非零出货量缺少有效日期，已停止生成，未写入输出。"
        )
    print(f"Total rows parsed: {len(rows)}")

    all_yms = sorted(set(r["ym"] for r in rows if r["ym"]))
    current_ym = all_yms[-1] if all_yms else ""
    prev_ym = all_yms[-2] if len(all_yms) >= 2 else ""
    print(f"Current month: {current_ym}, Previous month: {prev_ym}")

    current_rows = [r for r in rows if r["ym"] == current_ym]
    prev_rows = [r for r in rows if r["ym"] == prev_ym]

    # ------------------------------------------------------------------ #
    # 1. Channel summary cards
    # ------------------------------------------------------------------ #
    def channel_summary(data_rows):
        by_platform = defaultdict(int)
        for r in data_rows:
            by_platform[r["platform"]] += r["qty"]
        return {
            "total": sum(r["qty"] for r in data_rows),
            "tiktok": by_platform.get("Tiktok", 0),
            "shopee": by_platform.get("Shopee", 0),
            "lazada": by_platform.get("Lazada", 0),
        }

    current_summary = channel_summary(current_rows)
    prev_summary = channel_summary(prev_rows)

    channel_cards = {
        "current_ym": current_ym,
        "prev_ym": prev_ym,
        "cards": [
            {
                "label": label,
                "key": key,
                "current": current_summary[key],
                "prev": prev_summary[key],
                "delta": calc_delta(current_summary[key], prev_summary[key]),
            }
            for label, key in (("总出货", "total"), ("Tiktok", "tiktok"),
                               ("Shopee", "shopee"), ("Lazada", "lazada"))
        ],
    }

    # ------------------------------------------------------------------ #
    # 2. DMS category table (per platform detail + MoM)
    # ------------------------------------------------------------------ #
    cat_current = defaultdict(lambda: defaultdict(int))
    cat_prev = defaultdict(lambda: defaultdict(int))
    for r in current_rows:
        cat_current[r["category"]][r["platform"]] += r["qty"]
    for r in prev_rows:
        cat_prev[r["category"]][r["platform"]] += r["qty"]

    cat_total_current = sum(sum(v.values()) for v in cat_current.values())
    cat_total_prev = sum(sum(v.values()) for v in cat_prev.values())

    category_table = []
    for cat in sorted(cat_current.keys(),
                      key=lambda c: sum(cat_current[c].values()), reverse=True):
        curr_total = sum(cat_current[cat].values())
        prev_total = sum(cat_prev[cat].values())
        entry = {
            "category": cat,
            "total": curr_total,
            "share": round(curr_total / cat_total_current * 100, 1) if cat_total_current else 0,
            "delta": calc_delta(curr_total, prev_total),
        }
        for platform in PLATFORMS:
            key = PLATFORM_KEY[platform]
            curr = cat_current[cat].get(platform, 0)
            prev = cat_prev[cat].get(platform, 0)
            entry[key] = curr
            entry[f"{key}_share"] = round(curr / curr_total * 100, 1) if curr_total else 0
            entry[f"{key}_delta"] = calc_delta(curr, prev)
        category_table.append(entry)

    # ------------------------------------------------------------------ #
    # 3. Daily trend (per channel) for current month
    # ------------------------------------------------------------------ #
    daily_acc = defaultdict(lambda: defaultdict(int))
    for r in current_rows:
        if r["day"] > 0:
            daily_acc[r["platform"]][r["day"]] += r["qty"]

    days_sorted = sorted({d for p in daily_acc for d in daily_acc[p]})
    daily_trend = {
        PLATFORM_KEY[p]: [{"day": d, "qty": daily_acc[p].get(d, 0)} for d in days_sorted]
        for p in PLATFORMS
    }

    # ------------------------------------------------------------------ #
    # 4. Monthly trend (per channel) - placed at page bottom
    # ------------------------------------------------------------------ #
    monthly_acc = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r["ym"]:
            monthly_acc[r["ym"]][r["platform"]] += r["qty"]

    monthly_trend = []
    for ym in all_yms:
        entry = {"ym": ym}
        for platform in PLATFORMS:
            entry[PLATFORM_KEY[platform]] = monthly_acc[ym].get(platform, 0)
        entry["total"] = sum(entry[PLATFORM_KEY[p]] for p in PLATFORMS)
        monthly_trend.append(entry)

    # ------------------------------------------------------------------ #
    # 5. Product-level detail rows (for the "By 品" table)
    #    Grouped by sku / category / product name, all three carried on
    #    every row so the table can be re-grouped client-side.
    # ------------------------------------------------------------------ #
    prod_current = defaultdict(lambda: defaultdict(int))
    prod_prev = defaultdict(lambda: defaultdict(int))
    prod_meta = {}
    for r in current_rows:
        key = r["sku"]
        prod_current[key][r["platform"]] += r["qty"]
        prod_current[key]["total"] += r["qty"]
        if key not in prod_meta and r["name"]:
            prod_meta[key] = {"name": r["name"], "category": r["category"]}
    for r in prev_rows:
        key = r["sku"]
        prod_prev[key][r["platform"]] += r["qty"]
        prod_prev[key]["total"] += r["qty"]
        if key not in prod_meta and r["name"]:
            prod_meta[key] = {"name": r["name"], "category": r["category"]}

    # also carry category for SKUs that only exist in the previous month
    for r in rows:
        key = r["sku"]
        if key not in prod_meta and r["name"]:
            prod_meta[key] = {"name": r["name"], "category": r["category"]}

    all_skus = sorted(set(r["sku"] for r in rows if r["sku"]))

    product_rows = []
    for sku in sorted(prod_current.keys(),
                      key=lambda s: prod_current[s]["total"], reverse=True):
        meta = prod_meta.get(sku, {"name": "", "category": "未分类"})
        curr = prod_current[sku]
        prev = prod_prev[sku]
        product_rows.append({
            "sku": sku,
            "name": meta["name"],
            "category": meta["category"],
            "total": curr["total"],
            "tiktok": curr.get("Tiktok", 0),
            "shopee": curr.get("Shopee", 0),
            "lazada": curr.get("Lazada", 0),
            "prev_total": prev["total"],
            "prev_tiktok": prev.get("Tiktok", 0),
            "prev_shopee": prev.get("Shopee", 0),
            "prev_lazada": prev.get("Lazada", 0),
            "delta": calc_delta(curr["total"], prev["total"]),
        })

    catalog_keys = sorted({(r["sku"], r["name"], r["category"]) for r in rows})
    catalog = [
        {"sku": sku, "name": name, "category": category}
        for sku, name, category in catalog_keys
    ]
    catalog_index = {key: index for index, key in enumerate(catalog_keys)}
    platform_index = {platform: index for index, platform in enumerate(PLATFORMS)}
    daily_record_acc = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        index = catalog_index[(r["sku"], r["name"], r["category"])]
        daily_record_acc[(r["date"], index)][platform_index[r["platform"]]] += r["qty"]
    daily_records = [
        [iso_date, index, *quantities]
        for (iso_date, index), quantities in sorted(daily_record_acc.items())
    ]
    available_range = {
        "start": daily_records[0][0] if daily_records else None,
        "end": daily_records[-1][0] if daily_records else None,
    }

    output = {
        "schema_version": 2,
        "catalog": catalog,
        "daily_records": daily_records,
        "available_range": available_range,
        "source_row_count": source_row_count,
        "record_count": len(daily_records),
        "date_parse_error_count": date_parse_error_count,
        "channel_cards": channel_cards,
        "category_table": category_table,
        "monthly_trend": monthly_trend,
        "daily_trend": daily_trend,
        "product_rows": product_rows,
        "all_skus": all_skus,
        "current_ym": current_ym,
        "prev_ym": prev_ym,
        "all_yms": all_yms,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Output written to {OUTPUT_FILE}")
    print(f"Output size: {OUTPUT_FILE.stat().st_size} bytes; "
          f"catalog entries: {len(catalog)}; daily records: {len(daily_records)}")
    print(f"Available range: {available_range['start']} ~ {available_range['end']}")
    print(f"Current month {current_ym}: total={current_summary['total']}, "
          f"TT={current_summary['tiktok']}, SP={current_summary['shopee']}, "
          f"LZ={current_summary['lazada']}")
    print(f"Prev month {prev_ym}: total={prev_summary['total']}")
    print(f"Categories: {len(category_table)}, "
          f"product rows: {len(product_rows)}, "
          f"monthly points: {len(monthly_trend)}, "
          f"daily days: {len(days_sorted)}")


if __name__ == "__main__":
    main()
