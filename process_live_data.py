"""Normalize the two livestream sources without relying on formula helper columns."""
from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHEET = "https://docs.google.com/spreadsheets/d/1dwWGTlSeO9cL8NsYQBu3JUmB-H7t02pK16gSIpetl2Y/edit#gid="


def number(value):
    text = str(value or "").strip().replace(",", "")
    if not text or text.startswith("#"):
        return None
    try:
        result = float(text)
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def duration_hours(value):
    """Use the source hour:minute:second duration, including durations over 24h."""
    match = re.fullmatch(r"(\d+):([0-5]\d):([0-5]\d)", str(value or "").strip())
    if not match:
        return None
    hours, minutes, seconds = map(int, match.groups())
    return hours + minutes / 60 + seconds / 3600


def start_datetime(value):
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            pass
    raise ValueError(f"Invalid livestream Start Date: {value!r}")


def process(daily_path, sessions_path):
    daily = {}
    skipped_daily = 0
    with Path(daily_path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"Date", "Shop GMV", "Sales(Confirmed Orders)(₱)", "汇率"}.issubset(reader.fieldnames or []):
            raise ValueError("Livestream daily source headers changed")
        for row in reader:
            shop_gmv = number(row["Shop GMV"])
            if shop_gmv is None:
                skipped_daily += 1
                continue  # Future formula rows are not real zero-GMV dates.
            date = datetime.strptime(row["Date"].strip(), "%Y/%m/%d").date().isoformat()
            if date in daily:
                raise ValueError(f"Duplicate shop day: {date}")
            rate = number(row["汇率"])
            if rate is None or rate <= 0:
                raise ValueError(f"Missing or invalid exchange rate for shop day {date}")
            confirmed = number(row["Sales(Confirmed Orders)(₱)"])
            daily[date] = {"date": date, "shop_gmv": shop_gmv / rate, "exchange_rate": rate,
                           "confirmed_live_gmv": confirmed / rate if confirmed is not None else None}

    sessions, seen = [], set()
    repaired_dates = repaired_rates = 0
    with Path(sessions_path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"Livestream Session ID", "Start Date", "Total Live Duration", "Likes", "Buyers", "Gross Sales(Local Currency)", "汇率"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Livestream session source headers changed")
        for row in reader:
            session_id = row["Livestream Session ID"].strip()
            if not session_id:
                continue  # Empty template rows contain #NUM! in derived columns.
            if session_id in seen:
                raise ValueError(f"Duplicate livestream session: {session_id}")
            seen.add(session_id)
            start = start_datetime(row["Start Date"])
            hours = duration_hours(row["Total Live Duration"])
            gmv, likes, buyers = (number(row[key]) for key in ("Gross Sales(Local Currency)", "Likes", "Buyers"))
            if any(value is None or value < 0 for value in (hours, gmv, likes, buyers)):
                raise ValueError(f"Missing or invalid metric in session {session_id}")
            date = start.date().isoformat()
            rate = number(row["汇率"])
            if rate is None or rate <= 0:
                # Formula helper errors affect recent sessions; match the actual
                # Start Date to the daily source rather than inventing a rate.
                rate = daily.get(date, {}).get("exchange_rate")
                if rate is None:
                    raise ValueError(f"Missing or invalid exchange rate for session {session_id} on {date}")
                repaired_rates += 1
            repaired_dates += int(str(row.get("日期", "")).startswith("#"))
            sessions.append({"id": session_id, "name": row.get("Livestream Name", "").strip(),
                             "date": start.date().isoformat(), "start": start.isoformat(timespec="seconds"),
                             "end": (start + timedelta(hours=hours)).isoformat(timespec="seconds"),
                             "hours": round(hours, 8), "gmv": gmv / rate, "exchange_rate": rate,
                             "likes": likes, "buyers": buyers})
    sessions.sort(key=lambda item: (item["start"], item["id"]))
    if not daily or not sessions:
        raise ValueError("Livestream sources contain no usable data")
    return {"generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
            "currency": "CNY", "sources": {"daily": SHEET + "498581239", "sessions": SHEET + "1942385414"},
            "coverage": {"shop_start": min(daily), "shop_end": max(daily),
                         "sessions_start": sessions[0]["date"], "sessions_end": sessions[-1]["date"]},
            "quality": {"ignored_daily_template_rows": skipped_daily, "repaired_helper_dates": repaired_dates,
                        "repaired_session_exchange_rates": repaired_rates},
            "daily": sorted(daily.values(), key=lambda item: item["date"]), "sessions": sessions}


def main():
    payload = process(ROOT / "data/live_daily.csv", ROOT / "data/live_sessions.csv")
    (ROOT / "live_data.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"Livestream: {len(payload['daily'])} shop days, {len(payload['sessions'])} sessions; {payload['coverage']}")


if __name__ == "__main__":
    main()
