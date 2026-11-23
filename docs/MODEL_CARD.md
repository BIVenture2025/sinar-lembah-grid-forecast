# Model card — MDL_SinarLembah_DayAhead (P37 Sinar Lembah Grid, 2026-11-23)

One page per model that reaches a report page or a Gold table (template `_ENGINE/templates/analytics/MODEL_CARD_TEMPLATE.md`,
W4 A2). The template is written for a classifier; this model is a regression, so AUC, event rate and calibration become
WAPE, the benchmark and range coverage. Every **(run)** figure is the tenant run of `NB_SinarLembah_Forecast` on
2026-11-23 (MLflow run `fff123e6-e3ed-4cb0-8343-fa0c73cbd0c9`, verdict `FORECAST_OK`). The data is synthetic.

| Field | Content |
|---|---|
| What it predicts | Hourly demand in MW for each of 48 feeders for the next day (24 hours), issued after the day's last hourly batch. |
| Who uses it, for what | The control room's day-ahead view: tomorrow's peak, its hour and the load by substation, to plan switching and spot a substation running close to its limit. Not for billing, tariff design or a long-range capacity plan. |
| Population | All 48 feeders of the 8 main distribution substations (PPU). Hours with an alert on that feeder are left out of training, so a stuck meter or a planted spike does not teach the model. |
| Training window · test window | **(run)** Nine weekly folds from 21 Sep to 22 Nov 2026; each fold is fitted on everything before it (from day 28, when the 4-week lag exists) and tested on the next 7 days. The final model is fitted on all days to 22 Nov and forecasts 23 Nov. |
| Rows | **(run)** 72,576 backtest feeder-hours (48 × 1,512); 1,152 forecast-day rows; group tables 13,824 rows. K0 input checks all true: one row per feeder-hour, 455,040 readings, weather and calendar cover the forecast day. |
| Features | **(run)** lag 24 h (known at issue time), lag 168 h, mean of the same hour over the last 4 weeks, hour, weekday, day type, public holiday, festive week, feeder type, feeder number, and the day-ahead FORECAST temperature (never the actual). Lags join on the hour, not the row position. |
| Leakage check | **(run)** K2: no fold below 2% WAPE (an error that low would mean leakage). K7: the features hash over days 332 to 395 equals the offline replay's (`63a2fc16…`), so the tenant fed the model exactly the features the offline test saw. |
| Hold-out result | **(run)** Pooled WAPE over the 9 weeks: model 5.17%, same hour last week 7.82%. |
| Comparison | **(run)** Gain 2.65 points (pooled over feeders), weekly block bootstrap 95% interval 1.81 to 3.56 (above zero: K4 passes). Without holiday-affected days: 1.77 points (1.68 to 1.83). K8: AutoML (FLAML, extra trees, 300 s) on the last fold 5.42% against the model's 5.43%, so the model holds and AutoML is noted as a near-equal challenger. At the all-feeders level the independent check (`stats_check.py --regression`, 9 weekly blocks) gives model 1.31% against 3.07%, gain 1.76 points, 95% interval 1.09 to 2.53: MODEL_BETTER. The page states the model's error beside the benchmark's. |
| Calibration (ranges) | **(run)** Ranges from each level's own relative residual quantiles (10th and 90th percentile) by hour, fitted on folds 1 to 6 and checked on folds 7 to 9: coverage feeder 78.7%, substation 77.5%, all feeders 72.0%. K6 (band 70% to 90%) passes, so no widening factor was applied. **The independent check disagrees:** `stats_check.py --regression` gives the all-feeders coverage a Wilson 95% interval of 67.9% to 75.8%, which excludes 80%, so the range is too narrow for the name "80% range". The page therefore states the measured coverage (from `gold_model_metric`) instead of a nominal 80%. Next version: K6 tests the coverage interval, not the point. |
| Explanation shown to users | The forecast with its range, the benchmark's error beside the model's, and the gain with its interval. No per-feature attribution on the page in V1. |
| Refresh plan | `PL_SinarLembah_Daily` runs Gold, then this notebook, with a verdict gate after each. Every run re-fits, re-checks K0 to K8 and writes Gold only on `FORECAST_OK`; it registers a new model version only when K2, K3 and K7 pass. |
| Monitoring | The daily backtest error and the system range coverage are in `gold_model_metric`; a run whose verdict is not OK fails the pipeline (`P37_FORECAST_BLOCKED`) and keeps yesterday's tables. Reopen the model if the gain's interval touches zero on two runs in a row. |
| Limits | Synthetic data from a deterministic generator; one year of history, so one cycle of each holiday; no outage or restoration data; the temperature forecast is synthetic. The ranges are narrow because the generator's noise is narrow; on real meters expect wider ranges. |
| Kill criteria that fired | None on 2026-11-23. Champion rule: the benchmark (same hour last week) takes over, with ranges from its own residuals, whenever K2, K3, K4 or K7 fires. |
| Registered as | MLflow experiment `EXP_SinarLembah_Forecast`, model `MDL_SinarLembah_DayAhead`, version 1 from run `fff123e6-e3ed-4cb0-8343-fa0c73cbd0c9` in SinarLembah-Dev; daily pipeline runs add versions. |
