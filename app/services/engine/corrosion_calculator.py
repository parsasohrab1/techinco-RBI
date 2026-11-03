"""Deterministic corrosion-rate and interval screens for circuit measurement data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from math import sqrt

YEAR_DAYS = 365.25
MIN_RATE_INTERVAL_DAYS = 182
SUPPORTED_QUALITY = {"good", "verified"}


@dataclass(frozen=True)
class RateWindow:
    loss_mm: float
    elapsed_years: float
    rate_mm_yr: float


def circuit_defaults(equipment_type: str) -> dict[str, int | float | str]:
    equipment_group = equipment_type.strip().casefold().replace("-", "_")
    method_one_groups = {
        "air_cooler",
        "bundle",
        "furnace",
        "incinerator",
        "pipe",
        "piping",
        "piping_system",
    }
    if equipment_group in method_one_groups:
        return {
            "calculation_method": 1,
            "suggested_corrosion_rate_mm_yr": 0.127,
            "interval_factor": 0.5,
            "defaults_source": "reference_examples_engineering_review_required",
        }
    return {
        "calculation_method": 2,
        "suggested_corrosion_rate_mm_yr": 0.0762,
        "interval_factor": 0.5,
        "defaults_source": "reference_examples_engineering_review_required",
    }


def build_circuit_input_snapshot(circuit) -> dict:
    components = sorted(circuit.components, key=lambda item: item.id)
    return {
        "circuit": {
            "id": circuit.id,
            "calculation_method": circuit.calculation_method,
            "suggested_corrosion_rate_mm_yr": (
                circuit.suggested_corrosion_rate_mm_yr
            ),
            "interval_factor": circuit.interval_factor,
            "tif_override": circuit.tif_override,
            "time_based_interval_years": circuit.time_based_interval_years,
            "max_inspection_interval_years": (
                circuit.max_inspection_interval_years
            ),
            "ignore_calculated_interval": circuit.ignore_calculated_interval,
        },
        "components": [
            {
                "id": component.id,
                "t_min_mm": component.t_min_mm,
                "cmls": [
                    {
                        "id": cml.id,
                        "name": cml.name,
                        "inspections": [
                            {
                                "id": reading.id,
                                "date": reading.inspection_date.isoformat(),
                                "thickness_mm": reading.thickness_mm,
                                "quality_indicator": reading.quality_indicator,
                                "reading_type": reading.reading_type,
                            }
                            for reading in sorted(
                                cml.inspections,
                                key=lambda item: (item.inspection_date, item.id),
                            )
                        ],
                    }
                    for cml in sorted(component.cmls, key=lambda item: item.id)
                ],
            }
            for component in components
        ],
    }


def circuit_input_digest(snapshot: dict) -> str:
    serialized = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class InternalCorrosionCalculator:
    name = "internal_corrosion_screen"
    version = "1.0.0"
    compliance_status = "internal_screening"

    def calculate_circuit(self, circuit, components) -> dict:
        component_rows = []
        circuit_long = []
        circuit_short = []
        for component in components:
            for cml in component.cmls:
                row = self._calculate_cml(component, cml)
                component_rows.append(row)
                if row["_long_window"] is not None:
                    circuit_long.append(row["_long_window"])
                if row["_short_window"] is not None:
                    circuit_short.append(row["_short_window"])

        average_long = self._aggregate_rate(circuit_long)
        average_short = self._aggregate_rate(circuit_short)
        cml_results = []
        for row in component_rows:
            calculation = self._finish_cml(circuit, row, average_long, average_short)
            cml_results.append(calculation)

        dated_nids = [
            item for item in cml_results if item["recommended_nid"] is not None
        ]
        driving = min(dated_nids, key=lambda item: item["recommended_nid"]) if dated_nids else None
        return {
            "calculation_model": f"{self.name}-{self.version}",
            "compliance_status": self.compliance_status,
            "scope_note": (
                "Deterministic internal screen; not an API RP 580/581 or "
                "vendor calculation implementation."
            ),
            "circuit": {
                "id": circuit.id,
                "code": circuit.circuit_code,
                "calculation_method": circuit.calculation_method,
                "interval_factor": circuit.interval_factor,
                "tif_used": self._tif(circuit),
                "tif_source": (
                    "configured_full_tif"
                    if circuit.calculation_method == 1 and circuit.tif_override is not None
                    else "reference_interval_factor"
                    if circuit.calculation_method == 2
                    else "unavailable"
                ),
                "suggested_rate_mm_yr": circuit.suggested_corrosion_rate_mm_yr,
                "average_long_rate_mm_yr": average_long,
                "average_short_rate_mm_yr": average_short,
                "cml_count": len(cml_results),
                "calculated_cml_count": sum(
                    item["governing_rate_mm_yr"] is not None for item in cml_results
                ),
                "data_quality_issue_count": sum(
                    len(item["quality_flags"]) for item in cml_results
                ),
                "driving_cml": driving["cml_name"] if driving else None,
                "driving_nid": driving["recommended_nid"] if driving else None,
                "driving_remaining_life_years": (
                    driving["remaining_life_years"] if driving else None
                ),
            },
            "cml_results": cml_results,
            "limitations": [
                "Circuit-level DSCF and PERF are not calculated; method 1 requires an explicit full TIF override for a calculated NID.",
                "Dynamic Bayesian models, extreme-value analysis, renewal history, and schedule crediting are not implemented.",
                "Unreviewed and ignored measurements are excluded from the deterministic corrosion-rate screen.",
                "Any suggested interval requires qualified engineering review and approval.",
            ],
        }

    @staticmethod
    def _calculate_cml(component, cml) -> dict:
        records = sorted(
            cml.inspections,
            key=lambda reading: (reading.inspection_date, reading.id),
        )
        flags: dict[int, list[str]] = {}
        for earlier, later in pairwise(records):
            earlier_flags = flags.setdefault(earlier.id, [])
            later_flags = flags.setdefault(later.id, [])
            if later.inspection_date == earlier.inspection_date:
                later_flags.append("duplicate_date")
            elif (later.inspection_date - earlier.inspection_date).days < MIN_RATE_INTERVAL_DAYS:
                earlier_flags.append("short_interval")
            if later.thickness_mm == earlier.thickness_mm:
                later_flags.append("duplicate_thickness")
            if (
                later.quality_indicator != "verified"
                and later.thickness_mm > earlier.thickness_mm
            ):
                growth = (
                    later.thickness_mm - earlier.thickness_mm
                ) / max(earlier.thickness_mm, 1e-12)
                if growth <= 0.10:
                    later_flags.append("growth_warning")
                else:
                    later_flags.append("growth_error")

        eligible = [
            reading
            for reading in records
            if reading.quality_indicator in SUPPORTED_QUALITY
            and "growth_error" not in flags.get(reading.id, [])
        ]
        actual = [reading for reading in eligible if reading.reading_type == "measured"]
        baseline_pool = actual if len(actual) >= 2 else eligible
        baseline = baseline_pool[0] if baseline_pool else None
        latest = eligible[-1] if eligible else None
        long_window = InternalCorrosionCalculator._window(baseline, latest)
        short_window = None
        if len(eligible) >= 2:
            candidate = InternalCorrosionCalculator._window(eligible[-2], latest)
            if candidate is not None and (
                latest.inspection_date - eligible[-2].inspection_date
            ).days >= MIN_RATE_INTERVAL_DAYS:
                short_window = candidate

        regression_records = eligible
        regression_rate, correlation, r_squared = (
            InternalCorrosionCalculator._regression(regression_records)
        )
        flags_out = [
            {
                "inspection_id": reading.id,
                "codes": sorted(set(flags.get(reading.id, []))),
                "quality_indicator": reading.quality_indicator,
            }
            for reading in records
            if flags.get(reading.id)
            or reading.quality_indicator in {"unreviewed", "ignored"}
        ]
        return {
            "component_id": component.id,
            "component_name": component.name,
            "cml_id": cml.id,
            "cml_name": cml.name,
            "t_min_mm": component.t_min_mm,
            "measurement_count": len(records),
            "eligible_measurement_count": len(eligible),
            "baseline_date": baseline.inspection_date if baseline else None,
            "baseline_thickness_mm": baseline.thickness_mm if baseline else None,
            "latest_date": latest.inspection_date if latest else None,
            "latest_thickness_mm": latest.thickness_mm if latest else None,
            "long_rate_mm_yr": long_window.rate_mm_yr if long_window else None,
            "short_rate_mm_yr": short_window.rate_mm_yr if short_window else None,
            "linear_regression_rate_mm_yr": regression_rate,
            "linear_regression_correlation": correlation,
            "linear_regression_r_squared": r_squared,
            "quality_flags": flags_out,
            "_long_window": long_window,
            "_short_window": short_window,
        }

    @staticmethod
    def _window(earlier, later) -> RateWindow | None:
        if earlier is None or later is None or later.id == earlier.id:
            return None
        elapsed_days = (later.inspection_date - earlier.inspection_date).days
        if elapsed_days <= 0:
            return None
        elapsed_years = elapsed_days / YEAR_DAYS
        loss = earlier.thickness_mm - later.thickness_mm
        return RateWindow(
            loss_mm=loss,
            elapsed_years=elapsed_years,
            rate_mm_yr=max(loss / elapsed_years, 0.0),
        )

    @staticmethod
    def _regression(records) -> tuple[float | None, float | None, float | None]:
        if len(records) < 2:
            return None, None, None
        origin = records[0].inspection_date
        xs = [(reading.inspection_date - origin).days / YEAR_DAYS for reading in records]
        ys = [reading.thickness_mm for reading in records]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        variance_x = sum((x - mean_x) ** 2 for x in xs)
        variance_y = sum((y - mean_y) ** 2 for y in ys)
        if variance_x == 0:
            return None, None, None
        covariance = sum(
            (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)
        )
        slope = covariance / variance_x
        intercept = mean_y - slope * mean_x
        residual_sum = sum(
            (y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys)
        )
        r_squared = (
            1.0 if variance_y == 0 and residual_sum == 0
            else 0.0 if variance_y == 0
            else max(0.0, min(1.0, 1 - residual_sum / variance_y))
        )
        correlation = (
            (1 if covariance >= 0 else -1) * sqrt(r_squared)
            if variance_y > 0
            else 0.0
        )
        return max(-slope, 0.0), correlation, r_squared

    @staticmethod
    def _aggregate_rate(windows: list[RateWindow]) -> float | None:
        total_time = sum(window.elapsed_years for window in windows)
        if not windows or total_time <= 0:
            return None
        return round(max(sum(window.loss_mm for window in windows), 0.0) / total_time, 6)

    @staticmethod
    def _tif(circuit) -> float | None:
        if circuit.calculation_method == 1:
            return circuit.tif_override
        return circuit.interval_factor

    def _finish_cml(
        self,
        circuit,
        row: dict,
        average_long: float | None,
        average_short: float | None,
    ) -> dict:
        rates = {
            "long": row["long_rate_mm_yr"],
            "short": row["short_rate_mm_yr"],
            "linear_regression": row["linear_regression_rate_mm_yr"],
            "suggested": circuit.suggested_corrosion_rate_mm_yr,
        }
        if circuit.calculation_method == 1:
            rates["circuit_average_long"] = average_long
            rates["circuit_average_short"] = average_short
        available = {
            name: value for name, value in rates.items() if value is not None
        }
        governing_basis = max(available, key=available.get) if available else None
        governing_rate = available.get(governing_basis) if governing_basis else None
        latest_thickness = row["latest_thickness_mm"]
        rca = (
            max(latest_thickness - row["t_min_mm"], 0.0)
            if latest_thickness is not None
            else None
        )
        remaining_life = (
            0.0
            if rca == 0
            else rca / governing_rate
            if governing_rate and rca is not None
            else None
        )
        tif = self._tif(circuit)
        calculated_interval = (
            remaining_life * tif
            if remaining_life is not None and tif is not None
            else None
        )
        if (
            calculated_interval is not None
            and circuit.max_inspection_interval_years is not None
        ):
            calculated_interval = min(
                calculated_interval, circuit.max_inspection_interval_years
            )
        last_date: date | None = row["latest_date"]
        calculated_nid = (
            self._add_years(last_date, calculated_interval)
            if last_date is not None
            and calculated_interval is not None
            and not circuit.ignore_calculated_interval
            else None
        )
        time_based_nid = (
            self._add_years(last_date, circuit.time_based_interval_years)
            if last_date is not None
            and circuit.time_based_interval_years is not None
            else None
        )
        candidates = [
            candidate
            for candidate in (calculated_nid, time_based_nid)
            if candidate is not None
        ]
        recommended_nid = min(candidates) if candidates else None
        result = {
            key: value
            for key, value in row.items()
            if not key.startswith("_")
        }
        result["baseline_date"] = (
            row["baseline_date"].isoformat()
            if row["baseline_date"] is not None
            else None
        )
        result["latest_date"] = (
            row["latest_date"].isoformat()
            if row["latest_date"] is not None
            else None
        )
        result.update({
            "corrosion_rate_candidates_mm_yr": rates,
            "governing_rate_basis": governing_basis,
            "governing_rate_mm_yr": governing_rate,
            "remaining_corrosion_allowance_mm": rca,
            "remaining_life_years": (
                round(remaining_life, 4) if remaining_life is not None else None
            ),
            "tif_used": tif,
            "maximum_inspection_interval_years": circuit.max_inspection_interval_years,
            "calculated_interval_years": (
                round(calculated_interval, 4)
                if calculated_interval is not None
                else None
            ),
            "calculated_nid": calculated_nid.isoformat() if calculated_nid else None,
            "time_based_nid": time_based_nid.isoformat() if time_based_nid else None,
            "recommended_nid": (
                recommended_nid.isoformat() if recommended_nid else None
            ),
        })
        return result

    @staticmethod
    def _add_years(last_date: date, years: float) -> date:
        return date.fromordinal(last_date.toordinal() + round(years * YEAR_DAYS))
