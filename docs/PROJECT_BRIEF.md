# Project Brief — 37) Grid Demand Forecast and Meter Watch

`Solution type: Data Platform · Data: sample · Delivery: portfolio`
`Start mode: stack given · Brief accepted by the owner: 2026-11-23 (G1)`

Fictional company: **Sinar Lembah Grid Sdn Bhd**, an electricity distributor in the Klang Valley. All data is generated and declared synthetic in the report, the repo and the guide.

## 1. What done looks like
Hourly readings from 48 feeders run through an Eventhouse. Each new hour lands as a batch, and an update policy flags readings that sit far from the feeder's usual load for that hour and day type. Flagged readings go to an alerts table. A Fabric ML notebook trains a day-ahead forecast (24 hours × 48 feeders) on 13 months of history. It is checked by a rolling backtest against a seasonal naive benchmark and an AutoML baseline, registered as an ML model, and its scores are written to Gold. A Direct Lake model and a 5-page report show the alerts and the forecast. The estate lives in Git, deploys from scratch into an empty workspace, and a deployment plan runs the first notebook after the deploy. A public repo, guide and portfolio card are live, and the closure is written.

## 2. Who it is for
Purpose: portfolio piece #8 (Data Platform), and the first full run of the new five-stage process on this solution type.

| Role | Top tasks |
|---|---|
| Control-room engineer | See which feeders raised alerts in the last 24 hours and why (spike, drop, flat reading); open one feeder's recent load against its usual profile |
| Load planner | See tomorrow's hourly demand by substation and feeder with a range, and how far the forecast missed over recent weeks |
| Head of network operations | One page: alert count and trend, peak demand tomorrow, forecast accuracy |

## 3. Questions the solution must answer
1. Which feeders are behaving unusually right now, and what kind of anomaly is it? (Meter Watch)
2. How many alerts did each substation raise over the last 7 days, and are they rising? (Meter Watch)
3. What will demand be tomorrow, hour by hour, per substation and feeder, with a range? (Demand Forecast)
4. How accurate has the day-ahead forecast been, and does it beat a simple same-hour-last-week forecast? (Demand Forecast)
5. For one feeder: recent load, usual profile, alerts and tomorrow's forecast in one view. (Feeder Detail)
6. How good is the detector, measured against the planted events? (Meter Watch, graded by maturity)

## 4. Stack card
| Layer | Block chosen | Why | Status on this tenant (`reference/STACK_MENU.md`) | Probe needed |
|---|---|---|---|---|
| Source | KQL-generated sample data, hourly batches (no Eventstream; owner 2026-11-23) | The "stream" is hour-by-hour batch appends; no Windows replay notebook | Generator pattern proven (P27, P30, P34); KQL `.set-or-append` from a session: PR2 | yes: PR2 |
| Store (hot) | Eventhouse `EH_SinarLembah` + KQL database | Owner's stack; time-series functions, update policies | proven (P25, P30); this session: KQL reads by the connector by cluster URL, writes through the Windows runner | yes: PR1, PR2 |
| Detect | Update policy with a lookup into a baseline table, streaming ingestion off (S086) | Alerts land as each batch arrives | proven in P30 (S086); PR3 here | yes: PR3 |
| Store (cold) | Lakehouse `LH_SinarLembah`, OneLake shortcuts to the KQL tables (OneLake availability) | One copy of the data; Spark and Direct Lake read Delta | proven (P25 pattern); PR4 here | yes: PR4 |
| Analytics | Fabric ML, Skill 3 route R5: notebook, MLExperiment, MLModel, AutoML (FLAML) baseline, `stats_check.py` | Owner's stack; first R5 project | proven pieces (S154, S211, S217); never one project end to end | yes: PR5 (notebook run route) |
| Orchestration | Pipeline with a verdict gate per notebook | Proven shape | proven (S179) | no |
| Model | Direct Lake on OneLake over the Lakehouse | Owner's stack | proven (P30, P34) | no (checked in Build by `ri_probe.py`) |
| Report | PBIR, Skill 1, `lib/pbir_kit`, LEGO theme, 3 content pages + Home + Report Guide | Owner's answer 2026-11-23 | proven | no |
| Ops | Git integration (GitHub), Variable Library, deploy from Git into an empty workspace, deployment plan for the step after | Build exit (S207) and the review's test | proven (S207, S250) | yes: PR6 (Git connection) |
| Channels | Eventhouse MCP (reads), Core MCP, DW MCP, Windows runner `_probe/p37_20261123/p37_runner.py` (Fabric REST, Kusto mgmt, OneLake upload, notebook runs) | Cowork cannot reach Fabric REST or Kusto mgmt (S015, S079); the runner is started once by computer use | runner new this session; its routes are the proven Windows ones (S079, S080) | yes: PR1, PR2 |

**SETTLED domains to read every session:** FAB, MOD, RPT, HOST.

## 5. Components
| # | Component | Must-have or nice-to-have | Stage 3 workstream | Built? (filled at Publish) |
|---|---|---|---|---|
| 1 | Workspace `SinarLembah-Dev` deployed from the Git repo (Rev 2) | must | data | |
| 2 | Variable Library `VL_SinarLembah` (deployed first) | must | data | |
| 3 | KQL schema: `feeder`, `meter_reading`, `baseline_profile`, `reading_alert`, `planted_event`; functions; update policy; OneLake availability on before the first load | must | data | |
| 4 | Generator (KQL script): 13 months of history, planted anomalies, Malaysian public holidays | must | data | |
| 5 | Hourly batch replay of the last 7 days through the update policy | must | data | |
| 6 | Lakehouse shortcuts to the KQL tables | must | data | |
| 7 | `NB_SinarLembah_Gold`: date table, daily feeder summary, detector grading by maturity | must | data | |
| 8 | `NB_SinarLembah_Forecast` (R5): features, seasonal naive, gradient boosting, AutoML baseline, rolling backtest, paired interval, model card | must | analytics | |
| 9 | MLExperiment `EXP_SinarLembah_Forecast` + MLModel `MDL_SinarLembah_DayAhead` | must | analytics | |
| 10 | Pipeline `PL_SinarLembah_Daily` (Gold, then Forecast, verdict gates) | must | data | |
| 11 | Direct Lake model `SM_SinarLembah` | must | model | |
| 12 | Report `P37_SinarLembah`: Home, Meter Watch, Demand Forecast, Feeder Detail, Report Guide | must | report | |
| 13 | Deploy from Git into an empty scratch workspace, every definition read back | must | ops | |
| 14 | Deployment plan: notebook run as the post-action of the deploy | must | ops | |
| 15 | Technique library entries: hour-of-week baseline anomaly, day-ahead gradient boosting with lags | must | analytics | |
| 16 | Real-Time Dashboard | nice-to-have | — | |
| 17 | Activator alert | nice-to-have (owner: not now) | — | |

Notebook cap: **2**. A third is a brief change and gets written down as one.

## 6. Constraints
Host: Cowork, one session (owner, 2026-11-23: "start p37 in single session"). The budget for a Data Platform is 5 to 6. The session splits only where this brief records the owner's yes.
Capacity: trial FTL64, Malaysia West (`14e682a7…`). Trial expiry is not a planning factor (S048). Free tooling only.
Wording: plain, short, no AI-looking patterns. Narrative lives in DAX-driven titles and subtitles, and no measure hardcodes a number (owner, 2026-11-06). Malaysian utility terms are checked against real usage before they reach a page (owner preference).
Windows steps: one runner started by computer use; every later Windows step is a queued task, logged in `RUNNER_LOG.txt`.

## 7. Data
`sample`: Sinar Lembah Grid Sdn Bhd (fictional). 8 main distribution substations, PPU (fictional names, Klang Valley districts; Rev 4: 'main intake' corrected), 48 feeders of four types (residential, commercial, industrial, mixed), hourly demand in MW.
Period: 2025-10-24 00:00 to 2026-11-22 23:00 MYT (395 days, 9,480 hours). Rows: 48 × 9,480 = 455,040 (Rev 3). The last 7 days (2026-11-16 to 2026-11-22) arrive hour by hour as batches (168 batches × 48 rows). The day-ahead forecast is for 2026-11-23.
Shape: daily and weekly cycles by feeder type; weather-driven afternoon peaks with a seasonal trend; Malaysian public holidays and festive weeks lower commercial and industrial load. Hash-based noise, so the data is deterministic and a rebuild gives identical totals.
Planted anomalies (ground truth in `planted_event`, never read by the detector): meter spikes, drops, flat readings (stuck meter), and a slow drift on two feeders. Detector thresholds keep a margin from the generator's parameters and are never tuned to the planted events.
Control totals are frozen by query in Build (row count, SUM of demand_mw at full precision).

## 8. Probes (run in Discover, before any build)
| Probe | What it proves | How it is measured | Depends on | Result | Fallback or kill decision |
|---|---|---|---|---|---|
| PR0 Cost capture | The usage skill works in this host | Snapshot JSON committed to `_sessions/_cost/` | — | PASS: `S1_G0_usage.json` (21 requests) | — |
| PR1 Runner + KQL reach | Fabric REST and KQL reach the new database | Runner token check and Eventhouse GET (queryServiceUri); connector `.show tables` by cluster URL; unknown table gives a named error | runner started by computer use | PASS 07:50–07:51 MYT. Finding: the connector refuses control commands through the query endpoint | KQL writes go through `kusto_run.py` on the runner |
| PR2 KQL write | `.set-or-append` lands rows | 1,000 rows, 48 feeders written; read back by a second route (connector): 1,000 / 48 / 2,512.436 | PR1 | PASS | — |
| PR3 Update policy with lookup | Alerts land per batch through a lookup into a baseline, streaming off | 48-row batch appended; 2 alert rows by the policy | PR2 | PASS (mechanism). Finding: `hourofday()` is `long`; a type mismatch on `.set-or-replace` gives a bare BadRequest | Baseline covers every feeder × hour × day-type cell |
| PR4 OneLake availability + shortcut + reads | Lakehouse reads the KQL table by SQL and Spark | Shortcut by REST through the runner (Core MCP: InsufficientScopes); SQL COUNT after refreshMetadata | PR2 | PASS: table with availability on BEFORE its load reads 1,048 / 48 / 2,722.436 by SQL, same as KQL, about 2 min after the write at 5-minute latency. Control: the table switched on AFTER its load reads 0 rows (no backfill; `.alter-merge ... Backfill=true` on an enabled policy is refused) | Availability and `TargetLatencyInMinutes=5` are set at table creation, before any load |
| PR5 Notebook run from the session | A notebook runs and returns its exit value | Runner `runnb`: job Completed, exitValue verdict read back | runner, PR4 | PASS: `ZZ_NB_P37_Probe` created by Core MCP (ipynb), run by the runner, Completed in 77 s; exitValue PROBE_OK, 1,048 rows, 2,722.436, a module uploaded to `Files/` by the runner (`onelake_put.py`, 201/202/200) read back | — |
| PR6 Git connection | Workspace connects to a GitHub repo | Fabric Git connect by REST with an existing GitHub connection | repo `BIVenture2025/sinarlembah-fabric-estate` (private, created in Chrome) | FAIL: `ConnectionMismatch`. Each GitHub connection is bound to one repo URL (4 read); a new one needs a GitHub token entered, which Claude does not do | Owner decision G1: (a) owner adds a GitHub connection for the new repo, or (b) repo-first: the estate is authored as files, pushed from the session, and deployed to Dev and to the scratch workspace by `deploy_items.py`; no workspace-side Git sync |
| Connector and DLP | No Power Platform connector on the stack | — | — | not applicable | — |

## 9. Session plan
Budget by type: Data Platform 5 to 6. **Owner instruction 2026-11-23: one session.** Usage is captured at every gate (and after any summary, as a segment, S271).

| # | Part | Stage and work | Model | Ends when |
|---|---|---|---|---|
| 1 | G1 | Discover: probes, brief | Opus | Owner accepts the brief |
| 1 | G2 | Design: Design Package (mockups of 5 pages, architecture, model design sheet, measure contracts, tests), subagent audit | Opus | Owner approves the package |
| 1 | G3 | Build: KQL, generator, replay, shortcuts, notebooks, ML, pipeline, model, report, deploy from Git, deployment plan | Opus (owner's one-session choice; Build would otherwise be Sonnet) | Every exit check of Skills 8, 1, 3, 12 passes |
| 1 | G4 | Publish (Skill 9) | Opus | Links checked from outside |
| 1 | G5 | Close (Skill 10), handover, next kickoff, `session_close.py` | Opus | Ledger row, lessons dual-written |

Hard stop: this session. If context or time runs out first, the handover names the gate reached and the next part.

## 10. Exit criteria and review
- [ ] 17 components graded built or not built (counts from §5)
- [ ] Control totals frozen and matched after a replay (S029)
- [ ] Detector graded by maturity with a control that could refute it; no circular grading
- [ ] Forecast beats seasonal naive by a paired 95% interval above 0 (`stats_check.py`), or the page says it does not
- [ ] Every report page captured and read against the model
- [ ] Deploy from Git into an empty workspace passes (S207)
- [ ] Deployment plan post-action runs
- [ ] Repo, guide, card live; scrub 0 BLOCK
Second-agent review: the forecast backtest and the detector grading (scoring and loss logic).

## 11. Revision log
| Rev | Date | What changed and who decided |
|---|---|---|
| 1 | 2026-11-23 | Brief written. Probes PR0 to PR5 PASS, PR6 FAIL (fallback offered). Owner answers (07:2x MYT): name Sinar Lembah Grid; 48 feeders, 13 months; KQL hourly batches with an alerts table (no Eventstream, no Activator); LEGO theme, 3 content pages. One session (owner). |
| 2 | 2026-11-23 | G1: owner accepted the brief. PR6 fallback (b) chosen by the owner: repo-first, no workspace-side Git sync. The estate is files in `sinarlembah-fabric-estate` (private), pushed from the session; Dev and the scratch workspace are deployed from the repo by `deploy_items.py`. Component 1 reads "Workspace `SinarLembah-Dev` deployed from the Git repo". |
| 3 | 2026-11-23 | Data period corrected: 395 days, 9,480 hours, 455,040 rows (Rev 1 said 396). G2: owner approved the Design Package ("Go", 08:21 MYT) as summarised in chat, before the independent review table was in; review findings are applied during Build and listed in the handover. Scope frozen from here: components 1 to 15; 16 and 17 in `01_Design/NEXT_VERSION.md`. Build runs on Opus in this session (owner's one-session choice). |
| 4 | 2026-11-23 | Build decisions (Claude, inside the frozen scope; no owner question needed). (a) A third notebook `NB_SinarLembah_Seed` builds the KQL schema and generates the data in an empty workspace; it is the deployment plan's post-action for the Build exit. (b) `weather_hourly` (actual and day-ahead forecast temperature) added as a KQL table and shortcut, so the forecast never reads the actual temperature. (c) Three weak planted events (E062 to E064) added for the detector's recall by strength. (d) Usual load = 12 weeks before (Design said 8), baselines B1 and B2 with validity ranges. (e) Model: 10 tables (Forecast group and Detector metric added), 13 relationships, no UDFs, 48 measures with the titles in DAX. (f) Report bound byPath to the model, so a deploy from Git needs no model id. (g) Second code review (2026-11-23) applied to the notebooks: seeding idempotent with no early return and a count check; a failed verdict fails the run; shortcut tables waited on until they match the KQL counts; K0 checks the inputs are complete; lags join on the hour; the benchmark becomes champion whenever K2, K3, K4 or K7 fires; K6 acts. (h) An incident is a run of alerts in back-to-back hours (one quiet hour ends it). |
