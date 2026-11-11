from __future__ import annotations

import csv
import shutil
from pathlib import Path
from urllib.request import Request, urlopen


SHEET_ID = "1I_Q-Rx6QklML2023EUG8U1hb4MPN8shyeTyShiXrcYY"
SHIPMENT_SHEET_ID = "1dwWGTlSeO9cL8NsYQBu3JUmB-H7t02pK16gSIpetl2Y"
REPORT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = REPORT_DIR / "data"
SOURCES = [
    ("旗舰店数据源", "979789790", "flagship_store_sheet_979789790.csv", "店铺,品类"),
    ("站内广告", "1711647547", "onsite_ads_sheet_1711647547.csv", "date,产品ID"),
    ("Raw_data", "1292217820", "raw_data_sheet_1292217820.csv", "广告名称,广告组名称"),
]
SHIPMENT_SOURCE = ("出货数据源", "374772985", "shipment_raw.csv", "SKU,产品名")
SUBSIDY_SOURCES = [
    ("销售概览", "950073536", "subsidy_sales.csv", "", ("Country", "Brand", "Platform")),
    ("补贴日趋势", "1324626803", "subsidy_daily.csv", "", ("年", "日", "TT-GMV", "SP-GMV")),
    ("补贴月度趋势", "2029376544", "subsidy_monthly.csv", "", ("年", "月", "TT-GMV", "①SP-GMV")),
]
LIVE_SOURCES = [
    ("直播店铺日数据", "498581239", "live_daily.csv", "Date,", ("Shop GMV",)),
    ("直播场次明细", "1942385414", "live_sessions.csv", "Year,", ("Start Date", "Total Live Duration", "Likes", "Buyers", "Gross Sales(Local Currency)")),
]


def download_source(name: str, gid: str, filename: str, header_prefix: str, sheet_id: str = SHEET_ID, required_headers: tuple[str, ...] = ()) -> None:
    destination = DATA_DIR / filename
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    request = Request(url, headers={"User-Agent": "PH-Shopee-Dashboard-Refresh/1.0"})

    with urlopen(request, timeout=300) as response, temporary.open("wb") as output:
        if response.status != 200:
            raise RuntimeError(f"{name} 下载失败：HTTP {response.status}")
        shutil.copyfileobj(response, output)

    with temporary.open("r", encoding="utf-8-sig", errors="replace") as source:
        first_line = source.readline().strip()
    parsed_header = next(csv.reader([first_line]))
    if not first_line.startswith(header_prefix) or any(field not in parsed_header for field in required_headers):
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"{name} 表头不符合预期：{first_line[:120]}")

    temporary.replace(destination)
    print(f"Downloaded {name}: {destination.name} ({destination.stat().st_size:,} bytes)")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        download_source(*source)
    # Download shipment data from separate sheet
    download_source(*SHIPMENT_SOURCE, sheet_id=SHIPMENT_SHEET_ID)
    for name, gid, filename, prefix, headers in SUBSIDY_SOURCES:
        download_source(name, gid, filename, prefix, sheet_id=SHIPMENT_SHEET_ID, required_headers=headers)
    for name, gid, filename, prefix, headers in LIVE_SOURCES:
        download_source(name, gid, filename, prefix, sheet_id=SHIPMENT_SHEET_ID, required_headers=headers)


if __name__ == "__main__":
    main()
