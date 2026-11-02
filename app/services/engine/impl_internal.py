import numpy as np
from scipy.stats import norm

from ...config import settings
from .base import (
    CofResult,
    EngineMetadata,
    ICalculationEngine,
    ICofCalculator,
    IPofCalculator,
    IRiskMatrix,
    PofResult,
)
from .damage_mechanisms import CUIDamageMechanismEvaluator, SCCChecklistEvaluator


class InternalPofCalculator(IPofCalculator):
    def calculate(self, component, cml, inspections, active_mechanisms):
        if not inspections:
            return PofResult(
                value=1e-1, category=5,
                reference="Internal illustrative thinning screen (not API 581)",
                details={
                    "model_scope": "illustrative_not_standard_conforming",
                    "reason": "no_inspection_history",
                },
            )

        sorted_ins = sorted(inspections, key=lambda i: i.inspection_date)
        first, last = sorted_ins[0], sorted_ins[-1]
        years = (last.inspection_date - first.inspection_date).days / 365.25
        rate = max((first.thickness_mm - last.thickness_mm) / years, 0.0) if years > 0 else 0.0

        if rate > 0 and last.thickness_mm > component.t_min_mm:
            remaining_life = (last.thickness_mm - component.t_min_mm) / rate
        elif rate > 0:
            remaining_life = 0.0
        else:
            remaining_life = 999.0

        if len(sorted_ins) >= 3 and rate > 0:
            ths = np.array([i.thickness_mm for i in sorted_ins])
            sigma_life = float(np.std(ths, ddof=1)) / rate
        else:
            sigma_life = remaining_life * 0.3 if remaining_life < 999 else 100.0

        if remaining_life >= 999:
            pof, z = 1e-5, 0.0
        else:
            z = (remaining_life - 1.0) / max(sigma_life, 0.01)
            pof = float(1 - norm.cdf(z))
            pof = max(min(pof, 0.99), 1e-6)

        if pof < 1e-4: cat = 1
        elif pof < 1e-3: cat = 2
        elif pof < 1e-2: cat = 3
        elif pof < 1e-1: cat = 4
        else: cat = 5

        eff_adj = {"A": -1, "B": -1, "C": 0, "D": 1, "E": 1}.get(last.effectiveness, 0)
        cat = max(1, min(5, cat + eff_adj))

        return PofResult(
            value=pof, category=cat,
            reference="Internal illustrative thinning screen (not API 581)",
            details={
                "model_scope": "illustrative_not_standard_conforming",
                "probability_model": "normal_survival_proxy",
                "corrosion_rate_mm_yr": round(rate, 4),
                "remaining_life_years": round(remaining_life, 2),
                "sigma_life": round(sigma_life, 3),
                "z_score": round(float(z), 3),
                "inspection_count": len(sorted_ins),
                "inspection_span_years": round(years, 3),
                "observed_thickness_range_mm": {
                    "minimum": min(i.thickness_mm for i in sorted_ins),
                    "maximum": max(i.thickness_mm for i in sorted_ins),
                },
                "effectiveness": last.effectiveness,
                "effectiveness_adjustment": eff_adj,
            },
        )


class InternalCofCalculator(ICofCalculator):
    def calculate(self, equipment, component):
        safety = min(1 + (2 if equipment.hazardous else 0) + (1 if equipment.fluid_type == "gas" else 0), 5)
        env = 3 if equipment.inventory_m3 > 100 else 2 if equipment.inventory_m3 > 10 else 1
        econ = min(int((equipment.design_pressure_kpa * equipment.inventory_m3) / 10000.0) + 1, 5)

        w_s = settings.cof_weight_safety
        w_e = settings.cof_weight_environmental
        w_m = settings.cof_weight_economic
        total = w_s + w_e + w_m or 1.0
        combined = round((w_s * safety + w_e * env + w_m * econ) / total, 3)

        if combined < 1.5: cat = "A"
        elif combined < 2.5: cat = "B"
        elif combined < 3.5: cat = "C"
        elif combined < 4.5: cat = "D"
        else: cat = "E"

        return CofResult(
            value=combined, category=cat,
            reference="Internal illustrative consequence screen (not API 581)",
            details={
                "model_scope": "illustrative_score_only_not_physical_consequence_model",
                "safety": safety, "environmental": env, "economic": econ,
                "weights": {"safety": w_s, "environmental": w_e, "economic": w_m},
            },
        )


class StandardRiskMatrix(IRiskMatrix):
    def evaluate(self, pof, cof):
        cof_idx = ord(cof.category) - ord("A")
        pof_idx = pof.category - 1
        score = (pof_idx + 1) * (cof_idx + 1)
        if score <= 3: level = "Low"
        elif score <= 8: level = "Medium"
        elif score <= 14: level = "High"
        else: level = "Critical"
        return score, level


class InternalEngine(ICalculationEngine):
    metadata = EngineMetadata(
        name="internal", version="0.2.0",
        standard_ref="Internal illustrative screening model; not API 581 conforming",
    )

    def __init__(self):
        self.pof_calculator = InternalPofCalculator()
        self.cof_calculator = InternalCofCalculator()
        self.risk_matrix = StandardRiskMatrix()
        cui_evaluator = CUIDamageMechanismEvaluator()
        scc_evaluator = SCCChecklistEvaluator()
        self.damage_mechanism_evaluators = {
            cui_evaluator.mechanism_name.casefold(): cui_evaluator,
            scc_evaluator.mechanism_name.casefold(): scc_evaluator,
        }
