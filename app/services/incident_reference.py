"""Public hazardous-liquid accident context for the laboratory environment.

The summary is built from PHMSA flagged incident data. It is context for
reviewers. It is not a failure frequency and it does not change POF or COF.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SUMMARY_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "reference"
    / "phmsa_incident_summary.json"
)

LIMITATION = (
    "These are reported hazardous-liquid pipeline accidents. They are not "
    "fixed-equipment thickness histories, and they are not used to calculate "
    "probability, consequence, or inspection interval."
)


class IncidentReferenceError(RuntimeError):
    pass


def load_incident_reference() -> dict[str, Any]:
    if not SUMMARY_PATH.exists():
        raise IncidentReferenceError(
            f"PHMSA incident summary was not found at {SUMMARY_PATH.name}."
        )
    payload = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    digest = payload.pop("content_sha256", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    actual = hashlib.sha256(canonical).hexdigest()
    if digest != actual:
        raise IncidentReferenceError(
            "PHMSA incident summary failed its content checksum."
        )
    if payload.get("accident_count", 0) < 1:
        raise IncidentReferenceError("PHMSA incident summary contains no accidents.")
    if payload.get("corrosion_count", 0) < 1:
        raise IncidentReferenceError("PHMSA incident summary contains no corrosion accidents.")
    payload["content_sha256"] = digest
    payload["limitation"] = LIMITATION
    return payload


def present_incident_reference() -> dict[str, Any]:
    try:
        summary = load_incident_reference()
    except IncidentReferenceError as error:
        return {"available": False, "message": str(error), "display_causes": []}

    causes = list(summary["causes"])
    displayed = causes[:8]
    remainder = causes[8:]
    if remainder:
        displayed.append({
            "cause": "Other reported causes",
            "count": sum(item["count"] for item in remainder),
            "share": round(sum(item["share"] for item in remainder), 6),
        })
    leading_item = (summary.get("items_involved") or [{}])[0]
    return {
        "available": True,
        "message": "",
        "accident_count": summary["accident_count"],
        "year_min": summary["year_min"],
        "year_max": summary["year_max"],
        "corrosion_count": summary["corrosion_count"],
        "corrosion_share": summary["corrosion_share"],
        "serious_count": summary["serious_count"],
        "significant_count": summary["significant_count"],
        "release_p50_bbl": summary["release_bbl"]["p50"],
        "cost_p50_usd": summary["cost_current_usd"]["p50"],
        "datafile_as_of": summary["source"].get("datafile_as_of"),
        "retrieved_on": summary["source"].get("retrieved_on"),
        "original_url": summary["source"].get("original_url"),
        "leading_item": leading_item.get("label", "—"),
        "leading_item_share": leading_item.get("share", 0.0),
        "display_causes": displayed,
        "limitation": summary["limitation"],
        "content_sha256": summary["content_sha256"],
    }
