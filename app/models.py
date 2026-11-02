from datetime import date, datetime
from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(primary_key=True)
    tag_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
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
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )


class Component(Base):
    __tablename__ = "component"
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    name: Mapped[str] = mapped_column(String(50))
    t_min_mm: Mapped[float] = mapped_column(Float)
    t_nominal_mm: Mapped[float] = mapped_column(Float)
    geometry_type: Mapped[str] = mapped_column(String(30), default="shell")
    insulated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    operating_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)

    equipment: Mapped["Equipment"] = relationship(back_populates="components")
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
    id: Mapped[int] = mapped_column(primary_key=True)
    cml_id: Mapped[int] = mapped_column(ForeignKey("cml.id"))
    inspection_date: Mapped[date] = mapped_column(Date)
    thickness_mm: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(20), default="UT")
    effectiveness: Mapped[str] = mapped_column(String(2), default="C")
    inspector_id: Mapped[int] = mapped_column(Integer, default=0)

    cml: Mapped["CML"] = relationship(back_populates="inspections")


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
