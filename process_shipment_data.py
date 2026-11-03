#!/usr/bin/env python3
"""
Process shipment_raw.csv and generate JSON data for the shipment dashboard page.
Outputs: shipment_data.json (embedded into index.html)
"""
import csv
import json
from collections import defaultdict
from datetime import datetime

RAW_FILE = "shipment_raw.csv"
OUTPUT_FILE = "shipment_data.json"

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

def main():
    rows = []
    with open(RAW_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                qty = int(row.get("销量", 0) or 0)
            except ValueError:
                qty = 0
            if qty == 0:
                continue
            platform = normalize_platform(row.get("Platform", ""))
            category = normalize_category(row.get("品类", ""))
            date_str = row.get("日期", "").strip()
            month_str = row.get("月份", "").strip()
            year_str = row.get("年份", "").strip()

            # Parse date like "9/1" -> need year+month to make full date
            # Build year-month key
            if year_str and month_str:
                try:
                    year = int(year_str)
                    month = int(month_str)
                    ym = f"{year}-{month:02d}"
                except ValueError:
                    ym = ""
            else:
                ym = ""

            # Parse day from date_str
            day = 0
            if date_str:
                parts = date_str.split("/")
                if len(parts) >= 2:
                    try:
                        day = int(parts[-1])
                    except ValueError:
                        day = 0

            rows.append({
                "qty": qty,
                "platform": platform,
                "category": category,
                "ym": ym,
                "year": year_str,
                "month": month_str,
                "day": day,
                "date_str": date_str,
                "sku": row.get("SKU", "").strip(),
                "product_name": row.get("产品名", "").strip(),
            })

    print(f"Total rows parsed: {len(rows)}")

    # Get all unique year-months sorted
    all_yms = sorted(set(r["ym"] for r in rows if r["ym"]))
    print(f"All year-months: {all_yms}")

    # Current month = latest ym, previous month = second latest
    current_ym = all_yms[-1] if all_yms else ""
    prev_ym = all_yms[-2] if len(all_yms) >= 2 else ""
    print(f"Current month: {current_ym}, Previous month: {prev_ym}")

    # 1. Channel summary cards (total/Tiktok/Shopee/Lazada) for current month vs prev month
    current_rows = [r for r in rows if r["ym"] == current_ym]
    prev_rows = [r for r in rows if r["ym"] == prev_ym]

    def channel_summary(data_rows):
        total = sum(r["qty"] for r in data_rows)
        by_platform = defaultdict(int)
        for r in data_rows:
            by_platform[r["platform"]] += r["qty"]
        return {
            "total": total,
            "tiktok": by_platform.get("Tiktok", 0),
            "shopee": by_platform.get("Shopee", 0),
            "lazada": by_platform.get("Lazada", 0),
        }

    current_summary = channel_summary(current_rows)
    prev_summary = channel_summary(prev_rows)

    def calc_delta(curr, prev):
        if prev == 0:
            return 0
        return round((curr - prev) / prev * 100, 1)

    channel_cards = {
        "current_ym": current_ym,
        "prev_ym": prev_ym,
        "cards": [
            {
                "label": "总出货",
                "current": current_summary["total"],
                "prev": prev_summary["total"],
                "delta": calc_delta(current_summary["total"], prev_summary["total"]),
            },
            {
                "label": "Tiktok",
                "current": current_summary["tiktok"],
                "prev": prev_summary["tiktok"],
                "delta": calc_delta(current_summary["tiktok"], prev_summary["tiktok"]),
            },
            {
                "label": "Shopee",
                "current": current_summary["shopee"],
                "prev": prev_summary["shopee"],
                "delta": calc_delta(current_summary["shopee"], prev_summary["shopee"]),
            },
            {
                "label": "Lazada",
                "current": current_summary["lazada"],
                "prev": prev_summary["lazada"],
                "delta": calc_delta(current_summary["lazada"], prev_summary["lazada"]),
            },
        ],
    }

    # 2. DMS - Category shipment table
    # For each category: total qty, share%, per platform qty & share, MoM delta
    cat_current = defaultdict(lambda: defaultdict(int))
    cat_prev = defaultdict(lambda: defaultdict(int))
    for r in current_rows:
        cat_current[r["category"]][r["platform"]] += r["qty"]
    for r in prev_rows:
        cat_prev[r["category"]][r["platform"]] += r["qty"]

    cat_total_current = sum(sum(v.values()) for v in cat_current.values())
    cat_total_prev = sum(sum(v.values()) for v in cat_prev.values())

    category_table = []
    for cat in sorted(cat_current.keys(), key=lambda c: sum(cat_current[c].values()), reverse=True):
        curr_total = sum(cat_current[cat].values())
        prev_total = sum(cat_prev[cat].values())
        curr_tiktok = cat_current[cat].get("Tiktok", 0)
        curr_shopee = cat_current[cat].get("Shopee", 0)
        curr_lazada = cat_current[cat].get("Lazada", 0)
        prev_tiktok = cat_prev[cat].get("Tiktok", 0)
        prev_shopee = cat_prev[cat].get("Shopee", 0)
        prev_lazada = cat_prev[cat].get("Lazada", 0)

        category_table.append({
            "category": cat,
            "total": curr_total,
            "share": round(curr_total / cat_total_current * 100, 1) if cat_total_current else 0,
            "delta": calc_delta(curr_total, prev_total),
            "tiktok": curr_tiktok,
            "tiktok_share": round(curr_tiktok / curr_total * 100, 1) if curr_total else 0,
            "tiktok_delta": calc_delta(curr_tiktok, prev_tiktok),
            "shopee": curr_shopee,
            "shopee_share": round(curr_shopee / curr_total * 100, 1) if curr_total else 0,
            "shopee_delta": calc_delta(curr_shopee, prev_shopee),
            "lazada": curr_lazada,
            "lazada_share": round(curr_lazada / curr_total * 100, 1) if curr_total else 0,
            "lazada_delta": calc_delta(curr_lazada, prev_lazada),
        })

    # 3. TT sales & Shopee shipment trend (monthly time series)
    # For each year-month, total qty by platform
    monthly_trend = []
    for ym in all_yms:
        ym_rows = [r for r in rows if r["ym"] == ym]
        monthly_trend.append({
            "ym": ym,
            "tiktok": sum(r["qty"] for r in ym_rows if r["platform"] == "Tiktok"),
            "shopee": sum(r["qty"] for r in ym_rows if r["platform"] == "Shopee"),
            "lazada": sum(r["qty"] for r in ym_rows if r["platform"] == "Lazada"),
            "total": sum(r["qty"] for r in ym_rows),
        })

    # 4. Daily trend for current month - TT sales daily & Shopee sales daily
    daily_current = defaultdict(lambda: defaultdict(int))
    for r in current_rows:
        if r["day"] > 0:
            daily_current[r["day"]][r["platform"]] += r["qty"]

    days_sorted = sorted(daily_current.keys())
    daily_trend_tiktok = [{"day": d, "qty": daily_current[d].get("Tiktok", 0)} for d in days_sorted]
    daily_trend_shopee = [{"day": d, "qty": daily_current[d].get("Shopee", 0)} for d in days_sorted]
    daily_trend_lazada = [{"day": d, "qty": daily_current[d].get("Lazada", 0)} for d in days_sorted]

    # 5. Monthly cumulative comparison table (by SKU for current month)
    # Top 30 SKUs by qty in current month
    sku_current = defaultdict(lambda: defaultdict(int))
    sku_prev = defaultdict(lambda: defaultdict(int))
    for r in current_rows:
        sku_current[r["sku"]][r["platform"]] += r["qty"]
    for r in prev_rows:
        sku_prev[r["sku"]][r["platform"]] += r["qty"]

    sku_list = []
    for sku in sorted(sku_current.keys(), key=lambda s: sum(sku_current[s].values()), reverse=True)[:50]:
        curr_total = sum(sku_current[sku].values())
        prev_total = sum(sku_prev[sku].values())
        sku_list.append({
            "sku": sku,
            "name": next((r["product_name"] for r in current_rows if r["sku"] == sku), ""),
            "total": curr_total,
            "tiktok": sku_current[sku].get("Tiktok", 0),
            "shopee": sku_current[sku].get("Shopee", 0),
            "lazada": sku_current[sku].get("Lazada", 0),
            "prev_total": prev_total,
            "delta": calc_delta(curr_total, prev_total),
        })

    # Also get all unique SKUs for the filter dropdown
    all_skus = sorted(set(r["sku"] for r in rows if r["sku"]))

    output = {
        "channel_cards": channel_cards,
        "category_table": category_table,
        "monthly_trend": monthly_trend,
        "daily_trend": {
            "tiktok": daily_trend_tiktok,
            "shopee": daily_trend_shopee,
            "lazada": daily_trend_lazada,
        },
        "sku_table": sku_list,
        "all_skus": all_skus,
        "current_ym": current_ym,
        "prev_ym": prev_ym,
        "all_yms": all_yms,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Output written to {OUTPUT_FILE}")
    print(f"Current month: {current_ym} - Total: {current_summary['total']}")
    print(f"Prev month: {prev_ym} - Total: {prev_summary['total']}")
    print(f"Categories: {len(category_table)}")
    print(f"Monthly trend points: {len(monthly_trend)}")
    print(f"Daily trend days: {len(days_sorted)}")
    print(f"SKU table rows: {len(sku_list)}")

if __name__ == "__main__":
    main()
