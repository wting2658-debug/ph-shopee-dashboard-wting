"""Build same-origin flash data for the dashboard."""
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rows(name):
    with (ROOT / "data" / name).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.reader(source))


def main():
    detail = rows("flash_detail.csv")
    daily = rows("flash_by_day.csv")
    if not detail or not daily:
        raise ValueError("Flash source is empty")
    category_rows = rows("new_products_daily.csv")
    header = [name.strip() for name in category_rows[0]]
    required = ("Date", "类目", "产品简称", "Sales-￥", "Variation ID")
    if any(name not in header for name in required):
        raise ValueError(f"商品日表缺少字段：{required}")
    fields = {name: header.index(name) for name in required}
    category_gmv = defaultdict(float)
    product_gmv = defaultdict(float)
    for row in category_rows[1:]:
        if len(row) <= max(fields.values()) or row[fields["Variation ID"]].strip() != "-":
            continue
        sales = row[fields["Sales-￥"]].strip().replace(",", "")
        if not sales or sales == "-":
            continue
        day = datetime.strptime(row[fields["Date"]].strip().split(" ")[0].replace("/", "-"), "%Y-%m-%d").date().isoformat()
        category = row[fields["类目"]].strip()
        product = row[fields["产品简称"]].strip()
        if category:
            category_gmv[(day, category)] += float(sales)
        if product:
            product_gmv[(day, product)] += float(sales)
    output = {"schema": 1, "detail": detail, "daily": daily,
              "category_gmv": [[day, category, amount] for (day, category), amount in sorted(category_gmv.items())],
              "product_gmv": [[day, product, amount] for (day, product), amount in sorted(product_gmv.items())]}
    (ROOT / "assets" / "flash-data.json").write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    main()

