# TRL 5 validation report

Generated 2026-11-08T19:30:57.064197+00:00.

The integrated screening loop was exercised in a laboratory client with an in-memory database. The accident context is the committed PHMSA hazardous-liquid summary. A failing criterion fails this run.

| Code | Criterion | Result | Detail |
| --- | --- | --- | --- |
| E6 | PHMSA accident extract | pass | 5912 deduplicated accidents, 2010–2026, corrosion share 0.217, median release 2.2 bbl, file as of 2026-04-30. |
| E1 | Missing provenance blocks analysis | pass | HTTP 409 |
| E2 | Complete provenance produces a screening result | pass | HTTP 200, risk High |
| E3 | Independent replay matches the stored result | pass | HTTP 200, differences [[]] |
| E9 | Replay is repeatable | pass | Second replay compared with the first. |
| E4 | High screening result opens one laboratory work order | pass | HTTP 200, created 1 |
| E5 | Field reading is stored and stays blocked until quality evidence exists | pass | completion HTTP 200, reanalysis HTTP 409 |
| E5b | Verified field reading changes the next screen and still replays | pass | High -> Low, replay matched True |
| E7 | Dashboard shows the laboratory asset and the PHMSA context | pass | HTTP 200 |
| E8 | Screen remains an internal, nonconforming calculation | pass | Both runs stay on internal_screening. |

Overall: pass.

This run does not validate API RP 580 or API RP 581, and it does not use plant inspection history.
