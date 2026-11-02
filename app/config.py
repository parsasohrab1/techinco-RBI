import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("RBI_DATABASE_URL", "sqlite:///./rbi.db")
    debug: bool = os.getenv("RBI_DEBUG", "false").lower() == "true"
    cof_weight_safety: float = float(os.getenv("RBI_COF_WEIGHT_SAFETY", "0.4"))
    cof_weight_environmental: float = float(os.getenv("RBI_COF_WEIGHT_ENV", "0.3"))
    cof_weight_economic: float = float(os.getenv("RBI_COF_WEIGHT_ECON", "0.3"))


settings = Settings()
