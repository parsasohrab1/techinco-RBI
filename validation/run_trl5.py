"""Regenerate the TRL 5 evidence report. Exit 1 when a criterion fails."""

from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation.laboratory import render_report, run_criteria

REPORT = Path(__file__).resolve().parents[1] / "docs" / "validation" / "TRL5_REPORT.md"


def main() -> int:
    report = run_criteria()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render_report(report), encoding="utf-8")
    print(f"Wrote {REPORT}")
    for item in report["criteria"]:
        state = "PASS" if item["passed"] else "FAIL"
        print(f"{state} {item['code']} {item['detail']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
