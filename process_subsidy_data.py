#!/usr/bin/env python3
"""将三份补贴 CSV 导入为看板数据，不修改原看板或出货数据。"""
from __future__ import annotations

import csv
import json
import math
import re
from datetime import date
from decimal import Decimal
from pathlib import Path


REPORT_DIR = Path(__file__).resolve().parent
DATA_DIR = REPORT_DIR / "data"
OUTPUT_FILE = REPORT_DIR / "subsidy_data.json"
SHEET_ID = "1dwWGTlSeO9cL8NsYQBu3JUmB-H7t02pK16gSIpetl2Y"
SOURCES = {
    name: f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    for name, gid in (
        ("sales", "950073536"),
        ("daily", "1324626803"),
        ("monthly", "2029376544"),
    )
}
METRIC_HEADERS = {
    "total": ("全渠道",),
    "shelf": ("货架合计", "货架"),
    "tt_gmv": ("TT-GMV",),
    "tt_subsidy": ("TT-补贴",),
    "tt_rate": ("TT补贴占比",),
    "sp_gmv": ("SP-GMV",),
    "sp_subsidy": ("SP-补贴",),
    "sp_rate": ("SP补贴占比",),
    "lz_gmv": ("LZD-GMV",),
}
SALES_FIELDS = {
    "target": 5,
    "actual": 6,
    "achievement": 7,
    "mom": 8,
    "share": 10,
    "previous": 11,
}
RATE_FIELDS = {"achievement", "mom", "share", "shelf_share", "tt_rate", "sp_rate"}
NUMBER_PATTERN = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def _number(raw: str, context: str, *, fraction: bool = False) -> int | float | None:
    text = raw.strip()
    if not text or (fraction and text == "#DIV/0!"):
        return None
    text = text.replace(",", "").replace("，", "")
    has_percent = text.endswith(("%", "％"))
    if has_percent and fraction:
        text = text[:-1].strip()
    if not NUMBER_PATTERN.fullmatch(text):
        raise ValueError(f"{context}：畸形非空数字 {raw!r}")
    try:
        value = Decimal(text)
        if has_percent:
            value /= 100
        if not value.is_finite():
            raise ValueError("数字不是有限值")
        if not fraction and value == value.to_integral_value():
            return int(value)
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("数字超出有限浮点数范围")
        if value != 0 and result == 0:
            raise ValueError("数字超出浮点数精度范围")
        return result
    except (ArithmeticError, ValueError) as exc:
        raise ValueError(f"{context}：无效数字 {raw!r}（{exc}）") from exc


def _integer(raw: str, context: str, minimum: int, maximum: int) -> int:
    value = _number(raw, context)
    if value is None or value != int(value) or not minimum <= value <= maximum:
        raise ValueError(f"{context}：必须为 {minimum}～{maximum} 的整数，实际为 {raw!r}")
    return int(value)


def _read_csv(path: Path) -> tuple[list[str], list[tuple[int, list[str]]]]:
    if not path.is_file():
        raise FileNotFoundError(f"补贴数据源文件缺失：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        header = next(reader, None)
        if not header or not any(cell.strip() for cell in header):
            raise ValueError(f"{path}：文件为空或没有有效表头")
        rows = []
        for row in reader:
            if any(cell.strip() for cell in row):
                rows.append((reader.line_num, row))
    return header, rows


def _cell(row: list[str], index: int, context: str) -> str:
    if index >= len(row):
        raise ValueError(f"{context}：缺少第 {index + 1} 列（本行只有 {len(row)} 列）")
    return row[index].strip()


def _header_name(raw: str) -> str:
    return raw.strip().lstrip("①②").casefold()


def _columns(header: list[str], required: dict, path: Path) -> dict[str, int]:
    normalized = [_header_name(cell) for cell in header]
    columns = {}
    for field, aliases in required.items():
        for alias in aliases:
            matches = [i for i, name in enumerate(normalized) if name == _header_name(alias)]
            if len(matches) > 1:
                raise ValueError(f"{path}：表头 {alias!r} 重复")
            if matches:
                columns[field] = matches[0]
                break
        else:
            raise ValueError(f"{path}：缺少必需表头 {aliases!r}")
    return columns


def _identity(country: str, brand: str) -> tuple[str, str] | None:
    if country == "菲律宾" and brand.upper() == "SKINTIFIC":
        return "菲律宾", "SKINTIFIC"
    return None


def _append_unique(records: list, seen: dict, key: tuple, record: dict, context: str) -> None:
    if key in seen:
        raise ValueError(f"{context}：重复关键记录 {key!r}，首次出现于 {seen[key]}")
    seen[key] = context
    records.append(record)


def _sales_records(path: Path) -> list[dict]:
    header, rows = _read_csv(path)
    if len(header) < 12:
        raise ValueError(f"{path}：销售表必须至少有 12 列")
    expected = {
        0: ("", "年", "year"),
        1: ("", "月", "month"),
        2: ("Country",),
        3: ("Brand",),
        4: ("Platform",),
    }
    for index, aliases in expected.items():
        if _header_name(header[index]) not in {_header_name(alias) for alias in aliases}:
            raise ValueError(f"{path}：销售表第 {index + 1} 列表头位置不符：{header[index]!r}")
    records, seen = [], {}
    for line, row in rows:
        context = f"{path.name} 第 {line} 行"
        year_raw = _cell(row, 0, context)
        if not year_raw:
            continue
        month_raw = _cell(row, 1, context)
        if not month_raw:
            continue
        identity = _identity(_cell(row, 2, context), _cell(row, 3, context))
        if identity is None:
            continue
        year = _integer(year_raw, f"{context} 年", 1, 9999)
        month = _integer(month_raw, f"{context} 月", 1, 12)
        raw_platform = _cell(row, 4, context)
        platforms = {"tt": "TT", "tiktok": "TT", "货架": "货架"}
        if raw_platform.casefold() not in platforms:
            raise ValueError(f"{context}：未知销售平台 {raw_platform!r}")
        platform = platforms[raw_platform.casefold()]
        record = {
            "year": year,
            "month": f"{year:04d}-{month:02d}",
            "month_number": month,
            "country": identity[0],
            "brand": identity[1],
            "platform": platform,
        }
        for field, index in SALES_FIELDS.items():
            record[field] = _number(_cell(row, index, context), f"{context} {field}",
                                    fraction=field in RATE_FIELDS)
        key = (record["month"], *identity, platform)
        _append_unique(records, seen, key, record, context)
    if not records:
        raise ValueError(f"{path}：没有菲律宾/SKINTIFIC 的有效销售记录")
    records.sort(key=lambda item: (-item["year"], -item["month_number"], item["platform"] != "TT"))
    return records


def _trend_records(path: Path, *, daily: bool) -> list[dict]:
    header, rows = _read_csv(path)
    period_field = "date" if daily else "month"
    required = {
        "year": ("年", "year"),
        period_field: ("日", "date") if daily else ("月", "month"),
        "country": ("Country",),
        "brand": ("Brand",),
        **METRIC_HEADERS,
    }
    if not daily:
        required["shelf_share"] = ("货架占比",)
    columns = _columns(header, required, path)
    # 日表的辅助月份只用于一致性检查，日期仍取自年＋日。
    auxiliary_month = None
    if daily:
        for index, name in enumerate(header):
            if _header_name(name) in {"month", "月"}:
                if auxiliary_month is not None:
                    raise ValueError(f"{path}：日表辅助月份表头重复")
                auxiliary_month = index
    records, seen = [], {}
    for line, row in rows:
        context = f"{path.name} 第 {line} 行"
        year_raw = _cell(row, columns["year"], context)
        if not year_raw:
            continue
        period_raw = _cell(row, columns[period_field], context)
        if not period_raw or (not daily and period_raw in {"合计", "总计", "Total"}):
            continue
        identity = _identity(_cell(row, columns["country"], context),
                             _cell(row, columns["brand"], context))
        if identity is None:
            continue
        year = _integer(year_raw, f"{context} 年", 1, 9999)
        if daily:
            match = re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})", period_raw)
            if not match:
                raise ValueError(f"{context}：日必须为月/日，实际为 {period_raw!r}")
            month, day = map(int, match.groups())
            try:
                period = date(year, month, day).isoformat()
            except ValueError as exc:
                raise ValueError(f"{context}：无效日期 {year_raw}＋{period_raw}") from exc
            if auxiliary_month is not None:
                raw = _cell(row, auxiliary_month, context)
                if raw and _integer(raw, f"{context} 辅助月份", 1, 12) != month:
                    raise ValueError(f"{context}：辅助月份 {raw!r} 与日期 {period_raw!r} 不一致")
            record = {"date": period, "year": year, "country": identity[0], "brand": identity[1]}
        else:
            month = _integer(period_raw, f"{context} 月", 1, 12)
            period = f"{year:04d}-{month:02d}"
            record = {"year": year, "month": period, "month_number": month,
                      "country": identity[0], "brand": identity[1]}
        metrics = dict(METRIC_HEADERS)
        if not daily:
            metrics["shelf_share"] = ("货架占比",)
        for field in metrics:
            record[field] = _number(_cell(row, columns[field], context), f"{context} {field}",
                                    fraction=field in RATE_FIELDS)
        _append_unique(records, seen, (period, *identity), record, context)
    if not records:
        raise ValueError(f"{path}：没有菲律宾/SKINTIFIC 的有效{'日' if daily else '月'}度记录")
    records.sort(key=lambda item: item[period_field])
    return records


def _monthly_rollup(daily: list[dict]) -> list[dict]:
    """按自然月汇总日表，产出本月累计、上月全月与上月同期的 GMV/补贴/补贴率。

    累计口径为源表日值直接求和；补贴率为「本月累计补贴 ÷ 本月累计 GMV」，
    与日表逐日补贴率不同，避免按天平均造成偏差。
    """
    buckets: dict[str, list[dict]] = {}
    for record in daily:
        buckets.setdefault(record["date"][:7], []).append(record)
    months = sorted(buckets)
    rollup = []
    for index, month in enumerate(months):
        rows = sorted(buckets[month], key=lambda item: item["date"])
        entry: dict = {"month": month, "year": int(month[:4]), "month_number": int(month[5:7]),
                       "days": len(rows), "start": rows[0]["date"], "end": rows[-1]["date"]}
        for channel in ("sp", "tt"):
            gmv = _sum_metric(rows, f"{channel}_gmv")
            subsidy = _sum_metric(rows, f"{channel}_subsidy")
            entry[f"{channel}_gmv"] = gmv
            entry[f"{channel}_subsidy"] = subsidy
            entry[f"{channel}_rate"] = (subsidy / gmv) if subsidy is not None and gmv else None
        previous = months[index - 1] if index > 0 else None
        entry["previous_month"] = previous
        entry["previous_days"] = len(buckets[previous]) if previous else 0
        if previous:
            previous_rows = sorted(buckets[previous], key=lambda item: item["date"])
            for channel in ("sp", "tt"):
                full_gmv = _sum_metric(previous_rows, f"{channel}_gmv")
                full_subsidy = _sum_metric(previous_rows, f"{channel}_subsidy")
                same_gmv = _sum_metric(previous_rows[:len(rows)], f"{channel}_gmv")
                same_subsidy = _sum_metric(previous_rows[:len(rows)], f"{channel}_subsidy")
                entry[f"previous_{channel}_gmv"] = full_gmv
                entry[f"previous_{channel}_subsidy"] = full_subsidy
                entry[f"previous_{channel}_rate"] = (full_subsidy / full_gmv) if full_subsidy is not None and full_gmv else None
                entry[f"previous_same_{channel}_gmv"] = same_gmv
                entry[f"previous_same_{channel}_subsidy"] = same_subsidy
                entry[f"previous_same_{channel}_rate"] = (same_subsidy / same_gmv) if same_subsidy is not None and same_gmv else None
        rollup.append(entry)
    return rollup


def _sum_metric(rows: list[dict], field: str) -> int | float | None:
    """求和；任一缺数则返回 None，避免把缺失当作 0 参与累计。"""
    values = [row.get(field) for row in rows]
    if not values or any(value is None for value in values):
        return None
    total = sum(values)
    return int(total) if float(total).is_integer() else float(total)


def build_subsidy_data(data_dir: Path) -> dict:
    """严格读取本地 CSV；缺源、无记录、畸形数字和重复键均抛异常。"""
    data_dir = Path(data_dir)
    paths = {name: data_dir / f"subsidy_{name}.csv" for name in SOURCES}
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(f"补贴数据源文件缺失：{path}")
    sales = _sales_records(paths["sales"])
    daily = _trend_records(paths["daily"], daily=True)
    monthly = _trend_records(paths["monthly"], daily=False)
    rollup = _monthly_rollup(daily)
    latest = rollup[-1]
    return {
        "sales": sales,
        "daily": daily,
        "monthly": monthly,
        "monthly_rollup": rollup,
        "coverage": {
            "daily_start": daily[0]["date"],
            "daily_end": daily[-1]["date"],
            "latest_sales_month": sales[0]["month"],
            "latest_month": monthly[-1]["month"],
            "latest_daily_month": latest["month"],
            "previous_daily_month": latest["previous_month"],
            "latest_daily_days": latest["days"],
            "latest_daily_end_day": int(latest["end"][8:10]),
        },
        "sources": dict(SOURCES),
    }


def _json_literal(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")


def load_subsidy_json() -> str:
    """供构建器 import：从 CSV 现构建安全 JSON，不依赖旧 JSON、不写盘。"""
    return _json_literal(build_subsidy_data(DATA_DIR))


def main() -> None:
    data = build_subsidy_data(DATA_DIR)
    OUTPUT_FILE.write_text(_json_literal(data), encoding="utf-8")
    print(f"已输出：{OUTPUT_FILE}")
    print(f"记录数：sales={len(data['sales'])}，daily={len(data['daily'])}，monthly={len(data['monthly'])}")
    print(f"日覆盖：{data['coverage']['daily_start']} ～ {data['coverage']['daily_end']}")
    print(f"最新销售月：{data['coverage']['latest_sales_month']}；最新趋势月：{data['coverage']['latest_month']}")
    latest_sales = [row for row in data["sales"] if row["month"] == data["coverage"]["latest_sales_month"]]
    print("最新销售记录：" + _json_literal({"sales": latest_sales}))
    print("最新月度记录：" + _json_literal(data["monthly"][-1]))
    print("最新日累计：" + _json_literal(data["monthly_rollup"][-1]))


if __name__ == "__main__":
    main()
