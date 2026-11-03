# Synthetic RBI portfolio

The generator creates clearly labeled, deterministic demonstration records for
a five-unit process facility: gas separation, ethylene, polyethylene,
polypropylene, and energy supply. The default workload is 10,000 components
across 100 equipment items, with one CML and 50 thickness readings per component
(500,000 readings total). Equipment, materials, process conditions, fluid types,
wall thicknesses, inspection methods (UT, PAUT, RT, and Profile RT), and
effectiveness categories (A–E) vary across the portfolio. Inspection dates span
approximately 15 years with modest date and measurement variation; damage
profiles include different illustrative rates. Equipment types stay within the
application's supported screening scope; damage-mechanism assignments include
thinning, CUI, and SCC. Field-level quality records are labeled synthetic and do
not represent verified plant evidence. The generator runs the configured
**internal screening** engine and persists its analysis runs.

Use the isolated SQLite default; the generator refuses to reuse an existing
`SYN-RBI-` equipment tag prefix and never clears or overwrites records:

```bash
python -m scripts.generate_synthetic_portfolio
```

By default this creates `rbi-synthetic.db` in the current directory. For an
explicit location:

```bash
python -m scripts.generate_synthetic_portfolio \
  --database-url sqlite:////absolute/path/to/rbi-synthetic.db
```

Open the application against the same database to view the seeded dashboard:

```bash
RBI_DATABASE_URL=sqlite:////absolute/path/to/rbi-synthetic.db \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--components`, `--equipment`, `--inspections-per-component`, and `--seed` can
adjust workload size and reproducibility. `--seed-only` skips calculation
execution. Synthetic values are labeled in their quality notes and must not be
interpreted as plant data, engineering evidence, validated API 581 calculations,
or inspection advice.
The dashboard paginates results and aggregates portfolio metrics across each
equipment item's latest run. Its thickness trend and interval rates are derived
from generated measurements; they are not API damage factors. The dashboard
does not calculate monetary risk, and none of these records are plant data,
engineering evidence, validated API 581 results, or inspection advice.
Component-level mechanism and latest-assessment coverage counts describe stored
record presence only. They do not indicate task selection, schedule assignment,
engineering approval, barrier verification, monitoring-plan completion, or an
approved inspection due date.
