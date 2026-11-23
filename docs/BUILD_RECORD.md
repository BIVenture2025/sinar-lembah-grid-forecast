# P37 Grid Demand Forecast and Meter Watch: build record

Data Platform, sample data, portfolio. Fictional company Sinar Lembah Grid Sdn Bhd, an electricity distributor in the Klang
Valley. Built on 23 November 2026 in one session (owner's choice; the type's budget is 5 to 6). Microsoft Fabric: Eventhouse
(KQL), Lakehouse, notebooks with Fabric ML, a pipeline, a Direct Lake model and a PBIR report, all held as files in a Git
repository and deployed from it.

## Components (brief section 5)

| # | Component | Status | Evidence |
|---|---|---|---|
| 1 | Workspace `SinarLembah-Dev` deployed from the Git repo | Built | Every item deployed by `deploy_items.py` (fabric-cicd) from the estate folder that is the repository's `fabric/` tree; repo `sinarlembah-fabric-estate` (private) at `9ab11cf` |
| 2 | Variable Library `VL_SinarLembah` | Built | Deployed first in Dev and in wave 0 of the Scratch build |
| 3 | KQL schema, functions, update policies, OneLake availability before the first load | Built | 14 tables, 11 functions, 2 chained update policies (`meter_reading` to `reading_scored` to `reading_alert`), streaming ingestion off on the three stream tables; mirroring on 8 tables before any row |
| 4 | Generator: 13 months, planted anomalies, Malaysian public holidays | Built | KQL `fn_gen` equals the Python oracle at full precision: 455,040 rows, SUM(demand_mw) 1,703,132.743; 64 planted events, 43 planned load transfers, 2026 holidays for Kuala Lumpur and Selangor |
| 5 | Hourly batch replay of the last 7 days through the update policy | Built | 168 batches of 48 rows, each scored and alerted by the update policies as it lands; flat-meter scan per batch |
| 6 | Lakehouse shortcuts to the KQL tables | Built | 8 OneLake shortcuts; the notebooks wait until each shortcut shows the KQL row count (26 to 28 s on the tenant) |
| 7 | `NB_SinarLembah_Gold` | Built | `GOLD_OK`: 172 alert hours, 58 incidents, 15 of 16 matured planted events caught, 0 of 8 control windows hit; input checks against the KQL counts all true |
| 8 | `NB_SinarLembah_Forecast` (route R5) | Built | `FORECAST_OK`: K0 to K7 pass, K8 AutoML did not beat the model on fold 9; model card `00_Brief/MODEL_CARD_MDL_SinarLembah_DayAhead.md` |
| 9 | MLExperiment `EXP_SinarLembah_Forecast` + MLModel `MDL_SinarLembah_DayAhead` | Built | Registered by the notebook (run `fff123e6…`); the daily pipeline adds versions |
| 10 | Pipeline `PL_SinarLembah_Daily` with verdict gates | Built | Full run Completed (12 min); blocked run (`p_block_at = Gold`) Failed with `P37_GOLD_BLOCKED` after Gold, Forecast never started |
| 11 | Direct Lake model `SM_SinarLembah` | Built | 10 tables, 13 relationships, 48 measures (narrative in DAX); BPA gate 0 errors; every table counts equal to its Gold readback; 0 orphan rows on 13 relationships; `INFO.MEASURES()` 0 measures in error |
| 12 | Report `P37_SinarLembah`, five pages | Built | 66 visuals; `validate_pbip.py` 0 errors; official CLI 0.5.0 0 errors (schema unreachable, accepted); inspector 0 errors over 343 checks; captured in the service after three render passes |
| 13 | Deploy from Git into an empty workspace, every definition read back | Built | `SinarLembah-Scratch` from a fresh clone at `9ab11cf`: 3 Bulk Import waves, 9 of 9 repo items, 0 dev ids left, model 10 of 10 tables, 455,040 readings with the same SUM as Dev. Then `PL_SinarLembah_Daily` ran in Scratch (Completed, 11.7 min, both gates passed) and the model framed: every table, recall 15 of 16, 0 control hits, forecast error 5.1693% and tomorrow's peak 232.1 MW, all equal to Dev |
| 14 | Deployment plan with a notebook post-action | Built | `DP_P37_Create`; its post-action ran `NB_SinarLembah_Seed` (Completed in 2 min) and seeded the empty KQL database |
| 15 | Technique library entries | Built | `_ENGINE/reference/ANALYTICS_TECHNIQUES.md`: many-series day-ahead forecast; KQL batch anomaly scoring |
| 16 | Real-Time Dashboard (nice) | Not built | Out of the one-session budget; in `01_Design/NEXT_VERSION.md` |
| 17 | Activator alert (nice) | Not built | Owner: not now |

Brief changes during Build (Rev 4): a third notebook (`NB_SinarLembah_Seed`), a weather table with a day-ahead temperature
forecast, three weak planted events, 12-week baselines, the Forecast group and Detector metric tables.

## Exit criteria (brief section 10)

| Criterion | Result |
|---|---|
| 17 components graded | 15 built, 2 nice-to-haves not built |
| Control totals frozen and matched after a replay | 455,040 rows and 1,703,132.743 MW in Dev and again in Scratch, built from nothing |
| Detector graded by maturity with a control that could refute it | Recall 15 of 16 matured events (the missed one is a weak drop); 0 hits in 8 control windows (planted windows moved by their length plus 7 days) |
| Forecast beats seasonal naive by a paired 95% interval above 0 | Yes. Pooled over feeders: 5.17% against 7.82%, gain 2.65 points (1.81 to 3.56). All feeders, independent `stats_check.py --regression`: 1.31% against 3.07%, gain 1.76 points (1.09 to 2.53), MODEL_BETTER |
| Every report page captured and read against the model | Yes, in the service; measures queried by DAX beside the captures |
| Deploy from Git into an empty workspace passes | Yes (component 13) |
| Deployment plan post-action runs | Yes (component 14) |
| Repo, guide, card live; scrub 0 BLOCK | Publish, below |

## Reviews

| Review | Findings | Outcome |
|---|---|---|
| Design review (G2, independent agent) | Contrast, 12 px floor, slicer scope, answer-key cause kept out of operator tables, previous-7-day comparison, DAX titles | Applied in the report |
| Code review of the notebook modules (independent agent, before the first tenant run) | 3 blockers, 12 fixes | All applied: seeding idempotent with a count check; a failed verdict fails the run; shortcut tables awaited; K0 input completeness; lags joined on the hour; benchmark becomes champion when K2, K3, K4 or K7 fires; K6 acts; K7 hash covers days 332 to 395; pandas 2.1 compatible |
| Statistics check (`stats_check.py --regression`, new) | The all-feeders range held 72% of out-of-sample hours, 95% interval 68% to 76%: too narrow for the name "80% range" | The page states the measured coverage from the model instead of 80% |

## Defects found and fixed during the build

- A variable named `topN` in a DAX measure collided with `TOPN`; the deploy accepted it and the measure became `SYNTAXERROR`.
- `REMOVEFILTERS ( 'Forecast group' )` cleared the date and hour filters through the expanded table; the range summed every day. Column-scoped now.
- Window measures used `MAX ( 'Date'[date] )`; on a weekday axis that picked the forecast day and dropped Monday. They now test the dates in context.
- Render pass 1: scrollbars on 4 text boxes, a blank Direct Lake member row, crowded day and hour axes, two KPI labels wrapping, two tiles below contrast.
- The KQL database item definition refuses `.alter table ... policy mirroring`; the update policies would have scored the backfill twice. The seed sets both, in Dev's order.
- In the Scratch workspace the KQL database's display name was shared with the Eventhouse's default database, so lookups by name failed; the notebooks use the item id.
- Pipeline notebook references now use the Git form for "this workspace" (zero GUID), so Bulk Import resolves them in its payload.
- Pipeline run parameters by the job API are flat (`{"p_block_at": "Gold"}`); the `{value, type}` form was accepted and ignored.

## Known limits

- Synthetic, deterministic data; one year of history, so one cycle of each holiday; no outage data.
- The forecast range is narrower than its name: it held 72% of hours, not 80%. The page says so; K6 should test the interval.
- No per-feature explanation on the page; Real-Time Dashboard and Activator not built.
- The report opens Feeder Detail on all feeders (no proven default slicer selection in PBIR); its title asks for one feeder.
- The substation by day matrix has no colour scale and the range is two lines, not a band (no proven PBIR shapes).
