from pathlib import Path

from validation.laboratory import render_report, run_criteria

REPORT = Path(__file__).resolve().parents[1] / "docs" / "validation" / "TRL5_REPORT.md"


def test_trl5_laboratory_loop():
    report = run_criteria()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render_report(report), encoding="utf-8")
    failed = [item for item in report["criteria"] if not item["passed"]]
    assert not failed, failed
