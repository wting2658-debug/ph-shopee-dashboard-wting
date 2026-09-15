from __future__ import annotations

import json
import re
import unicodedata
from calendar import monthrange
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


SHEET_ID = "1I_Q-Rx6QklML2023EUG8U1hb4MPN8shyeTyShiXrcYY"
STORE_GID = "979789790"
AD_GID = "1711647547"
RAW_GID = "1292217820"
USD_TO_RMB = 6.9

REPORT_DIR = Path(__file__).resolve().parent
DATA_DIR = REPORT_DIR / "data"
STORE_CSV = DATA_DIR / "flagship_store_sheet_979789790.csv"
AD_CSV = DATA_DIR / "onsite_ads_sheet_1711647547.csv"
RAW_CSV = DATA_DIR / "raw_data_sheet_1292217820.csv"
OUTPUT_HTML = REPORT_DIR / "index.html"


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None or pd.isna(value):
        return fallback
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return fallback
    return text


def normalize_columns(columns: list[str]) -> list[str]:
    return [str(column).replace("\ufeff", "").strip() for column in columns]


def normalize_product_key(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", "", text)


def parse_number(series: pd.Series, *, percent_to_number: bool = False) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace({"": pd.NA, "-": pd.NA, "nan": pd.NA, "None": pd.NA})
    )
    percent_mask = cleaned.str.endswith("%", na=False)
    cleaned = cleaned.str.replace("%", "", regex=False)
    numbers = pd.to_numeric(cleaned, errors="coerce")
    if percent_to_number:
        numbers.loc[percent_mask] = numbers.loc[percent_mask] / 100.0
    return numbers


def first_non_empty(series: pd.Series, fallback: str = "") -> str:
    for value in series:
        text = clean_text(value)
        if text:
            return text
    return fallback


def join_unique(series: pd.Series) -> str:
    values: list[str] = []
    for value in series:
        text = clean_text(value)
        if text and text not in values:
            values.append(text)
    return " / ".join(values)


def parse_source_date(value: Any, default_year: int) -> pd.Timestamp | pd.NaT:
    text = clean_text(value)
    if not text:
        return pd.NaT

    match = re.fullmatch(r"(\d{1,2})月(\d{1,2})日", text)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        return pd.Timestamp(default_year, month, day)

    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    if parsed.year == 1900:
        return pd.Timestamp(default_year, parsed.month, parsed.day)
    return parsed.normalize()


def shift_month(date_value: pd.Timestamp, months: int) -> pd.Timestamp:
    target_month = date_value.month - 1 + months
    year = date_value.year + target_month // 12
    month = target_month % 12 + 1
    day = min(date_value.day, monthrange(year, month)[1])
    return pd.Timestamp(year=year, month=month, day=day)


def build_default_ranges(available_start: pd.Timestamp, available_end: pd.Timestamp) -> dict[str, dict[str, str]]:
    current_start = pd.Timestamp(year=available_end.year, month=available_end.month, day=1)
    current_start = max(current_start, available_start)
    current_end = available_end

    compare_start = shift_month(current_start, -1)
    compare_end = shift_month(current_end, -1)

    return {
        "current": {
            "start": current_start.strftime("%Y-%m-%d"),
            "end": current_end.strftime("%Y-%m-%d"),
        },
        "compare": {
            "start": compare_start.strftime("%Y-%m-%d"),
            "end": compare_end.strftime("%Y-%m-%d"),
        },
    }


def load_store_data(source_csv: Path) -> pd.DataFrame:
    store = pd.read_csv(source_csv, encoding="utf-8-sig", low_memory=False, dtype=str)
    store.columns = normalize_columns(store.columns.tolist())

    required = [
        "店铺",
        "品类",
        "FB-产品",
        "单日",
        "产品访客",
        "产品点击",
        "销量units",
        "GMV-￥",
        "产品加购",
        "产品ID",
        "产品",
        "小类目",
    ]
    missing = [column for column in required if column not in store.columns]
    if missing:
        raise KeyError(f"旗舰店数据源缺少列: {missing}")

    store["date"] = pd.to_datetime(store["单日"], errors="coerce")
    store["product_id"] = store["产品ID"].map(lambda value: clean_text(value))
    store["product_key"] = store["产品"].map(normalize_product_key)
    missing_key = store["product_key"].eq("")
    store.loc[missing_key, "product_key"] = store.loc[missing_key, "product_id"].map(
        lambda value: f"产品id:{value}" if value else ""
    )
    store["visitors"] = parse_number(store["产品访客"])
    store["clicks"] = parse_number(store["产品点击"], percent_to_number=True)
    store["orders"] = parse_number(store["销量units"]).fillna(0.0)
    store["gmv"] = parse_number(store["GMV-￥"]).fillna(0.0)
    store["add_to_cart"] = parse_number(store["产品加购"]).fillna(0.0)

    for column in ["店铺", "品类", "FB-产品", "产品", "小类目"]:
        store[column] = store[column].map(lambda value: clean_text(value))

    store = store[store["date"].notna() & store["product_key"].ne("")].copy()

    aggregated = (
        store.groupby(["date", "product_key"], as_index=False)
        .agg(
            product_ids=("product_id", join_unique),
            store_name=("店铺", first_non_empty),
            category=("品类", first_non_empty),
            subcategory=("小类目", first_non_empty),
            product_name=("产品", first_non_empty),
            fb_product_name=("FB-产品", first_non_empty),
            visitors=("visitors", "max"),
            clicks=("clicks", "max"),
            orders=("orders", "sum"),
            gmv=("gmv", "sum"),
            add_to_cart=("add_to_cart", "sum"),
        )
    )

    for column in ["visitors", "clicks", "orders", "gmv", "add_to_cart"]:
        aggregated[column] = aggregated[column].fillna(0.0)

    return aggregated


def load_ad_data(source_csv: Path, default_year: int) -> pd.DataFrame:
    ad = pd.read_csv(source_csv, encoding="utf-8-sig", low_memory=False, dtype=str)
    ad.columns = normalize_columns(ad.columns.tolist())

    required = [
        "date",
        "产品ID",
        "类目",
        "站内产品命名",
        "Ads Spend(rmb)",
        "站外产品命名",
        "小类目",
        "Ads GMV(rmb)",
        "Impression",
        "Clicks",
        "Order",
    ]
    missing = [column for column in required if column not in ad.columns]
    if missing:
        raise KeyError(f"站内广告缺少列: {missing}")

    ad["date"] = ad["date"].map(lambda value: parse_source_date(value, default_year))
    ad["product_id"] = ad["产品ID"].map(lambda value: clean_text(value))
    ad["product_key"] = ad["站内产品命名"].map(normalize_product_key)
    missing_key = ad["product_key"].eq("")
    ad.loc[missing_key, "product_key"] = ad.loc[missing_key, "product_id"].map(
        lambda value: f"产品id:{value}" if value else ""
    )
    ad["ad_spend"] = parse_number(ad["Ads Spend(rmb)"]).fillna(0.0)
    ad["ad_gmv"] = parse_number(ad["Ads GMV(rmb)"]).fillna(0.0)
    ad["impressions"] = parse_number(ad["Impression"]).fillna(0.0)
    ad["ad_clicks"] = parse_number(ad["Clicks"]).fillna(0.0)
    ad["ad_orders"] = parse_number(ad["Order"]).fillna(0.0)

    for column in ["类目", "站内产品命名", "站外产品命名", "小类目"]:
        ad[column] = ad[column].map(lambda value: clean_text(value))

    ad = ad[ad["date"].notna() & ad["product_key"].ne("")].copy()

    aggregated = (
        ad.groupby(["date", "product_key"], as_index=False)
        .agg(
            product_ids=("product_id", join_unique),
            category=("类目", first_non_empty),
            subcategory=("小类目", first_non_empty),
            product_name=("站内产品命名", first_non_empty),
            fb_product_name=("站外产品命名", first_non_empty),
            ad_spend=("ad_spend", "sum"),
            ad_gmv=("ad_gmv", "sum"),
            impressions=("impressions", "sum"),
            ad_clicks=("ad_clicks", "sum"),
            ad_orders=("ad_orders", "sum"),
        )
    )

    aggregated["store_name"] = ""

    return aggregated


def load_meta_data(source_csv: Path, default_year: int) -> pd.DataFrame:
    required = [
        "单日",
        "花费金额 (USD)",
        "展示次数",
        "链接点击量",
        "购物次数（共享商品）",
        "购物转化价值（仅共享商品）",
        "店铺",
        "产品1",
        "产品",
        "站内产品名",
        "品类",
        "小类目",
    ]
    meta = pd.read_csv(
        source_csv,
        encoding="utf-8-sig",
        low_memory=False,
        dtype=str,
        usecols=required,
    )
    meta.columns = normalize_columns(meta.columns.tolist())

    missing = [column for column in required if column not in meta.columns]
    if missing:
        raise KeyError(f"Raw_data 缺少列: {missing}")

    meta["date"] = meta["单日"].map(lambda value: parse_source_date(value, default_year))
    meta["product_key"] = meta["站内产品名"].map(normalize_product_key)
    fallback_key = meta["product_key"].eq("")
    meta.loc[fallback_key, "product_key"] = meta.loc[fallback_key, "产品"].map(normalize_product_key)
    meta["meta_spend"] = parse_number(meta["花费金额 (USD)"]).fillna(0.0) * USD_TO_RMB
    meta["meta_gmv"] = parse_number(meta["购物转化价值（仅共享商品）"]).fillna(0.0) * USD_TO_RMB
    meta["meta_impressions"] = parse_number(meta["展示次数"]).fillna(0.0)
    meta["meta_clicks"] = parse_number(meta["链接点击量"]).fillna(0.0)
    meta["meta_purchases"] = parse_number(meta["购物次数（共享商品）"]).fillna(0.0)
    meta["fb_product_name"] = meta["产品1"].where(meta["产品1"].map(clean_text).ne(""), meta["产品"])

    for column in ["店铺", "品类", "小类目", "站内产品名", "fb_product_name"]:
        meta[column] = meta[column].map(lambda value: clean_text(value))

    meta = meta[meta["date"].notna() & meta["product_key"].ne("")].copy()
    return (
        meta.groupby(["date", "product_key"], as_index=False)
        .agg(
            store_name=("店铺", first_non_empty),
            category=("品类", first_non_empty),
            subcategory=("小类目", first_non_empty),
            product_name=("站内产品名", first_non_empty),
            fb_product_name=("fb_product_name", first_non_empty),
            meta_spend=("meta_spend", "sum"),
            meta_gmv=("meta_gmv", "sum"),
            meta_impressions=("meta_impressions", "sum"),
            meta_clicks=("meta_clicks", "sum"),
            meta_purchases=("meta_purchases", "sum"),
        )
    )


def product_metadata(frame: pd.DataFrame, include_ids: bool = False) -> pd.DataFrame:
    aggregations: dict[str, tuple[str, Any]] = {
        "store_name": ("store_name", first_non_empty),
        "category": ("category", first_non_empty),
        "subcategory": ("subcategory", first_non_empty),
        "product_name": ("product_name", first_non_empty),
        "fb_product_name": ("fb_product_name", first_non_empty),
    }
    if include_ids:
        aggregations["product_ids"] = ("product_ids", join_unique)
    return frame.groupby("product_key", as_index=False).agg(**aggregations).set_index("product_key")


def build_product_dimension(
    store_daily: pd.DataFrame,
    ad_daily: pd.DataFrame,
    meta_daily: pd.DataFrame,
) -> list[dict[str, Any]]:
    store_meta = product_metadata(store_daily, include_ids=True)
    ad_meta = product_metadata(ad_daily, include_ids=True)
    meta_meta = product_metadata(meta_daily)
    product_keys = sorted(
        set(store_daily["product_key"]) | set(ad_daily["product_key"]) | set(meta_daily["product_key"])
    )
    products: list[dict[str, Any]] = []

    for product_key in product_keys:
        rows = [
            lookup.loc[product_key] if product_key in lookup.index else None
            for lookup in [store_meta, ad_meta, meta_meta]
        ]

        def preferred(field: str, fallback: str = "") -> str:
            for row in rows:
                if row is not None:
                    value = clean_text(row[field])
                    if value:
                        return value
            return fallback

        product_ids = []
        for row in rows[:2]:
            if row is not None and "product_ids" in row.index:
                value = clean_text(row["product_ids"])
                if value and value not in product_ids:
                    product_ids.append(value)

        products.append(
            {
                "id": product_key,
                "product_ids": " / ".join(product_ids) or "-",
                "store": preferred("store_name", "旗舰店"),
                "category": preferred("category", "未标注品类"),
                "subcategory": preferred("subcategory", "未标注小类目"),
                "product_name": preferred("product_name", product_key),
                "fb_product_name": preferred("fb_product_name", "-"),
                "has_store": product_key in store_meta.index,
                "has_onsite": product_key in ad_meta.index,
                "has_meta": product_key in meta_meta.index,
            }
        )

    products.sort(key=lambda item: (item["category"], item["subcategory"], item["product_name"], item["id"]))
    return products


def build_daily_facts(
    store_daily: pd.DataFrame,
    ad_daily: pd.DataFrame,
    meta_daily: pd.DataFrame,
    products: list[dict[str, Any]],
) -> pd.DataFrame:
    store_metrics = store_daily[
        ["date", "product_key", "gmv", "orders", "visitors", "clicks", "add_to_cart"]
    ]
    ad_metrics = ad_daily[
        ["date", "product_key", "ad_spend", "ad_gmv", "impressions", "ad_clicks", "ad_orders"]
    ]
    meta_metrics = meta_daily[
        ["date", "product_key", "meta_spend", "meta_gmv", "meta_impressions", "meta_clicks", "meta_purchases"]
    ]
    facts = store_metrics.merge(ad_metrics, on=["date", "product_key"], how="outer")
    facts = facts.merge(meta_metrics, on=["date", "product_key"], how="outer")
    numeric_columns = [
        "gmv",
        "orders",
        "visitors",
        "clicks",
        "add_to_cart",
        "ad_spend",
        "ad_gmv",
        "impressions",
        "ad_clicks",
        "ad_orders",
        "meta_spend",
        "meta_gmv",
        "meta_impressions",
        "meta_clicks",
        "meta_purchases",
    ]
    for column in numeric_columns:
        if column not in facts.columns:
            facts[column] = 0.0
        facts[column] = facts[column].fillna(0.0)

    product_lookup = {item["id"]: item for item in products}
    facts["meta"] = facts["product_key"].map(product_lookup)
    facts["category"] = facts["meta"].map(lambda value: value["category"])
    facts["subcategory"] = facts["meta"].map(lambda value: value["subcategory"])
    facts["product_name"] = facts["meta"].map(lambda value: value["product_name"])
    facts["fb_product_name"] = facts["meta"].map(lambda value: value["fb_product_name"])
    facts["store_name"] = facts["meta"].map(lambda value: value["store"])
    facts["date_str"] = facts["date"].dt.strftime("%Y-%m-%d")
    facts = facts.sort_values(["date", "category", "subcategory", "product_name"], kind="stable")
    return facts


def build_payload(store_csv: Path, ad_csv: Path, raw_csv: Path) -> dict[str, Any]:
    store_daily = load_store_data(store_csv)
    default_year = int(store_daily["date"].dt.year.mode().iat[0])
    ad_daily = load_ad_data(ad_csv, default_year)
    meta_daily = load_meta_data(raw_csv, default_year)
    products = build_product_dimension(store_daily, ad_daily, meta_daily)
    facts = build_daily_facts(store_daily, ad_daily, meta_daily, products)

    available_start = store_daily["date"].min()
    available_end = store_daily["date"].max()
    facts = facts[facts["date"].between(available_start, available_end)].copy()
    defaults = build_default_ranges(available_start, available_end)

    categories = sorted({product["category"] for product in products})
    subcategories = sorted({product["subcategory"] for product in products})
    fact_rows = [
        [
            row.date_str,
            row.product_key,
            round(float(row.gmv), 2),
            round(float(row.orders), 2),
            round(float(row.visitors), 2),
            round(float(row.clicks), 2),
            round(float(row.ad_spend), 2),
            round(float(row.ad_gmv), 2),
            round(float(row.impressions), 2),
            round(float(row.ad_clicks), 2),
            round(float(row.ad_orders), 2),
            round(float(row.add_to_cart), 2),
            round(float(row.meta_spend), 2),
            round(float(row.meta_gmv), 2),
            round(float(row.meta_impressions), 2),
            round(float(row.meta_clicks), 2),
            round(float(row.meta_purchases), 2),
        ]
        for row in facts.itertuples()
    ]

    store_keys = set(store_daily["product_key"])
    ad_keys = set(ad_daily["product_key"])
    meta_total_spend = float(meta_daily["meta_spend"].sum())
    meta_store_spend = float(meta_daily.loc[meta_daily["product_key"].isin(store_keys), "meta_spend"].sum())
    meta_ad_spend = float(meta_daily.loc[meta_daily["product_key"].isin(ad_keys), "meta_spend"].sum())

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sheet_id": SHEET_ID,
        "store_gid": STORE_GID,
        "ad_gid": AD_GID,
        "raw_gid": RAW_GID,
        "usd_to_rmb": USD_TO_RMB,
        "source_files": {
            "store_csv": str(store_csv),
            "ad_csv": str(ad_csv),
            "raw_csv": str(raw_csv),
        },
        "source_urls": {
            "store": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid={STORE_GID}#gid={STORE_GID}",
            "ad": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid={AD_GID}#gid={AD_GID}",
            "raw": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid={RAW_GID}#gid={RAW_GID}",
        },
        "data_quality": {
            "meta_spend_to_store": meta_store_spend / meta_total_spend if meta_total_spend else None,
            "meta_spend_to_onsite": meta_ad_spend / meta_total_spend if meta_total_spend else None,
            "store_products": len(store_keys),
            "onsite_products": len(ad_keys),
            "meta_products": len(set(meta_daily["product_key"])),
        },
        "available_range": {
            "start": available_start.strftime("%Y-%m-%d"),
            "end": available_end.strftime("%Y-%m-%d"),
        },
        "defaults": defaults,
        "categories": categories,
        "subcategories": subcategories,
        "products": products,
        "facts": fact_rows,
    }


def render_html(payload: dict[str, Any]) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False)
    html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SKT-PH-Meta x Shopee 看板 · 店铺分析</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700;800&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg-1: #f8fafc;
      --bg-2: #eef3f9;
      --ink: #20324a;
      --muted: #728197;
      --line: rgba(38, 61, 91, 0.11);
      --paper: rgba(255, 255, 255, 0.96);
      --panel: #ffffff;
      --accent: #ee4d2d;
      --accent-2: #2787e7;
      --accent-3: #f5a623;
      --good: #15966a;
      --bad: #df4f53;
      --shadow: 0 12px 34px rgba(51, 78, 112, 0.08);
      --radius-xl: 18px;
      --radius-lg: 15px;
      --radius-md: 13px;
      --radius-sm: 10px;
    }

    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: "Noto Sans SC", sans-serif;
      background:
        radial-gradient(circle at 8% 8%, rgba(238, 77, 45, 0.08), transparent 22%),
        radial-gradient(circle at 92% 18%, rgba(39, 135, 231, 0.08), transparent 24%),
        linear-gradient(180deg, var(--bg-1) 0%, var(--bg-2) 100%);
    }

    button, input {
      font: inherit;
    }

    .page {
      width: min(1720px, calc(100vw - 28px));
      margin: 0 auto;
      padding: 22px 0 40px;
    }

    .hero,
    .panel,
    .metric-card,
    .reference-card,
    .top-card,
    .swing-card {
      background: var(--paper);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: var(--radius-xl);
    }

    .hero {
      display: block;
      padding: 18px 4px 0;
      margin-bottom: 18px;
      background: transparent;
      border: 0;
      box-shadow: none;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      margin-bottom: 14px;
      padding: 12px 16px;
      background: rgba(255,255,255,0.92);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: var(--shadow);
    }

    .dashboard-title {
      margin: 0;
      font-size: clamp(30px, 4vw, 48px);
      line-height: 1.05;
      color: #152a45;
    }

    .dashboard-subtitle {
      margin: 12px 0 18px;
      color: #5e7591;
      font-size: 15px;
      line-height: 1.75;
    }

    .dashboard-controls {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto minmax(210px, 0.42fr);
      align-items: stretch;
      gap: 12px;
      padding: 14px;
      background: rgba(255,255,255,0.96);
      border: 1px solid #d8e2ee;
      border-radius: 14px;
      box-shadow: 0 8px 24px rgba(52, 77, 109, 0.06);
    }

    .dashboard-controls .date-grid {
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 10px;
    }

    .refresh-button {
      align-self: center;
      min-height: 44px;
      border: 0;
      border-radius: 8px;
      padding: 0 18px;
      color: #fff;
      background: #16748d;
      font-weight: 800;
      cursor: pointer;
      white-space: nowrap;
    }

    .refresh-button:hover { background: #0d6178; }
    .refresh-button:disabled { opacity: 0.65; cursor: wait; }

    .refresh-status {
      display: grid;
      align-content: center;
      gap: 6px;
      padding: 8px 14px;
      border: 1px solid #d8e2ee;
      border-radius: 10px;
      background: #f8fbfe;
      color: #546b84;
      font-size: 13px;
    }

    .refresh-state {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      color: #0f7a59;
      font-weight: 800;
    }

    .refresh-state::before {
      content: "";
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: currentColor;
    }

    .refresh-state.is-busy { color: #b87517; }
    .refresh-state.is-error { color: #c43e46; }

    .dashboard-tabs {
      display: flex;
      gap: 2px;
      width: max-content;
      max-width: 100%;
      margin-top: 14px;
      padding: 4px;
      border: 1px solid #d8e2ee;
      border-radius: 15px;
      background: rgba(255,255,255,0.92);
    }

    .dashboard-tab {
      border: 0;
      border-radius: 10px;
      padding: 11px 24px;
      color: #44617f;
      background: transparent;
      font-weight: 800;
    }

    .dashboard-tab.active {
      color: #fff;
      background: #16748d;
      box-shadow: 0 6px 14px rgba(22, 116, 141, 0.2);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }

    .brand-mark {
      width: 30px;
      height: 30px;
      display: inline-grid;
      place-items: center;
      color: #fff;
      background: var(--accent);
      border-radius: 9px;
      font-size: 15px;
    }

    .page-tab {
      padding: 8px 13px;
      color: var(--accent);
      background: rgba(238,77,45,0.08);
      border: 1px solid rgba(238,77,45,0.18);
      border-radius: 999px;
      font-size: 13px;
      font-weight: 700;
    }

    .hero-kicker {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      border-radius: 999px;
      color: var(--accent);
      background: rgba(238, 77, 45, 0.08);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 12px;
    }

    h1, h2, h3 {
      margin: 0;
      font-family: "Plus Jakarta Sans", "Noto Sans SC", sans-serif;
      letter-spacing: -0.03em;
    }

    h1 {
      margin-top: 14px;
      font-size: clamp(32px, 4vw, 50px);
      line-height: 1.02;
    }

    .hero-subtitle,
    .panel-subtitle,
    .mini-note,
    .filter-note {
      color: var(--muted);
      line-height: 1.7;
    }

    .hero-subtitle {
      margin: 14px 0 18px;
      font-size: 15px;
      max-width: 820px;
    }

    .hero-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 13px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.74);
      border: 1px solid rgba(54, 39, 19, 0.08);
      font-size: 13px;
      color: #51627a;
    }

    .filters-panel {
      display: grid;
      gap: 14px;
      padding: 18px;
      background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
      border-radius: var(--radius-lg);
      border: 1px solid rgba(54, 39, 19, 0.08);
    }

    .date-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }

    .field {
      display: grid;
      gap: 6px;
    }

    .field label {
      font-size: 12px;
      color: #617189;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .field input {
      width: 100%;
      min-height: 44px;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid rgba(54, 39, 19, 0.14);
      background: rgba(255,255,255,0.9);
    }

    .filter-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }

    .btn {
      appearance: none;
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      cursor: pointer;
      transition: transform 120ms ease, opacity 120ms ease;
    }

    .btn:hover { transform: translateY(-1px); }
    .btn-primary {
      color: white;
      background: linear-gradient(135deg, var(--accent) 0%, #e08747 100%);
    }
    .btn-secondary {
      color: #52647b;
      background: rgba(255,255,255,0.82);
      border: 1px solid rgba(54, 39, 19, 0.12);
    }

    .filters-strip {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }

    .filter-box {
      position: relative;
    }

    .filter-trigger {
      width: 100%;
      min-height: 58px;
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      background: var(--paper);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 16px;
      box-shadow: var(--shadow);
      cursor: pointer;
    }

    .filter-title {
      display: block;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #728197;
      margin-bottom: 4px;
    }

    .filter-value {
      font-size: 14px;
      font-weight: 700;
      color: var(--ink);
      text-align: left;
    }

    .filter-panel {
      position: absolute;
      z-index: 20;
      left: 0;
      right: 0;
      top: calc(100% + 10px);
      padding: 14px;
      border-radius: 18px;
      border: 1px solid rgba(54, 39, 19, 0.14);
      background: rgba(255,255,255,0.98);
      box-shadow: 0 24px 56px rgba(37, 28, 18, 0.16);
      display: none;
      gap: 10px;
    }

    .filter-box.open .filter-panel {
      display: grid;
    }

    .filter-toolbar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .filter-toolbar button {
      border: 1px solid rgba(54, 39, 19, 0.12);
      background: #fff8ef;
      color: #6b5848;
      border-radius: 999px;
      padding: 7px 10px;
      cursor: pointer;
    }

    .filter-search {
      width: 100%;
      border-radius: 12px;
      border: 1px solid rgba(54, 39, 19, 0.12);
      padding: 10px 12px;
    }

    .filter-options {
      max-height: 320px;
      overflow: auto;
      display: grid;
      gap: 8px;
      padding-right: 4px;
    }

    .option-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid rgba(54, 39, 19, 0.08);
      background: rgba(250, 245, 238, 0.7);
      cursor: pointer;
    }

    .option-row.selected {
      border-color: rgba(203, 95, 46, 0.38);
      background: rgba(203, 95, 46, 0.1);
    }

    .option-meta {
      font-size: 12px;
      color: #7a695b;
    }

    .metrics-grid,
    .reference-grid,
    .top-grid,
    .swing-grid {
      display: grid;
      gap: 14px;
      margin-bottom: 18px;
    }

    .metrics-grid {
      grid-template-columns: repeat(7, minmax(0, 1fr));
    }

    .reference-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }

    .metric-card,
    .reference-card {
      padding: 18px;
    }

    .metric-label,
    .reference-label {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #7c6f63;
      margin-bottom: 10px;
      font-weight: 700;
    }

    .metric-value,
    .reference-value {
      font-family: "Plus Jakarta Sans", "Noto Sans SC", sans-serif;
      font-size: 28px;
      font-weight: 800;
      line-height: 1;
    }

    .metric-delta,
    .cell-delta {
      margin-top: 12px;
      font-size: 13px;
      font-weight: 700;
    }

    .delta-up { color: var(--good); }
    .delta-down { color: var(--bad); }
    .delta-flat { color: #847463; }

    .three-col {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }

    .panel {
      padding: 18px;
    }

    .panel-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }

    .panel-title {
      font-size: 24px;
    }

    .trend-column {
      display: grid;
      gap: 14px;
    }

    .trend-card {
      border: 1px solid rgba(54, 39, 19, 0.08);
      background: rgba(255,255,255,0.7);
      border-radius: 18px;
      padding: 14px;
    }

    .trend-card h3 {
      font-size: 16px;
      margin-bottom: 6px;
    }

    .chart-wrap {
      position: relative;
      height: 185px;
    }

    .table-panel {
      padding: 0;
      overflow: hidden;
    }

    .table-header {
      padding: 18px 18px 12px;
    }

    .table-wrap {
      overflow-x: hidden;
      overflow-y: auto;
      border-top: 1px solid rgba(54, 39, 19, 0.08);
      scrollbar-color: #aab8c8 #edf2f7;
      scrollbar-width: thin;
    }

    table {
      width: 100%;
      min-width: 0;
      table-layout: fixed;
      border-collapse: collapse;
    }

    th,
    td {
      padding: 10px 7px;
      border-bottom: 1px solid rgba(54, 39, 19, 0.08);
      text-align: right;
      vertical-align: middle;
      font-size: 12px;
      line-height: 1.3;
      overflow-wrap: anywhere;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 3;
      background: rgba(246, 249, 253, 0.98);
      color: #40536c;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.01em;
      white-space: normal;
    }

    th:first-child,
    td:first-child {
      width: 15%;
      text-align: left;
      padding-left: 14px;
    }

    th:not(:first-child),
    td:not(:first-child) {
      width: 7.72%;
    }

    th:nth-child(7),
    td:nth-child(7),
    th:nth-child(10),
    td:nth-child(10) {
      border-left: 1px dashed #9eb1c7;
    }

    th:nth-child(n+7):nth-child(-n+9) { background: rgba(39, 135, 231, 0.07); }
    th:nth-child(n+10):nth-child(-n+12) { background: rgba(238, 77, 45, 0.07); }

    tbody tr:hover td { background: rgba(39, 135, 231, 0.035); }

    tfoot td {
      position: sticky;
      bottom: 0;
      z-index: 2;
      background: #eef4fa;
      border-top: 1px solid #b8c7d8;
      border-bottom: 0;
      box-shadow: 0 -5px 16px rgba(42, 69, 101, 0.08);
      font-weight: 800;
    }

    .category-scroll { max-height: 520px; }
    .product-scroll { max-height: 680px; }

    .cell-main {
      font-weight: 700;
      color: #263a53;
      white-space: nowrap;
    }

    .product-name {
      font-weight: 700;
      color: #263a53;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .product-meta {
      margin-top: 3px;
      color: #7a8798;
      font-size: 10px;
      line-height: 1.35;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .top-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .top-card,
    .swing-card {
      padding: 18px;
    }

    .rank-list {
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }

    .rank-item {
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 12px;
      align-items: center;
      padding: 12px;
      border-radius: 14px;
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(54, 39, 19, 0.08);
    }

    .rank-num {
      width: 34px;
      height: 34px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 50%;
      background: #2c241b;
      color: white;
      font-weight: 800;
      font-family: "Plus Jakarta Sans", sans-serif;
    }

    .rank-name {
      font-weight: 700;
      line-height: 1.4;
    }

    .rank-detail,
    .rank-side {
      color: #7a695c;
      font-size: 12px;
      line-height: 1.55;
    }

    .swing-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .formula-note {
      padding: 16px 18px;
      border-radius: 18px;
      background: rgba(255,255,255,0.65);
      border: 1px dashed rgba(54, 39, 19, 0.16);
      color: #6b5d51;
      line-height: 1.8;
      font-size: 13px;
    }

    .empty {
      padding: 22px;
      color: #7c6f63;
      text-align: center;
    }

    @media (max-width: 1280px) {
      .metrics-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .reference-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .hero,
      .three-col,
      .top-grid,
      .swing-grid { grid-template-columns: 1fr; }
    }

    @media (max-width: 860px) {
      .page { width: min(100vw - 16px, 1720px); }
      .date-grid,
      .filters-strip,
      .metrics-grid,
      .reference-grid { grid-template-columns: 1fr; }
      .hero { padding: 18px; }
      .dashboard-controls { grid-template-columns: 1fr; }
      .dashboard-controls .date-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .refresh-button { width: 100%; }
      .panel { padding: 16px; }
      .filter-panel { position: static; margin-top: 10px; }
      th, td { padding: 8px 4px; font-size: 10px; }
      th:first-child, td:first-child { width: 18%; padding-left: 7px; }
      th:not(:first-child), td:not(:first-child) { width: 7.45%; }
    }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="hero-kicker">Store · Shopee Ads · Meta Ads</div>
      <h1 class="dashboard-title">SKT-PH-Meta x Shopee 看板</h1>
      <p class="dashboard-subtitle">
        统一查看旗舰店、Shopee 站内广告与 Meta 站外广告，围绕流量、转化和投放费比定位 GMV 增长卡点。
        数据源每日更新，可通过“立即更新”重新导出并生成最新看板。
      </p>
      <div class="dashboard-controls">
        <div class="date-grid">
          <div class="field">
            <label for="start-date">查询开始</label>
            <input id="start-date" type="date">
          </div>
          <div class="field">
            <label for="end-date">查询结束</label>
            <input id="end-date" type="date">
          </div>
          <div class="field">
            <label for="compare-start-date">对比开始</label>
            <input id="compare-start-date" type="date">
          </div>
          <div class="field">
            <label for="compare-end-date">对比结束</label>
            <input id="compare-end-date" type="date">
          </div>
        </div>
        <button class="refresh-button" id="refresh-data-btn" type="button">立即更新</button>
        <div class="refresh-status">
          <div class="refresh-state" id="refresh-state">数据正常</div>
          <div id="last-updated">最新更新：--</div>
        </div>
      </div>
      <div class="dashboard-tabs" aria-label="看板分页">
        <button class="dashboard-tab active" type="button">店铺分析</button>
      </div>
    </section>

    <section class="filters-strip" id="filters-strip"></section>

    <section class="metrics-grid" id="metrics-grid"></section>

    <section class="three-col">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">总览趋势 · 店铺侧</h2>
            <div class="panel-subtitle">左侧重点看店铺 GMV、访客、点击和链接转化率，帮助区分问题更偏流量还是偏承接。</div>
          </div>
        </div>
        <div class="trend-column">
          <div class="trend-card"><h3>店铺 GMV</h3><div class="chart-wrap"><canvas id="chart-store-gmv"></canvas></div></div>
          <div class="trend-card"><h3>产品访客</h3><div class="chart-wrap"><canvas id="chart-visitors"></canvas></div></div>
          <div class="trend-card"><h3>产品点击</h3><div class="chart-wrap"><canvas id="chart-clicks"></canvas></div></div>
          <div class="trend-card"><h3>链接转化率</h3><div class="chart-wrap"><canvas id="chart-conversion"></canvas></div></div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">总览趋势 · 站内广告</h2>
            <div class="panel-subtitle">判断站内扩量是否伴随有效点击和效率提升。</div>
          </div>
        </div>
        <div class="trend-column">
          <div class="trend-card"><h3>站内广告花费</h3><div class="chart-wrap"><canvas id="chart-ad-spend"></canvas></div></div>
          <div class="trend-card"><h3>站内广告 ROI</h3><div class="chart-wrap"><canvas id="chart-ad-roi"></canvas></div></div>
          <div class="trend-card"><h3>站内广告 Clicks</h3><div class="chart-wrap"><canvas id="chart-ad-clicks"></canvas></div></div>
          <div class="trend-card"><h3>站内广告 CPC</h3><div class="chart-wrap"><canvas id="chart-ad-cpc"></canvas></div></div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">总览趋势 · 站外广告</h2>
            <div class="panel-subtitle">Meta 金额已统一按 6.9 换算人民币，关注曝光到点击的获客效率。</div>
          </div>
        </div>
        <div class="trend-column">
          <div class="trend-card"><h3>站外广告花费</h3><div class="chart-wrap"><canvas id="chart-meta-spend"></canvas></div></div>
          <div class="trend-card"><h3>站外展示次数</h3><div class="chart-wrap"><canvas id="chart-meta-impressions"></canvas></div></div>
          <div class="trend-card"><h3>站外链接点击量</h3><div class="chart-wrap"><canvas id="chart-meta-clicks"></canvas></div></div>
          <div class="trend-card"><h3>站外 CTR</h3><div class="chart-wrap"><canvas id="chart-meta-ctr"></canvas></div></div>
        </div>
      </div>
    </section>

    <section class="panel table-panel">
      <div class="table-header">
        <h2 class="panel-title">小品类情况</h2>
        <div class="panel-subtitle">按小品类拆解店铺贡献、站内外投放占比与费比；无对应花费显示为 - 。</div>
      </div>
      <div class="table-wrap category-scroll"><table id="category-table"></table></div>
    </section>

    <section class="panel table-panel" style="margin-top: 18px;">
      <div class="table-header">
        <h2 class="panel-title">产品链接表现</h2>
        <div class="panel-subtitle">按当前筛选窗口的店铺 GMV 排序；表内纵向滚动可查看全部产品。</div>
      </div>
      <div class="table-wrap product-scroll"><table id="product-table"></table></div>
    </section>

    <section class="top-grid" style="margin-top: 18px;">
      <div class="top-card">
        <h2>TOP5 · 访客增长</h2>
        <div class="mini-note">展示当前访客数、增长值和相对上个月同期的访客排名变化。</div>
        <div class="rank-list" id="top-visitors"></div>
      </div>
      <div class="top-card">
        <h2>TOP5 · 转化率</h2>
        <div class="mini-note">为减少极小样本干扰，这里默认只纳入当前窗口点击数 ≥ 100 的产品。</div>
        <div class="rank-list" id="top-conversion"></div>
      </div>
      <div class="top-card">
        <h2>TOP5 · GMV</h2>
        <div class="mini-note">展示当前 GMV、相对上个月同期的排名变化，以及产品当前所属品类。</div>
        <div class="rank-list" id="top-gmv"></div>
      </div>
    </section>

    <section class="swing-grid">
      <div class="swing-card">
        <h2>GMV 增长 TOP5</h2>
        <div class="mini-note">看哪些产品在当前窗口里真正拉动了增量。</div>
        <div class="rank-list" id="gmv-gainers"></div>
      </div>
      <div class="swing-card">
        <h2>GMV 下滑 TOP5</h2>
        <div class="mini-note">看哪些产品是当前阶段最需要优先补救的 GMV 缺口。</div>
        <div class="rank-list" id="gmv-decliners"></div>
      </div>
    </section>

    <section class="formula-note">
      指标口径：
      店铺转化率 = 店铺订单数 / 产品点击；
      链接点击率 = 产品点击 / 产品访客；
      站内 CPC = Ads Spend / Clicks；站内 ROI = Ads GMV / Ads Spend；
      站外 CTR = 链接点击量 / 展示次数；站外转化率 = 购物次数 / 链接点击量；
      站内/站外费比 = 对应广告花费 / 店铺 GMV。
      Raw_data 的花费金额与购物转化价值在进入任何汇总前均按 6.9 换算为人民币。
    </section>
  </div>

  <script>
    const PAYLOAD = __PAYLOAD_JSON__;
    const REFRESH_ENDPOINT = '/refresh-data';
    const FACT = {
      date: 0,
      id: 1,
      gmv: 2,
      orders: 3,
      visitors: 4,
      clicks: 5,
      adSpend: 6,
      adGMV: 7,
      impressions: 8,
      adClicks: 9,
      adOrders: 10,
      addToCart: 11,
      metaSpend: 12,
      metaGMV: 13,
      metaImpressions: 14,
      metaClicks: 15,
      metaPurchases: 16,
    };

    const products = PAYLOAD.products;
    const facts = PAYLOAD.facts;
    const productMap = new Map(products.map(item => [item.id, item]));
    const state = {
      start: PAYLOAD.defaults.current.start,
      end: PAYLOAD.defaults.current.end,
      compareStart: PAYLOAD.defaults.compare.start,
      compareEnd: PAYLOAD.defaults.compare.end,
      selectedCategories: new Set(PAYLOAD.categories),
      selectedSubcategories: new Set(PAYLOAD.subcategories),
      selectedProducts: new Set(products.map(item => item.id)),
      search: {
        categories: '',
        subcategories: '',
        products: '',
      },
      openFilter: null,
      charts: {},
    };

    function parseDate(dateStr) {
      return new Date(`${dateStr}T00:00:00`);
    }

    function formatDate(dateStr) {
      const date = parseDate(dateStr);
      return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    }

    function formatDateShort(dateStr) {
      const date = parseDate(dateStr);
      return `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')}`;
    }

    function formatCurrency(value) {
      if (value === null || value === undefined || Number.isNaN(value)) return '-';
      return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value);
    }

    function formatNumber(value, digits = 0) {
      if (value === null || value === undefined || Number.isNaN(value)) return '-';
      return new Intl.NumberFormat('zh-CN', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(value);
    }

    function formatPercent(value, digits = 1) {
      if (value === null || value === undefined || Number.isNaN(value)) return '-';
      return `${(value * 100).toFixed(digits)}%`;
    }

    function formatRatio(value, digits = 2) {
      if (value === null || value === undefined || Number.isNaN(value)) return '-';
      return `${value.toFixed(digits)}x`;
    }

    function escapeAttr(value) {
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    function safeDivide(numerator, denominator) {
      if (denominator === null || denominator === undefined || Number(denominator) === 0) return null;
      if (numerator === null || numerator === undefined) return null;
      return Number(numerator) / Number(denominator);
    }

    function deltaValue(current, compare) {
      if ((current === null || current === undefined) && (compare === null || compare === undefined)) return null;
      if (compare === null || compare === undefined || Number(compare) === 0) {
        if (!current) return 0;
        return null;
      }
      return Number(current) / Number(compare) - 1;
    }

    function deltaText(current, compare) {
      const delta = deltaValue(current, compare);
      if (delta === null) {
        return current ? '+新增' : '-';
      }
      const sign = delta >= 0 ? '+' : '';
      return `${sign}${(delta * 100).toFixed(1)}%`;
    }

    function deltaClass(current, compare) {
      const delta = deltaValue(current, compare);
      if (delta === null) return 'delta-flat';
      if (delta > 0) return 'delta-up';
      if (delta < 0) return 'delta-down';
      return 'delta-flat';
    }

    function daysInMonth(year, month) {
      return new Date(year, month, 0).getDate();
    }

    function shiftMonth(dateStr, offset) {
      const source = parseDate(dateStr);
      const year = source.getFullYear();
      const monthIndex = source.getMonth();
      const day = source.getDate();
      const totalMonths = year * 12 + monthIndex + offset;
      const nextYear = Math.floor(totalMonths / 12);
      const nextMonthIndex = ((totalMonths % 12) + 12) % 12;
      const maxDay = daysInMonth(nextYear, nextMonthIndex + 1);
      const nextDay = Math.min(day, maxDay);
      return `${nextYear}-${String(nextMonthIndex + 1).padStart(2, '0')}-${String(nextDay).padStart(2, '0')}`;
    }

    function compareRange() {
      return {
        start: state.compareStart,
        end: state.compareEnd,
      };
    }

    function createAgg() {
      return {
        gmv: 0,
        orders: 0,
        visitors: 0,
        clicks: 0,
        adSpend: 0,
        adGMV: 0,
        impressions: 0,
        adClicks: 0,
        adOrders: 0,
        addToCart: 0,
        metaSpend: 0,
        metaGMV: 0,
        metaImpressions: 0,
        metaClicks: 0,
        metaPurchases: 0,
      };
    }

    function addFact(target, row) {
      target.gmv += row[FACT.gmv];
      target.orders += row[FACT.orders];
      target.visitors += row[FACT.visitors];
      target.clicks += row[FACT.clicks];
      target.adSpend += row[FACT.adSpend];
      target.adGMV += row[FACT.adGMV];
      target.impressions += row[FACT.impressions];
      target.adClicks += row[FACT.adClicks];
      target.adOrders += row[FACT.adOrders];
      target.addToCart += row[FACT.addToCart];
      target.metaSpend += row[FACT.metaSpend];
      target.metaGMV += row[FACT.metaGMV];
      target.metaImpressions += row[FACT.metaImpressions];
      target.metaClicks += row[FACT.metaClicks];
      target.metaPurchases += row[FACT.metaPurchases];
    }

    function finalizeAgg(agg) {
      return {
        ...agg,
        conversion: safeDivide(agg.orders, agg.clicks),
        clickRate: safeDivide(agg.clicks, agg.visitors),
        cpc: safeDivide(agg.adSpend, agg.adClicks),
        cpa: safeDivide(agg.adSpend, agg.adOrders),
        adROI: safeDivide(agg.adGMV, agg.adSpend),
        metaCTR: safeDivide(agg.metaClicks, agg.metaImpressions),
        metaCVR: safeDivide(agg.metaPurchases, agg.metaClicks),
        metaROAS: safeDivide(agg.metaGMV, agg.metaSpend),
      };
    }

    function getSelectedProductIds() {
      const selected = [];
      for (const product of products) {
        if (!state.selectedCategories.has(product.category)) continue;
        if (!state.selectedSubcategories.has(product.subcategory)) continue;
        if (!state.selectedProducts.has(product.id)) continue;
        selected.push(product.id);
      }
      return new Set(selected);
    }

    function filterFacts(range, selectedIds) {
      return facts.filter(row => row[FACT.date] >= range.start && row[FACT.date] <= range.end && selectedIds.has(row[FACT.id]));
    }

    function aggregateFacts(rows) {
      const agg = createAgg();
      for (const row of rows) addFact(agg, row);
      return finalizeAgg(agg);
    }

    function aggregateBy(rows, keyGetter) {
      const map = new Map();
      for (const row of rows) {
        const key = keyGetter(row);
        if (!map.has(key)) map.set(key, createAgg());
        addFact(map.get(key), row);
      }
      return map;
    }

    function aggregateProductRows(currentRows, compareRows) {
      const currentMap = aggregateBy(currentRows, row => row[FACT.id]);
      const compareMap = aggregateBy(compareRows, row => row[FACT.id]);
      const rows = [];
      for (const product of products) {
        if (!getSelectedProductIds().has(product.id)) continue;
        const current = finalizeAgg(currentMap.get(product.id) || createAgg());
        const compare = finalizeAgg(compareMap.get(product.id) || createAgg());
        if (current.gmv === 0 && current.adSpend === 0 && current.metaSpend === 0 && current.visitors === 0 && compare.gmv === 0 && compare.adSpend === 0 && compare.metaSpend === 0 && compare.visitors === 0) {
          continue;
        }
        rows.push({
          ...product,
          current,
          compare,
        });
      }
      return rows;
    }

    function dateToYmd(date) {
      return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    }

    function rangeDays(start, end) {
      const days = [];
      let cursor = parseDate(start);
      const limit = parseDate(end);
      while (cursor <= limit) {
        days.push(dateToYmd(cursor));
        cursor.setDate(cursor.getDate() + 1);
      }
      return days;
    }

    function dailySeries(currentRows, compareRows) {
      const currentByDate = aggregateBy(currentRows, row => row[FACT.date]);
      const compareByDate = aggregateBy(compareRows, row => row[FACT.date]);
      const labels = rangeDays(state.start, state.end);
      const compare = compareRange();
      const compareLabels = rangeDays(compare.start, compare.end);
      const length = Math.max(labels.length, compareLabels.length);
      const result = {
        labels: [],
        storeGMVCurrent: [],
        storeGMVCompare: [],
        visitorsCurrent: [],
        visitorsCompare: [],
        clicksCurrent: [],
        clicksCompare: [],
        conversionCurrent: [],
        conversionCompare: [],
        adSpendCurrent: [],
        adSpendCompare: [],
        adGMVCurrent: [],
        adGMVCompare: [],
        adROICurrent: [],
        adROICompare: [],
        adClicksCurrent: [],
        adClicksCompare: [],
        adCPCCurrent: [],
        adCPCCompare: [],
        metaSpendCurrent: [],
        metaSpendCompare: [],
        metaImpressionsCurrent: [],
        metaImpressionsCompare: [],
        metaClicksCurrent: [],
        metaClicksCompare: [],
        metaCTRCurrent: [],
        metaCTRCompare: [],
      };

      for (let index = 0; index < length; index += 1) {
        const currentDate = labels[index];
        const compareDate = compareLabels[index];
        const currentAgg = finalizeAgg(currentByDate.get(currentDate) || createAgg());
        const compareAgg = finalizeAgg(compareByDate.get(compareDate) || createAgg());
        result.labels.push(currentDate ? formatDateShort(currentDate) : formatDateShort(compareDate));
        result.storeGMVCurrent.push(currentDate ? currentAgg.gmv : null);
        result.storeGMVCompare.push(compareDate ? compareAgg.gmv : null);
        result.visitorsCurrent.push(currentDate ? currentAgg.visitors : null);
        result.visitorsCompare.push(compareDate ? compareAgg.visitors : null);
        result.clicksCurrent.push(currentDate ? currentAgg.clicks : null);
        result.clicksCompare.push(compareDate ? compareAgg.clicks : null);
        result.conversionCurrent.push(currentDate ? currentAgg.conversion : null);
        result.conversionCompare.push(compareDate ? compareAgg.conversion : null);
        result.adSpendCurrent.push(currentDate ? currentAgg.adSpend : null);
        result.adSpendCompare.push(compareDate ? compareAgg.adSpend : null);
        result.adGMVCurrent.push(currentDate ? currentAgg.adGMV : null);
        result.adGMVCompare.push(compareDate ? compareAgg.adGMV : null);
        result.adROICurrent.push(currentDate ? currentAgg.adROI : null);
        result.adROICompare.push(compareDate ? compareAgg.adROI : null);
        result.adClicksCurrent.push(currentDate ? currentAgg.adClicks : null);
        result.adClicksCompare.push(compareDate ? compareAgg.adClicks : null);
        result.adCPCCurrent.push(currentDate ? currentAgg.cpc : null);
        result.adCPCCompare.push(compareDate ? compareAgg.cpc : null);
        result.metaSpendCurrent.push(currentDate ? currentAgg.metaSpend : null);
        result.metaSpendCompare.push(compareDate ? compareAgg.metaSpend : null);
        result.metaImpressionsCurrent.push(currentDate ? currentAgg.metaImpressions : null);
        result.metaImpressionsCompare.push(compareDate ? compareAgg.metaImpressions : null);
        result.metaClicksCurrent.push(currentDate ? currentAgg.metaClicks : null);
        result.metaClicksCompare.push(compareDate ? compareAgg.metaClicks : null);
        result.metaCTRCurrent.push(currentDate ? currentAgg.metaCTR : null);
        result.metaCTRCompare.push(compareDate ? compareAgg.metaCTR : null);
      }

      return result;
    }

    function renderMetricCards(current, compare) {
      const items = [
        { label: '店铺 GMV', value: formatCurrency(current.gmv), current: current.gmv, compare: compare.gmv },
        { label: '店铺订单数', value: formatNumber(current.orders), current: current.orders, compare: compare.orders },
        { label: '产品访客', value: formatNumber(current.visitors), current: current.visitors, compare: compare.visitors },
        { label: '产品点击', value: formatNumber(current.clicks), current: current.clicks, compare: compare.clicks },
        { label: '转化率', value: formatPercent(current.conversion), current: current.conversion, compare: compare.conversion },
        { label: '站内广告花费', value: formatCurrency(current.adSpend), current: current.adSpend, compare: compare.adSpend },
        { label: '站外广告花费', value: formatCurrency(current.metaSpend), current: current.metaSpend, compare: compare.metaSpend },
      ];
      document.getElementById('metrics-grid').innerHTML = items.map(item => `
        <div class="metric-card">
          <div class="metric-label">${item.label}</div>
          <div class="metric-value">${item.value}</div>
          <div class="metric-delta ${deltaClass(item.current, item.compare)}">${deltaText(item.current, item.compare)}</div>
        </div>
      `).join('');
    }

    function renderReferenceCards(current, compare) {
      const items = [
        { label: '链接点击率', value: formatPercent(current.clickRate), current: current.clickRate, compare: compare.clickRate },
        { label: 'CPC', value: current.cpc === null ? '-' : formatNumber(current.cpc, 2), current: current.cpc, compare: compare.cpc },
        { label: 'CPA', value: current.cpa === null ? '-' : formatNumber(current.cpa, 2), current: current.cpa, compare: compare.cpa },
        { label: '广告 ROI', value: formatRatio(current.adROI), current: current.adROI, compare: compare.adROI },
      ];
      document.getElementById('reference-grid').innerHTML = items.map(item => `
        <div class="reference-card">
          <div class="reference-label">${item.label}</div>
          <div class="reference-value">${item.value}</div>
          <div class="metric-delta ${deltaClass(item.current, item.compare)}">${deltaText(item.current, item.compare)}</div>
        </div>
      `).join('');
    }

    function sharedLineOptions(kind = 'currency') {
      const isPercent = kind === 'percent';
      const isRatio = kind === 'ratio';
      return {
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              usePointStyle: true,
              boxWidth: 8,
              color: '#66584d',
            },
          },
          tooltip: {
            callbacks: {
              label(context) {
                const value = context.raw;
                if (value === null || value === undefined) return `${context.dataset.label}: -`;
                if (isPercent) return `${context.dataset.label}: ${formatPercent(value)}`;
                if (isRatio) return `${context.dataset.label}: ${formatRatio(value)}`;
                if (kind === 'number') return `${context.dataset.label}: ${formatNumber(value)}`;
                return `${context.dataset.label}: ${formatCurrency(value)}`;
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { color: '#817365' },
            grid: { display: false },
          },
          y: {
            ticks: {
              color: '#817365',
              callback(value) {
                if (isPercent) return `${value * 100}%`;
                if (isRatio) return `${value}x`;
                return value >= 1000 ? `${Math.round(value / 1000)}k` : value;
              }
            },
            grid: { color: 'rgba(61, 42, 17, 0.08)' },
          },
        },
      };
    }

    function upsertChart(id, config) {
      if (state.charts[id]) state.charts[id].destroy();
      state.charts[id] = new Chart(document.getElementById(id), config);
    }

    function renderCharts(series) {
      const currentColor = '#ee4d2d';
      const compareColor = '#2787e7';
      const gmvConfig = metric => ({
        type: 'line',
        data: {
          labels: series.labels,
          datasets: [
            { label: '本期', data: series[`${metric}Current`], borderColor: currentColor, backgroundColor: 'rgba(203,95,46,0.16)', tension: 0.32, pointRadius: 0, borderWidth: 2.5 },
            { label: '上月同期', data: series[`${metric}Compare`], borderColor: compareColor, backgroundColor: 'rgba(31,122,114,0.12)', tension: 0.32, pointRadius: 0, borderWidth: 2.2, borderDash: [7, 5] },
          ],
        },
      });

      upsertChart('chart-store-gmv', { ...gmvConfig('storeGMV'), options: sharedLineOptions('currency') });
      upsertChart('chart-visitors', { ...gmvConfig('visitors'), options: sharedLineOptions('number') });
      upsertChart('chart-clicks', { ...gmvConfig('clicks'), options: sharedLineOptions('number') });
      upsertChart('chart-conversion', { ...gmvConfig('conversion'), options: sharedLineOptions('percent') });
      upsertChart('chart-ad-spend', { ...gmvConfig('adSpend'), options: sharedLineOptions('currency') });
      upsertChart('chart-ad-roi', { ...gmvConfig('adROI'), options: sharedLineOptions('ratio') });
      upsertChart('chart-ad-clicks', { ...gmvConfig('adClicks'), options: sharedLineOptions('number') });
      upsertChart('chart-ad-cpc', { ...gmvConfig('adCPC'), options: sharedLineOptions('currency') });
      upsertChart('chart-meta-spend', { ...gmvConfig('metaSpend'), options: sharedLineOptions('currency') });
      upsertChart('chart-meta-impressions', { ...gmvConfig('metaImpressions'), options: sharedLineOptions('number') });
      upsertChart('chart-meta-clicks', { ...gmvConfig('metaClicks'), options: sharedLineOptions('number') });
      upsertChart('chart-meta-ctr', { ...gmvConfig('metaCTR'), options: sharedLineOptions('percent') });
    }

    function renderMetricCell(value, current, compare, formatter, opts = {}) {
      if (opts.dashWhenZero && (!current || current === 0)) {
        return `<div class="cell-main">-</div><div class="cell-delta delta-flat">-</div>`;
      }
      return `
        <div class="cell-main">${formatter(value)}</div>
        <div class="cell-delta ${deltaClass(current, compare)}">${deltaText(current, compare)}</div>
      `;
    }

    function renderSummaryFooter(current, compare) {
      const currentGmvShare = current.gmv > 0 ? 1 : null;
      const compareGmvShare = compare.gmv > 0 ? 1 : null;
      const currentAdShare = current.adSpend > 0 ? 1 : null;
      const compareAdShare = compare.adSpend > 0 ? 1 : null;
      const currentMetaShare = current.metaSpend > 0 ? 1 : null;
      const compareMetaShare = compare.metaSpend > 0 ? 1 : null;
      const currentAdFeeRatio = current.adSpend > 0 ? safeDivide(current.adSpend, current.gmv) : null;
      const compareAdFeeRatio = compare.adSpend > 0 ? safeDivide(compare.adSpend, compare.gmv) : null;
      const currentMetaFeeRatio = current.metaSpend > 0 ? safeDivide(current.metaSpend, current.gmv) : null;
      const compareMetaFeeRatio = compare.metaSpend > 0 ? safeDivide(compare.metaSpend, compare.gmv) : null;
      return `
        <tfoot>
          <tr>
            <td><div class="cell-main">汇总</div></td>
            <td>${renderMetricCell(current.gmv, current.gmv, compare.gmv, formatCurrency)}</td>
            <td>${renderMetricCell(currentGmvShare, currentGmvShare, compareGmvShare, value => formatPercent(value))}</td>
            <td>${renderMetricCell(current.visitors, current.visitors, compare.visitors, formatNumber)}</td>
            <td>${renderMetricCell(current.clickRate, current.clickRate, compare.clickRate, value => formatPercent(value))}</td>
            <td>${renderMetricCell(current.conversion, current.conversion, compare.conversion, value => formatPercent(value))}</td>
            <td>${renderMetricCell(current.adSpend, current.adSpend, compare.adSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(currentAdShare, currentAdShare, compareAdShare, value => formatPercent(value), { dashWhenZero: current.adSpend === 0 })}</td>
            <td>${renderMetricCell(currentAdFeeRatio, currentAdFeeRatio, compareAdFeeRatio, value => formatPercent(value), { dashWhenZero: current.adSpend === 0 })}</td>
            <td>${renderMetricCell(current.metaSpend, current.metaSpend, compare.metaSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(currentMetaShare, currentMetaShare, compareMetaShare, value => formatPercent(value), { dashWhenZero: current.metaSpend === 0 })}</td>
            <td>${renderMetricCell(currentMetaFeeRatio, currentMetaFeeRatio, compareMetaFeeRatio, value => formatPercent(value), { dashWhenZero: current.metaSpend === 0 })}</td>
          </tr>
        </tfoot>
      `;
    }

    function renderCategoryTable(currentRows, compareRows, currentTotals, compareTotals) {
      const currentMap = aggregateBy(currentRows, row => productMap.get(row[FACT.id]).subcategory);
      const compareMap = aggregateBy(compareRows, row => productMap.get(row[FACT.id]).subcategory);
      const keys = Array.from(new Set([...currentMap.keys(), ...compareMap.keys()]));
      const rows = keys.map(key => {
        const current = finalizeAgg(currentMap.get(key) || createAgg());
        const compare = finalizeAgg(compareMap.get(key) || createAgg());
        return {
          subcategory: key,
          current,
          compare,
          gmvShare: safeDivide(current.gmv, currentTotals.gmv),
          compareGmvShare: safeDivide(compare.gmv, compareTotals.gmv),
          adShare: current.adSpend > 0 ? safeDivide(current.adSpend, currentTotals.adSpend) : null,
          compareAdShare: compare.adSpend > 0 ? safeDivide(compare.adSpend, compareTotals.adSpend) : null,
          adFeeRatio: current.adSpend > 0 ? safeDivide(current.adSpend, current.gmv) : null,
          compareAdFeeRatio: compare.adSpend > 0 ? safeDivide(compare.adSpend, compare.gmv) : null,
          metaShare: current.metaSpend > 0 ? safeDivide(current.metaSpend, currentTotals.metaSpend) : null,
          compareMetaShare: compare.metaSpend > 0 ? safeDivide(compare.metaSpend, compareTotals.metaSpend) : null,
          metaFeeRatio: current.metaSpend > 0 ? safeDivide(current.metaSpend, current.gmv) : null,
          compareMetaFeeRatio: compare.metaSpend > 0 ? safeDivide(compare.metaSpend, compare.gmv) : null,
        };
      }).sort((a, b) => b.current.gmv - a.current.gmv);

      const header = `
        <thead>
          <tr>
            <th>小品类</th>
            <th>店铺 GMV</th>
            <th>GMV 占比</th>
            <th>产品访客</th>
            <th>点击率</th>
            <th>链接转化率</th>
            <th>站内广告花费</th>
            <th>站内自身占比</th>
            <th>站内费比</th>
            <th>站外广告花费</th>
            <th>站外自身占比</th>
            <th>站外费比</th>
          </tr>
        </thead>
      `;
      const body = rows.length ? `<tbody>${rows.map(row => `
        <tr>
          <td><div class="cell-main">${row.subcategory}</div></td>
          <td>${renderMetricCell(row.current.gmv, row.current.gmv, row.compare.gmv, formatCurrency)}</td>
          <td>${renderMetricCell(row.gmvShare, row.gmvShare, row.compareGmvShare, value => formatPercent(value))}</td>
          <td>${renderMetricCell(row.current.visitors, row.current.visitors, row.compare.visitors, formatNumber)}</td>
          <td>${renderMetricCell(row.current.clickRate, row.current.clickRate, row.compare.clickRate, value => formatPercent(value))}</td>
          <td>${renderMetricCell(row.current.conversion, row.current.conversion, row.compare.conversion, value => formatPercent(value))}</td>
          <td>${renderMetricCell(row.current.adSpend, row.current.adSpend, row.compare.adSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.adShare, row.adShare, row.compareAdShare, value => formatPercent(value), { dashWhenZero: row.current.adSpend === 0 })}</td>
          <td>${renderMetricCell(row.adFeeRatio, row.adFeeRatio, row.compareAdFeeRatio, value => formatPercent(value), { dashWhenZero: row.current.adSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.metaSpend, row.current.metaSpend, row.compare.metaSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.metaShare, row.metaShare, row.compareMetaShare, value => formatPercent(value), { dashWhenZero: row.current.metaSpend === 0 })}</td>
          <td>${renderMetricCell(row.metaFeeRatio, row.metaFeeRatio, row.compareMetaFeeRatio, value => formatPercent(value), { dashWhenZero: row.current.metaSpend === 0 })}</td>
        </tr>
      `).join('')}</tbody>` : `<tbody><tr><td class="empty" colspan="12">当前筛选下暂无小品类数据。</td></tr></tbody>`;
      document.getElementById('category-table').innerHTML = header + body + renderSummaryFooter(currentTotals, compareTotals);
    }

    function renderProductTable(productRows, currentTotals, compareTotals) {
      const sorted = [...productRows].sort((a, b) => b.current.gmv - a.current.gmv);

      const header = `
        <thead>
          <tr>
            <th>产品</th>
            <th>店铺 GMV</th>
            <th>GMV 占比</th>
            <th>产品访客</th>
            <th>点击率</th>
            <th>链接转化率</th>
            <th>站内广告花费</th>
            <th>站内自身占比</th>
            <th>站内费比</th>
            <th>站外广告花费</th>
            <th>站外自身占比</th>
            <th>站外费比</th>
          </tr>
        </thead>
      `;
      const body = sorted.length ? `<tbody>${sorted.map(row => {
        const gmvShare = safeDivide(row.current.gmv, currentTotals.gmv);
        const compareGmvShare = safeDivide(row.compare.gmv, compareTotals.gmv);
        const adShare = row.current.adSpend > 0 ? safeDivide(row.current.adSpend, currentTotals.adSpend) : null;
        const compareAdShare = row.compare.adSpend > 0 ? safeDivide(row.compare.adSpend, compareTotals.adSpend) : null;
        const adFeeRatio = row.current.adSpend > 0 ? safeDivide(row.current.adSpend, row.current.gmv) : null;
        const compareAdFeeRatio = row.compare.adSpend > 0 ? safeDivide(row.compare.adSpend, row.compare.gmv) : null;
        const metaShare = row.current.metaSpend > 0 ? safeDivide(row.current.metaSpend, currentTotals.metaSpend) : null;
        const compareMetaShare = row.compare.metaSpend > 0 ? safeDivide(row.compare.metaSpend, compareTotals.metaSpend) : null;
        const metaFeeRatio = row.current.metaSpend > 0 ? safeDivide(row.current.metaSpend, row.current.gmv) : null;
        const compareMetaFeeRatio = row.compare.metaSpend > 0 ? safeDivide(row.compare.metaSpend, row.compare.gmv) : null;
        return `
          <tr>
            <td>
              <div class="product-name">${row.product_name}</div>
              <div class="product-meta" title="${escapeAttr(`${row.category} · ${row.subcategory} · FB: ${row.fb_product_name} · 产品 ID: ${row.product_ids}`)}">${row.category} · ${row.subcategory} · FB: ${row.fb_product_name} · ID: ${row.product_ids}</div>
            </td>
            <td>${renderMetricCell(row.current.gmv, row.current.gmv, row.compare.gmv, formatCurrency)}</td>
            <td>${renderMetricCell(gmvShare, gmvShare, compareGmvShare, value => formatPercent(value))}</td>
            <td>${renderMetricCell(row.current.visitors, row.current.visitors, row.compare.visitors, formatNumber)}</td>
            <td>${renderMetricCell(row.current.clickRate, row.current.clickRate, row.compare.clickRate, value => formatPercent(value))}</td>
            <td>${renderMetricCell(row.current.conversion, row.current.conversion, row.compare.conversion, value => formatPercent(value))}</td>
            <td>${renderMetricCell(row.current.adSpend, row.current.adSpend, row.compare.adSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(adShare, adShare, compareAdShare, value => formatPercent(value), { dashWhenZero: row.current.adSpend === 0 })}</td>
            <td>${renderMetricCell(adFeeRatio, adFeeRatio, compareAdFeeRatio, value => formatPercent(value), { dashWhenZero: row.current.adSpend === 0 })}</td>
            <td>${renderMetricCell(row.current.metaSpend, row.current.metaSpend, row.compare.metaSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(metaShare, metaShare, compareMetaShare, value => formatPercent(value), { dashWhenZero: row.current.metaSpend === 0 })}</td>
            <td>${renderMetricCell(metaFeeRatio, metaFeeRatio, compareMetaFeeRatio, value => formatPercent(value), { dashWhenZero: row.current.metaSpend === 0 })}</td>
          </tr>
        `;
      }).join('')}</tbody>` : `<tbody><tr><td class="empty" colspan="12">当前筛选下暂无产品数据。</td></tr></tbody>`;
      document.getElementById('product-table').innerHTML = header + body + renderSummaryFooter(currentTotals, compareTotals);
    }

    function rankMap(rows, getter) {
      const sorted = [...rows].sort((a, b) => getter(b) - getter(a));
      const map = new Map();
      sorted.forEach((row, index) => map.set(row.id, index + 1));
      return map;
    }

    function rankDeltaText(currentRank, previousRank) {
      if (!previousRank && currentRank) return '新上榜';
      if (!currentRank && previousRank) return '掉榜';
      const delta = previousRank - currentRank;
      if (delta > 0) return `↑${delta}`;
      if (delta < 0) return `↓${Math.abs(delta)}`;
      return '持平';
    }

    function renderRankBlock(targetId, rows, valueText, sideText) {
      document.getElementById(targetId).innerHTML = rows.length ? rows.map((row, index) => `
        <div class="rank-item">
          <div class="rank-num">${index + 1}</div>
          <div>
            <div class="rank-name">${row.product_name}</div>
            <div class="rank-detail">${valueText(row)}</div>
          </div>
          <div class="rank-side">${sideText(row)}</div>
        </div>
      `).join('') : `<div class="empty">当前筛选下暂无可展示数据。</div>`;
    }

    function renderTopLists(productRows) {
      const currentVisitorRank = rankMap(productRows, row => row.current.visitors);
      const compareVisitorRank = rankMap(productRows, row => row.compare.visitors);
      const currentConversionRank = rankMap(productRows.filter(row => row.current.clicks >= 100), row => row.current.conversion || 0);
      const compareConversionRank = rankMap(productRows.filter(row => row.compare.clicks >= 100), row => row.compare.conversion || 0);
      const currentGmvRank = rankMap(productRows, row => row.current.gmv);
      const compareGmvRank = rankMap(productRows, row => row.compare.gmv);

      const visitorsGrowth = [...productRows]
        .map(row => ({ ...row, visitorDelta: row.current.visitors - row.compare.visitors }))
        .sort((a, b) => b.visitorDelta - a.visitorDelta)
        .slice(0, 5);

      const conversionTop = [...productRows]
        .filter(row => row.current.clicks >= 100)
        .sort((a, b) => (b.current.conversion || 0) - (a.current.conversion || 0))
        .slice(0, 5);

      const gmvTop = [...productRows]
        .sort((a, b) => b.current.gmv - a.current.gmv)
        .slice(0, 5);

      renderRankBlock(
        'top-visitors',
        visitorsGrowth,
        row => `访客 ${formatNumber(row.current.visitors)} · 增长 ${formatNumber(row.visitorDelta)}`,
        row => `排名 ${rankDeltaText(currentVisitorRank.get(row.id), compareVisitorRank.get(row.id))}`
      );

      renderRankBlock(
        'top-conversion',
        conversionTop,
        row => `转化率 ${formatPercent(row.current.conversion)} · 点击 ${formatNumber(row.current.clicks)}`,
        row => `排名 ${rankDeltaText(currentConversionRank.get(row.id), compareConversionRank.get(row.id))}`
      );

      renderRankBlock(
        'top-gmv',
        gmvTop,
        row => `GMV ${formatCurrency(row.current.gmv)} · ${row.category}`,
        row => `排名 ${rankDeltaText(currentGmvRank.get(row.id), compareGmvRank.get(row.id))}`
      );
    }

    function renderGmvSwings(productRows) {
      const enriched = productRows.map(row => ({
        ...row,
        delta: row.current.gmv - row.compare.gmv,
        deltaRatio: deltaValue(row.current.gmv, row.compare.gmv),
      }));
      const gainers = [...enriched].sort((a, b) => b.delta - a.delta).slice(0, 5);
      const decliners = [...enriched].sort((a, b) => a.delta - b.delta).slice(0, 5);

      renderRankBlock(
        'gmv-gainers',
        gainers,
        row => `GMV ${formatCurrency(row.current.gmv)} · 增长 ${formatCurrency(row.delta)}`,
        row => `${row.deltaRatio === null ? '新增' : `${row.deltaRatio > 0 ? '+' : ''}${(row.deltaRatio * 100).toFixed(1)}%`}`
      );

      renderRankBlock(
        'gmv-decliners',
        decliners,
        row => `GMV ${formatCurrency(row.current.gmv)} · 变化 ${formatCurrency(row.delta)}`,
        row => `${row.deltaRatio === null ? '-' : `${row.deltaRatio > 0 ? '+' : ''}${(row.deltaRatio * 100).toFixed(1)}%`}`
      );
    }

    function renderHeaderMeta(currentRows, compareRows) {
      const compare = compareRange();
      const updateText = (id, value) => {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
      };
      updateText('range-chip', `本期 ${state.start} → ${state.end}`);
      updateText('compare-chip', `对比 ${compare.start} → ${compare.end}`);
      updateText('data-span-chip', `数据覆盖 ${PAYLOAD.available_range.start} → ${PAYLOAD.available_range.end}`);
      updateText('rows-chip', `当前命中 ${currentRows.length.toLocaleString('zh-CN')} 条日级记录 / 对比 ${compareRows.length.toLocaleString('zh-CN')} 条`);
      updateText('mapping-chip', `Meta 花费映射：店铺 ${formatPercent(PAYLOAD.data_quality.meta_spend_to_store)} / 站内 ${formatPercent(PAYLOAD.data_quality.meta_spend_to_onsite)}`);
      updateText('compare-summary', `本期与对比区间可独立调整；“对比前移一月”会按本期日期自动生成对比窗口。`);
      updateText('last-updated', `最新更新：${PAYLOAD.generated_at || '--'}`);
    }

    function setRefreshState(label, mode = 'ok') {
      const stateNode = document.getElementById('refresh-state');
      stateNode.textContent = label;
      stateNode.classList.toggle('is-busy', mode === 'busy');
      stateNode.classList.toggle('is-error', mode === 'error');
    }

    function isLocalDashboard() {
      return window.location.protocol === 'file:' || ['127.0.0.1', 'localhost'].includes(window.location.hostname);
    }

    function refreshRequestHeaders() {
      if (isLocalDashboard()) return {};
      let refreshKey = window.sessionStorage.getItem('dashboard-refresh-key') || '';
      if (!refreshKey) {
        refreshKey = window.prompt('请输入看板刷新口令') || '';
      }
      if (!refreshKey) throw new Error('已取消刷新');
      window.sessionStorage.setItem('dashboard-refresh-key', refreshKey);
      return { 'X-Refresh-Key': refreshKey };
    }

    async function pollRefreshJob(jobId, headers) {
      for (let attempt = 0; attempt < 180; attempt += 1) {
        const response = await fetch(`${REFRESH_ENDPOINT}?job_id=${encodeURIComponent(jobId)}`, {
          cache: 'no-store',
          headers,
        });
        if (response.status === 401) window.sessionStorage.removeItem('dashboard-refresh-key');
        if (!response.ok) throw new Error(`刷新服务返回 ${response.status}`);
        const job = await response.json();
        if (job.status === 'complete') {
          window.location.reload();
          return;
        }
        if (job.status === 'error') throw new Error(job.error || '数据刷新失败');
        await new Promise(resolve => window.setTimeout(resolve, 2000));
      }
      throw new Error('刷新等待超时');
    }

    async function refreshDashboard() {
      const button = document.getElementById('refresh-data-btn');
      button.disabled = true;
      setRefreshState('正在更新', 'busy');
      try {
        const headers = refreshRequestHeaders();
        const response = await fetch(REFRESH_ENDPOINT, { method: 'POST', cache: 'no-store', headers });
        if (response.status === 401) window.sessionStorage.removeItem('dashboard-refresh-key');
        if (!response.ok) throw new Error(`刷新服务不可用（${response.status}）`);
        const job = await response.json();
        if (!job.job_id) throw new Error(job.error || '刷新服务未返回任务编号');
        await pollRefreshJob(job.job_id, headers);
      } catch (error) {
        setRefreshState('更新失败', 'error');
        const localHint = isLocalDashboard()
          ? '；本地刷新请运行 start_report_server.cmd'
          : '；请检查 GitHub Actions 与 Cloudflare 环境变量';
        document.getElementById('last-updated').textContent = `${error.message}${localHint}`;
        button.disabled = false;
      }
    }

    function filterSummary(key) {
      let total = 0;
      let selected = 0;
      if (key === 'categories') {
        total = PAYLOAD.categories.length;
        selected = state.selectedCategories.size;
      }
      if (key === 'subcategories') {
        total = PAYLOAD.subcategories.length;
        selected = state.selectedSubcategories.size;
      }
      if (key === 'products') {
        total = products.length;
        selected = state.selectedProducts.size;
      }
      if (selected === total) return `全部 ${total}`;
      return `已选 ${selected} / ${total}`;
    }

    function filterOptions(key) {
      if (key === 'categories') {
        return PAYLOAD.categories.map(value => ({ value, label: value, meta: `${products.filter(item => item.category === value).length} 个产品` }));
      }
      if (key === 'subcategories') {
        return PAYLOAD.subcategories.map(value => ({ value, label: value, meta: `${products.filter(item => item.subcategory === value).length} 个产品` }));
      }
      return products.map(item => ({
        value: item.id,
        label: item.product_name,
        meta: `${item.category} · ${item.subcategory} · FB: ${item.fb_product_name}`,
      }));
    }

    function isSelected(key, value) {
      if (key === 'categories') return state.selectedCategories.has(value);
      if (key === 'subcategories') return state.selectedSubcategories.has(value);
      return state.selectedProducts.has(value);
    }

    function toggleSelection(key, value) {
      const target = key === 'categories' ? state.selectedCategories : key === 'subcategories' ? state.selectedSubcategories : state.selectedProducts;
      if (target.has(value)) {
        target.delete(value);
      } else {
        target.add(value);
      }
      renderAll();
      renderFilters();
    }

    function fillAll(key) {
      if (key === 'categories') state.selectedCategories = new Set(PAYLOAD.categories);
      if (key === 'subcategories') state.selectedSubcategories = new Set(PAYLOAD.subcategories);
      if (key === 'products') state.selectedProducts = new Set(products.map(item => item.id));
      renderAll();
      renderFilters();
    }

    function clearAll(key) {
      if (key === 'categories') state.selectedCategories = new Set();
      if (key === 'subcategories') state.selectedSubcategories = new Set();
      if (key === 'products') state.selectedProducts = new Set();
      renderAll();
      renderFilters();
    }

    function renderFilters() {
      const configs = [
        { key: 'categories', title: '品类' },
        { key: 'subcategories', title: '小类目' },
        { key: 'products', title: '产品' },
      ];
      document.getElementById('filters-strip').innerHTML = configs.map(config => {
        const search = state.search[config.key].toLowerCase();
        const options = filterOptions(config.key).filter(option =>
          option.label.toLowerCase().includes(search) || option.meta.toLowerCase().includes(search)
        );
        return `
          <div class="filter-box ${state.openFilter === config.key ? 'open' : ''}" data-filter-box="${config.key}">
            <button class="filter-trigger" data-filter-trigger="${config.key}">
              <div>
                <span class="filter-title">${config.title}</span>
                <span class="filter-value">${filterSummary(config.key)}</span>
              </div>
              <span>▾</span>
            </button>
            <div class="filter-panel">
              <div class="filter-toolbar">
                <button data-filter-all="${config.key}">全选</button>
                <button data-filter-clear="${config.key}">清空</button>
              </div>
              <input class="filter-search" data-filter-search="${config.key}" placeholder="搜索 ${config.title}" value="${escapeAttr(state.search[config.key])}">
              <div class="filter-options">
                ${options.map(option => `
                  <div class="option-row ${isSelected(config.key, option.value) ? 'selected' : ''}" data-filter-option="${config.key}" data-filter-value="${String(option.value).replace(/"/g, '&quot;')}">
                    <div>
                      <div>${option.label}</div>
                      <div class="option-meta">${option.meta}</div>
                    </div>
                    <div>${isSelected(config.key, option.value) ? '已选' : ''}</div>
                  </div>
                `).join('') || '<div class="empty">没有匹配项。</div>'}
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    function renderAll() {
      const selectedIds = getSelectedProductIds();
      const currentRange = { start: state.start, end: state.end };
      const compare = compareRange();
      const currentRows = filterFacts(currentRange, selectedIds);
      const compareRows = filterFacts(compare, selectedIds);
      const currentTotals = aggregateFacts(currentRows);
      const compareTotals = aggregateFacts(compareRows);
      const productRows = aggregateProductRows(currentRows, compareRows);
      renderHeaderMeta(currentRows, compareRows);
      renderMetricCards(currentTotals, compareTotals);
      renderCharts(dailySeries(currentRows, compareRows));
      renderCategoryTable(currentRows, compareRows, currentTotals, compareTotals);
      renderProductTable(productRows, currentTotals, compareTotals);
      renderTopLists(productRows);
      renderGmvSwings(productRows);
    }

    function resetDefaults() {
      state.start = PAYLOAD.defaults.current.start;
      state.end = PAYLOAD.defaults.current.end;
      state.compareStart = PAYLOAD.defaults.compare.start;
      state.compareEnd = PAYLOAD.defaults.compare.end;
      document.getElementById('start-date').value = state.start;
      document.getElementById('end-date').value = state.end;
      document.getElementById('compare-start-date').value = state.compareStart;
      document.getElementById('compare-end-date').value = state.compareEnd;
      renderAll();
    }

    function autoCompareRange() {
      state.compareStart = shiftMonth(state.start, -1);
      state.compareEnd = shiftMonth(state.end, -1);
      document.getElementById('compare-start-date').value = state.compareStart;
      document.getElementById('compare-end-date').value = state.compareEnd;
      renderAll();
    }

    function syncDateInputs() {
      document.getElementById('start-date').value = state.start;
      document.getElementById('end-date').value = state.end;
      document.getElementById('compare-start-date').value = state.compareStart;
      document.getElementById('compare-end-date').value = state.compareEnd;
    }

    document.getElementById('reset-btn')?.addEventListener('click', resetDefaults);
    document.getElementById('auto-compare-btn')?.addEventListener('click', autoCompareRange);
    document.getElementById('refresh-data-btn').addEventListener('click', refreshDashboard);

    document.getElementById('start-date').addEventListener('change', event => {
      state.start = event.target.value;
      if (state.end < state.start) {
        state.end = state.start;
        document.getElementById('end-date').value = state.end;
      }
      renderAll();
    });

    document.getElementById('end-date').addEventListener('change', event => {
      state.end = event.target.value;
      if (state.end < state.start) {
        state.start = state.end;
        document.getElementById('start-date').value = state.start;
      }
      renderAll();
    });

    document.getElementById('compare-start-date').addEventListener('change', event => {
      state.compareStart = event.target.value;
      if (state.compareEnd < state.compareStart) {
        state.compareEnd = state.compareStart;
        document.getElementById('compare-end-date').value = state.compareEnd;
      }
      renderAll();
    });

    document.getElementById('compare-end-date').addEventListener('change', event => {
      state.compareEnd = event.target.value;
      if (state.compareEnd < state.compareStart) {
        state.compareStart = state.compareEnd;
        document.getElementById('compare-start-date').value = state.compareStart;
      }
      renderAll();
    });

    document.addEventListener('click', event => {
      const trigger = event.target.closest('[data-filter-trigger]');
      if (trigger) {
        const key = trigger.getAttribute('data-filter-trigger');
        state.openFilter = state.openFilter === key ? null : key;
        renderFilters();
        return;
      }

      const option = event.target.closest('[data-filter-option]');
      if (option) {
        const key = option.getAttribute('data-filter-option');
        const rawValue = option.getAttribute('data-filter-value');
        const value = rawValue;
        toggleSelection(key, value);
        return;
      }

      const selectAll = event.target.closest('[data-filter-all]');
      if (selectAll) {
        fillAll(selectAll.getAttribute('data-filter-all'));
        return;
      }

      const clear = event.target.closest('[data-filter-clear]');
      if (clear) {
        clearAll(clear.getAttribute('data-filter-clear'));
        return;
      }

      if (!event.target.closest('.filter-box')) {
        if (state.openFilter !== null) {
          state.openFilter = null;
          renderFilters();
        }
      }
    });

    document.addEventListener('input', event => {
      const search = event.target.closest('[data-filter-search]');
      if (!search) return;
      const key = search.getAttribute('data-filter-search');
      state.search[key] = search.value;
      renderFilters();
      const next = document.querySelector(`[data-filter-search="${key}"]`);
      if (next) {
        next.focus();
        next.setSelectionRange(state.search[key].length, state.search[key].length);
      }
    });

    syncDateInputs();
    renderFilters();
    renderAll();
  </script>
</body>
</html>
"""
    return html.replace("__PAYLOAD_JSON__", payload_json)


def generate_report(
    store_csv: Path | None = None,
    ad_csv: Path | None = None,
    raw_csv: Path | None = None,
) -> dict[str, str]:
    store_path = store_csv or STORE_CSV
    ad_path = ad_csv or AD_CSV
    raw_path = raw_csv or RAW_CSV
    payload = build_payload(store_path, ad_path, raw_path)
    OUTPUT_HTML.write_text(render_html(payload), encoding="utf-8")
    return {
        "output_html": str(OUTPUT_HTML),
        "generated_at": payload["generated_at"],
        "store_csv": str(store_path),
        "ad_csv": str(ad_path),
        "raw_csv": str(raw_path),
    }


def main() -> None:
    result = generate_report()
    print(result["output_html"])


if __name__ == "__main__":
    main()
