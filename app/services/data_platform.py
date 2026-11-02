"""Data-quality enforcement and traceable RBI workflow operations."""

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as date_type
from types import SimpleNamespace
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from .. import models
from ..models_data_platform import (
    ApprovalWorkflow,
    DataQualityStatus,
    EngineeringAssumption,
    TraceableEvent,
)

ENTITY_MODELS = {
    "equipment": models.Equipment,
    "component": models.Component,
    "cml": models.CML,
    "inspection_record": models.InspectionRecord,
    "component_damage_mechanism": models.ComponentDamageMechanism,
    "analysis_run": models.AnalysisRun,
}

QUALITY_FIELDS = {
    "equipment": ("material", "design_pressure_kpa", "inventory_m3", "fluid_type", "hazardous"),
    "component": (
        "t_min_mm",
        "t_nominal_mm",
        "geometry_type",
        "damage_mechanism_review",
    ),
}


class DataPlatformError(ValueError):
    def __init__(
        self,
        message: str,
        missing_fields: list[str] | None = None,
        status_code: int = 409,
    ):
        super().__init__(message)
        self.missing_fields = missing_fields or []
        self.status_code = status_code


@dataclass
class AnalysisQualitySnapshot:
    evidence: list[dict[str, Any]]
    assumed_values: dict[tuple[str, int, str], Any]


class DataPlatformService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_entity_exists(self, entity_type: str, entity_id: int) -> None:
        entity_model = ENTITY_MODELS.get(entity_type)
        if entity_model is None:
            raise DataPlatformError(
                f"Unsupported entity type '{entity_type}'.",
                status_code=422,
            )
        if self.db.get(entity_model, entity_id) is None:
            raise DataPlatformError(
                f"{entity_type} {entity_id} was not found.",
                status_code=404,
            )

    def record_quality(
        self,
        entity_type: str,
        entity_id: int,
        field_name: str,
        source: str,
        source_date: datetime,
        quality: str,
        actor: str,
        note: str = "",
    ) -> DataQualityStatus:
        self.ensure_entity_exists(entity_type, entity_id)
        if quality not in {"unverified", "verified", "assumed", "defaulted"}:
            raise DataPlatformError(f"Invalid data quality status '{quality}'.")
        if quality == "assumed":
            assumption = self._active_assumption(entity_type, entity_id, field_name)
            if assumption is None:
                raise DataPlatformError(
                    "Assumed data requires an active engineering assumption "
                    "for the same entity and field."
                )
            if assumption.approved_at is None:
                raise DataPlatformError("Assumed data requires an approved engineering assumption.")

        record = DataQualityStatus(
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            source=source,
            source_date=source_date,
            recorded_by=actor,
            quality=quality,
            note=note,
        )
        self.db.add(record)
        self.db.flush()
        self.record_event(
            "data_quality_recorded",
            entity_type,
            entity_id,
            actor,
            {
                "quality_record_id": record.id,
                "field_name": field_name,
                "quality": quality,
                "source": source,
                "source_date": source_date.isoformat(),
                "recorded_by": actor,
                "recorded_at": record.recorded_at.isoformat(),
                "note": note,
            },
        )
        return record

    def require_quality(
        self,
        entity_type: str,
        entity_id: int,
        field_name: str,
        allowed: frozenset[str] = frozenset({"verified", "assumed"}),
    ) -> DataQualityStatus:
        record = (
            self.db.query(DataQualityStatus)
            .filter_by(
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=field_name,
            )
            .order_by(DataQualityStatus.id.desc())
            .first()
        )
        label = f"{entity_type}.{entity_id}.{field_name}"
        if record is None:
            raise DataPlatformError(f"No data quality record for {label}.", [label])
        if record.quality not in allowed:
            raise DataPlatformError(
                f"Field {label} has quality '{record.quality}'; "
                "verified data or an approved assumption is required.",
                [label],
            )
        if record.quality == "assumed":
            assumption = self._active_assumption(entity_type, entity_id, field_name)
            if assumption is None or assumption.approved_at is None:
                raise DataPlatformError(
                    f"Field {label} has no approved active engineering assumption.",
                    [label],
                )
        return record

    def require_analysis_quality(
        self,
        equipment: models.Equipment,
    ) -> AnalysisQualitySnapshot:
        evidence: list[dict[str, Any]] = []
        assumed_values: dict[tuple[str, int, str], Any] = {}
        missing: list[str] = []

        requirements: list[tuple[str, int, str]] = [
            ("equipment", equipment.id, field) for field in QUALITY_FIELDS["equipment"]
        ]
        for component in equipment.components:
            if not component.cmls:
                continue
            requirements.extend(
                ("component", component.id, field) for field in QUALITY_FIELDS["component"]
            )
            if any(
                link.status == "active" and link.damage_mechanism.name.casefold() == "cui"
                for link in component.damage_mechanisms
            ):
                requirements.extend(
                    (
                        ("component", component.id, "insulated"),
                        ("component", component.id, "operating_temperature_c"),
                    )
                )
            for link in component.damage_mechanisms:
                requirements.append(
                    (
                        "component_damage_mechanism",
                        link.id,
                        "status",
                    )
                )
                if link.status == "active":
                    requirements.append(
                        (
                            "component_damage_mechanism",
                            link.id,
                            "assessment_data",
                        )
                    )
            for cml in component.cmls:
                requirements.append(("cml", cml.id, "inspection_history"))
                for inspection in cml.inspections:
                    requirements.extend(
                        (
                            ("inspection_record", inspection.id, "inspection_date"),
                            ("inspection_record", inspection.id, "thickness_mm"),
                            ("inspection_record", inspection.id, "effectiveness"),
                        )
                    )

        requirements = list(dict.fromkeys(requirements))
        entity_ids: dict[str, set[int]] = {}
        for entity_type, entity_id, _ in requirements:
            entity_ids.setdefault(entity_type, set()).add(entity_id)

        latest_records: dict[tuple[str, int, str], DataQualityStatus] = {}
        for entity_type, ids in entity_ids.items():
            ordered_ids = sorted(ids)
            for start in range(0, len(ordered_ids), 900):
                records = self.db.scalars(
                    select(DataQualityStatus)
                    .where(
                        DataQualityStatus.entity_type == entity_type,
                        DataQualityStatus.entity_id.in_(
                            ordered_ids[start : start + 900]
                        ),
                    )
                    .order_by(DataQualityStatus.id)
                )
                for record in records:
                    key = (record.entity_type, record.entity_id, record.field_name)
                    latest_records[key] = record

        for entity_type, entity_id, field_name in requirements:
            label = f"{entity_type}.{entity_id}.{field_name}"
            record = latest_records.get((entity_type, entity_id, field_name))
            if record is None:
                missing.append(label)
                continue
            if record.quality not in {"verified", "assumed"}:
                missing.append(label)
                continue
            if record.quality == "assumed":
                assumption = self._active_assumption(entity_type, entity_id, field_name)
                if assumption is None or assumption.approved_at is None:
                    missing.append(label)
                    continue
            evidence.append(
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "field_name": field_name,
                    "quality": record.quality,
                    "source": record.source,
                    "source_date": record.source_date.isoformat(),
                    "recorded_by": record.recorded_by,
                    "recorded_at": record.recorded_at.isoformat(),
                    "quality_record_id": record.id,
                }
            )
            if record.quality == "assumed":
                try:
                    value = self._parse_assumption(
                        entity_type,
                        field_name,
                        assumption.assumed_value,
                    )
                except ValueError as error:
                    raise DataPlatformError(
                        f"Invalid assumption for {entity_type}.{entity_id}.{field_name}: {error}",
                        [f"{entity_type}.{entity_id}.{field_name}"],
                        422,
                    ) from error
                assumed_values[(entity_type, entity_id, field_name)] = value
                evidence[-1]["assumption_id"] = assumption.id
                evidence[-1]["assumed_value"] = assumption.assumed_value

        for component in equipment.components:
            if (
                component.cmls
                and any(
                    link.status == "active" and link.damage_mechanism.name.casefold() == "cui"
                    for link in component.damage_mechanisms
                )
                and component.operating_temperature_c is None
                and (
                    "component",
                    component.id,
                    "operating_temperature_c",
                )
                not in assumed_values
            ):
                missing.append(f"component.{component.id}.operating_temperature_c")

        if missing:
            unique_missing = sorted(set(missing))
            raise DataPlatformError(
                "Analysis is blocked because required data quality evidence "
                "is missing or unacceptable.",
                unique_missing,
            )
        return AnalysisQualitySnapshot(evidence, assumed_values)

    @staticmethod
    def analysis_input(
        entity_type: str,
        entity: Any,
        quality: AnalysisQualitySnapshot,
    ) -> Any:
        overrides = {
            field_name: value
            for (record_type, entity_id, field_name), value in quality.assumed_values.items()
            if record_type == entity_type and entity_id == entity.id
        }
        if not overrides:
            return entity

        values = {
            column.key: getattr(entity, column.key)
            for column in inspect(entity).mapper.column_attrs
        }
        for field_name, value in overrides.items():
            column_name = (
                "assessment_data_json"
                if entity_type == "component_damage_mechanism" and field_name == "assessment_data"
                else field_name
            )
            values[column_name] = (
                json.dumps(value) if column_name == "assessment_data_json" else value
            )
        result = SimpleNamespace(**values)
        if entity_type == "component_damage_mechanism":
            result.mechanism_name = entity.damage_mechanism.name
        return result

    def create_assumption(
        self,
        entity_type: str,
        entity_id: int,
        field_name: str,
        value: str,
        basis: str,
        actor: str,
    ) -> EngineeringAssumption:
        self.ensure_entity_exists(entity_type, entity_id)
        superseded = (
            self.db.query(EngineeringAssumption)
            .filter_by(
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=field_name,
                is_active=True,
            )
            .all()
        )
        for previous in superseded:
            previous.is_active = False
            self.record_event(
                "engineering_assumption_superseded",
                entity_type,
                entity_id,
                actor,
                {
                    "assumption_id": previous.id,
                    "field_name": field_name,
                },
            )
        assumption = EngineeringAssumption(
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            assumed_value=value,
            basis=basis,
        )
        self.db.add(assumption)
        self.db.flush()
        self.record_event(
            "engineering_assumption_created",
            entity_type,
            entity_id,
            actor,
            {
                "assumption_id": assumption.id,
                "field_name": field_name,
                "assumed_value": value,
                "basis": basis,
            },
        )
        return assumption

    def approve_assumption(
        self,
        assumption_id: int,
        actor: str,
    ) -> EngineeringAssumption:
        assumption = self.db.get(EngineeringAssumption, assumption_id)
        if assumption is None:
            raise DataPlatformError(
                f"Assumption {assumption_id} was not found.",
                status_code=404,
            )
        if not assumption.is_active:
            raise DataPlatformError("An inactive assumption cannot be approved.")
        if assumption.approved_at is not None:
            raise DataPlatformError("Assumption has already been approved.")
        assumption.approved_by = actor
        assumption.approved_at = datetime.now(UTC).replace(tzinfo=None)
        self.record_event(
            "engineering_assumption_approved",
            assumption.entity_type,
            assumption.entity_id,
            actor,
            {"assumption_id": assumption.id, "field_name": assumption.field_name},
        )
        return assumption

    def deactivate_assumption(
        self,
        assumption_id: int,
        actor: str,
    ) -> EngineeringAssumption:
        assumption = self.db.get(EngineeringAssumption, assumption_id)
        if assumption is None:
            raise DataPlatformError(
                f"Assumption {assumption_id} was not found.",
                status_code=404,
            )
        if not assumption.is_active:
            raise DataPlatformError("Assumption is already inactive.")
        assumption.is_active = False
        self.record_event(
            "engineering_assumption_deactivated",
            assumption.entity_type,
            assumption.entity_id,
            actor,
            {"assumption_id": assumption.id, "field_name": assumption.field_name},
        )
        return assumption

    def submit_for_approval(
        self,
        entity_type: str,
        entity_id: int,
        actor: str,
    ) -> ApprovalWorkflow:
        self.ensure_entity_exists(entity_type, entity_id)
        workflow = ApprovalWorkflow(
            entity_type=entity_type,
            entity_id=entity_id,
            stage="pending",
            requested_by=actor,
        )
        self.db.add(workflow)
        self.db.flush()
        self.record_event(
            "workflow_submitted",
            entity_type,
            entity_id,
            actor,
            {"workflow_id": workflow.id},
        )
        return workflow

    def decide(
        self,
        workflow_id: int,
        decision: str,
        actor: str,
        comment: str = "",
    ) -> ApprovalWorkflow:
        workflow = self.db.get(ApprovalWorkflow, workflow_id)
        if workflow is None:
            raise DataPlatformError(
                f"Workflow {workflow_id} was not found.",
                status_code=404,
            )
        if decision not in {"reviewed", "approved", "rejected"}:
            raise DataPlatformError("Invalid workflow decision.")
        if workflow.stage in {"approved", "rejected"}:
            raise DataPlatformError(
                f"Workflow in '{workflow.stage}' stage is final and cannot be changed."
            )
        if workflow.stage == "reviewed" and decision == "reviewed":
            raise DataPlatformError("Workflow has already been reviewed.")
        workflow.stage = decision
        workflow.decided_by = actor
        workflow.decided_at = datetime.now(UTC).replace(tzinfo=None)
        workflow.comment = comment
        self.record_event(
            f"workflow_{decision}",
            workflow.entity_type,
            workflow.entity_id,
            actor,
            {"workflow_id": workflow.id, "comment": comment},
        )
        return workflow

    def record_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: int,
        actor: str,
        payload: dict[str, Any],
    ) -> TraceableEvent:
        event = TraceableEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            payload=payload,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def _active_assumption(
        self,
        entity_type: str,
        entity_id: int,
        field_name: str,
    ) -> EngineeringAssumption | None:
        return (
            self.db.query(EngineeringAssumption)
            .filter_by(
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=field_name,
                is_active=True,
            )
            .order_by(EngineeringAssumption.id.desc())
            .first()
        )

    @staticmethod
    def _parse_assumption(entity_type: str, field_name: str, value: str) -> Any:
        if entity_type == "cml" and field_name == "inspection_history":
            if value.strip().casefold() not in {
                "none",
                "no history",
                "no inspection history",
                "no records",
            }:
                raise ValueError("use an explicit no-history value for an assumed history")
            return None
        if entity_type == "component_damage_mechanism" and field_name == "assessment_data":
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError("assessment data must be a JSON object")
            return parsed

        numeric_fields = {
            ("equipment", "design_pressure_kpa"),
            ("equipment", "inventory_m3"),
            ("component", "t_min_mm"),
            ("component", "t_nominal_mm"),
            ("component", "operating_temperature_c"),
            ("inspection_record", "thickness_mm"),
        }
        boolean_fields = {
            ("equipment", "hazardous"),
            ("component", "insulated"),
        }
        string_fields = {
            ("equipment", "material"),
            ("equipment", "fluid_type"),
            ("component", "geometry_type"),
            ("inspection_record", "effectiveness"),
        }
        if (entity_type, field_name) in numeric_fields:
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError("numeric values must be finite")
            return parsed
        if (entity_type, field_name) in boolean_fields:
            normalized = value.strip().casefold()
            if normalized not in {"true", "false"}:
                raise ValueError("boolean values must be 'true' or 'false'")
            return normalized == "true"
        if (entity_type, field_name) in string_fields:
            return value
        if entity_type == "inspection_record" and field_name == "inspection_date":
            return date_type.fromisoformat(value)
        raise ValueError("assumptions are not supported for this field")
