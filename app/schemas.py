from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EquipmentCreate(BaseModel):
    tag_number: str
    plant_unit: str = "Unassigned"
    equipment_type: str = "vessel"
    material: str = "Carbon Steel"
    design_pressure_kpa: float = 1000.0
    design_temperature_c: float = 50.0
    inventory_m3: float = 10.0
    fluid_type: str = "liquid"
    hazardous: bool = True


class EquipmentOut(EquipmentCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class CMLOut(BaseModel):
    id: int
    name: str
    surface_condition: str
    model_config = ConfigDict(from_attributes=True)


class ComponentCreate(BaseModel):
    name: str
    t_min_mm: float
    t_nominal_mm: float
    geometry_type: str = "shell"
    insulated: bool = False
    operating_temperature_c: float | None = Field(default=None, ge=-273.15)
    cml_names: list[str] = []


class ComponentOut(BaseModel):
    id: int
    circuit_id: int | None = None
    name: str
    t_min_mm: float
    t_nominal_mm: float
    geometry_type: str
    insulated: bool
    operating_temperature_c: float | None
    cmls: list[CMLOut] = []
    model_config = ConfigDict(from_attributes=True)


class EquipmentDetail(EquipmentOut):
    components: list[ComponentOut] = []


class InspectionCreate(BaseModel):
    inspection_date: date
    thickness_mm: float
    method: str = "UT"
    effectiveness: str = Field(default="C", pattern="^[A-E]$")
    measurement_set_id: int | None = Field(default=None, gt=0)
    quality_indicator: Literal["good", "verified", "ignored", "unreviewed"] = "unreviewed"
    reading_type: Literal["measured", "nominal"] = "measured"


class InspectionOut(InspectionCreate):
    id: int
    cml_id: int
    inspector_id: int = 0
    model_config = ConfigDict(from_attributes=True)


class CorrosionCircuitCreate(BaseModel):
    circuit_code: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=200)
    calculation_method: Literal[1, 2] | None = None
    suggested_corrosion_rate_mm_yr: float | None = Field(default=None, ge=0)
    interval_factor: float = Field(default=0.5, gt=0, le=1)
    tif_override: float | None = Field(default=None, gt=0, le=1)
    time_based_interval_years: float | None = Field(default=None, gt=0)
    max_inspection_interval_years: float | None = Field(default=None, gt=0)
    ignore_calculated_interval: bool = False


class CorrosionCircuitOut(CorrosionCircuitCreate):
    id: int
    equipment_id: int
    calculation_method: Literal[1, 2]
    defaults_source: str
    active: bool
    model_config = ConfigDict(from_attributes=True)


class MeasurementSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=200)
    measurement_date: date
    technician: str = Field(default="", max_length=80)


class MeasurementSetOut(MeasurementSetCreate):
    id: int
    circuit_id: int
    status: Literal["open", "completed"]
    model_config = ConfigDict(from_attributes=True)


class CorrosionCalculateRequest(BaseModel):
    measurement_set_id: int | None = Field(default=None, gt=0)
    actor: str = Field(min_length=1, max_length=80)


class CorrosionApproveRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=80)
    comment: str = Field(default="", max_length=2000)


class CorrosionCalcSummaryOut(BaseModel):
    id: int
    circuit_id: int
    measurement_set_id: int | None
    status: Literal["calculated", "approved", "rejected"]
    input_snapshot: dict
    results: dict
    calculated_by: str
    calculated_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    approval_comment: str


class DamageMechanismOut(BaseModel):
    id: int
    name: str
    api571_ref: str
    category: str
    model_config = ConfigDict(from_attributes=True)


class ComponentDMCreate(BaseModel):
    dm_id: int
    status: str = Field(default="active", pattern="^(active|rejected)$")
    justification: str = ""
    assessment_data: dict[str, bool] = Field(default_factory=dict)


class CMLAnalysisOut(BaseModel):
    cml_id: int
    cml_name: str
    component: str
    pof_value: float
    pof_category: int
    cof_value: float
    cof_category: str
    risk_score: int
    risk_level: str
    remaining_life_years: float
    recommended_interval_years: float
    details: dict = {}


class EquipmentAnalysisOut(BaseModel):
    run_id: int
    equipment_id: int
    tag_number: str
    engine_version: str
    standard_ref: str
    overall_risk_level: str
    results: list[CMLAnalysisOut]


class AuditLogOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    action: str
    user_id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)


class CMMSStatusOut(BaseModel):
    adapter: str
    mode: str
    connected: bool
    message: str


class CMMSWorkOrderOut(BaseModel):
    external_reference: str
    work_order_id: str
    status: str
    created: bool
    asset_number: str
    location: str
    risk_level: str
    risk_score: int
    summary: str
    recommended_interval_years: float
    model_config = ConfigDict(from_attributes=True)


class CMMSRunSyncOut(BaseModel):
    adapter: str
    run_id: int
    eligible_count: int
    created_count: int
    work_orders: list[CMMSWorkOrderOut]


class CMMSWorkOrderComplete(BaseModel):
    inspection_date: date
    thickness_mm: float = Field(gt=0)
    method: str = "UT"
    effectiveness: str = Field(default="B", pattern="^[A-E]$")
    actor: str = "field-inspector"


class CMMSCompletionOut(BaseModel):
    work_order_id: str
    external_reference: str
    status: str
    cml_id: int
    inspection_id: int
    thickness_mm: float
    note: str


DataEntityType = Literal[
    "equipment",
    "component",
    "cml",
    "inspection_record",
    "component_damage_mechanism",
    "analysis_run",
]


class DataQualityCreate(BaseModel):
    entity_type: DataEntityType
    entity_id: int = Field(gt=0)
    field_name: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=120)
    source_date: datetime
    actor: str = Field(min_length=1, max_length=80)
    quality: Literal["unverified", "verified", "assumed", "defaulted"]
    note: str = ""


class DataQualityOut(BaseModel):
    id: int
    entity_type: DataEntityType
    entity_id: int
    field_name: str
    source: str
    source_date: datetime
    recorded_by: str
    recorded_at: datetime
    quality: str
    note: str
    model_config = ConfigDict(from_attributes=True)


class EngineeringAssumptionCreate(BaseModel):
    entity_type: DataEntityType
    entity_id: int = Field(gt=0)
    field_name: str = Field(min_length=1, max_length=80)
    assumed_value: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    actor: str = Field(min_length=1, max_length=80)


class EngineeringAssumptionOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    field_name: str
    assumed_value: str
    basis: str
    approved_by: str | None
    approved_at: datetime | None
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class ActorAction(BaseModel):
    actor: str = Field(min_length=1, max_length=80)


class ApprovalWorkflowCreate(BaseModel):
    entity_type: DataEntityType
    entity_id: int = Field(gt=0)
    actor: str = Field(min_length=1, max_length=80)


class ApprovalWorkflowDecision(BaseModel):
    decision: Literal["reviewed", "approved", "rejected"]
    actor: str = Field(min_length=1, max_length=80)
    comment: str = ""


class ApprovalWorkflowOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    stage: str
    requested_by: str
    requested_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    comment: str
    model_config = ConfigDict(from_attributes=True)


class TraceableEventOut(BaseModel):
    id: int
    event_type: str
    entity_type: str
    entity_id: int
    payload: dict
    actor: str
    occurred_at: datetime
    model_config = ConfigDict(from_attributes=True)
