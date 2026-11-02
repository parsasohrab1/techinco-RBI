from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class EquipmentCreate(BaseModel):
    tag_number: str
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


class InspectionOut(InspectionCreate):
    id: int
    cml_id: int
    inspector_id: int = 0
    model_config = ConfigDict(from_attributes=True)


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
