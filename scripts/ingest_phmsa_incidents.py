"""Build the committed PHMSA hazardous-liquid accident summary.

The official zip is public-domain PHMSA flagged incident data. This network
receives HTTP 403 from phmsa.dot.gov, so the bytes are read from the Internet
Archive snapshot of that same URL. The raw zip stays in data/raw and is not
required at runtime; the product reads data/reference/phmsa_incident_summary.json.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
ZIP_PATH = ROOT / "data" / "raw" / "PHMSA_Pipeline_Safety_Flagged_Incidents.zip"
WORKBOOK_NAME = "hl2010toPresent.xlsx"
SHEET_NAME = "hl2010toPresent"
SUMMARY_PATH = ROOT / "data" / "reference" / "phmsa_incident_summary.json"

ORIGINAL_URL = (
    "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/"
    "data_statistics/pipeline/PHMSA_Pipeline_Safety_Flagged_Incidents.zip"
)
WAYBACK_TIMESTAMP = "20260508063624"
RETRIEVED_FROM = (
    f"https://web.archive.org/web/{WAYBACK_TIMESTAMP}id_/{ORIGINAL_URL}"
)

COLUMNS = (
    "DATAFILE_AS_OF",
    "IYEAR",
    "REPORT_NUMBER",
    "SUPPLEMENTAL_NUMBER",
    "CAUSE",
    "MAP_EIGHT_CAUSE",
    "SIGNIFICANT",
    "SERIOUS",
    "FATAL",
    "INJURE",
    "UNINTENTIONAL_RELEASE_BBLS",
    "TOTAL_COST_CURRENT",
    "COMMODITY_RELEASED_TYPE",
    "ITEM_INVOLVED",
)
YES = {"YES", "Y", "TRUE", "1"}


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _yes(value) -> bool:
    return _text(value).upper() in YES


def _number(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _int(value, default: int = 0) -> int:
    number = _number(value)
    if number is None:
        return default
    return int(number)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * fraction
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _stamp(value) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _text(value)
    return text or None


def _shares(counter: Counter[str], total: int) -> list[dict]:
    rows = []
    for label, count in counter.most_common():
        rows.append({
            "label": label,
            "count": count,
            "share": round(count / total, 6) if total else 0.0,
        })
    return rows


def _extract_workbook(destination: Path) -> Path:
    target = destination / WORKBOOK_NAME
    if target.exists():
        return target
    if not ZIP_PATH.exists():
        raise SystemExit(f"Missing {ZIP_PATH}")
    with zipfile.ZipFile(ZIP_PATH) as archive:
        archive.extract(WORKBOOK_NAME, destination)
    return target


def _read_accidents(workbook: Path) -> tuple[str | None, list[dict]]:
    book = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    sheet = book[SHEET_NAME]
    rows = sheet.iter_rows(values_only=True)
    header = [_text(name) for name in next(rows)]
    index = {name: position for position, name in enumerate(header)}
    missing = [name for name in COLUMNS if name not in index]
    if missing:
        raise SystemExit(f"Workbook is missing columns: {', '.join(missing)}")

    latest: dict[str, tuple[int, dict]] = {}
    datafile_as_of = None
    for raw in rows:
        report_number = _text(raw[index["REPORT_NUMBER"]])
        if not report_number:
            continue
        supplemental = _int(raw[index["SUPPLEMENTAL_NUMBER"]])
        cause_group = _text(raw[index["MAP_EIGHT_CAUSE"]]) or _text(raw[index["CAUSE"]])
        accident = {
            "year": _int(raw[index["IYEAR"]]),
            "cause": cause_group or "UNREPORTED",
            "significant": _yes(raw[index["SIGNIFICANT"]]),
            "serious": _yes(raw[index["SERIOUS"]]),
            "fatalities": _int(raw[index["FATAL"]]),
            "injuries": _int(raw[index["INJURE"]]),
            "release_bbl": _number(raw[index["UNINTENTIONAL_RELEASE_BBLS"]]),
            "cost_current_usd": _number(raw[index["TOTAL_COST_CURRENT"]]),
            "commodity": _text(raw[index["COMMODITY_RELEASED_TYPE"]]) or "UNREPORTED",
            "item_involved": _text(raw[index["ITEM_INVOLVED"]]) or "UNREPORTED",
        }
        stamped = _stamp(raw[index["DATAFILE_AS_OF"]])
        if stamped and (datafile_as_of is None or stamped > datafile_as_of):
            datafile_as_of = stamped
        current = latest.get(report_number)
        if current is None or supplemental >= current[0]:
            latest[report_number] = (supplemental, accident)
    book.close()
    return datafile_as_of, [item[1] for item in latest.values()]


def build_summary(accidents: list[dict], datafile_as_of: str | None) -> dict:
    total = len(accidents)
    if total == 0:
        raise SystemExit("No hazardous-liquid accidents were read.")
    causes = Counter(item["cause"] for item in accidents)
    corrosion_count = sum(
        count for label, count in causes.items() if "CORROSION" in label.upper()
    )
    releases = [
        item["release_bbl"] for item in accidents
        if item["release_bbl"] is not None and item["release_bbl"] >= 0
    ]
    costs = [
        item["cost_current_usd"] for item in accidents
        if item["cost_current_usd"] is not None and item["cost_current_usd"] >= 0
    ]
    years = [item["year"] for item in accidents if item["year"] > 0]
    summary = {
        "source": {
            "publisher": "Pipeline and Hazardous Materials Safety Administration",
            "dataset": "Pipeline Incident Flagged Files",
            "file": WORKBOOK_NAME,
            "sheet": SHEET_NAME,
            "original_url": ORIGINAL_URL,
            "retrieved_from": RETRIEVED_FROM,
            "wayback_timestamp": WAYBACK_TIMESTAMP,
            "retrieved_on": "2026-11-08",
            "datafile_as_of": datafile_as_of,
            "license": "U.S. Government work, public domain",
            "retrieval_note": (
                "phmsa.dot.gov returned HTTP 403 from the build network. "
                "The zip is the Internet Archive copy of that official file."
            ),
            "deduplication": (
                "One row per REPORT_NUMBER, keeping the highest SUPPLEMENTAL_NUMBER."
            ),
            "scope": (
                "Hazardous-liquid pipeline accidents reported to PHMSA. "
                "Not refinery or petrochemical fixed-equipment inspection data, "
                "and not an API RP 581 generic failure frequency."
            ),
        },
        "accident_count": total,
        "year_min": min(years),
        "year_max": max(years),
        "corrosion_count": corrosion_count,
        "corrosion_share": round(corrosion_count / total, 6),
        "serious_count": sum(item["serious"] for item in accidents),
        "significant_count": sum(item["significant"] for item in accidents),
        "fatality_accidents": sum(item["fatalities"] > 0 for item in accidents),
        "injury_accidents": sum(item["injuries"] > 0 for item in accidents),
        "total_fatalities": sum(item["fatalities"] for item in accidents),
        "total_injuries": sum(item["injuries"] for item in accidents),
        "release_bbl": {
            "count": len(releases),
            "p50": round(_percentile(releases, 0.50) or 0.0, 3),
            "p90": round(_percentile(releases, 0.90) or 0.0, 3),
            "max": round(max(releases), 3) if releases else 0.0,
        },
        "cost_current_usd": {
            "count": len(costs),
            "p50": round(_percentile(costs, 0.50) or 0.0, 2),
            "p90": round(_percentile(costs, 0.90) or 0.0, 2),
            "max": round(max(costs), 2) if costs else 0.0,
        },
        "causes": [
            {
                "cause": label,
                "count": count,
                "share": round(count / total, 6),
            }
            for label, count in causes.most_common()
        ],
        "commodities": _shares(
            Counter(item["commodity"] for item in accidents), total
        )[:8],
        "items_involved": _shares(
            Counter(item["item_involved"] for item in accidents), total
        )[:8],
    }
    encoded = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode()
    summary["content_sha256"] = hashlib.sha256(encoded).hexdigest()
    return summary


def main() -> None:
    workbook = _extract_workbook(ZIP_PATH.parent)
    datafile_as_of, accidents = _read_accidents(workbook)
    summary = build_summary(accidents, datafile_as_of)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {SUMMARY_PATH} accidents={summary['accident_count']} "
        f"years={summary['year_min']}-{summary['year_max']} "
        f"corrosion_share={summary['corrosion_share']}"
    )


if __name__ == "__main__":
    main()
