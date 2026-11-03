from __future__ import annotations

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


def download_source(name: str, gid: str, filename: str, header_prefix: str, sheet_id: str = SHEET_ID) -> None:
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
    if not first_line.startswith(header_prefix):
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


if __name__ == "__main__":
    main()
