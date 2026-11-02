import json

from sqlalchemy.orm import Session, selectinload

from .. import models
from ..config import settings
from ..standards.baseline import Baseline
from . import audit
from .data_platform import DataPlatformService
from .engine.contract import (
    EngineConfig,
    EngineInputSnapshot,
    EngineOutput,
    EngineRegistry,
    ICalculationEngine,
)
from .engine.impl_internal import InternalEngine

RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}


def get_engine() -> ICalculationEngine:
    config = EngineConfig.from_settings(settings)
    if config.engine_name == "internal":
        EngineRegistry.register(InternalEngine(
            cof_weights=config.cof_weights,
            strict_compliance=config.strict_compliance,
        ))
    return config.resolve_engine()


def recommended_interval(remaining_life: float, risk_level: str) -> float:
    base = 10.0 if remaining_life >= 999 else remaining_life / 2.0
    cap = {"Critical": 2.0, "High": 4.0, "Medium": 6.0, "Low": 10.0}[risk_level]
    return round(max(min(base, cap), 1.0), 1)


def _column_snapshot(entity) -> dict:
    def serialize(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

    mapper = getattr(type(entity), "__mapper__", None)
    if mapper is None:
        return {
            key: serialize(value)
            for key, value in vars(entity).items()
            if not key.startswith("_")
        }
    return {
        column.key: serialize(getattr(entity, column.key))
        for column in mapper.column_attrs
    }


def analyze_equipment(db: Session, equipment: models.Equipment) -> models.AnalysisRun:
    equipment = (
        db.query(models.Equipment)
        .options(
            selectinload(models.Equipment.components).selectinload(
                models.Component.cmls
            ).selectinload(models.CML.inspections),
            selectinload(models.Equipment.components).selectinload(
                models.Component.damage_mechanisms
            ).joinedload(models.ComponentDamageMechanism.damage_mechanism),
        )
        .filter(models.Equipment.id == equipment.id)
        .one()
    )
    data_platform = DataPlatformService(db)
    data_quality = data_platform.require_analysis_quality(equipment)
    evidence_by_entity: dict[tuple[str, int], list[dict]] = {}
    for evidence in data_quality.evidence:
        key = (evidence["entity_type"], evidence["entity_id"])
        evidence_by_entity.setdefault(key, []).append(evidence)
    equipment_input = data_platform.analysis_input("equipment", equipment, data_quality)
    engine = get_engine()
    run = models.AnalysisRun(
        equipment_id=equipment.id,
        engine_version=f"{engine.name}-{engine.version}",
        standard_ref=engine.metadata.standard_ref,
        overall_risk_level="Low",
    )
    db.add(run)
    db.flush()

    worst_rank, worst_level = 0, "Low"
    input_snapshot = {
        "equipment": _column_snapshot(equipment_input),
        "components": [],
    }
    for comp in equipment.components:
        for cml in comp.cmls:
            inspections = sorted(cml.inspections, key=lambda i: i.inspection_date)
            active_dms = [dm for dm in comp.damage_mechanisms if dm.status == "active"]
            component_input = data_platform.analysis_input(
                "component", comp, data_quality
            )
            cml_input = data_platform.analysis_input("cml", cml, data_quality)
            inspection_inputs = [
                data_platform.analysis_input("inspection_record", inspection, data_quality)
                for inspection in inspections
            ]
            active_dm_inputs = {
                mechanism.id: data_platform.analysis_input(
                    "component_damage_mechanism",
                    mechanism,
                    data_quality,
                )
                for mechanism in active_dms
            }
            component_snapshot = next(
                (
                    item for item in input_snapshot["components"]
                    if item["id"] == comp.id
                ),
                None,
            )
            if component_snapshot is None:
                component_snapshot = _column_snapshot(component_input)
                component_snapshot["cmls"] = []
                component_snapshot["damage_mechanisms"] = [
                    {
                        **_column_snapshot(
                            active_dm_inputs.get(mechanism.id, mechanism)
                        ),
                        "name": mechanism.damage_mechanism.name,
                    }
                    for mechanism in comp.damage_mechanisms
                ]
                input_snapshot["components"].append(component_snapshot)
            component_snapshot["cmls"].append({
                **_column_snapshot(cml_input),
                "inspections": [
                    _column_snapshot(inspection_input)
                    for inspection_input in inspection_inputs
                ],
            })

            mechanism_inputs = [
                {
                    "name": mechanism.damage_mechanism.name,
                    "status": mechanism.status,
                    "assessment_data": json.loads(
                        active_dm_inputs[mechanism.id].assessment_data_json or "{}"
                    ),
                }
                for mechanism in active_dms
            ]
            evidence_for_cml = (
                evidence_by_entity.get(("equipment", equipment.id), [])
                + evidence_by_entity.get(("component", comp.id), [])
                + evidence_by_entity.get(("cml", cml.id), [])
            )
            for inspection in inspections:
                evidence_for_cml += evidence_by_entity.get(
                    ("inspection_record", inspection.id), []
                )
            for mechanism in active_dms:
                evidence_for_cml += evidence_by_entity.get(
                    ("component_damage_mechanism", mechanism.id), []
                )
            engine_snapshot = EngineInputSnapshot(
                equipment_id=equipment.id,
                component_id=comp.id,
                cml_id=cml.id,
                inputs={
                    "equipment": _column_snapshot(equipment_input),
                    "component": _column_snapshot(component_input),
                    "cml": _column_snapshot(cml_input),
                    "inspections": [
                        _column_snapshot(inspection_input)
                        for inspection_input in inspection_inputs
                    ],
                    "damage_mechanisms": mechanism_inputs,
                },
                assumptions=[
                    item for item in evidence_for_cml
                    if item.get("quality") == "assumed"
                ],
                data_quality={
                    f"{item['entity_type']}.{item['entity_id']}.{item['field_name']}":
                    item["quality"]
                    for item in evidence_for_cml
                },
            )
            output: EngineOutput = engine.compute(engine_snapshot)
            details = {
                **output.intermediate_details,
                "inputs": engine_snapshot.inputs,
                "assumptions": engine_snapshot.assumptions,
                "data_quality": engine_snapshot.data_quality,
                "standard_references": output.standard_references,
                "engine": {
                    "name": output.engine_name,
                    "version": output.engine_version,
                    "compliance_status": output.compliance_status,
                    "calculated_at": output.calculated_at,
                },
            }

            db.add(models.CMLAnalysisResult(
                run_id=run.id,
                cml_id=cml.id,
                pof_value=output.pof_value,
                pof_category=output.pof_category,
                cof_value=output.cof_value,
                cof_category=output.cof_category,
                risk_score=output.risk_score,
                risk_level=output.risk_level,
                recommended_interval_years=output.recommended_interval_years,
                remaining_life_years=output.remaining_life_years,
                details_json=json.dumps(details),
            ))
            if RANK[output.risk_level] > worst_rank:
                worst_rank, worst_level = RANK[output.risk_level], output.risk_level

    run.overall_risk_level = worst_level
    audit.log(db, run, "create")
    db.flush()
    DataPlatformService(db).record_event(
        "analysis_run_created",
        "equipment",
        equipment.id,
        str(audit.current_user_id.get()),
        {
            "run_id": run.id,
            "engine_version": run.engine_version,
            "standard_ref": run.standard_ref,
            "standards": {
                "api_580": Baseline.api580.label(),
                "api_581": Baseline.api581.label(),
                "api_571": Baseline.api571.label(),
            },
            "compliance_status": Baseline.compliance_label(),
            "data_quality_evidence": data_quality.evidence,
            "input_snapshot": input_snapshot,
            "result_ids": [result.id for result in run.results],
        },
    )
    db.commit()
    db.refresh(run)
    return run
