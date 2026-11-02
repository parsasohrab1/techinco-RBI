# Synthetic RBI portfolio

The generator creates clearly labeled, deterministic demonstration records. The
default workload is 10,000 components across 100 synthetic vessels, with one CML
and two thickness readings per component. It records field-level provenance so
the dataset can pass the current analysis gate, then runs the configured
**internal screening** engine and persists the resulting analysis runs.

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

`--components`, `--equipment`, and `--seed` can adjust workload size and
reproducibility. `--seed-only` skips calculation execution. Synthetic values
are labeled in their quality notes and must not be interpreted as plant data,
engineering evidence, validated API 581 calculations, or inspection advice.
The dashboard paginates results and aggregates portfolio metrics across each
equipment item's latest run.
