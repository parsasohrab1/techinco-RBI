import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/run/{run_id}/worklist.csv")
def worklist_csv(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.AnalysisRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Tag", "CML", "Component", "POF_Cat", "COF_Cat",
        "Risk_Score", "Risk_Level", "Remaining_Life_yr", "Recommended_Interval_yr",
    ])
    for r in run.results:
        cml = db.get(models.CML, r.cml_id)
        comp = cml.component
        w.writerow([
            run.equipment.tag_number, cml.name, comp.name,
            r.pof_category, r.cof_category, r.risk_score, r.risk_level,
            r.remaining_life_years, r.recommended_interval_years,
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="worklist-{run_id}.csv"'},
    )
