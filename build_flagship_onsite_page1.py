from __future__ import annotations

import json
import re
import unicodedata
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


SHEET_ID = "1I_Q-Rx6QklML2023EUG8U1hb4MPN8shyeTyShiXrcYY"
STORE_GID = "979789790"
AD_GID = "1711647547"
RAW_GID = "1292217820"
USD_TO_RMB = 6.9
BEIJING_TZ = timezone(timedelta(hours=8))

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


def load_meta_campaign_data(source_csv: Path, default_year: int) -> pd.DataFrame:
    required = [
        "单日",
        "花费金额 (USD)",
        "展示次数",
        "链接点击量",
        "购物次数（共享商品）",
        "购物转化价值（仅共享商品）",
        "广告形式",
        "广告目标",
        "广告类型",
        "版位",
        "拉新/再营销",
        "产品",
        "站内产品名",
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
        raise KeyError(f"Raw_data 站外投放分析缺少列: {missing}")

    meta["date"] = meta["单日"].map(lambda value: parse_source_date(value, default_year))
    meta["product_key"] = meta["站内产品名"].map(normalize_product_key)
    fallback_key = meta["product_key"].eq("")
    meta.loc[fallback_key, "product_key"] = meta.loc[fallback_key, "产品"].map(normalize_product_key)
    meta["ad_format"] = meta["广告形式"].map(lambda value: clean_text(value, "未标注"))
    meta["ad_goal"] = meta["广告目标"].map(lambda value: clean_text(value, "未标注"))
    meta["ad_structure"] = meta["ad_goal"].map(
        lambda value: "收割广告" if value == "销量" else "种草广告"
    )
    meta["ad_type"] = meta["广告类型"].map(lambda value: clean_text(value, "未标注"))
    meta["ad_type"] = meta["ad_type"].replace({"图片广告": "图文广告"})
    harvest_collab = meta["ad_structure"].eq("收割广告") & meta["ad_type"].eq("合创广告")
    seeding = meta["ad_structure"].eq("种草广告")
    meta["structure_type"] = meta["ad_type"]
    meta.loc[harvest_collab & meta["ad_format"].eq("目录"), "structure_type"] = "合创目录销量"
    meta.loc[harvest_collab & ~meta["ad_format"].eq("目录"), "structure_type"] = "合创无目录销量"
    meta.loc[seeding, "structure_type"] = "合创" + meta.loc[seeding, "ad_goal"]
    meta["placement"] = meta["版位"].map(lambda value: clean_text(value, "未标注"))
    meta["audience"] = meta["拉新/再营销"].map(lambda value: clean_text(value, "未标注"))
    meta["meta_spend"] = parse_number(meta["花费金额 (USD)"]).fillna(0.0) * USD_TO_RMB
    meta["meta_gmv"] = parse_number(meta["购物转化价值（仅共享商品）"]).fillna(0.0) * USD_TO_RMB
    meta["meta_impressions"] = parse_number(meta["展示次数"]).fillna(0.0)
    meta["meta_clicks"] = parse_number(meta["链接点击量"]).fillna(0.0)
    meta["meta_purchases"] = parse_number(meta["购物次数（共享商品）"]).fillna(0.0)
    meta["acquisition_spend"] = meta["meta_spend"].where(meta["audience"].eq("拉新"), 0.0)
    meta["remarketing_spend"] = meta["meta_spend"].where(meta["audience"].eq("再营销"), 0.0)

    meta = meta[meta["date"].notna() & meta["product_key"].ne("")].copy()
    return (
        meta.groupby(
            [
                "date",
                "product_key",
                "ad_structure",
                "ad_type",
                "structure_type",
                "placement",
                "audience",
            ],
            as_index=False,
        )
        .agg(
            meta_spend=("meta_spend", "sum"),
            meta_gmv=("meta_gmv", "sum"),
            meta_impressions=("meta_impressions", "sum"),
            meta_clicks=("meta_clicks", "sum"),
            meta_purchases=("meta_purchases", "sum"),
            acquisition_spend=("acquisition_spend", "sum"),
            remarketing_spend=("remarketing_spend", "sum"),
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
    meta_campaign_daily = load_meta_campaign_data(raw_csv, default_year)
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
    meta_campaign_rows = [
        [
            row.date.strftime("%Y-%m-%d"),
            row.product_key,
            row.ad_structure,
            row.ad_type,
            round(float(row.meta_spend), 6),
            round(float(row.meta_gmv), 6),
            round(float(row.meta_impressions), 6),
            round(float(row.meta_clicks), 6),
            round(float(row.meta_purchases), 6),
            round(float(row.acquisition_spend), 6),
            round(float(row.remarketing_spend), 6),
            row.placement,
            row.audience,
            row.structure_type,
        ]
        for row in meta_campaign_daily.itertuples()
        if available_start <= row.date <= available_end
    ]

    store_keys = set(store_daily["product_key"])
    ad_keys = set(ad_daily["product_key"])
    meta_total_spend = float(meta_daily["meta_spend"].sum())
    meta_store_spend = float(meta_daily.loc[meta_daily["product_key"].isin(store_keys), "meta_spend"].sum())
    meta_ad_spend = float(meta_daily.loc[meta_daily["product_key"].isin(ad_keys), "meta_spend"].sum())

    return {
        "generated_at": f"{datetime.now(BEIJING_TZ):%Y-%m-%d %H:%M:%S}（北京时间）",
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
        "meta_categories": sorted({product["category"] for product in products if product["has_meta"]}),
        "meta_subcategories": sorted({product["subcategory"] for product in products if product["has_meta"]}),
        "onsite_categories": sorted({product["category"] for product in products if product["has_onsite"]}),
        "onsite_subcategories": sorted({product["subcategory"] for product in products if product["has_onsite"]}),
        "meta_ad_structures": ["收割广告", "种草广告"],
        "meta_ad_types": sorted(set(meta_campaign_daily["ad_type"])),
        "products": products,
        "facts": fact_rows,
        "meta_campaign_facts": meta_campaign_rows,
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

    .dashboard-page[hidden] { display: none; }

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

    .filters-strip.meta-filters {
      grid-template-columns: repeat(5, minmax(0, 1fr));
    }

    .filters-strip.onsite-filters {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .onsite-metrics-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
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
    .top-grid,
    .swing-grid {
      display: grid;
      gap: 14px;
      margin-bottom: 18px;
    }

    .metrics-grid {
      grid-template-columns: 1fr;
    }

    .metric-group {
      padding: 14px;
      border-radius: 20px;
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(54, 39, 19, 0.08);
    }

    .metric-group + .metric-group {
      border-top: 1px dashed #9eb1c7;
    }

    .metric-group-title {
      margin: 0 0 10px 2px;
      color: #40536c;
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0.04em;
    }

    .metric-group-grid {
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 10px;
    }

    .metric-card {
      padding: 14px;
    }

    .metric-card.overview-selectable {
      cursor: pointer;
      transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
    }

    .metric-card.overview-selectable:hover {
      transform: translateY(-2px);
      border-color: rgba(39, 135, 231, 0.38);
      box-shadow: 0 12px 28px rgba(42, 69, 101, 0.12);
    }

    .metric-card.overview-active {
      border-color: #2787e7;
      box-shadow: 0 0 0 2px rgba(39, 135, 231, 0.14), 0 12px 28px rgba(42, 69, 101, 0.12);
    }

    .metric-label {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #7c6f63;
      margin-bottom: 10px;
      font-weight: 700;
    }

    .metric-value {
      font-family: "Plus Jakarta Sans", "Noto Sans SC", sans-serif;
      font-size: 24px;
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

    .interactive-overview {
      margin-bottom: 18px;
    }

    .overview-selected {
      color: #2787e7;
      font-weight: 800;
    }

    .overview-chart-wrap {
      position: relative;
      height: 360px;
    }

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

    .trend-title-value {
      margin-left: 8px;
      font-size: 14px;
      font-weight: 700;
      color: #53677f;
    }

    .trend-title-delta {
      margin-left: 5px;
      font-size: 13px;
      font-weight: 800;
    }

    .chart-wrap {
      position: relative;
      height: 185px;
      cursor: zoom-in;
    }

    .overview-chart-wrap { cursor: zoom-in; }

    .chart-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      z-index: 90;
      background: rgba(25, 39, 58, 0.42);
      backdrop-filter: blur(2px);
    }

    .chart-backdrop.is-visible { display: block; }

    .chart-wrap.chart-zoomed,
    .overview-chart-wrap.chart-zoomed {
      position: fixed;
      inset: 6vh 6vw;
      z-index: 100;
      height: 88vh;
      padding: 22px;
      border: 1px solid rgba(54, 75, 101, 0.18);
      border-radius: 18px;
      background: #ffffff;
      box-shadow: 0 24px 80px rgba(18, 35, 58, 0.28);
      cursor: zoom-out;
    }

    .chart-wrap.chart-zoomed canvas,
    .overview-chart-wrap.chart-zoomed canvas {
      width: 100% !important;
      height: 100% !important;
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
      height: 40px;
      padding: 6px 4px;
      background: rgba(246, 249, 253, 0.98);
      color: #0b2038;
      font-size: 12px;
      font-weight: 900;
      letter-spacing: 0.01em;
      white-space: nowrap;
      text-align: center;
    }

    .sortable-header {
      cursor: pointer;
      user-select: none;
    }

    .sort-header-content {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 10px;
      align-items: center;
      gap: 2px;
      min-height: 24px;
    }

    .sort-header-label {
      display: flex;
      min-height: 24px;
      align-items: center;
      justify-content: flex-end;
      line-height: 1.2;
      text-align: right;
      white-space: nowrap;
    }

    .sortable-header:first-child .sort-header-label {
      justify-content: center;
      text-align: center;
    }

    .sortable-header:hover {
      color: #ee4d2d;
      background: rgba(238, 77, 45, 0.1);
    }

    .sort-indicator {
      display: block;
      width: 10px;
      margin: 0;
      color: #8ba0b5;
      font-size: 10px;
      line-height: 1;
      text-align: center;
    }

    .sortable-header.is-sorted .sort-indicator {
      color: #244d75;
      font-weight: 900;
    }

    th:first-child,
    td:first-child {
      width: 11%;
      text-align: left;
      padding-left: 14px;
    }

    th:not(:first-child),
    td:not(:first-child) {
      width: 5.5625%;
    }

    th:nth-child(8),
    td:nth-child(8),
    th:nth-child(13),
    td:nth-child(13) {
      border-left: 1px dashed #9eb1c7;
    }

    th:nth-child(n+8):nth-child(-n+12) { background: rgba(39, 135, 231, 0.07); }
    th:nth-child(n+13):nth-child(-n+17) { background: rgba(238, 77, 45, 0.07); }

    tbody tr:hover td { background: rgba(39, 135, 231, 0.035); }

    .drill-row {
      cursor: pointer;
    }

    .drill-row:hover td:first-child .cell-main,
    .drill-row:hover .product-name {
      color: #ee4d2d;
    }

    .drill-row.is-active .row-label-pill {
      border-color: #2787e7;
      background: rgba(39, 135, 231, 0.12);
      color: #174d80;
      box-shadow: inset 0 0 0 1px rgba(39, 135, 231, 0.12);
    }

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

    .category-scroll { max-height: 760px; }
    .product-scroll { max-height: 1040px; }
    .share-scroll { max-height: 760px; }

    .share-mode-tabs,
    .meta-dimension-tabs,
    .collab-mode-tabs,
    .onsite-mode-tabs {
      display: inline-flex;
      gap: 8px;
      padding: 4px;
      border-radius: 12px;
      background: #edf3f8;
    }

    .share-mode-tab,
    .meta-dimension-tab,
    .collab-mode-tab,
    .onsite-mode-tab {
      border: 0;
      border-radius: 9px;
      padding: 8px 18px;
      background: transparent;
      color: #49627b;
      font-weight: 800;
      cursor: pointer;
    }

    .share-mode-tab.active,
    .meta-dimension-tab.active,
    .collab-mode-tab.active,
    .onsite-mode-tab.active {
      background: #176f8b;
      color: white;
      box-shadow: 0 5px 14px rgba(23, 111, 139, 0.2);
    }

    .share-table th:first-child,
    .share-table td:first-child {
      width: 12%;
    }

    .share-table th:not(:first-child),
    .share-table td:not(:first-child) {
      width: 7.333%;
    }

    .share-table th:nth-child(8),
    .share-table td:nth-child(8),
    .share-table th:nth-child(11),
    .share-table td:nth-child(11) {
      border-left: 1px dashed #9eb1c7;
    }

    .share-table th:nth-child(n+8):nth-child(-n+10) { background: rgba(39, 135, 231, 0.07); }
    .share-table th:nth-child(n+11):nth-child(-n+13) { background: rgba(238, 77, 45, 0.07); }

    .share-table th,
    .share-table td,
    .meta-dimension-table th,
    .meta-dimension-table td,
    .onsite-table th,
    .onsite-table td {
      text-align: center;
    }

    #onsite-gmv-table th:first-child,
    #onsite-gmv-table td:first-child { width: 12%; }
    #onsite-gmv-table th:not(:first-child),
    #onsite-gmv-table td:not(:first-child) { width: 9.777%; }
    #onsite-dimension-table th:first-child,
    #onsite-dimension-table td:first-child { width: 10%; }
    #onsite-dimension-table th:not(:first-child),
    #onsite-dimension-table td:not(:first-child) { width: 6.923%; }
    #onsite-gmv-table th,
    #onsite-gmv-table td,
    #onsite-dimension-table th,
    #onsite-dimension-table td { border-left: 0; }
    #onsite-gmv-table .sort-header-content,
    #onsite-dimension-table .sort-header-content {
      position: relative;
      display: flex;
      justify-content: center;
    }
    #onsite-gmv-table .sort-header-label,
    #onsite-dimension-table .sort-header-label {
      justify-content: center;
      padding: 0 11px;
      text-align: center;
    }
    #onsite-gmv-table .sort-indicator,
    #onsite-dimension-table .sort-indicator {
      position: absolute;
      right: 0;
      top: 50%;
      transform: translateY(-50%);
    }

    .meta-structure-table th:first-child,
    .meta-structure-table td:first-child { width: 10%; }
    .meta-structure-table th:nth-child(2),
    .meta-structure-table td:nth-child(2) { width: 10%; text-align: center; }
    .meta-structure-table th:not(:first-child):not(:nth-child(2)),
    .meta-structure-table td:not(:first-child):not(:nth-child(2)) { width: 8.888%; }
    .meta-structure-table th:nth-child(3),
    .meta-structure-table td:nth-child(3),
    .meta-structure-table th:nth-child(8),
    .meta-structure-table td:nth-child(8) { border-left: 1px dashed #9eb1c7; }

    .meta-structure-table .structure-group-cell {
      text-align: center;
      vertical-align: middle;
      background: #f5f8fb;
      color: #0b2038;
      font-size: 14px;
      font-weight: 900;
    }

    .meta-structure-table .subtotal-row td {
      background: #f3f7fb;
      color: #0b2038;
      font-weight: 900;
      border-top: 1px solid #c7d4e2;
    }

    .meta-structure-table th,
    .meta-structure-table td {
      text-align: center;
    }

    .meta-analysis-table th:first-child,
    .meta-analysis-table td:first-child { width: 12%; }
    .meta-analysis-table th:not(:first-child),
    .meta-analysis-table td:not(:first-child) { width: 6.769%; }
    .meta-analysis-table th:nth-child(3),
    .meta-analysis-table td:nth-child(3),
    .meta-analysis-table th:nth-child(11),
    .meta-analysis-table td:nth-child(11) { border-left: 1px dashed #9eb1c7; }
    .meta-dimension-table th:first-child,
    .meta-dimension-table td:first-child { width: 14%; }
    .meta-dimension-table th:not(:first-child),
    .meta-dimension-table td:not(:first-child) { width: 8.6%; }
    .meta-dimension-table th:nth-child(2),
    .meta-dimension-table td:nth-child(2),
    .meta-dimension-table th:nth-child(7),
    .meta-dimension-table td:nth-child(7) { border-left: 1px dashed #9eb1c7; }
    .collab-table th,
    .collab-table td { text-align: center; }
    .collab-table th:first-child,
    .collab-table td:first-child { width: 12%; }
    .collab-table th:not(:first-child),
    .collab-table td:not(:first-child) { width: 5.5%; }
    .collab-table th:nth-child(n+5):nth-child(-n+9) { background: rgba(120, 95, 206, 0.08); }
    .collab-table th:nth-child(n+10):nth-child(-n+13) { background: rgba(39, 135, 231, 0.08); }
    .collab-table th:nth-child(n+14):nth-child(-n+17) { background: rgba(238, 77, 45, 0.08); }
    .meta-table-scroll { max-height: 920px; }

    table th:first-child {
      text-align: center;
    }

    #meta-page th,
    #meta-page td {
      border-left: 0 !important;
    }

    .cell-main {
      font-weight: 700;
      color: #263a53;
      white-space: nowrap;
    }

    .row-label-pill {
      display: block;
      width: 100%;
      padding: 5px 10px;
      overflow: hidden;
      border: 1px solid #cbdbea;
      border-radius: 999px;
      background: linear-gradient(180deg, #ffffff 0%, #f5f9fd 100%);
      color: #1f3e5c;
      font-size: 13px;
      text-align: center;
      text-overflow: ellipsis;
    }

    .product-name {
      font-weight: 700;
      color: #263a53;
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
      .metric-group-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
      .hero,
      .three-col,
      .top-grid,
      .swing-grid { grid-template-columns: 1fr; }
    }

    @media (max-width: 860px) {
      .page { width: min(100vw - 16px, 1720px); }
      .date-grid,
      .filters-strip,
      .metric-group-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .hero { padding: 18px; }
      .dashboard-controls { grid-template-columns: 1fr; }
      .dashboard-controls .date-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .filters-strip.meta-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .onsite-metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .refresh-button { width: 100%; }
      .panel { padding: 16px; }
      .filter-panel { position: static; margin-top: 10px; }
      th, td { padding: 8px 4px; font-size: 10px; }
      th { font-size: 11px; }
      th:first-child, td:first-child { width: 18%; padding-left: 7px; }
      th:not(:first-child), td:not(:first-child) { width: 7.45%; }
    }
  </style>
</head>
<body>
  <div class="chart-backdrop" id="chart-backdrop" aria-hidden="true"></div>
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
        <button class="dashboard-tab active" type="button" data-dashboard-page="store">店铺分析</button>
        <button class="dashboard-tab" type="button" data-dashboard-page="meta">站外投放</button>
        <button class="dashboard-tab" type="button" data-dashboard-page="onsite">站内投放</button>
      </div>
    </section>

    <main class="dashboard-page" id="store-page">
    <section class="filters-strip" id="filters-strip"></section>

    <section class="metrics-grid" id="metrics-grid"></section>

    <section class="panel interactive-overview">
      <div class="panel-head">
        <div>
          <h2 class="panel-title">GMV 与指标联动趋势</h2>
          <div class="panel-subtitle">柱状固定展示店铺 GMV 本期/对比；点击上方指标卡可多选折线，再次点击取消。</div>
        </div>
        <div class="overview-selected" id="overview-selected">折线指标：订单数</div>
      </div>
      <div class="overview-chart-wrap" data-chart-wrap><canvas id="chart-interactive-overview"></canvas></div>
    </section>

    <section class="three-col">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">总览趋势 · 店铺侧</h2>
            <div class="panel-subtitle">对照店铺 GMV、订单、访客、点击和链接转化率，判断增长问题更偏流量还是承接。</div>
          </div>
        </div>
        <div class="trend-column">
          <div class="trend-card"><h3 data-trend-title="storeGMV">店铺 GMV</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-store-gmv"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="orders">订单数</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-orders"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="visitors">产品访客</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-visitors"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="clicks">产品点击</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-clicks"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="conversion">链接转化率</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-conversion"></canvas></div></div>
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
          <div class="trend-card"><h3 data-trend-title="adSpend">站内广告花费</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-ad-spend"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="adROI">站内广告 ROI</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-ad-roi"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="adImpressions">站内广告曝光</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-ad-impressions"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="adClicks">站内广告 Clicks</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-ad-clicks"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="adCPC">站内广告 CPC</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-ad-cpc"></canvas></div></div>
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
          <div class="trend-card"><h3 data-trend-title="metaSpend">站外广告花费</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-meta-spend"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="metaCPM">站外 CPM</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-meta-cpm"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="metaImpressions">站外展示次数</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-meta-impressions"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="metaClicks">站外链接点击量</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-meta-clicks"></canvas></div></div>
          <div class="trend-card"><h3 data-trend-title="metaCTR">站外 CTR</h3><div class="chart-wrap" data-chart-wrap><canvas id="chart-meta-ctr"></canvas></div></div>
        </div>
      </div>
    </section>

    <section class="panel table-panel">
      <div class="table-header">
        <h2 class="panel-title">小品类情况</h2>
        <div class="panel-subtitle">点击小品类可联动全局筛选；点击表头可切换升序/降序；无对应广告花费显示为 - 。</div>
      </div>
      <div class="table-wrap category-scroll"><table id="category-table"></table></div>
    </section>

    <section class="panel table-panel" style="margin-top: 18px;">
      <div class="table-header">
        <h2 class="panel-title">产品链接表现</h2>
        <div class="panel-subtitle">点击产品可联动全局筛选；点击表头可切换升序/降序；表内纵向滚动可查看全部产品。</div>
      </div>
      <div class="table-wrap product-scroll"><table id="product-table"></table></div>
    </section>

    <section class="panel table-panel" style="margin-top: 18px;">
      <div class="table-header">
        <div class="panel-head" style="margin-bottom: 8px;">
          <div>
            <h2 class="panel-title">占比拆解</h2>
            <div class="panel-subtitle">页签只切换本模块的数据维度，不改变全局筛选；全部指标均展示本期值与对比变化。</div>
          </div>
          <div class="share-mode-tabs" aria-label="占比拆解维度">
            <button class="share-mode-tab active" type="button" data-share-mode="category">品类</button>
            <button class="share-mode-tab" type="button" data-share-mode="product">产品</button>
          </div>
        </div>
      </div>
      <div class="table-wrap share-scroll"><table class="share-table" id="share-table"></table></div>
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
      店铺客单价 = 店铺 GMV / 订单数，CTR = 产品点击 / 产品访客，CVR = 订单数 / 产品点击；
      站内 ROAS = Ads GMV / Ads Spend，客单价 = Ads GMV / Order，CPC = Ads Spend / Clicks，CVR = Order / Clicks；
      Meta ROAS = 购物转化价值 / 花费，客单价 = 购物转化价值 / 购物次数，CPM = 花费 × 1000 / 展示次数，CTR = 链接点击量 / 展示次数；
      总花费 = 站内广告花费 + Meta 广告花费。
      Raw_data 的花费金额与购物转化价值在进入任何汇总前均按 6.9 换算为人民币。
    </section>
    </main>

    <main class="dashboard-page" id="meta-page" hidden>
      <section class="filters-strip meta-filters" id="meta-filters-strip"></section>

      <section class="panel table-panel">
        <div class="table-header">
          <h2 class="panel-title">广告结构汇总</h2>
          <div class="panel-subtitle">Raw_data O 列“销量”归为收割广告，其余目标归为种草广告；合创明细结合 N 列目录状态和 O 列目标分类。</div>
        </div>
        <div class="table-wrap"><table class="meta-structure-table" id="meta-structure-table"></table></div>
      </section>

      <section class="panel table-panel" style="margin-top: 18px;">
        <div class="table-header">
          <h2 class="panel-title">小品类投放分析</h2>
          <div class="panel-subtitle">点击小品类可联动站外投放分页全部模块，再次点击恢复全部；点击表头切换升序/降序。</div>
        </div>
        <div class="table-wrap meta-table-scroll"><table class="meta-analysis-table" id="meta-category-table"></table></div>
      </section>

      <section class="panel table-panel" style="margin-top: 18px;">
        <div class="table-header">
          <h2 class="panel-title">产品投放分析</h2>
          <div class="panel-subtitle">点击产品可联动站外投放分页全部模块，再次点击恢复全部；点击表头切换升序/降序。</div>
        </div>
        <div class="table-wrap meta-table-scroll"><table class="meta-analysis-table" id="meta-product-table"></table></div>
      </section>

      <section class="panel table-panel" style="margin-top: 18px;">
        <div class="table-header">
          <div class="panel-head" style="margin-bottom: 8px;">
            <div>
              <h2 class="panel-title" id="collab-analysis-title">合创数据分析 · 合创小品类</h2>
              <div class="panel-subtitle">仅统计 Raw_data R 列“合创广告”；O 列“销量”为合创收割，其余目标为合创种草。页签只切换本模块维度。</div>
            </div>
            <div class="collab-mode-tabs" aria-label="合创数据分析维度">
              <button class="collab-mode-tab active" type="button" data-collab-mode="category">合创小品类</button>
              <button class="collab-mode-tab" type="button" data-collab-mode="product">合创产品</button>
            </div>
          </div>
        </div>
        <div class="table-wrap meta-table-scroll"><table class="collab-table" id="collab-analysis-table"></table></div>
      </section>

      <section class="panel table-panel" style="margin-top: 18px;">
        <div class="table-header">
          <div class="panel-head" style="margin-bottom: 8px;">
            <div>
              <h2 class="panel-title" id="meta-dimension-title">站外维度分析 · 小品类</h2>
              <div class="panel-subtitle">页签仅切换本模块的汇总维度，不改变站外投放页的全局筛选；全部指标均展示本期值与对比变化。</div>
            </div>
            <div class="meta-dimension-tabs" aria-label="站外维度分析维度">
              <button class="meta-dimension-tab active" type="button" data-meta-dimension="subcategory">小品类</button>
              <button class="meta-dimension-tab" type="button" data-meta-dimension="product">产品</button>
              <button class="meta-dimension-tab" type="button" data-meta-dimension="type">类型</button>
              <button class="meta-dimension-tab" type="button" data-meta-dimension="structure">形式</button>
              <button class="meta-dimension-tab" type="button" data-meta-dimension="placement">版位</button>
              <button class="meta-dimension-tab" type="button" data-meta-dimension="audience">人群</button>
            </div>
          </div>
        </div>
        <div class="table-wrap meta-table-scroll"><table class="meta-dimension-table" id="meta-dimension-table"></table></div>
      </section>

      <section class="formula-note">
        站外投放口径：花费及购物转化价值先按 6.9 换算人民币；店铺 GMV 来自“旗舰店数据源”的 GMV-￥；ROI = 购物转化价值 / 花费，CPM = 花费 × 1000 / 展示，CTR = 链接点击 / 展示，CVR = 购物次数 / 链接点击，CPA = 花费 / 购物次数；
        再营销占比与拉新占比均按对应人群花费 / 站外总花费计算。
      </section>
    </main>

    <main class="dashboard-page" id="onsite-page" hidden>
      <section class="filters-strip onsite-filters" id="onsite-filters-strip"></section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">站内总览</h2>
            <div class="panel-subtitle">全部指标均来自站内广告，并跟随顶部日期与站内筛选器变化。</div>
          </div>
        </div>
        <div class="onsite-metrics-grid" id="onsite-metrics-grid"></div>
      </section>

      <section class="panel" style="margin-top: 18px;">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">GMV 占比 · 分日趋势</h2>
            <div class="panel-subtitle">柱状展示店铺 GMV 与站内广告 GMV，折线展示广告 GMV 占比。</div>
          </div>
        </div>
        <div class="overview-chart-wrap" data-chart-wrap><canvas id="chart-onsite-gmv-share"></canvas></div>
      </section>

      <section class="panel table-panel" style="margin-top: 18px;">
        <div class="table-header">
          <div class="panel-head" style="margin-bottom: 8px;">
            <div>
              <h2 class="panel-title" id="onsite-gmv-title">GMV 占比 · 小品类</h2>
              <div class="panel-subtitle">页签只切换本模块维度；全部指标跟随顶部日期及站内筛选器变化。</div>
            </div>
            <div class="onsite-mode-tabs" aria-label="站内 GMV 占比维度">
              <button class="onsite-mode-tab active" type="button" data-onsite-gmv-mode="category">小品类</button>
              <button class="onsite-mode-tab" type="button" data-onsite-gmv-mode="product">产品</button>
            </div>
          </div>
        </div>
        <div class="table-wrap meta-table-scroll"><table class="onsite-table" id="onsite-gmv-table"></table></div>
      </section>

      <section class="panel table-panel" style="margin-top: 18px;">
        <div class="table-header">
          <div class="panel-head" style="margin-bottom: 8px;">
            <div>
              <h2 class="panel-title" id="onsite-dimension-title">站内维度分析 · 小品类</h2>
              <div class="panel-subtitle">页签仅切换本模块维度，不改变站内投放页的全局筛选。</div>
            </div>
            <div class="onsite-mode-tabs" aria-label="站内维度分析维度">
              <button class="onsite-mode-tab active" type="button" data-onsite-dimension-mode="category">小品类</button>
              <button class="onsite-mode-tab" type="button" data-onsite-dimension-mode="product">产品</button>
            </div>
          </div>
        </div>
        <div class="table-wrap meta-table-scroll"><table class="onsite-table" id="onsite-dimension-table"></table></div>
      </section>

      <section class="formula-note">
        站内投放口径：订单量 = 站内广告 Order；广告 GMV 占比 = Ads GMV / 店铺 GMV；ROI = Ads GMV / Ads Spend；CPC = Ads Spend / Clicks；CTR = Clicks / Impression；CVR = Order / Clicks；CPA = Ads Spend / Order。
      </section>
    </main>
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
    const META_FACT = {
      date: 0,
      id: 1,
      structure: 2,
      type: 3,
      spend: 4,
      gmv: 5,
      impressions: 6,
      clicks: 7,
      purchases: 8,
      acquisitionSpend: 9,
      remarketingSpend: 10,
      placement: 11,
      audience: 12,
      structureType: 13,
    };

    const OVERVIEW_METRICS = {
      storeGMV: { label: '店铺 GMV', kind: 'currency' },
      orders: { label: '店铺订单数', kind: 'number' },
      storeAOV: { label: '店铺客单价', kind: 'currency' },
      visitors: { label: '产品访客', kind: 'number' },
      clicks: { label: '产品点击', kind: 'number' },
      storeCTR: { label: '店铺 CTR', kind: 'percent' },
      conversion: { label: '店铺 CVR', kind: 'percent' },
      adSpend: { label: '站内广告花费', kind: 'currency' },
      adROI: { label: '站内广告 ROAS', kind: 'ratio' },
      adAOV: { label: '站内广告客单价', kind: 'currency' },
      adCPC: { label: '站内广告 CPC', kind: 'decimal2' },
      adImpressions: { label: '站内广告曝光', kind: 'number' },
      adClicks: { label: '站内广告点击', kind: 'number' },
      adCVR: { label: '站内广告 CVR', kind: 'percent' },
      metaSpend: { label: 'Meta 广告花费', kind: 'currency' },
      metaROAS: { label: 'Meta 广告 ROAS', kind: 'ratio' },
      metaAOV: { label: 'Meta 广告客单价', kind: 'currency' },
      metaCPM: { label: 'Meta 广告 CPM', kind: 'decimal2' },
      metaImpressions: { label: 'Meta 广告曝光', kind: 'number' },
      metaClicks: { label: 'Meta 链接点击', kind: 'number' },
      metaCTR: { label: 'Meta 广告 CTR', kind: 'percent' },
    };

    const products = PAYLOAD.products;
    const facts = PAYLOAD.facts;
    const metaCampaignFacts = PAYLOAD.meta_campaign_facts;
    const productMap = new Map(products.map(item => [item.id, item]));
    const metaProducts = products.filter(item => item.has_meta);
    const onsiteProducts = products.filter(item => item.has_onsite);
    const state = {
      activePage: 'store',
      start: PAYLOAD.defaults.current.start,
      end: PAYLOAD.defaults.current.end,
      compareStart: PAYLOAD.defaults.compare.start,
      compareEnd: PAYLOAD.defaults.compare.end,
      selectedCategories: new Set(PAYLOAD.categories),
      selectedSubcategories: new Set(PAYLOAD.subcategories),
      selectedProducts: new Set(products.map(item => item.id)),
      metaSelectedCategories: new Set(PAYLOAD.meta_categories),
      metaSelectedSubcategories: new Set(PAYLOAD.meta_subcategories),
      metaSelectedProducts: new Set(metaProducts.map(item => item.id)),
      metaSelectedStructures: new Set(PAYLOAD.meta_ad_structures),
      metaSelectedTypes: new Set(PAYLOAD.meta_ad_types),
      onsiteSelectedCategories: new Set(PAYLOAD.onsite_categories),
      onsiteSelectedSubcategories: new Set(PAYLOAD.onsite_subcategories),
      onsiteSelectedProducts: new Set(onsiteProducts.map(item => item.id)),
      search: {
        categories: '',
        subcategories: '',
        products: '',
        metaCategories: '',
        metaSubcategories: '',
        metaProducts: '',
        metaStructures: '',
        metaTypes: '',
        onsiteCategories: '',
        onsiteSubcategories: '',
        onsiteProducts: '',
      },
      tableSort: {
        category: { key: 'gmv', direction: 'desc' },
        product: { key: 'gmv', direction: 'desc' },
        metaCategory: { key: 'metaSpend', direction: 'desc' },
        metaProduct: { key: 'metaSpend', direction: 'desc' },
        onsiteGmvCategory: { key: 'adGMV', direction: 'desc' },
        onsiteGmvProduct: { key: 'adGMV', direction: 'desc' },
        onsiteDimensionCategory: { key: 'adSpend', direction: 'desc' },
        onsiteDimensionProduct: { key: 'adSpend', direction: 'desc' },
      },
      overviewMetrics: new Set(['orders']),
      shareMode: 'category',
      metaDimension: 'subcategory',
      collabMode: 'category',
      onsiteGmvMode: 'category',
      onsiteDimensionMode: 'category',
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
        totalSpend: agg.adSpend + agg.metaSpend,
        averageOrderValue: safeDivide(agg.gmv, agg.orders),
        conversion: safeDivide(agg.orders, agg.clicks),
        clickRate: safeDivide(agg.clicks, agg.visitors),
        cpc: safeDivide(agg.adSpend, agg.adClicks),
        cpa: safeDivide(agg.adSpend, agg.adOrders),
        adROI: safeDivide(agg.adGMV, agg.adSpend),
        adAverageOrderValue: safeDivide(agg.adGMV, agg.adOrders),
        adCTR: safeDivide(agg.adClicks, agg.impressions),
        adCVR: safeDivide(agg.adOrders, agg.adClicks),
        metaCTR: safeDivide(agg.metaClicks, agg.metaImpressions),
        metaCVR: safeDivide(agg.metaPurchases, agg.metaClicks),
        metaROAS: safeDivide(agg.metaGMV, agg.metaSpend),
        metaAverageOrderValue: safeDivide(agg.metaGMV, agg.metaPurchases),
        metaCPM: safeDivide(agg.metaSpend * 1000, agg.metaImpressions),
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

    function createMetaAgg() {
      return {
        spend: 0,
        gmv: 0,
        impressions: 0,
        clicks: 0,
        purchases: 0,
        acquisitionSpend: 0,
        remarketingSpend: 0,
      };
    }

    function addMetaFact(target, row) {
      target.spend += row[META_FACT.spend];
      target.gmv += row[META_FACT.gmv];
      target.impressions += row[META_FACT.impressions];
      target.clicks += row[META_FACT.clicks];
      target.purchases += row[META_FACT.purchases];
      target.acquisitionSpend += row[META_FACT.acquisitionSpend];
      target.remarketingSpend += row[META_FACT.remarketingSpend];
    }

    function finalizeMetaAgg(agg) {
      return {
        ...agg,
        roi: safeDivide(agg.gmv, agg.spend),
        cpm: safeDivide(agg.spend * 1000, agg.impressions),
        ctr: safeDivide(agg.clicks, agg.impressions),
        cvr: safeDivide(agg.purchases, agg.clicks),
        cpa: safeDivide(agg.spend, agg.purchases),
        acquisitionShare: safeDivide(agg.acquisitionSpend, agg.spend),
        remarketingShare: safeDivide(agg.remarketingSpend, agg.spend),
      };
    }

    function getMetaSelectedProductIds() {
      return new Set(metaProducts.filter(product =>
        state.metaSelectedCategories.has(product.category) &&
        state.metaSelectedSubcategories.has(product.subcategory) &&
        state.metaSelectedProducts.has(product.id)
      ).map(product => product.id));
    }

    function getOnsiteSelectedProductIds() {
      return new Set(onsiteProducts.filter(product =>
        state.onsiteSelectedCategories.has(product.category) &&
        state.onsiteSelectedSubcategories.has(product.subcategory) &&
        state.onsiteSelectedProducts.has(product.id)
      ).map(product => product.id));
    }

    function filterMetaFacts(range, selectedIds) {
      return metaCampaignFacts.filter(row =>
        row[META_FACT.date] >= range.start &&
        row[META_FACT.date] <= range.end &&
        selectedIds.has(row[META_FACT.id]) &&
        state.metaSelectedStructures.has(row[META_FACT.structure]) &&
        state.metaSelectedTypes.has(row[META_FACT.type])
      );
    }

    function aggregateMetaFacts(rows) {
      const agg = createMetaAgg();
      for (const row of rows) addMetaFact(agg, row);
      return finalizeMetaAgg(agg);
    }

    function aggregateMetaBy(rows, keyGetter) {
      const map = new Map();
      for (const row of rows) {
        const key = keyGetter(row);
        if (!map.has(key)) map.set(key, createMetaAgg());
        addMetaFact(map.get(key), row);
      }
      return map;
    }

    function createMetaBuckets() {
      return {
        all: createMetaAgg(),
        image: createMetaAgg(),
        video: createMetaAgg(),
        harvestCollab: createMetaAgg(),
        seedingCollab: createMetaAgg(),
      };
    }

    function addMetaBucketFact(buckets, row) {
      addMetaFact(buckets.all, row);
      if (row[META_FACT.type] === '图文广告') addMetaFact(buckets.image, row);
      if (row[META_FACT.type] === '视频广告') addMetaFact(buckets.video, row);
      if (row[META_FACT.type] === '合创广告' && row[META_FACT.structure] === '收割广告') {
        addMetaFact(buckets.harvestCollab, row);
      }
      if (row[META_FACT.type] === '合创广告' && row[META_FACT.structure] === '种草广告') {
        addMetaFact(buckets.seedingCollab, row);
      }
    }

    function aggregateMetaBucketsBy(rows, keyGetter) {
      const map = new Map();
      for (const row of rows) {
        const key = keyGetter(row);
        if (!map.has(key)) map.set(key, createMetaBuckets());
        addMetaBucketFact(map.get(key), row);
      }
      return map;
    }

    function finalizeMetaBuckets(buckets) {
      return {
        all: finalizeMetaAgg(buckets.all),
        image: finalizeMetaAgg(buckets.image),
        video: finalizeMetaAgg(buckets.video),
        harvestCollab: finalizeMetaAgg(buckets.harvestCollab),
        seedingCollab: finalizeMetaAgg(buckets.seedingCollab),
      };
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
        storeAOVCurrent: [],
        storeAOVCompare: [],
        ordersCurrent: [],
        ordersCompare: [],
        visitorsCurrent: [],
        visitorsCompare: [],
        clicksCurrent: [],
        clicksCompare: [],
        storeCTRCurrent: [],
        storeCTRCompare: [],
        conversionCurrent: [],
        conversionCompare: [],
        adSpendCurrent: [],
        adSpendCompare: [],
        adGMVCurrent: [],
        adGMVCompare: [],
        adROICurrent: [],
        adROICompare: [],
        adAOVCurrent: [],
        adAOVCompare: [],
        adImpressionsCurrent: [],
        adImpressionsCompare: [],
        adClicksCurrent: [],
        adClicksCompare: [],
        adCPCCurrent: [],
        adCPCCompare: [],
        adCVRCurrent: [],
        adCVRCompare: [],
        metaSpendCurrent: [],
        metaSpendCompare: [],
        metaROASCurrent: [],
        metaROASCompare: [],
        metaAOVCurrent: [],
        metaAOVCompare: [],
        metaCPMCurrent: [],
        metaCPMCompare: [],
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
        result.storeAOVCurrent.push(currentDate ? currentAgg.averageOrderValue : null);
        result.storeAOVCompare.push(compareDate ? compareAgg.averageOrderValue : null);
        result.ordersCurrent.push(currentDate ? currentAgg.orders : null);
        result.ordersCompare.push(compareDate ? compareAgg.orders : null);
        result.visitorsCurrent.push(currentDate ? currentAgg.visitors : null);
        result.visitorsCompare.push(compareDate ? compareAgg.visitors : null);
        result.clicksCurrent.push(currentDate ? currentAgg.clicks : null);
        result.clicksCompare.push(compareDate ? compareAgg.clicks : null);
        result.storeCTRCurrent.push(currentDate ? currentAgg.clickRate : null);
        result.storeCTRCompare.push(compareDate ? compareAgg.clickRate : null);
        result.conversionCurrent.push(currentDate ? currentAgg.conversion : null);
        result.conversionCompare.push(compareDate ? compareAgg.conversion : null);
        result.adSpendCurrent.push(currentDate ? currentAgg.adSpend : null);
        result.adSpendCompare.push(compareDate ? compareAgg.adSpend : null);
        result.adGMVCurrent.push(currentDate ? currentAgg.adGMV : null);
        result.adGMVCompare.push(compareDate ? compareAgg.adGMV : null);
        result.adROICurrent.push(currentDate ? currentAgg.adROI : null);
        result.adROICompare.push(compareDate ? compareAgg.adROI : null);
        result.adAOVCurrent.push(currentDate ? currentAgg.adAverageOrderValue : null);
        result.adAOVCompare.push(compareDate ? compareAgg.adAverageOrderValue : null);
        result.adImpressionsCurrent.push(currentDate ? currentAgg.impressions : null);
        result.adImpressionsCompare.push(compareDate ? compareAgg.impressions : null);
        result.adClicksCurrent.push(currentDate ? currentAgg.adClicks : null);
        result.adClicksCompare.push(compareDate ? compareAgg.adClicks : null);
        result.adCPCCurrent.push(currentDate ? currentAgg.cpc : null);
        result.adCPCCompare.push(compareDate ? compareAgg.cpc : null);
        result.adCVRCurrent.push(currentDate ? currentAgg.adCVR : null);
        result.adCVRCompare.push(compareDate ? compareAgg.adCVR : null);
        result.metaSpendCurrent.push(currentDate ? currentAgg.metaSpend : null);
        result.metaSpendCompare.push(compareDate ? compareAgg.metaSpend : null);
        result.metaROASCurrent.push(currentDate ? currentAgg.metaROAS : null);
        result.metaROASCompare.push(compareDate ? compareAgg.metaROAS : null);
        result.metaAOVCurrent.push(currentDate ? currentAgg.metaAverageOrderValue : null);
        result.metaAOVCompare.push(compareDate ? compareAgg.metaAverageOrderValue : null);
        result.metaCPMCurrent.push(currentDate ? currentAgg.metaCPM : null);
        result.metaCPMCompare.push(compareDate ? compareAgg.metaCPM : null);
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
      const groups = [
        {
          title: '店铺',
          items: [
            { key: 'storeGMV', label: '店铺 GMV', value: formatCurrency(current.gmv), current: current.gmv, compare: compare.gmv },
            { key: 'orders', label: '订单数', value: formatNumber(current.orders), current: current.orders, compare: compare.orders },
            { key: 'storeAOV', label: '客单价', value: formatCurrency(current.averageOrderValue), current: current.averageOrderValue, compare: compare.averageOrderValue },
            { key: 'visitors', label: '访客', value: formatNumber(current.visitors), current: current.visitors, compare: compare.visitors },
            { key: 'clicks', label: '点击', value: formatNumber(current.clicks), current: current.clicks, compare: compare.clicks },
            { key: 'storeCTR', label: 'CTR', value: formatPercent(current.clickRate, 2), current: current.clickRate, compare: compare.clickRate },
            { key: 'conversion', label: 'CVR', value: formatPercent(current.conversion, 2), current: current.conversion, compare: compare.conversion },
          ],
        },
        {
          title: '站内广告',
          items: [
            { key: 'adSpend', label: '广告花费', value: formatCurrency(current.adSpend), current: current.adSpend, compare: compare.adSpend, dash: current.adSpend === 0 },
            { key: 'adROI', label: 'ROAS', value: formatRatio(current.adROI), current: current.adROI, compare: compare.adROI, dash: current.adSpend === 0 },
            { key: 'adAOV', label: '客单价', value: formatCurrency(current.adAverageOrderValue), current: current.adAverageOrderValue, compare: compare.adAverageOrderValue, dash: current.adSpend === 0 },
            { key: 'adCPC', label: 'CPC', value: formatNumber(current.cpc, 2), current: current.cpc, compare: compare.cpc, dash: current.adSpend === 0 },
            { key: 'adImpressions', label: '曝光', value: formatNumber(current.impressions), current: current.impressions, compare: compare.impressions, dash: current.adSpend === 0 },
            { key: 'adClicks', label: '点击', value: formatNumber(current.adClicks), current: current.adClicks, compare: compare.adClicks, dash: current.adSpend === 0 },
            { key: 'adCVR', label: 'CVR', value: formatPercent(current.adCVR, 2), current: current.adCVR, compare: compare.adCVR, dash: current.adSpend === 0 },
          ],
        },
        {
          title: 'Meta 广告',
          items: [
            { key: 'metaSpend', label: '广告花费', value: formatCurrency(current.metaSpend), current: current.metaSpend, compare: compare.metaSpend, dash: current.metaSpend === 0 },
            { key: 'metaROAS', label: 'ROAS', value: formatRatio(current.metaROAS), current: current.metaROAS, compare: compare.metaROAS, dash: current.metaSpend === 0 },
            { key: 'metaAOV', label: '客单价', value: formatCurrency(current.metaAverageOrderValue), current: current.metaAverageOrderValue, compare: compare.metaAverageOrderValue, dash: current.metaSpend === 0 },
            { key: 'metaCPM', label: 'CPM', value: formatNumber(current.metaCPM, 2), current: current.metaCPM, compare: compare.metaCPM, dash: current.metaSpend === 0 },
            { key: 'metaImpressions', label: '曝光', value: formatNumber(current.metaImpressions), current: current.metaImpressions, compare: compare.metaImpressions, dash: current.metaSpend === 0 },
            { key: 'metaClicks', label: '链接点击', value: formatNumber(current.metaClicks), current: current.metaClicks, compare: compare.metaClicks, dash: current.metaSpend === 0 },
            { key: 'metaCTR', label: 'CTR', value: formatPercent(current.metaCTR, 2), current: current.metaCTR, compare: compare.metaCTR, dash: current.metaSpend === 0 },
          ],
        },
      ];
      document.getElementById('metrics-grid').innerHTML = groups.map(group => `
        <div class="metric-group">
          <div class="metric-group-title">${group.title}</div>
          <div class="metric-group-grid">
            ${group.items.map(item => `
              <div class="metric-card overview-selectable ${state.overviewMetrics.has(item.key) ? 'overview-active' : ''}" data-overview-metric="${item.key}" title="点击选择/取消下方折线指标，可多选">
                <div class="metric-label">${item.label}</div>
                <div class="metric-value">${item.dash ? '-' : item.value}</div>
                <div class="metric-delta ${item.dash ? 'delta-flat' : deltaClass(item.current, item.compare)}">${item.dash ? '-' : deltaText(item.current, item.compare)}</div>
              </div>
            `).join('')}
          </div>
        </div>
      `).join('');
    }

    function sharedLineOptions(kind = 'currency') {
      const isPercent = kind === 'percent';
      const isRatio = kind === 'ratio';
      const isDecimal = kind === 'decimal2';
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
                if (isDecimal) return `${context.dataset.label}: ${formatNumber(value, 2)}`;
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
                if (isDecimal) return Number(value).toFixed(2);
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

    function formatOverviewChartValue(value, kind) {
      if (kind === 'percent') return formatPercent(value, 2);
      if (kind === 'ratio') return formatRatio(value);
      if (kind === 'decimal2') return formatNumber(value, 2);
      if (kind === 'number') return formatNumber(value);
      return formatCurrency(value);
    }

    function overviewAxisTick(value, kind) {
      if (kind === 'percent') return `${(Number(value) * 100).toFixed(1)}%`;
      if (kind === 'ratio') return `${Number(value).toFixed(1)}x`;
      if (kind === 'decimal2') return Number(value).toFixed(2);
      return Number(value) >= 1000 ? `${Math.round(Number(value) / 1000)}k` : formatNumber(Number(value));
    }

    function renderInteractiveOverviewChart(series) {
      const selectedKeys = Array.from(state.overviewMetrics);
      const selectedMetrics = selectedKeys.map(key => ({ key, ...OVERVIEW_METRICS[key] })).filter(item => item.label);
      const axisMetric = selectedMetrics[0] || { key: 'orders', ...OVERVIEW_METRICS.orders };
      const selectedNode = document.getElementById('overview-selected');
      selectedNode.textContent = selectedMetrics.length
        ? `折线指标：${selectedMetrics.map(item => item.label).join('、')}`
        : '折线指标：未选择';
      const lineDatasets = selectedMetrics.flatMap((metric, index) => {
        const color = `hsl(${(index * 47 + 10) % 360} 72% 46%)`;
        return [
          {
            type: 'line',
            label: `${metric.label} · 本期`,
            data: series[`${metric.key}Current`],
            yAxisID: 'yMetric',
            metricKind: metric.kind,
            borderColor: color,
            backgroundColor: color,
            pointRadius: 2,
            pointHoverRadius: 5,
            borderWidth: 2.5,
            tension: 0.3,
            order: 1,
          },
          {
            type: 'line',
            label: `${metric.label} · 对比`,
            data: series[`${metric.key}Compare`],
            yAxisID: 'yMetric',
            metricKind: metric.kind,
            borderColor: color,
            backgroundColor: color,
            pointRadius: 1.5,
            pointHoverRadius: 5,
            borderWidth: 2,
            borderDash: [7, 5],
            tension: 0.3,
            order: 2,
          },
        ];
      });
      upsertChart('chart-interactive-overview', {
        type: 'bar',
        data: {
          labels: series.labels,
          datasets: [
            {
              type: 'bar',
              label: '店铺 GMV · 本期',
              data: series.storeGMVCurrent,
              yAxisID: 'yGMV',
              metricKind: 'currency',
              backgroundColor: 'rgba(23, 111, 139, 0.9)',
              borderColor: '#176f8b',
              borderWidth: 0,
              borderRadius: 3,
              categoryPercentage: 0.72,
              barPercentage: 0.78,
              order: 3,
            },
            {
              type: 'bar',
              label: '店铺 GMV · 对比',
              data: series.storeGMVCompare,
              yAxisID: 'yGMV',
              metricKind: 'currency',
              backgroundColor: 'rgba(119, 192, 209, 0.72)',
              borderColor: '#77c0d1',
              borderWidth: 0,
              borderRadius: 3,
              categoryPercentage: 0.72,
              barPercentage: 0.78,
              order: 4,
            },
            ...lineDatasets,
          ],
        },
        options: {
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              position: 'bottom',
              labels: { usePointStyle: true, boxWidth: 9, color: '#66584d' },
            },
            tooltip: {
              callbacks: {
                label(context) {
                  const value = context.raw;
                  if (value === null || value === undefined) return `${context.dataset.label}: -`;
                  return `${context.dataset.label}: ${formatOverviewChartValue(value, context.dataset.metricKind)}`;
                },
              },
            },
          },
          scales: {
            x: {
              stacked: false,
              ticks: { color: '#718198', maxRotation: 45, minRotation: 0 },
              grid: { display: false },
            },
            yGMV: {
              type: 'linear',
              position: 'left',
              ticks: { color: '#176f8b', callback: value => overviewAxisTick(value, 'currency') },
              grid: { color: 'rgba(61, 42, 17, 0.08)' },
            },
            yMetric: {
              type: 'linear',
              position: 'right',
              ticks: { color: '#ee4d2d', callback: value => overviewAxisTick(value, axisMetric.kind) },
              grid: { drawOnChartArea: false },
            },
          },
        },
      });
    }

    function renderTrendTitles(current, compare) {
      const metrics = {
        storeGMV: { label: '店铺 GMV', kind: 'currency', current: current.gmv, compare: compare.gmv },
        orders: { label: '订单数', kind: 'number', current: current.orders, compare: compare.orders },
        visitors: { label: '产品访客', kind: 'number', current: current.visitors, compare: compare.visitors },
        clicks: { label: '产品点击', kind: 'number', current: current.clicks, compare: compare.clicks },
        conversion: { label: '链接转化率', kind: 'percent', current: current.conversion, compare: compare.conversion },
        adSpend: { label: '站内广告花费', kind: 'currency', current: current.adSpend, compare: compare.adSpend },
        adROI: { label: '站内广告 ROI', kind: 'ratio', current: current.adROI, compare: compare.adROI },
        adImpressions: { label: '站内广告曝光', kind: 'number', current: current.impressions, compare: compare.impressions },
        adClicks: { label: '站内广告 Clicks', kind: 'number', current: current.adClicks, compare: compare.adClicks },
        adCPC: { label: '站内广告 CPC', kind: 'decimal2', current: current.cpc, compare: compare.cpc },
        metaSpend: { label: '站外广告花费', kind: 'currency', current: current.metaSpend, compare: compare.metaSpend },
        metaCPM: { label: '站外 CPM', kind: 'decimal2', current: current.metaCPM, compare: compare.metaCPM },
        metaImpressions: { label: '站外展示次数', kind: 'number', current: current.metaImpressions, compare: compare.metaImpressions },
        metaClicks: { label: '站外链接点击量', kind: 'number', current: current.metaClicks, compare: compare.metaClicks },
        metaCTR: { label: '站外 CTR', kind: 'percent', current: current.metaCTR, compare: compare.metaCTR },
      };
      Object.values(metrics).forEach(metric => {
        const title = document.querySelector(`[data-trend-title="${Object.keys(metrics).find(key => metrics[key] === metric)}"]`);
        if (!title) return;
        const delta = deltaText(metric.current, metric.compare);
        title.innerHTML = `${metric.label}<span class="trend-title-value">${formatOverviewChartValue(metric.current, metric.kind)}</span><span class="trend-title-delta ${deltaClass(metric.current, metric.compare)}">${delta}</span>`;
      });
    }

    function renderCharts(series, current, compare) {
      renderTrendTitles(current, compare);
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
      upsertChart('chart-orders', { ...gmvConfig('orders'), options: sharedLineOptions('number') });
      upsertChart('chart-visitors', { ...gmvConfig('visitors'), options: sharedLineOptions('number') });
      upsertChart('chart-clicks', { ...gmvConfig('clicks'), options: sharedLineOptions('number') });
      upsertChart('chart-conversion', { ...gmvConfig('conversion'), options: sharedLineOptions('percent') });
      upsertChart('chart-ad-spend', { ...gmvConfig('adSpend'), options: sharedLineOptions('currency') });
      upsertChart('chart-ad-roi', { ...gmvConfig('adROI'), options: sharedLineOptions('ratio') });
      upsertChart('chart-ad-impressions', { ...gmvConfig('adImpressions'), options: sharedLineOptions('number') });
      upsertChart('chart-ad-clicks', { ...gmvConfig('adClicks'), options: sharedLineOptions('number') });
      upsertChart('chart-ad-cpc', { ...gmvConfig('adCPC'), options: sharedLineOptions('currency') });
      upsertChart('chart-meta-spend', { ...gmvConfig('metaSpend'), options: sharedLineOptions('currency') });
      upsertChart('chart-meta-cpm', { ...gmvConfig('metaCPM'), options: sharedLineOptions('decimal2') });
      upsertChart('chart-meta-impressions', { ...gmvConfig('metaImpressions'), options: sharedLineOptions('number') });
      upsertChart('chart-meta-clicks', { ...gmvConfig('metaClicks'), options: sharedLineOptions('number') });
      upsertChart('chart-meta-ctr', { ...gmvConfig('metaCTR'), options: sharedLineOptions('percent') });
    }

    function renderMetricCell(value, current, compare, formatter, opts = {}) {
      if (opts.forceDash || (opts.dashWhenZero && (!current || current === 0))) {
        return `<div class="cell-main">-</div><div class="cell-delta delta-flat">-</div>`;
      }
      return `
        <div class="cell-main">${formatter(value)}</div>
        <div class="cell-delta ${deltaClass(current, compare)}">${deltaText(current, compare)}</div>
      `;
    }

    function tableSortValue(row, key) {
      if (key === 'name') return row.name || row.product_name || row.subcategory || '';
      if (Object.prototype.hasOwnProperty.call(row, key)) return row[key];
      return row.current[key];
    }

    function sortTableRows(rows, tableKey) {
      const sort = state.tableSort[tableKey];
      return [...rows].sort((leftRow, rightRow) => {
        const left = tableSortValue(leftRow, sort.key);
        const right = tableSortValue(rightRow, sort.key);
        const leftMissing = left === null || left === undefined || Number.isNaN(left);
        const rightMissing = right === null || right === undefined || Number.isNaN(right);
        if (leftMissing && rightMissing) return 0;
        if (leftMissing) return 1;
        if (rightMissing) return -1;
        const comparison = typeof left === 'string'
          ? left.localeCompare(right, 'zh-CN', { numeric: true })
          : Number(left) - Number(right);
        return sort.direction === 'asc' ? comparison : -comparison;
      });
    }

    function sortableHeader(label, tableKey, sortKey) {
      const sort = state.tableSort[tableKey];
      const active = sort.key === sortKey;
      const indicator = active ? (sort.direction === 'asc' ? '↑' : '↓') : '↕';
      return `<th class="sortable-header ${active ? 'is-sorted' : ''}" data-sort-table="${tableKey}" data-sort-key="${sortKey}" title="点击切换升序/降序"><span class="sort-header-content"><span class="sort-header-label">${label}</span><span class="sort-indicator">${indicator}</span></span></th>`;
    }

    function isSubcategoryDrillActive(subcategory) {
      return state.selectedSubcategories.size === 1 && state.selectedSubcategories.has(subcategory);
    }

    function isProductDrillActive(productId) {
      return state.selectedProducts.size === 1 && state.selectedProducts.has(productId);
    }

    function isMetaSubcategoryDrillActive(subcategory) {
      return state.metaSelectedSubcategories.size === 1 && state.metaSelectedSubcategories.has(subcategory);
    }

    function isMetaProductDrillActive(productId) {
      return state.metaSelectedProducts.size === 1 && state.metaSelectedProducts.has(productId);
    }

    function isOnsiteSubcategoryDrillActive(subcategory) {
      return state.onsiteSelectedSubcategories.size === 1 && state.onsiteSelectedSubcategories.has(subcategory);
    }

    function isOnsiteProductDrillActive(productId) {
      return state.onsiteSelectedProducts.size === 1 && state.onsiteSelectedProducts.has(productId);
    }

    function renderSummaryFooter(current, compare) {
      const currentGmvShare = current.gmv > 0 ? 1 : null;
      const compareGmvShare = compare.gmv > 0 ? 1 : null;
      const noAdSpend = current.adSpend === 0;
      const noMetaSpend = current.metaSpend === 0;
      return `
        <tfoot>
          <tr>
            <td><div class="cell-main">汇总</div></td>
            <td>${renderMetricCell(current.gmv, current.gmv, compare.gmv, formatCurrency)}</td>
            <td>${renderMetricCell(currentGmvShare, currentGmvShare, compareGmvShare, value => formatPercent(value))}</td>
            <td>${renderMetricCell(current.totalSpend, current.totalSpend, compare.totalSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(current.visitors, current.visitors, compare.visitors, formatNumber)}</td>
            <td>${renderMetricCell(current.clicks, current.clicks, compare.clicks, formatNumber)}</td>
            <td>${renderMetricCell(current.conversion, current.conversion, compare.conversion, value => formatPercent(value))}</td>
            <td>${renderMetricCell(current.adSpend, current.adSpend, compare.adSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(current.impressions, current.impressions, compare.impressions, formatNumber, { forceDash: noAdSpend })}</td>
            <td>${renderMetricCell(current.adClicks, current.adClicks, compare.adClicks, formatNumber, { forceDash: noAdSpend })}</td>
            <td>${renderMetricCell(current.cpc, current.cpc, compare.cpc, value => formatNumber(value, 2), { forceDash: noAdSpend })}</td>
            <td>${renderMetricCell(current.adCVR, current.adCVR, compare.adCVR, value => formatPercent(value), { forceDash: noAdSpend })}</td>
            <td>${renderMetricCell(current.metaSpend, current.metaSpend, compare.metaSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(current.metaImpressions, current.metaImpressions, compare.metaImpressions, formatNumber, { forceDash: noMetaSpend })}</td>
            <td>${renderMetricCell(current.metaClicks, current.metaClicks, compare.metaClicks, formatNumber, { forceDash: noMetaSpend })}</td>
            <td>${renderMetricCell(current.metaCTR, current.metaCTR, compare.metaCTR, value => formatPercent(value), { forceDash: noMetaSpend })}</td>
            <td>${renderMetricCell(current.metaCPM, current.metaCPM, compare.metaCPM, value => formatNumber(value, 2), { forceDash: noMetaSpend })}</td>
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
        };
      });
      const sortedRows = sortTableRows(rows, 'category');

      const header = `
        <thead>
          <tr>
            ${sortableHeader('小品类', 'category', 'name')}
            ${sortableHeader('店铺 GMV', 'category', 'gmv')}
            ${sortableHeader('GMV 占比', 'category', 'gmvShare')}
            ${sortableHeader('总花费', 'category', 'totalSpend')}
            ${sortableHeader('访客', 'category', 'visitors')}
            ${sortableHeader('点击', 'category', 'clicks')}
            ${sortableHeader('转化率', 'category', 'conversion')}
            ${sortableHeader('站内花费', 'category', 'adSpend')}
            ${sortableHeader('站内曝光', 'category', 'impressions')}
            ${sortableHeader('站内点击', 'category', 'adClicks')}
            ${sortableHeader('站内 CPC', 'category', 'cpc')}
            ${sortableHeader('站内 CVR', 'category', 'adCVR')}
            ${sortableHeader('Meta 花费', 'category', 'metaSpend')}
            ${sortableHeader('Meta 曝光', 'category', 'metaImpressions')}
            ${sortableHeader('Meta 点击', 'category', 'metaClicks')}
            ${sortableHeader('Meta CTR', 'category', 'metaCTR')}
            ${sortableHeader('Meta CPM', 'category', 'metaCPM')}
          </tr>
        </thead>
      `;
      const body = sortedRows.length ? `<tbody>${sortedRows.map(row => `
        <tr class="drill-row ${isSubcategoryDrillActive(row.subcategory) ? 'is-active' : ''}" data-drill-subcategory="${escapeAttr(row.subcategory)}" title="点击筛选；再次点击恢复全部">
          <td><div class="cell-main row-label-pill">${row.subcategory}</div></td>
          <td>${renderMetricCell(row.current.gmv, row.current.gmv, row.compare.gmv, formatCurrency)}</td>
          <td>${renderMetricCell(row.gmvShare, row.gmvShare, row.compareGmvShare, value => formatPercent(value))}</td>
          <td>${renderMetricCell(row.current.totalSpend, row.current.totalSpend, row.compare.totalSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.current.visitors, row.current.visitors, row.compare.visitors, formatNumber)}</td>
          <td>${renderMetricCell(row.current.clicks, row.current.clicks, row.compare.clicks, formatNumber)}</td>
          <td>${renderMetricCell(row.current.conversion, row.current.conversion, row.compare.conversion, value => formatPercent(value))}</td>
          <td>${renderMetricCell(row.current.adSpend, row.current.adSpend, row.compare.adSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.current.impressions, row.current.impressions, row.compare.impressions, formatNumber, { forceDash: row.current.adSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.adClicks, row.current.adClicks, row.compare.adClicks, formatNumber, { forceDash: row.current.adSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.cpc, row.current.cpc, row.compare.cpc, value => formatNumber(value, 2), { forceDash: row.current.adSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.adCVR, row.current.adCVR, row.compare.adCVR, value => formatPercent(value), { forceDash: row.current.adSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.metaSpend, row.current.metaSpend, row.compare.metaSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.current.metaImpressions, row.current.metaImpressions, row.compare.metaImpressions, formatNumber, { forceDash: row.current.metaSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.metaClicks, row.current.metaClicks, row.compare.metaClicks, formatNumber, { forceDash: row.current.metaSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.metaCTR, row.current.metaCTR, row.compare.metaCTR, value => formatPercent(value), { forceDash: row.current.metaSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.metaCPM, row.current.metaCPM, row.compare.metaCPM, value => formatNumber(value, 2), { forceDash: row.current.metaSpend === 0 })}</td>
        </tr>
      `).join('')}</tbody>` : `<tbody><tr><td class="empty" colspan="17">当前筛选下暂无小品类数据。</td></tr></tbody>`;
      document.getElementById('category-table').innerHTML = header + body + renderSummaryFooter(currentTotals, compareTotals);
    }

    function renderProductTable(productRows, currentTotals, compareTotals) {
      const enrichedRows = productRows.map(row => ({
        ...row,
        gmvShare: safeDivide(row.current.gmv, currentTotals.gmv),
        compareGmvShare: safeDivide(row.compare.gmv, compareTotals.gmv),
      }));
      const sorted = sortTableRows(enrichedRows, 'product');

      const header = `
        <thead>
          <tr>
            ${sortableHeader('产品', 'product', 'name')}
            ${sortableHeader('店铺 GMV', 'product', 'gmv')}
            ${sortableHeader('GMV 占比', 'product', 'gmvShare')}
            ${sortableHeader('总花费', 'product', 'totalSpend')}
            ${sortableHeader('访客', 'product', 'visitors')}
            ${sortableHeader('点击', 'product', 'clicks')}
            ${sortableHeader('转化率', 'product', 'conversion')}
            ${sortableHeader('站内花费', 'product', 'adSpend')}
            ${sortableHeader('站内曝光', 'product', 'impressions')}
            ${sortableHeader('站内点击', 'product', 'adClicks')}
            ${sortableHeader('站内 CPC', 'product', 'cpc')}
            ${sortableHeader('站内 CVR', 'product', 'adCVR')}
            ${sortableHeader('Meta 花费', 'product', 'metaSpend')}
            ${sortableHeader('Meta 曝光', 'product', 'metaImpressions')}
            ${sortableHeader('Meta 点击', 'product', 'metaClicks')}
            ${sortableHeader('Meta CTR', 'product', 'metaCTR')}
            ${sortableHeader('Meta CPM', 'product', 'metaCPM')}
          </tr>
        </thead>
      `;
      const body = sorted.length ? `<tbody>${sorted.map(row => {
        return `
          <tr class="drill-row ${isProductDrillActive(row.id) ? 'is-active' : ''}" data-drill-product="${escapeAttr(row.id)}" title="点击筛选；再次点击恢复全部">
            <td>
              <div class="product-name row-label-pill" title="${escapeAttr(row.product_name)}">${row.product_name}</div>
            </td>
            <td>${renderMetricCell(row.current.gmv, row.current.gmv, row.compare.gmv, formatCurrency)}</td>
            <td>${renderMetricCell(row.gmvShare, row.gmvShare, row.compareGmvShare, value => formatPercent(value))}</td>
            <td>${renderMetricCell(row.current.totalSpend, row.current.totalSpend, row.compare.totalSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(row.current.visitors, row.current.visitors, row.compare.visitors, formatNumber)}</td>
            <td>${renderMetricCell(row.current.clicks, row.current.clicks, row.compare.clicks, formatNumber)}</td>
            <td>${renderMetricCell(row.current.conversion, row.current.conversion, row.compare.conversion, value => formatPercent(value))}</td>
            <td>${renderMetricCell(row.current.adSpend, row.current.adSpend, row.compare.adSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(row.current.impressions, row.current.impressions, row.compare.impressions, formatNumber, { forceDash: row.current.adSpend === 0 })}</td>
            <td>${renderMetricCell(row.current.adClicks, row.current.adClicks, row.compare.adClicks, formatNumber, { forceDash: row.current.adSpend === 0 })}</td>
            <td>${renderMetricCell(row.current.cpc, row.current.cpc, row.compare.cpc, value => formatNumber(value, 2), { forceDash: row.current.adSpend === 0 })}</td>
            <td>${renderMetricCell(row.current.adCVR, row.current.adCVR, row.compare.adCVR, value => formatPercent(value), { forceDash: row.current.adSpend === 0 })}</td>
            <td>${renderMetricCell(row.current.metaSpend, row.current.metaSpend, row.compare.metaSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(row.current.metaImpressions, row.current.metaImpressions, row.compare.metaImpressions, formatNumber, { forceDash: row.current.metaSpend === 0 })}</td>
            <td>${renderMetricCell(row.current.metaClicks, row.current.metaClicks, row.compare.metaClicks, formatNumber, { forceDash: row.current.metaSpend === 0 })}</td>
            <td>${renderMetricCell(row.current.metaCTR, row.current.metaCTR, row.compare.metaCTR, value => formatPercent(value), { forceDash: row.current.metaSpend === 0 })}</td>
            <td>${renderMetricCell(row.current.metaCPM, row.current.metaCPM, row.compare.metaCPM, value => formatNumber(value, 2), { forceDash: row.current.metaSpend === 0 })}</td>
          </tr>
        `;
      }).join('')}</tbody>` : `<tbody><tr><td class="empty" colspan="17">当前筛选下暂无产品数据。</td></tr></tbody>`;
      document.getElementById('product-table').innerHTML = header + body + renderSummaryFooter(currentTotals, compareTotals);
    }

    function renderShareBreakdown(currentRows, compareRows, currentTotals, compareTotals) {
      const isCategory = state.shareMode === 'category';
      const keyGetter = isCategory
        ? row => productMap.get(row[FACT.id]).subcategory
        : row => row[FACT.id];
      const currentMap = aggregateBy(currentRows, keyGetter);
      const compareMap = aggregateBy(compareRows, keyGetter);
      const keys = Array.from(new Set([...currentMap.keys(), ...compareMap.keys()]));
      const rows = keys.map(key => {
        const current = finalizeAgg(currentMap.get(key) || createAgg());
        const compare = finalizeAgg(compareMap.get(key) || createAgg());
        const product = isCategory ? null : productMap.get(key);
        return {
          name: isCategory ? key : (product?.product_name || key),
          current,
          compare,
          gmvShare: safeDivide(current.gmv, currentTotals.gmv),
          compareGmvShare: safeDivide(compare.gmv, compareTotals.gmv),
          visitorShare: safeDivide(current.visitors, currentTotals.visitors),
          compareVisitorShare: safeDivide(compare.visitors, compareTotals.visitors),
          clickShare: safeDivide(current.clicks, currentTotals.clicks),
          compareClickShare: safeDivide(compare.clicks, compareTotals.clicks),
          adShare: current.adSpend > 0 ? safeDivide(current.adSpend, currentTotals.adSpend) : null,
          compareAdShare: compare.adSpend > 0 ? safeDivide(compare.adSpend, compareTotals.adSpend) : null,
          adFeeRatio: current.adSpend > 0 ? safeDivide(current.adSpend, current.gmv) : null,
          compareAdFeeRatio: compare.adSpend > 0 ? safeDivide(compare.adSpend, compare.gmv) : null,
          metaShare: current.metaSpend > 0 ? safeDivide(current.metaSpend, currentTotals.metaSpend) : null,
          compareMetaShare: compare.metaSpend > 0 ? safeDivide(compare.metaSpend, compareTotals.metaSpend) : null,
          metaFeeRatio: current.metaSpend > 0 ? safeDivide(current.metaSpend, current.gmv) : null,
          compareMetaFeeRatio: compare.metaSpend > 0 ? safeDivide(compare.metaSpend, compare.gmv) : null,
        };
      }).sort((left, right) => right.current.gmv - left.current.gmv);

      const label = isCategory ? '小品类' : '产品';
      const header = `
        <thead>
          <tr>
            <th>${label}</th>
            <th>店铺 GMV</th>
            <th>GMV 占比</th>
            <th>访客</th>
            <th>访客占比</th>
            <th>点击</th>
            <th>点击占比</th>
            <th>站内花费</th>
            <th>站内占比</th>
            <th>站内费比</th>
            <th>Meta 花费</th>
            <th>Meta 占比</th>
            <th>站外费比</th>
          </tr>
        </thead>
      `;
      const body = rows.length ? `<tbody>${rows.map(row => `
        <tr>
          <td><div class="cell-main row-label-pill" title="${escapeAttr(row.name)}">${row.name}</div></td>
          <td>${renderMetricCell(row.current.gmv, row.current.gmv, row.compare.gmv, formatCurrency)}</td>
          <td>${renderMetricCell(row.gmvShare, row.gmvShare, row.compareGmvShare, value => formatPercent(value, 2))}</td>
          <td>${renderMetricCell(row.current.visitors, row.current.visitors, row.compare.visitors, formatNumber)}</td>
          <td>${renderMetricCell(row.visitorShare, row.visitorShare, row.compareVisitorShare, value => formatPercent(value, 2))}</td>
          <td>${renderMetricCell(row.current.clicks, row.current.clicks, row.compare.clicks, formatNumber)}</td>
          <td>${renderMetricCell(row.clickShare, row.clickShare, row.compareClickShare, value => formatPercent(value, 2))}</td>
          <td>${renderMetricCell(row.current.adSpend, row.current.adSpend, row.compare.adSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.adShare, row.adShare, row.compareAdShare, value => formatPercent(value, 2), { forceDash: row.current.adSpend === 0 })}</td>
          <td>${renderMetricCell(row.adFeeRatio, row.adFeeRatio, row.compareAdFeeRatio, value => formatPercent(value, 2), { forceDash: row.current.adSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.metaSpend, row.current.metaSpend, row.compare.metaSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.metaShare, row.metaShare, row.compareMetaShare, value => formatPercent(value, 2), { forceDash: row.current.metaSpend === 0 })}</td>
          <td>${renderMetricCell(row.metaFeeRatio, row.metaFeeRatio, row.compareMetaFeeRatio, value => formatPercent(value, 2), { forceDash: row.current.metaSpend === 0 })}</td>
        </tr>
      `).join('')}</tbody>` : `<tbody><tr><td class="empty" colspan="13">当前筛选下暂无${label}占比数据。</td></tr></tbody>`;

      const currentGmvShare = currentTotals.gmv > 0 ? 1 : null;
      const compareGmvShare = compareTotals.gmv > 0 ? 1 : null;
      const currentVisitorShare = currentTotals.visitors > 0 ? 1 : null;
      const compareVisitorShare = compareTotals.visitors > 0 ? 1 : null;
      const currentClickShare = currentTotals.clicks > 0 ? 1 : null;
      const compareClickShare = compareTotals.clicks > 0 ? 1 : null;
      const currentAdShare = currentTotals.adSpend > 0 ? 1 : null;
      const compareAdShare = compareTotals.adSpend > 0 ? 1 : null;
      const currentMetaShare = currentTotals.metaSpend > 0 ? 1 : null;
      const compareMetaShare = compareTotals.metaSpend > 0 ? 1 : null;
      const currentAdFeeRatio = currentTotals.adSpend > 0 ? safeDivide(currentTotals.adSpend, currentTotals.gmv) : null;
      const compareAdFeeRatio = compareTotals.adSpend > 0 ? safeDivide(compareTotals.adSpend, compareTotals.gmv) : null;
      const currentMetaFeeRatio = currentTotals.metaSpend > 0 ? safeDivide(currentTotals.metaSpend, currentTotals.gmv) : null;
      const compareMetaFeeRatio = compareTotals.metaSpend > 0 ? safeDivide(compareTotals.metaSpend, compareTotals.gmv) : null;
      const footer = `
        <tfoot>
          <tr>
            <td><div class="cell-main">汇总</div></td>
            <td>${renderMetricCell(currentTotals.gmv, currentTotals.gmv, compareTotals.gmv, formatCurrency)}</td>
            <td>${renderMetricCell(currentGmvShare, currentGmvShare, compareGmvShare, value => formatPercent(value, 2))}</td>
            <td>${renderMetricCell(currentTotals.visitors, currentTotals.visitors, compareTotals.visitors, formatNumber)}</td>
            <td>${renderMetricCell(currentVisitorShare, currentVisitorShare, compareVisitorShare, value => formatPercent(value, 2))}</td>
            <td>${renderMetricCell(currentTotals.clicks, currentTotals.clicks, compareTotals.clicks, formatNumber)}</td>
            <td>${renderMetricCell(currentClickShare, currentClickShare, compareClickShare, value => formatPercent(value, 2))}</td>
            <td>${renderMetricCell(currentTotals.adSpend, currentTotals.adSpend, compareTotals.adSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(currentAdShare, currentAdShare, compareAdShare, value => formatPercent(value, 2), { forceDash: currentTotals.adSpend === 0 })}</td>
            <td>${renderMetricCell(currentAdFeeRatio, currentAdFeeRatio, compareAdFeeRatio, value => formatPercent(value, 2), { forceDash: currentTotals.adSpend === 0 })}</td>
            <td>${renderMetricCell(currentTotals.metaSpend, currentTotals.metaSpend, compareTotals.metaSpend, formatCurrency, { dashWhenZero: true })}</td>
            <td>${renderMetricCell(currentMetaShare, currentMetaShare, compareMetaShare, value => formatPercent(value, 2), { forceDash: currentTotals.metaSpend === 0 })}</td>
            <td>${renderMetricCell(currentMetaFeeRatio, currentMetaFeeRatio, compareMetaFeeRatio, value => formatPercent(value, 2), { forceDash: currentTotals.metaSpend === 0 })}</td>
          </tr>
        </tfoot>
      `;
      document.querySelectorAll('[data-share-mode]').forEach(button => {
        button.classList.toggle('active', button.getAttribute('data-share-mode') === state.shareMode);
      });
      document.getElementById('share-table').innerHTML = header + body + footer;
    }

    function renderMetaStructureTable(currentRows, compareRows) {
      const currentTotals = aggregateMetaFacts(currentRows);
      const compareTotals = aggregateMetaFacts(compareRows);
      const typeOrder = new Map([
        ['图文广告', 0],
        ['视频广告', 1],
        ['混合目录', 2],
        ['合创目录销量', 3],
        ['合创无目录销量', 4],
        ['合创知名度', 5],
        ['合创流量', 6],
        ['合创流量BUG', 7],
      ]);
      const structures = ['收割广告', '种草广告'].filter(structure =>
        currentRows.some(row => row[META_FACT.structure] === structure) ||
        compareRows.some(row => row[META_FACT.structure] === structure)
      );

      function renderStructureMetricCells(current, compare, spendShare, compareSpendShare) {
        return `
          <td>${renderMetricCell(current.spend, current.spend, compare.spend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(spendShare, spendShare, compareSpendShare, value => formatPercent(value), { forceDash: current.spend === 0 })}</td>
          <td>${renderMetricCell(current.purchases, current.purchases, compare.purchases, formatNumber, { forceDash: current.spend === 0 })}</td>
          <td>${renderMetricCell(current.roi, current.roi, compare.roi, formatRatio, { forceDash: current.spend === 0 })}</td>
          <td>${renderMetricCell(current.impressions, current.impressions, compare.impressions, formatNumber, { forceDash: current.spend === 0 })}</td>
          <td>${renderMetricCell(current.clicks, current.clicks, compare.clicks, formatNumber, { forceDash: current.spend === 0 })}</td>
          <td>${renderMetricCell(current.cpm, current.cpm, compare.cpm, value => formatNumber(value, 2), { forceDash: current.spend === 0 })}</td>
          <td>${renderMetricCell(current.ctr, current.ctr, compare.ctr, value => formatPercent(value, 2), { forceDash: current.spend === 0 })}</td>
          <td>${renderMetricCell(current.cvr, current.cvr, compare.cvr, value => formatPercent(value, 2), { forceDash: current.spend === 0 })}</td>`;
      }

      const bodyRows = [];
      for (const structure of structures) {
        const currentStructureRows = currentRows.filter(row => row[META_FACT.structure] === structure);
        const compareStructureRows = compareRows.filter(row => row[META_FACT.structure] === structure);
        const currentTypeMap = aggregateMetaBy(currentStructureRows, row => row[META_FACT.structureType]);
        const compareTypeMap = aggregateMetaBy(compareStructureRows, row => row[META_FACT.structureType]);
        const types = Array.from(new Set([...currentTypeMap.keys(), ...compareTypeMap.keys()]))
          .sort((left, right) => (typeOrder.get(left) ?? 99) - (typeOrder.get(right) ?? 99));
        const rowSpan = Math.max(types.length, 1) + 1;
        types.forEach((type, index) => {
          const current = finalizeMetaAgg(currentTypeMap.get(type) || createMetaAgg());
          const compare = finalizeMetaAgg(compareTypeMap.get(type) || createMetaAgg());
          const structureCell = index === 0
            ? `<td class="structure-group-cell" rowspan="${rowSpan}">${structure}</td>`
            : '';
          bodyRows.push(`<tr>
            ${structureCell}
            <td><div class="cell-main">${type}</div></td>
            ${renderStructureMetricCells(
              current,
              compare,
              safeDivide(current.spend, currentTotals.spend),
              safeDivide(compare.spend, compareTotals.spend),
            )}
          </tr>`);
        });
        const currentSubtotal = aggregateMetaFacts(currentStructureRows);
        const compareSubtotal = aggregateMetaFacts(compareStructureRows);
        if (!types.length) {
          bodyRows.push(`<tr><td class="structure-group-cell" rowspan="2">${structure}</td><td>暂无类型</td>${renderStructureMetricCells(finalizeMetaAgg(createMetaAgg()), finalizeMetaAgg(createMetaAgg()), null, null)}</tr>`);
        }
        bodyRows.push(`<tr class="subtotal-row">
          <td><div class="cell-main">${structure}小计</div></td>
          ${renderStructureMetricCells(
            currentSubtotal,
            compareSubtotal,
            safeDivide(currentSubtotal.spend, currentTotals.spend),
            safeDivide(compareSubtotal.spend, compareTotals.spend),
          )}
        </tr>`);
      }
      const header = `
        <thead><tr>
          <th>广告形式</th><th>广告类型</th><th>花费</th><th>花费占比</th><th>订单数</th><th>ROI</th>
          <th>曝光</th><th>点击</th><th>CPM</th><th>点击率</th><th>转化率</th>
        </tr></thead>`;
      const body = bodyRows.length
        ? `<tbody>${bodyRows.join('')}</tbody>`
        : `<tbody><tr><td class="empty" colspan="11">当前筛选下暂无站外投放数据。</td></tr></tbody>`;
      const currentShare = currentTotals.spend > 0 ? 1 : null;
      const compareShare = compareTotals.spend > 0 ? 1 : null;
      const footer = `<tfoot><tr>
        <td><div class="cell-main">汇总</div></td><td><div class="cell-main">全部类型</div></td>
        <td>${renderMetricCell(currentTotals.spend, currentTotals.spend, compareTotals.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(currentShare, currentShare, compareShare, value => formatPercent(value), { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.purchases, currentTotals.purchases, compareTotals.purchases, formatNumber, { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.roi, currentTotals.roi, compareTotals.roi, formatRatio, { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.impressions, currentTotals.impressions, compareTotals.impressions, formatNumber, { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.clicks, currentTotals.clicks, compareTotals.clicks, formatNumber, { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.cpm, currentTotals.cpm, compareTotals.cpm, value => formatNumber(value, 2), { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.ctr, currentTotals.ctr, compareTotals.ctr, value => formatPercent(value, 2), { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.cvr, currentTotals.cvr, compareTotals.cvr, value => formatPercent(value, 2), { forceDash: currentTotals.spend === 0 })}</td>
      </tr></tfoot>`;
      document.getElementById('meta-structure-table').innerHTML = header + body + footer;
    }

    function buildMetaAnalysisRows(mode, currentMetaRows, compareMetaRows, currentStoreRows, compareStoreRows) {
      const isCategory = mode === 'category';
      const keyGetter = isCategory
        ? row => productMap.get(row[META_FACT.id])?.subcategory || '未标注小类目'
        : row => row[META_FACT.id];
      const storeKeyGetter = isCategory
        ? row => productMap.get(row[FACT.id])?.subcategory || '未标注小类目'
        : row => row[FACT.id];
      const currentMetaMap = aggregateMetaBucketsBy(currentMetaRows, keyGetter);
      const compareMetaMap = aggregateMetaBucketsBy(compareMetaRows, keyGetter);
      const currentStoreMap = aggregateBy(currentStoreRows, storeKeyGetter);
      const compareStoreMap = aggregateBy(compareStoreRows, storeKeyGetter);
      const keys = Array.from(new Set([...currentMetaMap.keys(), ...compareMetaMap.keys()]));
      return keys.map(key => {
        const currentBuckets = finalizeMetaBuckets(currentMetaMap.get(key) || createMetaBuckets());
        const compareBuckets = finalizeMetaBuckets(compareMetaMap.get(key) || createMetaBuckets());
        const product = isCategory ? null : productMap.get(key);
        const currentStore = finalizeAgg(currentStoreMap.get(key) || createAgg());
        const compareStore = finalizeAgg(compareStoreMap.get(key) || createAgg());
        return {
          id: key,
          subcategory: isCategory ? key : product?.subcategory,
          product_name: isCategory ? '' : (product?.product_name || key),
          current: {
            storeGMV: currentStore.gmv,
            metaSpend: currentBuckets.all.spend,
            imageSpend: currentBuckets.image.spend,
            imageROI: currentBuckets.image.roi,
            videoSpend: currentBuckets.video.spend,
            videoROI: currentBuckets.video.roi,
            harvestCollabSpend: currentBuckets.harvestCollab.spend,
            harvestCollabROI: currentBuckets.harvestCollab.roi,
            seedingCollabSpend: currentBuckets.seedingCollab.spend,
            remarketingShare: currentBuckets.all.remarketingShare,
            acquisitionShare: currentBuckets.all.acquisitionShare,
          },
          compare: {
            storeGMV: compareStore.gmv,
            metaSpend: compareBuckets.all.spend,
            imageSpend: compareBuckets.image.spend,
            imageROI: compareBuckets.image.roi,
            videoSpend: compareBuckets.video.spend,
            videoROI: compareBuckets.video.roi,
            harvestCollabSpend: compareBuckets.harvestCollab.spend,
            harvestCollabROI: compareBuckets.harvestCollab.roi,
            seedingCollabSpend: compareBuckets.seedingCollab.spend,
            remarketingShare: compareBuckets.all.remarketingShare,
            acquisitionShare: compareBuckets.all.acquisitionShare,
          },
          currentBuckets,
          compareBuckets,
        };
      });
    }

    function renderMetaAnalysisFooter(rows) {
      const currentStoreGMV = rows.reduce((sum, row) => sum + (row.current.metaSpend > 0 ? row.current.storeGMV : 0), 0);
      const compareStoreGMV = rows.reduce((sum, row) => sum + (row.compare.metaSpend > 0 ? row.compare.storeGMV : 0), 0);
      const currentBuckets = createMetaBuckets();
      const compareBuckets = createMetaBuckets();
      for (const row of rows) {
        for (const bucket of ['all', 'image', 'video', 'harvestCollab', 'seedingCollab']) {
          const current = row.currentBuckets[bucket];
          const compare = row.compareBuckets[bucket];
          for (const key of ['spend', 'gmv', 'impressions', 'clicks', 'purchases', 'acquisitionSpend', 'remarketingSpend']) {
            currentBuckets[bucket][key] += current[key];
            compareBuckets[bucket][key] += compare[key];
          }
        }
      }
      const current = finalizeMetaBuckets(currentBuckets);
      const compare = finalizeMetaBuckets(compareBuckets);
      const currentGmvShare = currentStoreGMV > 0 ? 1 : null;
      const compareGmvShare = compareStoreGMV > 0 ? 1 : null;
      const currentSpendShare = current.all.spend > 0 ? 1 : null;
      const compareSpendShare = compare.all.spend > 0 ? 1 : null;
      return `<tfoot><tr>
        <td><div class="cell-main">汇总</div></td>
        <td>${renderMetricCell(currentStoreGMV, currentStoreGMV, compareStoreGMV, formatCurrency)}</td>
        <td>${renderMetricCell(currentGmvShare, currentGmvShare, compareGmvShare, value => formatPercent(value))}</td>
        <td>${renderMetricCell(current.all.spend, current.all.spend, compare.all.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(currentSpendShare, currentSpendShare, compareSpendShare, value => formatPercent(value), { forceDash: current.all.spend === 0 })}</td>
        <td>${renderMetricCell(current.image.spend, current.image.spend, compare.image.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(current.image.roi, current.image.roi, compare.image.roi, formatRatio, { forceDash: current.image.spend === 0 })}</td>
        <td>${renderMetricCell(current.video.spend, current.video.spend, compare.video.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(current.video.roi, current.video.roi, compare.video.roi, formatRatio, { forceDash: current.video.spend === 0 })}</td>
        <td>${renderMetricCell(current.harvestCollab.spend, current.harvestCollab.spend, compare.harvestCollab.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(current.harvestCollab.roi, current.harvestCollab.roi, compare.harvestCollab.roi, formatRatio, { forceDash: current.harvestCollab.spend === 0 })}</td>
        <td>${renderMetricCell(current.seedingCollab.spend, current.seedingCollab.spend, compare.seedingCollab.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(current.all.remarketingShare, current.all.remarketingShare, compare.all.remarketingShare, value => formatPercent(value), { forceDash: current.all.spend === 0 })}</td>
        <td>${renderMetricCell(current.all.acquisitionShare, current.all.acquisitionShare, compare.all.acquisitionShare, value => formatPercent(value), { forceDash: current.all.spend === 0 })}</td>
      </tr></tfoot>`;
    }

    function renderMetaAnalysisTable(mode, rows) {
      const tableKey = mode === 'category' ? 'metaCategory' : 'metaProduct';
      const tableId = mode === 'category' ? 'meta-category-table' : 'meta-product-table';
      const label = mode === 'category' ? '小品类' : '产品';
      const displayRows = rows.filter(row => row.current.metaSpend > 0);
      const currentStoreGmvTotal = displayRows.reduce((sum, row) => sum + row.current.storeGMV, 0);
      const compareStoreGmvTotal = rows.reduce((sum, row) => sum + (row.compare.metaSpend > 0 ? row.compare.storeGMV : 0), 0);
      const currentMetaSpendTotal = rows.reduce((sum, row) => sum + row.current.metaSpend, 0);
      const compareMetaSpendTotal = rows.reduce((sum, row) => sum + row.compare.metaSpend, 0);
      const enrichedRows = rows.map(row => ({
        ...row,
        gmvShare: safeDivide(row.current.storeGMV, currentStoreGmvTotal),
        compareGmvShare: safeDivide(row.compare.storeGMV, compareStoreGmvTotal),
        metaSpendShare: safeDivide(row.current.metaSpend, currentMetaSpendTotal),
        compareMetaSpendShare: safeDivide(row.compare.metaSpend, compareMetaSpendTotal),
      }));
      const sortedRows = sortTableRows(enrichedRows.filter(row => row.current.metaSpend > 0), tableKey);
      const header = `<thead><tr>
        ${sortableHeader(label, tableKey, 'name')}
        ${sortableHeader('店铺 GMV', tableKey, 'storeGMV')}
        ${sortableHeader('GMV 占比', tableKey, 'gmvShare')}
        ${sortableHeader('站外花费', tableKey, 'metaSpend')}
        ${sortableHeader('花费占比', tableKey, 'metaSpendShare')}
        ${sortableHeader('图文花费', tableKey, 'imageSpend')}
        ${sortableHeader('图文 ROI', tableKey, 'imageROI')}
        ${sortableHeader('视频花费', tableKey, 'videoSpend')}
        ${sortableHeader('视频 ROI', tableKey, 'videoROI')}
        ${sortableHeader('合创收割花费', tableKey, 'harvestCollabSpend')}
        ${sortableHeader('合创收割 ROI', tableKey, 'harvestCollabROI')}
        ${sortableHeader('合创种草花费', tableKey, 'seedingCollabSpend')}
        ${sortableHeader('再营销占比', tableKey, 'remarketingShare')}
        ${sortableHeader('拉新占比', tableKey, 'acquisitionShare')}
      </tr></thead>`;
      const body = sortedRows.length ? `<tbody>${sortedRows.map(row => {
        const rowName = mode === 'category' ? row.subcategory : row.product_name;
        const drillAttribute = mode === 'category'
          ? `data-meta-drill-subcategory="${escapeAttr(row.subcategory)}"`
          : `data-meta-drill-product="${escapeAttr(row.id)}"`;
        const active = mode === 'category' ? isMetaSubcategoryDrillActive(row.subcategory) : isMetaProductDrillActive(row.id);
        return `<tr class="drill-row ${active ? 'is-active' : ''}" ${drillAttribute} title="点击筛选；再次点击恢复全部">
          <td><div class="cell-main row-label-pill" title="${escapeAttr(rowName)}">${rowName}</div></td>
          <td>${renderMetricCell(row.current.storeGMV, row.current.storeGMV, row.compare.storeGMV, formatCurrency)}</td>
          <td>${renderMetricCell(row.gmvShare, row.gmvShare, row.compareGmvShare, value => formatPercent(value))}</td>
          <td>${renderMetricCell(row.current.metaSpend, row.current.metaSpend, row.compare.metaSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.metaSpendShare, row.metaSpendShare, row.compareMetaSpendShare, value => formatPercent(value), { forceDash: row.current.metaSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.imageSpend, row.current.imageSpend, row.compare.imageSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.current.imageROI, row.current.imageROI, row.compare.imageROI, formatRatio, { forceDash: row.current.imageSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.videoSpend, row.current.videoSpend, row.compare.videoSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.current.videoROI, row.current.videoROI, row.compare.videoROI, formatRatio, { forceDash: row.current.videoSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.harvestCollabSpend, row.current.harvestCollabSpend, row.compare.harvestCollabSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.current.harvestCollabROI, row.current.harvestCollabROI, row.compare.harvestCollabROI, formatRatio, { forceDash: row.current.harvestCollabSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.seedingCollabSpend, row.current.seedingCollabSpend, row.compare.seedingCollabSpend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.current.remarketingShare, row.current.remarketingShare, row.compare.remarketingShare, value => formatPercent(value), { forceDash: row.current.metaSpend === 0 })}</td>
          <td>${renderMetricCell(row.current.acquisitionShare, row.current.acquisitionShare, row.compare.acquisitionShare, value => formatPercent(value), { forceDash: row.current.metaSpend === 0 })}</td>
        </tr>`;
      }).join('')}</tbody>` : `<tbody><tr><td class="empty" colspan="14">当前筛选下暂无${label}投放数据。</td></tr></tbody>`;
      document.getElementById(tableId).innerHTML = header + body + renderMetaAnalysisFooter(rows);
    }

    function buildCollabAnalysisRows(mode, currentMetaRows, compareMetaRows, currentStoreRows, compareStoreRows) {
      const isCategory = mode === 'category';
      const currentCollabRows = currentMetaRows.filter(row => row[META_FACT.type] === '合创广告');
      const compareCollabRows = compareMetaRows.filter(row => row[META_FACT.type] === '合创广告');
      const metaKeyGetter = isCategory
        ? row => productMap.get(row[META_FACT.id])?.subcategory || '未标注小类目'
        : row => row[META_FACT.id];
      const storeKeyGetter = isCategory
        ? row => productMap.get(row[FACT.id])?.subcategory || '未标注小类目'
        : row => row[FACT.id];
      const currentMetaMap = aggregateMetaBucketsBy(currentCollabRows, metaKeyGetter);
      const compareMetaMap = aggregateMetaBucketsBy(compareCollabRows, metaKeyGetter);
      const currentStoreMap = aggregateBy(currentStoreRows, storeKeyGetter);
      const compareStoreMap = aggregateBy(compareStoreRows, storeKeyGetter);
      const keys = Array.from(new Set([...currentMetaMap.keys(), ...compareMetaMap.keys()]));
      return keys.map(key => {
        const currentBuckets = finalizeMetaBuckets(currentMetaMap.get(key) || createMetaBuckets());
        const compareBuckets = finalizeMetaBuckets(compareMetaMap.get(key) || createMetaBuckets());
        const currentStore = finalizeAgg(currentStoreMap.get(key) || createAgg());
        const compareStore = finalizeAgg(compareStoreMap.get(key) || createAgg());
        const product = isCategory ? null : productMap.get(key);
        return {
          id: key,
          name: isCategory ? key : (product?.product_name || key),
          currentStore,
          compareStore,
          currentBuckets,
          compareBuckets,
        };
      }).filter(row => row.currentBuckets.all.spend > 0);
    }

    function renderCollabAnalysis(currentMetaRows, compareMetaRows, currentStoreRows, compareStoreRows) {
      const mode = state.collabMode;
      const label = mode === 'category' ? '小品类' : '产品';
      const tabLabel = mode === 'category' ? '合创小品类' : '合创产品';
      const rows = buildCollabAnalysisRows(mode, currentMetaRows, compareMetaRows, currentStoreRows, compareStoreRows);
      const currentCollabRows = currentMetaRows.filter(row => row[META_FACT.type] === '合创广告');
      const compareCollabRows = compareMetaRows.filter(row => row[META_FACT.type] === '合创广告');
      const currentAll = aggregateMetaFacts(currentCollabRows);
      const compareAll = aggregateMetaFacts(compareCollabRows);
      const currentSeeding = aggregateMetaFacts(currentCollabRows.filter(row => row[META_FACT.structure] === '种草广告'));
      const compareSeeding = aggregateMetaFacts(compareCollabRows.filter(row => row[META_FACT.structure] === '种草广告'));
      const currentHarvest = aggregateMetaFacts(currentCollabRows.filter(row => row[META_FACT.structure] === '收割广告'));
      const compareHarvest = aggregateMetaFacts(compareCollabRows.filter(row => row[META_FACT.structure] === '收割广告'));
      const collabKeyGetter = mode === 'category'
        ? row => productMap.get(row[META_FACT.id])?.subcategory || '未标注小类目'
        : row => row[META_FACT.id];
      const storeKeyGetter = mode === 'category'
        ? row => productMap.get(row[FACT.id])?.subcategory || '未标注小类目'
        : row => row[FACT.id];
      const currentMetaMap = aggregateMetaBy(currentCollabRows, collabKeyGetter);
      const compareMetaMap = aggregateMetaBy(compareCollabRows, collabKeyGetter);
      const currentStoreMap = aggregateBy(currentStoreRows, storeKeyGetter);
      const compareStoreMap = aggregateBy(compareStoreRows, storeKeyGetter);
      const sumStoreForCollabKeys = (metaMap, storeMap) => {
        const total = { gmv: 0, visitors: 0, clicks: 0 };
        for (const [key, metaAgg] of metaMap.entries()) {
          if (metaAgg.spend <= 0) continue;
          const storeAgg = storeMap.get(key);
          if (!storeAgg) continue;
          total.gmv += storeAgg.gmv;
          total.visitors += storeAgg.visitors;
          total.clicks += storeAgg.clicks;
        }
        return total;
      };
      const currentStore = sumStoreForCollabKeys(currentMetaMap, currentStoreMap);
      const compareStore = sumStoreForCollabKeys(compareMetaMap, compareStoreMap);
      const enrichedRows = rows.map(row => ({
        ...row,
        allShare: safeDivide(row.currentBuckets.all.spend, currentAll.spend),
        compareAllShare: safeDivide(row.compareBuckets.all.spend, compareAll.spend),
        seedingShare: safeDivide(row.currentBuckets.seedingCollab.spend, currentSeeding.spend),
        compareSeedingShare: safeDivide(row.compareBuckets.seedingCollab.spend, compareSeeding.spend),
        harvestShare: safeDivide(row.currentBuckets.harvestCollab.spend, currentHarvest.spend),
        compareHarvestShare: safeDivide(row.compareBuckets.harvestCollab.spend, compareHarvest.spend),
      })).sort((left, right) => right.currentBuckets.all.spend - left.currentBuckets.all.spend);

      const header = `<thead><tr>
        <th>${label}</th>
        <th>店铺 GMV</th><th>店铺访客</th><th>店铺点击</th>
        <th>合创广告花费</th><th>花费占比</th><th>合创曝光</th><th>合创点击</th><th>合创 CPM</th>
        <th>合创种草花费</th><th>种草占比</th><th>种草曝光</th><th>种草 ROI</th>
        <th>合创收割花费</th><th>收割占比</th><th>收割订单数</th><th>收割 ROI</th>
      </tr></thead>`;
      const body = enrichedRows.length ? `<tbody>${enrichedRows.map(row => `
        <tr>
          <td><div class="cell-main row-label-pill" title="${escapeAttr(row.name)}">${row.name}</div></td>
          <td>${renderMetricCell(row.currentStore.gmv, row.currentStore.gmv, row.compareStore.gmv, formatCurrency)}</td>
          <td>${renderMetricCell(row.currentStore.visitors, row.currentStore.visitors, row.compareStore.visitors, formatNumber)}</td>
          <td>${renderMetricCell(row.currentStore.clicks, row.currentStore.clicks, row.compareStore.clicks, formatNumber)}</td>
          <td>${renderMetricCell(row.currentBuckets.all.spend, row.currentBuckets.all.spend, row.compareBuckets.all.spend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.allShare, row.allShare, row.compareAllShare, value => formatPercent(value), { forceDash: row.currentBuckets.all.spend === 0 })}</td>
          <td>${renderMetricCell(row.currentBuckets.all.impressions, row.currentBuckets.all.impressions, row.compareBuckets.all.impressions, formatNumber, { forceDash: row.currentBuckets.all.spend === 0 })}</td>
          <td>${renderMetricCell(row.currentBuckets.all.clicks, row.currentBuckets.all.clicks, row.compareBuckets.all.clicks, formatNumber, { forceDash: row.currentBuckets.all.spend === 0 })}</td>
          <td>${renderMetricCell(row.currentBuckets.all.cpm, row.currentBuckets.all.cpm, row.compareBuckets.all.cpm, value => formatNumber(value, 2), { forceDash: row.currentBuckets.all.spend === 0 })}</td>
          <td>${renderMetricCell(row.currentBuckets.seedingCollab.spend, row.currentBuckets.seedingCollab.spend, row.compareBuckets.seedingCollab.spend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.seedingShare, row.seedingShare, row.compareSeedingShare, value => formatPercent(value), { forceDash: row.currentBuckets.seedingCollab.spend === 0 })}</td>
          <td>${renderMetricCell(row.currentBuckets.seedingCollab.impressions, row.currentBuckets.seedingCollab.impressions, row.compareBuckets.seedingCollab.impressions, formatNumber, { forceDash: row.currentBuckets.seedingCollab.spend === 0 })}</td>
          <td>${renderMetricCell(row.currentBuckets.seedingCollab.roi, row.currentBuckets.seedingCollab.roi, row.compareBuckets.seedingCollab.roi, formatRatio, { forceDash: row.currentBuckets.seedingCollab.spend === 0 })}</td>
          <td>${renderMetricCell(row.currentBuckets.harvestCollab.spend, row.currentBuckets.harvestCollab.spend, row.compareBuckets.harvestCollab.spend, formatCurrency, { dashWhenZero: true })}</td>
          <td>${renderMetricCell(row.harvestShare, row.harvestShare, row.compareHarvestShare, value => formatPercent(value), { forceDash: row.currentBuckets.harvestCollab.spend === 0 })}</td>
          <td>${renderMetricCell(row.currentBuckets.harvestCollab.purchases, row.currentBuckets.harvestCollab.purchases, row.compareBuckets.harvestCollab.purchases, formatNumber, { forceDash: row.currentBuckets.harvestCollab.spend === 0 })}</td>
          <td>${renderMetricCell(row.currentBuckets.harvestCollab.roi, row.currentBuckets.harvestCollab.roi, row.compareBuckets.harvestCollab.roi, formatRatio, { forceDash: row.currentBuckets.harvestCollab.spend === 0 })}</td>
        </tr>`).join('')}</tbody>` : `<tbody><tr><td class="empty" colspan="17">当前筛选下暂无${tabLabel}数据。</td></tr></tbody>`;

      const currentAllShare = currentAll.spend > 0 ? 1 : null;
      const compareAllShare = compareAll.spend > 0 ? 1 : null;
      const currentSeedingShare = currentSeeding.spend > 0 ? 1 : null;
      const compareSeedingShare = compareSeeding.spend > 0 ? 1 : null;
      const currentHarvestShare = currentHarvest.spend > 0 ? 1 : null;
      const compareHarvestShare = compareHarvest.spend > 0 ? 1 : null;
      const footer = `<tfoot><tr>
        <td><div class="cell-main">汇总</div></td>
        <td>${renderMetricCell(currentStore.gmv, currentStore.gmv, compareStore.gmv, formatCurrency)}</td>
        <td>${renderMetricCell(currentStore.visitors, currentStore.visitors, compareStore.visitors, formatNumber)}</td>
        <td>${renderMetricCell(currentStore.clicks, currentStore.clicks, compareStore.clicks, formatNumber)}</td>
        <td>${renderMetricCell(currentAll.spend, currentAll.spend, compareAll.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(currentAllShare, currentAllShare, compareAllShare, value => formatPercent(value), { forceDash: currentAll.spend === 0 })}</td>
        <td>${renderMetricCell(currentAll.impressions, currentAll.impressions, compareAll.impressions, formatNumber, { forceDash: currentAll.spend === 0 })}</td>
        <td>${renderMetricCell(currentAll.clicks, currentAll.clicks, compareAll.clicks, formatNumber, { forceDash: currentAll.spend === 0 })}</td>
        <td>${renderMetricCell(currentAll.cpm, currentAll.cpm, compareAll.cpm, value => formatNumber(value, 2), { forceDash: currentAll.spend === 0 })}</td>
        <td>${renderMetricCell(currentSeeding.spend, currentSeeding.spend, compareSeeding.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(currentSeedingShare, currentSeedingShare, compareSeedingShare, value => formatPercent(value), { forceDash: currentSeeding.spend === 0 })}</td>
        <td>${renderMetricCell(currentSeeding.impressions, currentSeeding.impressions, compareSeeding.impressions, formatNumber, { forceDash: currentSeeding.spend === 0 })}</td>
        <td>${renderMetricCell(currentSeeding.roi, currentSeeding.roi, compareSeeding.roi, formatRatio, { forceDash: currentSeeding.spend === 0 })}</td>
        <td>${renderMetricCell(currentHarvest.spend, currentHarvest.spend, compareHarvest.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(currentHarvestShare, currentHarvestShare, compareHarvestShare, value => formatPercent(value), { forceDash: currentHarvest.spend === 0 })}</td>
        <td>${renderMetricCell(currentHarvest.purchases, currentHarvest.purchases, compareHarvest.purchases, formatNumber, { forceDash: currentHarvest.spend === 0 })}</td>
        <td>${renderMetricCell(currentHarvest.roi, currentHarvest.roi, compareHarvest.roi, formatRatio, { forceDash: currentHarvest.spend === 0 })}</td>
      </tr></tfoot>`;

      document.querySelectorAll('[data-collab-mode]').forEach(button => {
        button.classList.toggle('active', button.getAttribute('data-collab-mode') === mode);
      });
      document.getElementById('collab-analysis-title').textContent = `合创数据分析 · ${tabLabel}`;
      document.getElementById('collab-analysis-table').innerHTML = header + body + footer;
    }

    function renderMetaDimension(currentRows, compareRows) {
      const configs = {
        subcategory: {
          label: '小品类',
          key: row => productMap.get(row[META_FACT.id])?.subcategory || '未标注小类目',
          display: key => key,
        },
        product: {
          label: '产品',
          key: row => row[META_FACT.id],
          display: key => productMap.get(key)?.product_name || key,
        },
        type: { label: '类型', key: row => row[META_FACT.type], display: key => key },
        structure: { label: '形式', key: row => row[META_FACT.structure], display: key => key },
        placement: { label: '版位', key: row => row[META_FACT.placement], display: key => key },
        audience: { label: '人群', key: row => row[META_FACT.audience], display: key => key },
      };
      const config = configs[state.metaDimension];
      const currentMap = aggregateMetaBy(currentRows, config.key);
      const compareMap = aggregateMetaBy(compareRows, config.key);
      const currentTotals = aggregateMetaFacts(currentRows);
      const compareTotals = aggregateMetaFacts(compareRows);
      const keys = Array.from(new Set([...currentMap.keys(), ...compareMap.keys()]));
      const rows = keys.map(key => {
        const current = finalizeMetaAgg(currentMap.get(key) || createMetaAgg());
        const compare = finalizeMetaAgg(compareMap.get(key) || createMetaAgg());
        return {
          key,
          name: config.display(key),
          current,
          compare,
          spendShare: safeDivide(current.spend, currentTotals.spend),
          compareSpendShare: safeDivide(compare.spend, compareTotals.spend),
        };
      }).filter(row => !['subcategory', 'product'].includes(state.metaDimension) || row.current.spend > 0)
        .sort((left, right) => right.current.spend - left.current.spend || left.name.localeCompare(right.name, 'zh-CN'));
      const header = `<thead><tr>
        <th>${config.label}</th><th>花费</th><th>花费占比</th><th>订单数</th><th>ROI</th>
        <th>曝光</th><th>点击</th><th>CPM</th><th>CTR</th><th>CVR</th><th>CPA</th>
      </tr></thead>`;
      const body = rows.length ? `<tbody>${rows.map(row => `<tr>
        <td><div class="cell-main row-label-pill" title="${escapeAttr(row.name)}">${row.name}</div></td>
        <td>${renderMetricCell(row.current.spend, row.current.spend, row.compare.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(row.spendShare, row.spendShare, row.compareSpendShare, value => formatPercent(value), { forceDash: row.current.spend === 0 })}</td>
        <td>${renderMetricCell(row.current.purchases, row.current.purchases, row.compare.purchases, formatNumber, { forceDash: row.current.spend === 0 })}</td>
        <td>${renderMetricCell(row.current.roi, row.current.roi, row.compare.roi, formatRatio, { forceDash: row.current.spend === 0 })}</td>
        <td>${renderMetricCell(row.current.impressions, row.current.impressions, row.compare.impressions, formatNumber, { forceDash: row.current.spend === 0 })}</td>
        <td>${renderMetricCell(row.current.clicks, row.current.clicks, row.compare.clicks, formatNumber, { forceDash: row.current.spend === 0 })}</td>
        <td>${renderMetricCell(row.current.cpm, row.current.cpm, row.compare.cpm, value => formatNumber(value, 2), { forceDash: row.current.spend === 0 })}</td>
        <td>${renderMetricCell(row.current.ctr, row.current.ctr, row.compare.ctr, value => formatPercent(value, 2), { forceDash: row.current.spend === 0 })}</td>
        <td>${renderMetricCell(row.current.cvr, row.current.cvr, row.compare.cvr, value => formatPercent(value, 2), { forceDash: row.current.spend === 0 })}</td>
        <td>${renderMetricCell(row.current.cpa, row.current.cpa, row.compare.cpa, value => formatNumber(value, 2), { forceDash: row.current.spend === 0 })}</td>
      </tr>`).join('')}</tbody>` : `<tbody><tr><td class="empty" colspan="11">当前筛选下暂无${config.label}数据。</td></tr></tbody>`;
      const currentShare = currentTotals.spend > 0 ? 1 : null;
      const compareShare = compareTotals.spend > 0 ? 1 : null;
      const footer = `<tfoot><tr>
        <td><div class="cell-main">汇总</div></td>
        <td>${renderMetricCell(currentTotals.spend, currentTotals.spend, compareTotals.spend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(currentShare, currentShare, compareShare, value => formatPercent(value), { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.purchases, currentTotals.purchases, compareTotals.purchases, formatNumber, { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.roi, currentTotals.roi, compareTotals.roi, formatRatio, { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.impressions, currentTotals.impressions, compareTotals.impressions, formatNumber, { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.clicks, currentTotals.clicks, compareTotals.clicks, formatNumber, { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.cpm, currentTotals.cpm, compareTotals.cpm, value => formatNumber(value, 2), { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.ctr, currentTotals.ctr, compareTotals.ctr, value => formatPercent(value, 2), { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.cvr, currentTotals.cvr, compareTotals.cvr, value => formatPercent(value, 2), { forceDash: currentTotals.spend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.cpa, currentTotals.cpa, compareTotals.cpa, value => formatNumber(value, 2), { forceDash: currentTotals.spend === 0 })}</td>
      </tr></tfoot>`;
      document.querySelectorAll('[data-meta-dimension]').forEach(button => {
        button.classList.toggle('active', button.getAttribute('data-meta-dimension') === state.metaDimension);
      });
      document.getElementById('meta-dimension-title').textContent = `站外维度分析 · ${config.label}`;
      document.getElementById('meta-dimension-table').innerHTML = header + body + footer;
    }

    function buildOnsiteAnalysisRows(mode, currentRows, compareRows) {
      const isCategory = mode === 'category';
      const keyGetter = isCategory
        ? row => productMap.get(row[FACT.id])?.subcategory || '未标注小类目'
        : row => row[FACT.id];
      const currentMap = aggregateBy(currentRows, keyGetter);
      const compareMap = aggregateBy(compareRows, keyGetter);
      const keys = Array.from(new Set([...currentMap.keys(), ...compareMap.keys()]));
      return keys.map(key => {
        const product = isCategory ? null : productMap.get(key);
        return {
          id: key,
          name: isCategory ? key : (product?.product_name || key),
          current: finalizeAgg(currentMap.get(key) || createAgg()),
          compare: finalizeAgg(compareMap.get(key) || createAgg()),
        };
      });
    }

    function renderOnsiteOverview(current, compare) {
      const metrics = [
        { label: '站内广告花费', current: current.adSpend, compare: compare.adSpend, format: formatCurrency },
        { label: '订单量', current: current.adOrders, compare: compare.adOrders, format: formatNumber },
        { label: '站内广告 GMV', current: current.adGMV, compare: compare.adGMV, format: formatCurrency },
        { label: 'ROI', current: current.adROI, compare: compare.adROI, format: formatRatio },
        { label: 'CPC', current: current.cpc, compare: compare.cpc, format: value => formatNumber(value, 2) },
        { label: 'CTR', current: current.adCTR, compare: compare.adCTR, format: value => formatPercent(value, 2) },
        { label: 'CVR', current: current.adCVR, compare: compare.adCVR, format: value => formatPercent(value, 2) },
        { label: 'CPA', current: current.cpa, compare: compare.cpa, format: value => formatNumber(value, 2) },
      ];
      document.getElementById('onsite-metrics-grid').innerHTML = metrics.map(metric => `
        <div class="metric-card">
          <div class="metric-label">${metric.label}</div>
          <div class="metric-value">${metric.format(metric.current)}</div>
          <div class="metric-delta ${deltaClass(metric.current, metric.compare)}">${deltaText(metric.current, metric.compare)}</div>
        </div>
      `).join('');
    }

    function renderOnsiteGmvChart(currentRows) {
      const byDate = aggregateBy(currentRows, row => row[FACT.date]);
      const labels = rangeDays(state.start, state.end);
      const daily = labels.map(date => finalizeAgg(byDate.get(date) || createAgg()));
      upsertChart('chart-onsite-gmv-share', {
        type: 'bar',
        data: {
          labels: labels.map(formatDateShort),
          datasets: [
            { type: 'bar', label: '店铺 GMV', data: daily.map(item => item.gmv), yAxisID: 'yGMV', backgroundColor: 'rgba(23, 111, 139, 0.82)', borderRadius: 3, order: 2 },
            { type: 'bar', label: '站内广告 GMV', data: daily.map(item => item.adGMV), yAxisID: 'yGMV', backgroundColor: 'rgba(238, 77, 45, 0.76)', borderRadius: 3, order: 3 },
            { type: 'line', label: '广告 GMV 占比', data: daily.map(item => safeDivide(item.adGMV, item.gmv)), yAxisID: 'yShare', borderColor: '#f5a623', backgroundColor: '#f5a623', borderWidth: 2.5, pointRadius: 2, tension: 0.3, order: 1 },
          ],
        },
        plugins: [{
          id: 'onsiteGmvShareValueLabels',
          afterDatasetsDraw(chart) {
            const datasetIndex = chart.data.datasets.findIndex(dataset => dataset.yAxisID === 'yShare');
            if (datasetIndex < 0) return;
            const meta = chart.getDatasetMeta(datasetIndex);
            const values = chart.data.datasets[datasetIndex].data;
            const { ctx, chartArea } = chart;
            ctx.save();
            ctx.font = '700 10px Arial, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            meta.data.forEach((point, index) => {
              const value = values[index];
              if (value === null || value === undefined || !Number.isFinite(Number(value))) return;
              const text = formatPercent(value, 2);
              const textWidth = ctx.measureText(text).width;
              const labelX = Math.min(Math.max(point.x, chartArea.left + textWidth / 2 + 4), chartArea.right - textWidth / 2 - 4);
              const labelY = Math.max(chartArea.top + 9, point.y - 12);
              ctx.fillStyle = 'rgba(255, 255, 255, 0.88)';
              ctx.fillRect(labelX - textWidth / 2 - 3, labelY - 7, textWidth + 6, 14);
              ctx.fillStyle = '#9a5b00';
              ctx.fillText(text, labelX, labelY);
            });
            ctx.restore();
          },
        }],
        options: {
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 9, color: '#66584d' } },
            tooltip: { callbacks: { label(context) { return context.dataset.yAxisID === 'yShare' ? `${context.dataset.label}: ${formatPercent(context.raw, 2)}` : `${context.dataset.label}: ${formatCurrency(context.raw)}`; } } },
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: '#718198' } },
            yGMV: { position: 'left', ticks: { color: '#176f8b', callback: value => overviewAxisTick(value, 'currency') }, grid: { color: 'rgba(61, 42, 17, 0.08)' } },
            yShare: { position: 'right', ticks: { color: '#f5a623', callback: value => formatPercent(value) }, grid: { drawOnChartArea: false } },
          },
        },
      });
    }

    function renderOnsiteGmvTable(rows, currentTotals, compareTotals) {
      const mode = state.onsiteGmvMode;
      const label = mode === 'category' ? '小品类' : '产品';
      const tableKey = mode === 'category' ? 'onsiteGmvCategory' : 'onsiteGmvProduct';
      const enrichedRows = rows.filter(row => row.current.gmv > 0 || row.current.adSpend > 0 || row.current.adGMV > 0)
        .map(row => ({
          ...row,
          storeGmvShare: safeDivide(row.current.gmv, currentTotals.gmv),
          compareStoreGmvShare: safeDivide(row.compare.gmv, compareTotals.gmv),
          adGmvShare: safeDivide(row.current.adGMV, currentTotals.adGMV),
          compareAdGmvShare: safeDivide(row.compare.adGMV, compareTotals.adGMV),
          adGmvRatio: safeDivide(row.current.adGMV, row.current.gmv),
          compareAdGmvRatio: safeDivide(row.compare.adGMV, row.compare.gmv),
          spendShare: safeDivide(row.current.adSpend, currentTotals.adSpend),
          compareSpendShare: safeDivide(row.compare.adSpend, compareTotals.adSpend),
        }));
      const displayRows = sortTableRows(enrichedRows, tableKey);
      const header = `<thead><tr>
        ${sortableHeader(label, tableKey, 'name')}
        ${sortableHeader('店铺 GMV', tableKey, 'gmv')}
        ${sortableHeader('GMV 占比', tableKey, 'storeGmvShare')}
        ${sortableHeader('站内广告 GMV', tableKey, 'adGMV')}
        ${sortableHeader('广告 GMV 占比', tableKey, 'adGmvShare')}
        ${sortableHeader('广告 GMV / 店铺 GMV', tableKey, 'adGmvRatio')}
        ${sortableHeader('站内花费', tableKey, 'adSpend')}
        ${sortableHeader('花费占比', tableKey, 'spendShare')}
        ${sortableHeader('ROI', tableKey, 'adROI')}
        ${sortableHeader('CPC', tableKey, 'cpc')}
      </tr></thead>`;
      const body = displayRows.length ? `<tbody>${displayRows.map(row => {
        const active = mode === 'category' ? isOnsiteSubcategoryDrillActive(row.id) : isOnsiteProductDrillActive(row.id);
        const drillAttr = mode === 'category' ? `data-onsite-drill-subcategory="${escapeAttr(row.id)}"` : `data-onsite-drill-product="${escapeAttr(row.id)}"`;
        return `<tr class="drill-row ${active ? 'is-active' : ''}">
        <td><div class="cell-main row-label-pill" ${drillAttr} title="点击筛选：${escapeAttr(row.name)}">${row.name}</div></td>
        <td>${renderMetricCell(row.current.gmv, row.current.gmv, row.compare.gmv, formatCurrency)}</td>
        <td>${renderMetricCell(row.storeGmvShare, row.storeGmvShare, row.compareStoreGmvShare, value => formatPercent(value))}</td>
        <td>${renderMetricCell(row.current.adGMV, row.current.adGMV, row.compare.adGMV, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(row.adGmvShare, row.adGmvShare, row.compareAdGmvShare, value => formatPercent(value), { forceDash: row.current.adGMV === 0 })}</td>
        <td>${renderMetricCell(row.adGmvRatio, row.adGmvRatio, row.compareAdGmvRatio, value => formatPercent(value), { forceDash: row.current.gmv === 0 })}</td>
        <td>${renderMetricCell(row.current.adSpend, row.current.adSpend, row.compare.adSpend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(row.spendShare, row.spendShare, row.compareSpendShare, value => formatPercent(value), { forceDash: row.current.adSpend === 0 })}</td>
        <td>${renderMetricCell(row.current.adROI, row.current.adROI, row.compare.adROI, formatRatio, { forceDash: row.current.adSpend === 0 })}</td>
        <td>${renderMetricCell(row.current.cpc, row.current.cpc, row.compare.cpc, value => formatNumber(value, 2), { forceDash: row.current.adSpend === 0 })}</td>
      </tr>`;
      }).join('')}</tbody>` : `<tbody><tr><td class="empty" colspan="10">当前筛选下暂无站内广告数据。</td></tr></tbody>`;
      const currentAdGmvRatio = safeDivide(currentTotals.adGMV, currentTotals.gmv);
      const compareAdGmvRatio = safeDivide(compareTotals.adGMV, compareTotals.gmv);
      const footer = `<tfoot><tr><td><div class="cell-main">汇总</div></td>
        <td>${renderMetricCell(currentTotals.gmv, currentTotals.gmv, compareTotals.gmv, formatCurrency)}</td>
        <td>${renderMetricCell(1, 1, 1, value => formatPercent(value))}</td>
        <td>${renderMetricCell(currentTotals.adGMV, currentTotals.adGMV, compareTotals.adGMV, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(1, 1, 1, value => formatPercent(value), { forceDash: currentTotals.adGMV === 0 })}</td>
        <td>${renderMetricCell(currentAdGmvRatio, currentAdGmvRatio, compareAdGmvRatio, value => formatPercent(value), { forceDash: currentTotals.gmv === 0 })}</td>
        <td>${renderMetricCell(currentTotals.adSpend, currentTotals.adSpend, compareTotals.adSpend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(1, 1, 1, value => formatPercent(value), { forceDash: currentTotals.adSpend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.adROI, currentTotals.adROI, compareTotals.adROI, formatRatio, { forceDash: currentTotals.adSpend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.cpc, currentTotals.cpc, compareTotals.cpc, value => formatNumber(value, 2), { forceDash: currentTotals.adSpend === 0 })}</td>
      </tr></tfoot>`;
      document.querySelectorAll('[data-onsite-gmv-mode]').forEach(button => button.classList.toggle('active', button.getAttribute('data-onsite-gmv-mode') === mode));
      document.getElementById('onsite-gmv-title').textContent = `GMV 占比 · ${label}`;
      document.getElementById('onsite-gmv-table').innerHTML = header + body + footer;
    }

    function renderOnsiteDimensionTable(rows, currentTotals, compareTotals) {
      const mode = state.onsiteDimensionMode;
      const label = mode === 'category' ? '小品类' : '产品';
      const tableKey = mode === 'category' ? 'onsiteDimensionCategory' : 'onsiteDimensionProduct';
      const enrichedRows = rows.filter(row => row.current.gmv > 0 || row.current.visitors > 0 || row.current.adSpend > 0)
        .map(row => ({ ...row, spendShare: safeDivide(row.current.adSpend, currentTotals.adSpend), compareSpendShare: safeDivide(row.compare.adSpend, compareTotals.adSpend) }));
      const displayRows = sortTableRows(enrichedRows, tableKey);
      const header = `<thead><tr>
        ${sortableHeader(label, tableKey, 'name')}
        ${sortableHeader('店铺 GMV', tableKey, 'gmv')}
        ${sortableHeader('店铺访客', tableKey, 'visitors')}
        ${sortableHeader('店铺点击', tableKey, 'clicks')}
        ${sortableHeader('站内花费', tableKey, 'adSpend')}
        ${sortableHeader('花费占比', tableKey, 'spendShare')}
        ${sortableHeader('ROI', tableKey, 'adROI')}
        ${sortableHeader('订单数', tableKey, 'adOrders')}
        ${sortableHeader('曝光', tableKey, 'impressions')}
        ${sortableHeader('点击', tableKey, 'adClicks')}
        ${sortableHeader('CPC', tableKey, 'cpc')}
        ${sortableHeader('CTR', tableKey, 'adCTR')}
        ${sortableHeader('CVR', tableKey, 'adCVR')}
        ${sortableHeader('CPA', tableKey, 'cpa')}
      </tr></thead>`;
      const body = displayRows.length ? `<tbody>${displayRows.map(row => {
        const active = mode === 'category' ? isOnsiteSubcategoryDrillActive(row.id) : isOnsiteProductDrillActive(row.id);
        const drillAttr = mode === 'category' ? `data-onsite-drill-subcategory="${escapeAttr(row.id)}"` : `data-onsite-drill-product="${escapeAttr(row.id)}"`;
        return `<tr class="drill-row ${active ? 'is-active' : ''}">
        <td><div class="cell-main row-label-pill" ${drillAttr} title="点击筛选：${escapeAttr(row.name)}">${row.name}</div></td>
        <td>${renderMetricCell(row.current.gmv, row.current.gmv, row.compare.gmv, formatCurrency)}</td>
        <td>${renderMetricCell(row.current.visitors, row.current.visitors, row.compare.visitors, formatNumber)}</td>
        <td>${renderMetricCell(row.current.clicks, row.current.clicks, row.compare.clicks, formatNumber)}</td>
        <td>${renderMetricCell(row.current.adSpend, row.current.adSpend, row.compare.adSpend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(row.spendShare, row.spendShare, row.compareSpendShare, value => formatPercent(value), { forceDash: row.current.adSpend === 0 })}</td>
        <td>${renderMetricCell(row.current.adROI, row.current.adROI, row.compare.adROI, formatRatio, { forceDash: row.current.adSpend === 0 })}</td>
        <td>${renderMetricCell(row.current.adOrders, row.current.adOrders, row.compare.adOrders, formatNumber, { forceDash: row.current.adSpend === 0 })}</td>
        <td>${renderMetricCell(row.current.impressions, row.current.impressions, row.compare.impressions, formatNumber, { forceDash: row.current.adSpend === 0 })}</td>
        <td>${renderMetricCell(row.current.adClicks, row.current.adClicks, row.compare.adClicks, formatNumber, { forceDash: row.current.adSpend === 0 })}</td>
        <td>${renderMetricCell(row.current.cpc, row.current.cpc, row.compare.cpc, value => formatNumber(value, 2), { forceDash: row.current.adSpend === 0 })}</td>
        <td>${renderMetricCell(row.current.adCTR, row.current.adCTR, row.compare.adCTR, value => formatPercent(value, 2), { forceDash: row.current.adSpend === 0 })}</td>
        <td>${renderMetricCell(row.current.adCVR, row.current.adCVR, row.compare.adCVR, value => formatPercent(value, 2), { forceDash: row.current.adSpend === 0 })}</td>
        <td>${renderMetricCell(row.current.cpa, row.current.cpa, row.compare.cpa, value => formatNumber(value, 2), { forceDash: row.current.adSpend === 0 })}</td>
      </tr>`;
      }).join('')}</tbody>` : `<tbody><tr><td class="empty" colspan="14">当前筛选下暂无站内广告数据。</td></tr></tbody>`;
      const footer = `<tfoot><tr><td><div class="cell-main">汇总</div></td>
        <td>${renderMetricCell(currentTotals.gmv, currentTotals.gmv, compareTotals.gmv, formatCurrency)}</td>
        <td>${renderMetricCell(currentTotals.visitors, currentTotals.visitors, compareTotals.visitors, formatNumber)}</td>
        <td>${renderMetricCell(currentTotals.clicks, currentTotals.clicks, compareTotals.clicks, formatNumber)}</td>
        <td>${renderMetricCell(currentTotals.adSpend, currentTotals.adSpend, compareTotals.adSpend, formatCurrency, { dashWhenZero: true })}</td>
        <td>${renderMetricCell(1, 1, 1, value => formatPercent(value), { forceDash: currentTotals.adSpend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.adROI, currentTotals.adROI, compareTotals.adROI, formatRatio, { forceDash: currentTotals.adSpend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.adOrders, currentTotals.adOrders, compareTotals.adOrders, formatNumber, { forceDash: currentTotals.adSpend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.impressions, currentTotals.impressions, compareTotals.impressions, formatNumber, { forceDash: currentTotals.adSpend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.adClicks, currentTotals.adClicks, compareTotals.adClicks, formatNumber, { forceDash: currentTotals.adSpend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.cpc, currentTotals.cpc, compareTotals.cpc, value => formatNumber(value, 2), { forceDash: currentTotals.adSpend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.adCTR, currentTotals.adCTR, compareTotals.adCTR, value => formatPercent(value, 2), { forceDash: currentTotals.adSpend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.adCVR, currentTotals.adCVR, compareTotals.adCVR, value => formatPercent(value, 2), { forceDash: currentTotals.adSpend === 0 })}</td>
        <td>${renderMetricCell(currentTotals.cpa, currentTotals.cpa, compareTotals.cpa, value => formatNumber(value, 2), { forceDash: currentTotals.adSpend === 0 })}</td>
      </tr></tfoot>`;
      document.querySelectorAll('[data-onsite-dimension-mode]').forEach(button => button.classList.toggle('active', button.getAttribute('data-onsite-dimension-mode') === mode));
      document.getElementById('onsite-dimension-title').textContent = `站内维度分析 · ${label}`;
      document.getElementById('onsite-dimension-table').innerHTML = header + body + footer;
    }

    function renderOnsitePage() {
      const selectedIds = getOnsiteSelectedProductIds();
      const currentRows = filterFacts({ start: state.start, end: state.end }, selectedIds);
      const compareRows = filterFacts(compareRange(), selectedIds);
      const currentTotals = aggregateFacts(currentRows);
      const compareTotals = aggregateFacts(compareRows);
      renderHeaderMeta(currentRows, compareRows);
      renderOnsiteOverview(currentTotals, compareTotals);
      renderOnsiteGmvChart(currentRows);
      renderOnsiteGmvTable(buildOnsiteAnalysisRows(state.onsiteGmvMode, currentRows, compareRows), currentTotals, compareTotals);
      renderOnsiteDimensionTable(buildOnsiteAnalysisRows(state.onsiteDimensionMode, currentRows, compareRows), currentTotals, compareTotals);
    }

    function renderMetaPage() {
      const selectedIds = getMetaSelectedProductIds();
      const currentRange = { start: state.start, end: state.end };
      const compare = compareRange();
      const currentMetaRows = filterMetaFacts(currentRange, selectedIds);
      const compareMetaRows = filterMetaFacts(compare, selectedIds);
      const currentStoreRows = filterFacts(currentRange, selectedIds);
      const compareStoreRows = filterFacts(compare, selectedIds);
      const categoryRows = buildMetaAnalysisRows('category', currentMetaRows, compareMetaRows, currentStoreRows, compareStoreRows);
      const productRows = buildMetaAnalysisRows('product', currentMetaRows, compareMetaRows, currentStoreRows, compareStoreRows);
      renderHeaderMeta(currentMetaRows, compareMetaRows);
      renderMetaStructureTable(currentMetaRows, compareMetaRows);
      renderMetaAnalysisTable('category', categoryRows);
      renderMetaAnalysisTable('product', productRows);
      renderCollabAnalysis(currentMetaRows, compareMetaRows, currentStoreRows, compareStoreRows);
      renderMetaDimension(currentMetaRows, compareMetaRows);
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
      if (key === 'metaCategories') {
        total = PAYLOAD.meta_categories.length;
        selected = state.metaSelectedCategories.size;
      }
      if (key === 'metaSubcategories') {
        total = PAYLOAD.meta_subcategories.length;
        selected = state.metaSelectedSubcategories.size;
      }
      if (key === 'metaProducts') {
        total = metaProducts.length;
        selected = state.metaSelectedProducts.size;
      }
      if (key === 'metaStructures') {
        total = PAYLOAD.meta_ad_structures.length;
        selected = state.metaSelectedStructures.size;
      }
      if (key === 'metaTypes') {
        total = PAYLOAD.meta_ad_types.length;
        selected = state.metaSelectedTypes.size;
      }
      if (key === 'onsiteCategories') {
        total = PAYLOAD.onsite_categories.length;
        selected = state.onsiteSelectedCategories.size;
      }
      if (key === 'onsiteSubcategories') {
        total = PAYLOAD.onsite_subcategories.length;
        selected = state.onsiteSelectedSubcategories.size;
      }
      if (key === 'onsiteProducts') {
        total = onsiteProducts.length;
        selected = state.onsiteSelectedProducts.size;
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
      if (key === 'products') {
        return products.map(item => ({
          value: item.id,
          label: item.product_name,
          meta: `${item.category} · ${item.subcategory} · FB: ${item.fb_product_name}`,
        }));
      }
      if (key === 'metaCategories') {
        return PAYLOAD.meta_categories.map(value => ({ value, label: value, meta: `${metaProducts.filter(item => item.category === value).length} 个产品` }));
      }
      if (key === 'metaSubcategories') {
        return PAYLOAD.meta_subcategories.map(value => ({ value, label: value, meta: `${metaProducts.filter(item => item.subcategory === value).length} 个产品` }));
      }
      if (key === 'metaProducts') {
        return metaProducts.map(item => ({ value: item.id, label: item.product_name, meta: `${item.category} · ${item.subcategory}` }));
      }
      if (key === 'metaStructures') {
        return PAYLOAD.meta_ad_structures.map(value => ({ value, label: value, meta: value === '收割广告' ? 'O 列：销量' : 'O 列：非销量' }));
      }
      if (key === 'onsiteCategories') {
        return PAYLOAD.onsite_categories.map(value => ({ value, label: value, meta: `${onsiteProducts.filter(item => item.category === value).length} 个产品` }));
      }
      if (key === 'onsiteSubcategories') {
        return PAYLOAD.onsite_subcategories.map(value => ({ value, label: value, meta: `${onsiteProducts.filter(item => item.subcategory === value).length} 个产品` }));
      }
      if (key === 'onsiteProducts') {
        return onsiteProducts.map(item => ({ value: item.id, label: item.product_name, meta: `${item.category} · ${item.subcategory}` }));
      }
      return PAYLOAD.meta_ad_types.map(value => ({ value, label: value, meta: 'Raw_data 广告类型' }));
    }

    function isSelected(key, value) {
      if (key === 'categories') return state.selectedCategories.has(value);
      if (key === 'subcategories') return state.selectedSubcategories.has(value);
      if (key === 'products') return state.selectedProducts.has(value);
      if (key === 'metaCategories') return state.metaSelectedCategories.has(value);
      if (key === 'metaSubcategories') return state.metaSelectedSubcategories.has(value);
      if (key === 'metaProducts') return state.metaSelectedProducts.has(value);
      if (key === 'metaStructures') return state.metaSelectedStructures.has(value);
      if (key === 'onsiteCategories') return state.onsiteSelectedCategories.has(value);
      if (key === 'onsiteSubcategories') return state.onsiteSelectedSubcategories.has(value);
      if (key === 'onsiteProducts') return state.onsiteSelectedProducts.has(value);
      return state.metaSelectedTypes.has(value);
    }

    function toggleSelection(key, value) {
      const targets = {
        categories: state.selectedCategories,
        subcategories: state.selectedSubcategories,
        products: state.selectedProducts,
        metaCategories: state.metaSelectedCategories,
        metaSubcategories: state.metaSelectedSubcategories,
        metaProducts: state.metaSelectedProducts,
        metaStructures: state.metaSelectedStructures,
        metaTypes: state.metaSelectedTypes,
        onsiteCategories: state.onsiteSelectedCategories,
        onsiteSubcategories: state.onsiteSelectedSubcategories,
        onsiteProducts: state.onsiteSelectedProducts,
      };
      const target = targets[key];
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
      if (key === 'metaCategories') state.metaSelectedCategories = new Set(PAYLOAD.meta_categories);
      if (key === 'metaSubcategories') state.metaSelectedSubcategories = new Set(PAYLOAD.meta_subcategories);
      if (key === 'metaProducts') state.metaSelectedProducts = new Set(metaProducts.map(item => item.id));
      if (key === 'metaStructures') state.metaSelectedStructures = new Set(PAYLOAD.meta_ad_structures);
      if (key === 'metaTypes') state.metaSelectedTypes = new Set(PAYLOAD.meta_ad_types);
      if (key === 'onsiteCategories') state.onsiteSelectedCategories = new Set(PAYLOAD.onsite_categories);
      if (key === 'onsiteSubcategories') state.onsiteSelectedSubcategories = new Set(PAYLOAD.onsite_subcategories);
      if (key === 'onsiteProducts') state.onsiteSelectedProducts = new Set(onsiteProducts.map(item => item.id));
      renderAll();
      renderFilters();
    }

    function clearAll(key) {
      if (key === 'categories') state.selectedCategories = new Set();
      if (key === 'subcategories') state.selectedSubcategories = new Set();
      if (key === 'products') state.selectedProducts = new Set();
      if (key === 'metaCategories') state.metaSelectedCategories = new Set();
      if (key === 'metaSubcategories') state.metaSelectedSubcategories = new Set();
      if (key === 'metaProducts') state.metaSelectedProducts = new Set();
      if (key === 'metaStructures') state.metaSelectedStructures = new Set();
      if (key === 'metaTypes') state.metaSelectedTypes = new Set();
      if (key === 'onsiteCategories') state.onsiteSelectedCategories = new Set();
      if (key === 'onsiteSubcategories') state.onsiteSelectedSubcategories = new Set();
      if (key === 'onsiteProducts') state.onsiteSelectedProducts = new Set();
      renderAll();
      renderFilters();
    }

    function applyTableSort(tableKey, sortKey) {
      const current = state.tableSort[tableKey];
      if (current.key === sortKey) {
        current.direction = current.direction === 'asc' ? 'desc' : 'asc';
      } else {
        current.key = sortKey;
        current.direction = sortKey === 'name' ? 'asc' : 'desc';
      }
      renderAll();
    }

    function resetGlobalProductFilters() {
      state.selectedCategories = new Set(PAYLOAD.categories);
      state.selectedSubcategories = new Set(PAYLOAD.subcategories);
      state.selectedProducts = new Set(products.map(item => item.id));
      state.openFilter = null;
      renderFilters();
      renderAll();
    }

    function filterToSubcategory(subcategory) {
      if (isSubcategoryDrillActive(subcategory)) {
        resetGlobalProductFilters();
        return;
      }
      const matchingProducts = products.filter(item => item.subcategory === subcategory);
      state.selectedCategories = new Set(matchingProducts.map(item => item.category));
      state.selectedSubcategories = new Set([subcategory]);
      state.selectedProducts = new Set(matchingProducts.map(item => item.id));
      state.openFilter = null;
      renderFilters();
      renderAll();
    }

    function filterToProduct(productId) {
      if (isProductDrillActive(productId)) {
        resetGlobalProductFilters();
        return;
      }
      const product = productMap.get(productId);
      if (!product) return;
      state.selectedCategories = new Set([product.category]);
      state.selectedSubcategories = new Set([product.subcategory]);
      state.selectedProducts = new Set([product.id]);
      state.openFilter = null;
      renderFilters();
      renderAll();
    }

    function resetMetaProductFilters() {
      state.metaSelectedCategories = new Set(PAYLOAD.meta_categories);
      state.metaSelectedSubcategories = new Set(PAYLOAD.meta_subcategories);
      state.metaSelectedProducts = new Set(metaProducts.map(item => item.id));
      state.openFilter = null;
      renderFilters();
      renderAll();
    }

    function filterMetaToSubcategory(subcategory) {
      if (isMetaSubcategoryDrillActive(subcategory)) {
        resetMetaProductFilters();
        return;
      }
      const matchingProducts = metaProducts.filter(item => item.subcategory === subcategory);
      state.metaSelectedCategories = new Set(matchingProducts.map(item => item.category));
      state.metaSelectedSubcategories = new Set([subcategory]);
      state.metaSelectedProducts = new Set(matchingProducts.map(item => item.id));
      state.openFilter = null;
      renderFilters();
      renderAll();
    }

    function filterMetaToProduct(productId) {
      if (isMetaProductDrillActive(productId)) {
        resetMetaProductFilters();
        return;
      }
      const product = productMap.get(productId);
      if (!product) return;
      state.metaSelectedCategories = new Set([product.category]);
      state.metaSelectedSubcategories = new Set([product.subcategory]);
      state.metaSelectedProducts = new Set([product.id]);
      state.openFilter = null;
      renderFilters();
      renderAll();
    }

    function resetOnsiteProductFilters() {
      state.onsiteSelectedCategories = new Set(PAYLOAD.onsite_categories);
      state.onsiteSelectedSubcategories = new Set(PAYLOAD.onsite_subcategories);
      state.onsiteSelectedProducts = new Set(onsiteProducts.map(item => item.id));
      state.openFilter = null;
      renderFilters();
      renderAll();
    }

    function filterOnsiteToSubcategory(subcategory) {
      if (isOnsiteSubcategoryDrillActive(subcategory)) {
        resetOnsiteProductFilters();
        return;
      }
      const matchingProducts = onsiteProducts.filter(item => item.subcategory === subcategory);
      state.onsiteSelectedCategories = new Set(matchingProducts.map(item => item.category));
      state.onsiteSelectedSubcategories = new Set([subcategory]);
      state.onsiteSelectedProducts = new Set(matchingProducts.map(item => item.id));
      state.openFilter = null;
      renderFilters();
      renderAll();
    }

    function filterOnsiteToProduct(productId) {
      if (isOnsiteProductDrillActive(productId)) {
        resetOnsiteProductFilters();
        return;
      }
      const product = productMap.get(productId);
      if (!product || !product.has_onsite) return;
      state.onsiteSelectedCategories = new Set([product.category]);
      state.onsiteSelectedSubcategories = new Set([product.subcategory]);
      state.onsiteSelectedProducts = new Set([product.id]);
      state.openFilter = null;
      renderFilters();
      renderAll();
    }

    function renderFilters() {
      const isMetaPage = state.activePage === 'meta';
      const isOnsitePage = state.activePage === 'onsite';
      const configs = isMetaPage ? [
        { key: 'metaCategories', title: '品类' },
        { key: 'metaSubcategories', title: '小类目' },
        { key: 'metaProducts', title: '产品' },
        { key: 'metaStructures', title: '广告形式' },
        { key: 'metaTypes', title: '广告类型' },
      ] : isOnsitePage ? [
        { key: 'onsiteCategories', title: '品类' },
        { key: 'onsiteSubcategories', title: '小类目' },
        { key: 'onsiteProducts', title: '产品' },
      ] : [
        { key: 'categories', title: '品类' },
        { key: 'subcategories', title: '小类目' },
        { key: 'products', title: '产品' },
      ];
      const targetId = isMetaPage ? 'meta-filters-strip' : isOnsitePage ? 'onsite-filters-strip' : 'filters-strip';
      document.getElementById(targetId).innerHTML = configs.map(config => {
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
      document.getElementById('store-page').hidden = state.activePage !== 'store';
      document.getElementById('meta-page').hidden = state.activePage !== 'meta';
      document.getElementById('onsite-page').hidden = state.activePage !== 'onsite';
      document.querySelectorAll('[data-dashboard-page]').forEach(button => {
        button.classList.toggle('active', button.getAttribute('data-dashboard-page') === state.activePage);
      });
      if (state.activePage === 'meta') {
        renderMetaPage();
        return;
      }
      if (state.activePage === 'onsite') {
        renderOnsitePage();
        return;
      }
      const selectedIds = getSelectedProductIds();
      const currentRange = { start: state.start, end: state.end };
      const compare = compareRange();
      const currentRows = filterFacts(currentRange, selectedIds);
      const compareRows = filterFacts(compare, selectedIds);
      const currentTotals = aggregateFacts(currentRows);
      const compareTotals = aggregateFacts(compareRows);
      const productRows = aggregateProductRows(currentRows, compareRows);
      const series = dailySeries(currentRows, compareRows);
      renderHeaderMeta(currentRows, compareRows);
      renderMetricCards(currentTotals, compareTotals);
      renderInteractiveOverviewChart(series);
      renderCharts(series, currentTotals, compareTotals);
      renderCategoryTable(currentRows, compareRows, currentTotals, compareTotals);
      renderProductTable(productRows, currentTotals, compareTotals);
      renderShareBreakdown(currentRows, compareRows, currentTotals, compareTotals);
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

    function closeZoomedChart() {
      const zoomed = document.querySelector('[data-chart-wrap].chart-zoomed');
      if (zoomed) zoomed.classList.remove('chart-zoomed');
      const backdrop = document.getElementById('chart-backdrop');
      if (backdrop) {
        backdrop.classList.remove('is-visible');
        backdrop.setAttribute('aria-hidden', 'true');
      }
      document.body.classList.remove('chart-modal-open');
      if (zoomed?.querySelector('canvas')?.id && state.charts[zoomed.querySelector('canvas').id]) {
        state.charts[zoomed.querySelector('canvas').id].resize();
      }
    }

    function toggleChartZoom(canvas) {
      const wrapper = canvas.closest('[data-chart-wrap]');
      if (!wrapper) return;
      const alreadyZoomed = wrapper.classList.contains('chart-zoomed');
      closeZoomedChart();
      if (alreadyZoomed) return;
      wrapper.classList.add('chart-zoomed');
      const backdrop = document.getElementById('chart-backdrop');
      backdrop.classList.add('is-visible');
      backdrop.setAttribute('aria-hidden', 'false');
      document.body.classList.add('chart-modal-open');
      requestAnimationFrame(() => state.charts[canvas.id]?.resize());
    }

    document.getElementById('reset-btn')?.addEventListener('click', resetDefaults);
    document.getElementById('auto-compare-btn')?.addEventListener('click', autoCompareRange);
    document.getElementById('refresh-data-btn').addEventListener('click', refreshDashboard);
    document.getElementById('chart-backdrop').addEventListener('click', closeZoomedChart);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') closeZoomedChart();
    });
    document.addEventListener('dblclick', event => {
      const canvas = event.target.closest('canvas');
      if (canvas) toggleChartZoom(canvas);
    });

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
      const dashboardPage = event.target.closest('[data-dashboard-page]');
      if (dashboardPage) {
        state.activePage = dashboardPage.getAttribute('data-dashboard-page');
        state.openFilter = null;
        renderFilters();
        renderAll();
        return;
      }

      const metaDimension = event.target.closest('[data-meta-dimension]');
      if (metaDimension) {
        state.metaDimension = metaDimension.getAttribute('data-meta-dimension');
        const selectedIds = getMetaSelectedProductIds();
        renderMetaDimension(
          filterMetaFacts({ start: state.start, end: state.end }, selectedIds),
          filterMetaFacts(compareRange(), selectedIds),
        );
        return;
      }

      const collabMode = event.target.closest('[data-collab-mode]');
      if (collabMode) {
        state.collabMode = collabMode.getAttribute('data-collab-mode');
        const selectedIds = getMetaSelectedProductIds();
        renderCollabAnalysis(
          filterMetaFacts({ start: state.start, end: state.end }, selectedIds),
          filterMetaFacts(compareRange(), selectedIds),
          filterFacts({ start: state.start, end: state.end }, selectedIds),
          filterFacts(compareRange(), selectedIds),
        );
        return;
      }

      const onsiteGmvMode = event.target.closest('[data-onsite-gmv-mode]');
      if (onsiteGmvMode) {
        state.onsiteGmvMode = onsiteGmvMode.getAttribute('data-onsite-gmv-mode');
        renderOnsitePage();
        return;
      }

      const onsiteDimensionMode = event.target.closest('[data-onsite-dimension-mode]');
      if (onsiteDimensionMode) {
        state.onsiteDimensionMode = onsiteDimensionMode.getAttribute('data-onsite-dimension-mode');
        renderOnsitePage();
        return;
      }

      const shareMode = event.target.closest('[data-share-mode]');
      if (shareMode) {
        state.shareMode = shareMode.getAttribute('data-share-mode');
        renderAll();
        return;
      }

      const overviewMetric = event.target.closest('[data-overview-metric]');
      if (overviewMetric) {
        const metricKey = overviewMetric.getAttribute('data-overview-metric');
        if (state.overviewMetrics.has(metricKey)) {
          state.overviewMetrics.delete(metricKey);
        } else {
          state.overviewMetrics.add(metricKey);
        }
        renderAll();
        return;
      }

      const sortHeader = event.target.closest('[data-sort-table]');
      if (sortHeader) {
        applyTableSort(
          sortHeader.getAttribute('data-sort-table'),
          sortHeader.getAttribute('data-sort-key'),
        );
        return;
      }

      const subcategoryRow = event.target.closest('[data-drill-subcategory]');
      if (subcategoryRow) {
        filterToSubcategory(subcategoryRow.getAttribute('data-drill-subcategory'));
        return;
      }

      const productRow = event.target.closest('[data-drill-product]');
      if (productRow) {
        filterToProduct(productRow.getAttribute('data-drill-product'));
        return;
      }

      const metaSubcategoryRow = event.target.closest('[data-meta-drill-subcategory]');
      if (metaSubcategoryRow) {
        filterMetaToSubcategory(metaSubcategoryRow.getAttribute('data-meta-drill-subcategory'));
        return;
      }

      const metaProductRow = event.target.closest('[data-meta-drill-product]');
      if (metaProductRow) {
        filterMetaToProduct(metaProductRow.getAttribute('data-meta-drill-product'));
        return;
      }

      const onsiteSubcategoryRow = event.target.closest('[data-onsite-drill-subcategory]');
      if (onsiteSubcategoryRow) {
        filterOnsiteToSubcategory(onsiteSubcategoryRow.getAttribute('data-onsite-drill-subcategory'));
        return;
      }

      const onsiteProductRow = event.target.closest('[data-onsite-drill-product]');
      if (onsiteProductRow) {
        filterOnsiteToProduct(onsiteProductRow.getAttribute('data-onsite-drill-product'));
        return;
      }

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
