from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .models_data_platform import (
    ApprovalWorkflow,
    DataQualityStatus,
    EngineeringAssumption,
    TraceableEvent,
)

__all__ = [
    "CML",
    "AnalysisRun",
    "ApprovalWorkflow",
    "AuditLog",
    "CMLAnalysisResult",
    "Component",
    "ComponentDamageMechanism",
    "CorrosionCalcSummary",
    "CorrosionCircuit",
    "DamageMechanism",
    "DataQualityStatus",
    "EngineeringAssumption",
    "Equipment",
    "InspectionRecord",
    "MeasurementSet",
    "TraceableEvent",
]


class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(primary_key=True)
    tag_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    plant_unit: Mapped[str] = mapped_column(
        String(80), default="Unassigned", server_default="Unassigned", nullable=False
    )
    equipment_type: Mapped[str] = mapped_column(String(30), default="vessel")
    material: Mapped[str] = mapped_column(String(50), default="Carbon Steel")
    design_pressure_kpa: Mapped[float] = mapped_column(Float, default=1000.0)
    design_temperature_c: Mapped[float] = mapped_column(Float, default=50.0)
    inventory_m3: Mapped[float] = mapped_column(Float, default=10.0)
    fluid_type: Mapped[str] = mapped_column(String(10), default="liquid")
    hazardous: Mapped[bool] = mapped_column(Boolean, default=True)

    components: Mapped[list["Component"]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )
    corrosion_circuits: Mapped[list["CorrosionCircuit"]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )


class CorrosionCircuit(Base):
    __tablename__ = "corrosion_circuit"
    __table_args__ = (
        UniqueConstraint("equipment_id", "circuit_code", name="uq_circuit_equipment_code"),
        CheckConstraint(
            "calculation_method IN (1, 2)", name="ck_circuit_calculation_method"
        ),
        CheckConstraint(
            "interval_factor > 0 AND interval_factor <= 1",
            name="ck_circuit_interval_factor",
        ),
        CheckConstraint(
            "tif_override IS NULL OR (tif_override > 0 AND tif_override <= 1)",
            name="ck_circuit_tif_override",
        ),
        CheckConstraint(
            "suggested_corrosion_rate_mm_yr IS NULL "
            "OR suggested_corrosion_rate_mm_yr >= 0",
            name="ck_circuit_suggested_rate",
        ),
        CheckConstraint(
            "time_based_interval_years IS NULL OR time_based_interval_years > 0",
            name="ck_circuit_time_based_interval",
        ),
        CheckConstraint(
            "max_inspection_interval_years IS NULL "
            "OR max_inspection_interval_years > 0",
            name="ck_circuit_max_interval",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), index=True)
    circuit_code: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    calculation_method: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    suggested_corrosion_rate_mm_yr: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    interval_factor: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    tif_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_based_interval_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_inspection_interval_years: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    ignore_calculated_interval: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    defaults_source: Mapped[str] = mapped_column(
        String(80), default="user_configured", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    equipment: Mapped["Equipment"] = relationship(back_populates="corrosion_circuits")
    components: Mapped[list["Component"]] = relationship(back_populates="circuit")
    measurement_sets: Mapped[list["MeasurementSet"]] = relationship(
        back_populates="circuit", cascade="all, delete-orphan"
    )
    calculations: Mapped[list["CorrosionCalcSummary"]] = relationship(
        back_populates="circuit", cascade="all, delete-orphan"
    )


class Component(Base):
    __tablename__ = "component"
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    circuit_id: Mapped[int | None] = mapped_column(
        ForeignKey("corrosion_circuit.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    t_min_mm: Mapped[float] = mapped_column(Float)
    t_nominal_mm: Mapped[float] = mapped_column(Float)
    geometry_type: Mapped[str] = mapped_column(String(30), default="shell")
    insulated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    operating_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)

    equipment: Mapped["Equipment"] = relationship(back_populates="components")
    circuit: Mapped["CorrosionCircuit | None"] = relationship(
        back_populates="components"
    )
    cmls: Mapped[list["CML"]] = relationship(
        back_populates="component", cascade="all, delete-orphan"
    )
    damage_mechanisms: Mapped[list["ComponentDamageMechanism"]] = relationship(
        back_populates="component", cascade="all, delete-orphan"
    )


class CML(Base):
    __tablename__ = "cml"
    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("component.id"))
    name: Mapped[str] = mapped_column(String(50))
    surface_condition: Mapped[str] = mapped_column(String(30), default="normal")

    component: Mapped["Component"] = relationship(back_populates="cmls")
    inspections: Mapped[list["InspectionRecord"]] = relationship(
        back_populates="cml",
        cascade="all, delete-orphan",
        order_by="InspectionRecord.inspection_date",
    )


class InspectionRecord(Base):
    __tablename__ = "inspection_record"
    __table_args__ = (
        CheckConstraint(
            "quality_indicator IN ('good', 'verified', 'ignored', 'unreviewed')",
            name="ck_inspection_quality_indicator",
        ),
        CheckConstraint(
            "reading_type IN ('measured', 'nominal')",
            name="ck_inspection_reading_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cml_id: Mapped[int] = mapped_column(ForeignKey("cml.id"))
    measurement_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("measurement_set.id"), nullable=True, index=True
    )
    inspection_date: Mapped[date] = mapped_column(Date)
    thickness_mm: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(20), default="UT")
    effectiveness: Mapped[str] = mapped_column(String(2), default="C")
    quality_indicator: Mapped[str] = mapped_column(
        String(20),
        default="unreviewed",
        server_default="unreviewed",
        nullable=False,
    )
    reading_type: Mapped[str] = mapped_column(
        String(20),
        default="measured",
        server_default="measured",
        nullable=False,
    )
    inspector_id: Mapped[int] = mapped_column(Integer, default=0)

    cml: Mapped["CML"] = relationship(back_populates="inspections")
    measurement_set: Mapped["MeasurementSet | None"] = relationship(
        back_populates="inspections"
    )


class MeasurementSet(Base):
    __tablename__ = "measurement_set"
    __table_args__ = (
        UniqueConstraint("circuit_id", "name", name="uq_measurement_set_circuit_name"),
        CheckConstraint(
            "status IN ('open', 'completed')", name="ck_measurement_set_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    circuit_id: Mapped[int] = mapped_column(ForeignKey("corrosion_circuit.id"))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(200), default="")
    measurement_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    technician: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    circuit: Mapped["CorrosionCircuit"] = relationship(back_populates="measurement_sets")
    inspections: Mapped[list["InspectionRecord"]] = relationship(
        back_populates="measurement_set"
    )


class CorrosionCalcSummary(Base):
    __tablename__ = "corrosion_calc_summary"
    __table_args__ = (
        CheckConstraint(
            "status IN ('calculated', 'approved', 'rejected')",
            name="ck_corrosion_calc_summary_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    circuit_id: Mapped[int] = mapped_column(ForeignKey("corrosion_circuit.id"))
    measurement_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("measurement_set.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="calculated")
    input_snapshot_json: Mapped[str] = mapped_column(Text)
    results_json: Mapped[str] = mapped_column(Text)
    calculated_by: Mapped[str] = mapped_column(String(80))
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approval_comment: Mapped[str] = mapped_column(Text, default="")

    circuit: Mapped["CorrosionCircuit"] = relationship(back_populates="calculations")


class DamageMechanism(Base):
    __tablename__ = "damage_mechanism"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    api571_ref: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(30))


class ComponentDamageMechanism(Base):
    __tablename__ = "component_damage_mechanism"
    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("component.id"))
    dm_id: Mapped[int] = mapped_column(ForeignKey("damage_mechanism.id"))
    status: Mapped[str] = mapped_column(String(10), default="active")
    justification: Mapped[str] = mapped_column(Text, default="")
    assessment_data_json: Mapped[str] = mapped_column(Text, default="{}")

    component: Mapped["Component"] = relationship(back_populates="damage_mechanisms")
    damage_mechanism: Mapped["DamageMechanism"] = relationship()


class AnalysisRun(Base):
    __tablename__ = "analysis_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    run_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    engine_version: Mapped[str] = mapped_column(String(50))
    standard_ref: Mapped[str] = mapped_column(String(200))
    overall_risk_level: Mapped[str] = mapped_column(String(20))

    equipment: Mapped["Equipment"] = relationship(back_populates="analysis_runs")
    results: Mapped[list["CMLAnalysisResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class CMLAnalysisResult(Base):
    __tablename__ = "cml_analysis_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_run.id"))
    cml_id: Mapped[int] = mapped_column(ForeignKey("cml.id"))
    pof_value: Mapped[float] = mapped_column(Float)
    pof_category: Mapped[int] = mapped_column(Integer)
    cof_value: Mapped[float] = mapped_column(Float)
    cof_category: Mapped[str] = mapped_column(String(2))
    risk_score: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(20))
    recommended_interval_years: Mapped[float] = mapped_column(Float)
    remaining_life_years: Mapped[float] = mapped_column(Float)
    details_json: Mapped[str] = mapped_column(Text, default="{}")

    run: Mapped["AnalysisRun"] = relationship(back_populates="results")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
