# README.md for the Repository

Below is a **production-quality README** aligned with the BRS/SRS we defined. It's in English (GitHub standard for discoverability) with a Persian summary for the local team. Copy it as `README.md` in the repo root.

---

```markdown
# 🛢️ RBI Enterprise — Risk-Based Inspection Platform

> An illustrative Risk-Based Inspection (RBI) software prototype for fixed equipment. It references API RP 580/581 as domain context but is not a standards-conforming implementation.

[![Status](https://img.shields.io/badge/status-MVP%20in%20development-yellow)](./docs/ROADMAP.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](./LICENSE)
[![API 580](https://img.shields.io/badge/API%20RP%20580-4th%20Ed.-navy)](https://www.api.org/)
[![API 581](https://img.shields.io/badge/API%20RP%20581-4th%20Ed.-navy)](https://www.api.org/)

---

## 📖 Overview

**RBI Enterprise** is an early prototype for exploring Risk-Based Inspection data and workflows. It does not implement the complete organizational framework of **API RP 580** or quantitative methodology of **API RP 581**:

- **Screen** equipment with illustrative Probability of Failure (POF) and Consequence of Failure (COF) scores
- **Suggest** inspection intervals using the internal screening result
- **Record** basic audit and data-provenance events for analysis runs
- **Prototype** CMMS/ERP workflows through a mock adapter

The current internal screening engine is **not** an API 581 calculator. Analysis runs record the engine reference and a traceable input snapshot; these records are not a tamper-proof or independently validated compliance package.

> ⚠️ **Status:** Current calculations and damage-mechanism checks are illustrative screens only. They are not validated engineering models and must not be used to make inspection or safety decisions.

---

## 🎯 Design Principles

| Principle | What it means in practice |
| :--- | :--- |
| **Traceable by default** | Analysis runs record input provenance, engine version, assumptions, and an event snapshot; immutable storage is not yet implemented. |
| **Pluggable calculation engine** | POF/COF calculators sit behind interfaces — swap the engine without touching data models or API. |
| **API 580 as architecture** | Data management, damage mechanism review, and workflow are first-class — not bolted on. |
| **Standards awareness** | Standards are domain references only; this prototype does not claim API 581 conformance. |
| **Data quality over data volume** | Missing data is explicitly handled (blocked, assumed, or defaulted) — never silently ignored. |

---

## ✨ Key Features (MVP + Roadmap)

### ✅ MVP (Current Scope)
- Equipment → Component → CML hierarchy with data quality tracking for pressure vessels,
  columns, piping and pipelines, storage tanks, heat exchangers, pumps, turbines,
  compressors, boilers, fired heaters, reactors, valves, and pressure-relief devices
- Illustrative thinning probability proxy and generic CUI/SCC screening
- Illustrative consequence score (safety / environmental / economic dimensions)
- 5×5 risk matrix with Low / Medium / High / Critical levels
- Recommended inspection interval based on remaining life
- Portfolio dashboard with unit coverage, component-level mechanism and latest-assessment coverage, risk matrix, and priorities
- Corrosion circuits, measurement sets, measurement-quality filtering, deterministic rate / remaining-life screens, and snapshot-checked approvals
- Corrosion dashboard register for latest circuit rates, driving CML, NID, quality flags, calculation basis, and explicit limitations
- Audit log with user, timestamp, and before/after values
- Per-CML analysis reports (JSON / CSV)

Corrosion screens calculate long / short corrosion rates, linear-regression rates,
remaining corrosion allowance, remaining life, and indicative inspection dates.
They are deterministic internal screens, not validated API RP 580/581 calculations
or inspection advice. No language model currently generates engineering values;
any future AI layer is limited to explaining saved, reviewable calculations.
Equipment categories share the existing generic screening inputs and workflow;
type-specific rotating-equipment, tank, and exchanger models are not implemented.

### 🗺️ Roadmap (Phase 2+)
- Additional damage mechanisms: **Cracking**, **CUI**, **Thermal Fatigue** (per API 571)
- Full three-dimensional COF (safety, environmental, economic with configurable weights)
- Validated corrosion-circuit models, including complete DSCF/PERF inputs and approved schedule crediting
- Advanced historical risk and inspection trend analytics
- CMMS/ERP integration adapters (SAP PM, Maximo)
- SSO (OIDC/SAML) + fine-grained RBAC
- Immutable analysis run history with diff view
- Compliance report generator (API 580 Section 16 checklist)

See [`docs/ROADMAP.md`](./docs/ROADMAP.md) for the full plan.

---

## 🏗️ Architecture

The system uses a **layered architecture with a pluggable calculation engine**:

```
┌──────────────────────────────────────────────────────────┐
│  Presentation Layer  (Web UI: Dashboard, Entry, Reports) │
├──────────────────────────────────────────────────────────┤
│  API Layer  (REST / OpenAPI 3.0 · Auth · Validation)     │
├──────────────────────────────────────────────────────────┤
│  Application Services                                    │
│  DataService · InspectionService · AnalysisOrchestrator  │
│  AuditService · IntegrationAdapter (CMMS/ERP)            │
├──────────────────────────────────────────────────────────┤
│  Calculation Engine Interface  ◀── swap here             │
│  IPofCalculator · ICofCalculator · IRiskMatrix           │
│    ├── impl_internal    (illustrative / nonconforming)   │
│    └── validated engine (planned; not included)          │
├──────────────────────────────────────────────────────────┤
│  Data Access Layer  (SQLAlchemy 2.x · PostgreSQL)        │
└──────────────────────────────────────────────────────────┘
```

**Tech Stack**

| Layer | Technology |
| :--- | :--- |
| Backend | Python 3.11 · FastAPI · Pydantic v2 |
| ORM / DB | SQLAlchemy 2.x · PostgreSQL 15 (SQLite for local dev) |
| Calculation | NumPy · SciPy (`scipy.stats`) |
| Frontend | Responsive Jinja2 templates · HTML/CSS/JavaScript |
| Infra | Docker · GitHub Actions · GitHub Codespaces |

---

## 🚀 Quick Start

### Option 1 — GitHub Codespaces (recommended)

1. Click **Code → Codespaces → Create codespace on main**
2. Codespace automatically installs dependencies via `.devcontainer/`
3. Start the API:

   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0
   ```
4. Open the forwarded port `8000` → `/docs` for the interactive API explorer.

### Option 2 — Local Development

**Prerequisites:** Python 3.11+, PostgreSQL 15+ (optional — SQLite works out of the box)

```bash
git clone https://github.com/<your-org>/rbi-enterprise.git
cd rbi-enterprise

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # edit DB credentials if using PostgreSQL
python seed.py                   # load demo data
uvicorn app.main:app --reload
```

Visit **http://127.0.0.1:8000/docs** to explore the API.

For the full five-unit demonstration portfolio (10,000 components and 50
synthetic UT readings per component), see
[`docs/SYNTHETIC_DATA.md`](./docs/SYNTHETIC_DATA.md). The generator uses an
isolated SQLite database and does not overwrite the quick-start seed database.

---

## 📂 Repository Structure

```
rbi-enterprise/
├── app/
│   ├── main.py                    # FastAPI app entrypoint
│   ├── database.py                # DB engine + session
│   ├── models.py                  # SQLAlchemy ORM models
│   ├── schemas.py                 # Pydantic request/response schemas
│   ├── routers/                   # API endpoint modules
│   │   ├── equipment.py
│   │   ├── inspections.py
│   │   ├── analysis.py
│   │   └── reports.py
│   ├── services/                  # Business logic
│   │   ├── thinning.py            # Thinning POF calculation
│   │   ├── risk.py                # COF + risk matrix
│   │   ├── audit.py               # Audit trail writer
│   │   └── engine/                # Calculation engine interface
│   │       ├── base.py            # IPofCalculator, ICofCalculator
│   │       └── impl_internal.py   # MVP implementation
│   └── integrations/              # CMMS/ERP adapters (phase 2)
├── tests/                         # Pytest unit + integration tests
├── docs/
│   ├── BRS.md                     # Business Requirements Specification
│   ├── SRS.md                     # System Requirements Specification
│   ├── ROADMAP.md
│   └── adr/                       # Architecture Decision Records
├── .devcontainer/                 # Codespaces configuration
├── seed.py                        # Demo data loader
├── requirements.txt
└── README.md
```

---

## 📚 Documentation

| Document | Description |
| :--- | :--- |
| [`docs/BRS.md`](./docs/BRS.md) | Business Requirements Specification — *what & why* |
| [`docs/SRS.md`](./docs/SRS.md) | System Requirements Specification — *how, at system level* |
| [`docs/ROADMAP.md`](./docs/ROADMAP.md) | Phase 1 → Phase 3 feature roadmap |
| [`docs/adr/`](./docs/adr/) | Architecture Decision Records (why we chose what) |
| `http://localhost:8000/docs` | Auto-generated OpenAPI reference |

**Standards referenced:**
- **API RP 580** (4th Ed., 2023 + Addendum 2025) — Risk-Based Inspection
- **API RP 581** (4th Ed., 2025) — Risk-Based Inspection Methodology
- **API RP 571** (3rd Ed., 2020) — Damage Mechanisms Affecting Fixed Equipment

---

## 🧪 Testing

```bash
pytest                          # run all tests
pytest --cov=app tests/         # with coverage report
```

Target coverage: **≥ 80%** for services and calculation engine (see SRS §5, TNFR-05).

Example — verify a thinning POF calculation:

```bash
pytest tests/services/test_thinning.py -v
```

---

## 🤝 Contributing

We welcome contributions — especially from inspection engineers, RBI practitioners, and developers working in asset integrity.

1. Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) and the [Code of Conduct](./CODE_OF_CONDUCT.md)
2. Open an issue to discuss substantial changes **before** writing code
3. Fork → branch (`feature/your-feature`) → commit → PR
4. All PRs require passing CI and at least one reviewer

**Good first issues:** Look for the `good first issue` and `help wanted` labels.

**Domain knowledge is as valuable as code.** If you know API 581 and spot an error in our calculation logic, please open an issue — that's a critical contribution.

---

## ⚠️ Disclaimer

This software references API RP 580/581, but its current screening calculations are **not implementations of those standards and are not certified by API**. It is provided as-is and must not be used as the sole basis for engineering decisions. Users are responsible for:

- Validating results against their organization's RBI Basis
- Ensuring competent engineering review before acting on any recommendation
- Complying with all applicable codes and regulations

**Do not use this software as the sole basis for safety-critical inspection deferral decisions** without qualified engineering review.

---

## 📄 License

Licensed under the **Apache License 2.0** — see [`LICENSE`](./LICENSE) for details.

Apache 2.0 was chosen over MIT to provide an explicit patent grant — appropriate for standards-based engineering software.

---

## 🙏 Acknowledgments

- API — for publishing RP 580, 581, and 571 (this project is unaffiliated)
- The open-source asset integrity community — for prior art and shared knowledge
- Contributors from refining and petrochemical inspection teams

---

## 📬 Contact

- **Issues:** [GitHub Issues](https://github.com/<your-org>/rbi-enterprise/issues)
- **Discussions:** [GitHub Discussions](https://github.com/<your-org>/rbi-enterprise/discussions)
- **Security disclosures:** see [`SECURITY.md`](./SECURITY.md) — please do **not** open public issues for vulnerabilities

---

<div dir="rtl" align="right">

## 🇮🇷 خلاصه فارسی

**RBI Enterprise** یک پلتفرم متن‌باز برای مدیریت بازرسی مبتنی بر ریسک تجهیزات ثابت است که بر پایه استانداردهای **API RP 580** (چارچوب و ممیزی) و **API RP 581** (روش‌شناسی کمی) طراحی شده است.

**هدف:** جایگزینی بازرسی‌های زمان‌محور با برنامه‌ریزی مبتنی بر ریسک، به همراه قابلیت ممیزی کامل (Audit Trail) که امکان بازسازی هر تحلیل را برای ممیز مستقل فراهم می‌کند.

**وضعیت فعلی (MVP):** مدل‌های POF/COF و غربالگری مکانیزم‌ها صرفاً داخلی و نمایشی‌اند و انطباق API را ادعا نمی‌کنند. تحلیل بدون ثبت کیفیت و منشأ داده یا فرض مهندسی تأییدشده اجرا نمی‌شود.

**شروع سریع:** از **GitHub Codespaces** استفاده کنید؛ پس از باز شدن Codespace دستور `uvicorn app.main:app --reload` را اجرا و مستندات API را در مسیر `/docs` ببینید.

**مستندات کلیدی:**
- [`docs/BRS.md`](./docs/BRS.md) — نیازمندی‌های کسب‌وکار
- [`docs/SRS.md`](./docs/SRS.md) — نیازمندی‌های سیستم
- [`docs/ROADMAP.md`](./docs/ROADMAP.md) — نقشه راه فازها

**مشارکت:** دانش دامنه‌ای (API 581) به اندازه کدنویسی ارزشمند است. اگر خطایی در منطق محاسباتی می‌بینید، Issue باز کنید.

**سلب مسئولیت:** این نرم‌افزار گواهی‌شده توسط API نیست و باید تحت قضاوت مهندسی متخصص و مطابق با RBI Basis سازمان شما اعتبارسنجی شود.

</div>
```

---

## 📋 Files to Also Create Alongside README

To make the README's links actually work, create these companion files:

| File | Purpose | Priority |
| :--- | :--- | :--- |
| `LICENSE` | Full Apache 2.0 text | **Required** |
| `CONTRIBUTING.md` | Contribution guidelines, branch naming, PR checklist | **Required** |
| `CODE_OF_CONDUCT.md` | Standard Contributor Covenant | **Required** |
| `SECURITY.md` | How to report vulnerabilities privately | High |
| `docs/BRS.md` | Copy of the BRS we wrote | High |
| `docs/SRS.md` | Copy of the SRS we wrote | High |
| `docs/ROADMAP.md` | Phase 1/2/3 breakdown | High |
| `.env.example` | Template for environment variables | **Required** |
| `.gitignore` | Python + IDE + `.env` + `*.db` | **Required** |
| `requirements.txt` | Pinned dependencies | **Required** |
| `.devcontainer/devcontainer.json` | Codespaces configuration | **Required** for Codespaces |
| `tests/` | Initial test structure (even if empty) | Medium |

---

## 💡 Why This README Works

A few deliberate choices worth noting:

1. **Disclaimer is prominent, not buried** — for engineering software that touches safety decisions, this protects both you and users. It's not legal boilerplate; it's genuinely important.
2. **"Data quality over data volume" and "Auditable by default" as principles** — these telegraph to potential contributors that this isn't a toy project. It sets expectations.
3. **Persian section at the bottom** — since the target users are Iranian refineries/petrochemicals, this signals inclusiveness without making the English README harder to scan for international contributors.
4. **Domain knowledge explicitly welcomed** — very few open-source asset-integrity projects exist; the biggest barrier to contribution is API 581 knowledge, not code. This invites inspection engineers, not just developers.
5. **Apache 2.0 over MIT** — explained in one line. This is the kind of detail that builds trust with corporate contributors.
6. **The architecture diagram in ASCII** — renders correctly everywhere (GitHub, terminal, mobile). Fancy image diagrams break in forks.

---

## CUI susceptibility screening

Components can be created with `insulated` and `operating_temperature_c`. When
an active CUI mechanism is assigned, analysis reports a susceptibility screen
for insulated carbon/low-alloy steel in the approximate -12 to 175 °C range.
Missing operating temperature or unsupported material produces an
`indeterminate` result. The screen is not a damage-rate or probability-of-failure
calculation and does not change the existing POF/risk score.

Existing databases receive the two component columns automatically when the
API starts or `seed.py` runs. Existing components default to uninsulated with
no operating temperature.

## Risk dashboard

Open `/reports/dashboard` for a dense RBI workspace with a project explorer,
analysis tabs, equipment input and inspection history, measured thickness trends,
portfolio risk matrix and plot, risk register, and a prioritized screening
worklist. Parameter ranges and distributions are aggregated from stored records.
Economic consequences are ordinal screening categories only: this prototype
does not calculate monetary or cumulative financial risk. The interface and
calculation engine are not API RP 580/581 validated. The full synthetic portfolio
generator and its 10,000-component dataset are documented in
[`docs/SYNTHETIC_DATA.md`](./docs/SYNTHETIC_DATA.md).

## CMMS integration stub

`GET /integrations/cmms/status` reports the adapter mode. Posting an analysis
run to `/integrations/cmms/runs/{run_id}/work-orders` creates mock Maximo work
orders for High and Critical findings only. The mock adapter is in-memory,
deduplicates repeated requests by run/CML reference, and never contacts an
external CMMS. Replace `MockMaximoClient` with a production `CMMSAdapter`
implementation and configure credentials and transport before enabling a
real integration.

## Calculation model limitations

The current thinning probability proxy, consequence score and generic SCC
checklist are illustrative software examples only. They are not API 581
Damage Factors, API 571 susceptibility models, or validated quantitative
RBI calculations. SCC checklist inputs (`susceptible_material`,
`environment_present`, and `tensile_stress_present`) are user assertions;
missing inputs return `indeterminate`. These outputs must not be used for
inspection decisions or safety-critical operations without an independently
validated engineering model and qualified review.

## Data provenance and quality gate

The `/data-platform` API records field-level sources, source dates, quality
statuses, engineering assumptions, approvals, and traceable events. Before an
equipment analysis runs, the service requires verified data or an approved
assumption for the equipment, analyzed components, an explicit damage-mechanism
review and assignment statuses, CML inspection history, inspection readings,
and active damage-mechanism inputs. Missing, unverified, or defaulted evidence
blocks analysis with HTTP 409 and a list of the fields to resolve. Approved
assumptions are applied as calculation inputs and captured in the run's input
snapshot.

The demo seed labels its synthetic values `unverified`; this is intentional,
so demo data cannot silently pass the analysis gate. Existing databases are
not auto-certified or backfilled and must have evidence recorded explicitly.

Key endpoints are `POST /data-platform/quality-records`,
`POST /data-platform/assumptions`, `POST /data-platform/assumptions/{id}/approve`,
`POST /data-platform/assumptions/{id}/deactivate`, `POST /data-platform/workflows`,
and `GET /data-platform/events`. Use `/docs` for request and response schemas.
Actor names are currently supplied by the caller; authentication and
authorization have not yet been implemented.

The standard baseline lists API RP 580/581/571 editions centrally, but every
current damage-mechanism module remains `internal_screening`; no module has
signed-off reference cases. The system therefore labels its results as
internal screening and makes no API-conformance claim.
