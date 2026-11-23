"""build_model.py - P37 SM_SinarLembah: Direct Lake on OneLake over LH_SinarLembah (no schemas), written as TMDL.

Shape from P34's and P30's delivered models (expressions.tmdl, entity partitions, compatibilityLevel 1606).
Our Lakehouse has no schemas, so partitions carry entityName only (probe: the first refresh and a DAX count per table).
CRLF on every .tmdl (non-negotiable 1). Measures follow the contracts in the Design Package (S108).
Differences from the approved model sheet (decision lines in the brief, Rev 4): + Forecast group (group ranges, review
item 8) + Detector metric (grading figures), 13 relationships; no UDFs (Cut-off is a measure; level stays 1606).
"""
import os, sys, uuid

OUT = sys.argv[1] if len(sys.argv) > 1 else "estate/fabric"
WS = "aaaaaaaa-0000-4000-8000-000000000001"; LH = "aaaaaaaa-0000-4000-8000-000000000002"
M = os.path.join(OUT, "SM_SinarLembah.SemanticModel")
NS = uuid.UUID("37a00000-0000-4000-8000-0000000000ff")
EXPR = "DirectLake - LH_SinarLembah"


def tag(*k):
    return str(uuid.uuid5(NS, "/".join(k)))


S, I, D, DT, B = "string", "int64", "double", "dateTime", "boolean"
TABLES = {
    "Reading": ("reading_scored", "Hourly readings scored against the usual load, 21 Sep to 22 Nov 2026 (KQL table reading_scored).", [
        ("feeder_id", S, 1), ("reading_hour", DT, 0), ("reading_date", DT, 1), ("hour_of_day", I, 1), ("hour_index", I, 1), ("demand_mw", D, 1),
        ("day_type", S, 0), ("usual_mw", D, 1), ("spread_mw", D, 1), ("z", D, 1), ("switch_id", S, 1), ("baseline_id", S, 1), ("batch_id", S, 1)]),
    "Alert": ("gold_alert", "One row per alert hour; incidents group consecutive hours on one feeder.", [
        ("alert_id", S, 1), ("incident_id", S, 1), ("feeder_id", S, 1), ("reading_hour", DT, 0), ("reading_date", DT, 1), ("hour_of_day", I, 1),
        ("hour_index", I, 1), ("alert_type", S, 0), ("incident_type", S, 0), ("incident_hours", I, 0), ("is_incident_start", B, 1), ("z", D, 0),
        ("demand_mw", D, 0), ("usual_mw", D, 0), ("spread_mw", D, 1), ("switch_id", S, 0), ("cause", S, 0), ("event_id", S, 1), ("grade_cause", S, 0),
        ("is_matured", B, 1), ("source", S, 0), ("batch_id", S, 1)]),
    "Forecast": ("gold_forecast_hourly", "Feeder-hour forecasts: 63 backtest days and the forecast day.", [
        ("feeder_id", S, 1), ("target_date", DT, 1), ("hour_of_day", I, 1), ("target_hour", DT, 0), ("hour_index", I, 1), ("forecast_mw", D, 1),
        ("lo_mw", D, 1), ("hi_mw", D, 1), ("naive_mw", D, 1), ("actual_mw", D, 1), ("fold", I, 1), ("is_backtest", B, 1), ("model_name", S, 0), ("run_id", S, 1)]),
    "Forecast group": ("gold_forecast_group", "Substation and system forecasts with ranges from their own backtest residuals.", [
        ("group_key", S, 1), ("target_date", DT, 1), ("hour_of_day", I, 1), ("target_hour", DT, 1), ("hour_index", I, 1), ("fold", I, 1),
        ("is_backtest", B, 1), ("forecast_mw", D, 1), ("naive_mw", D, 1), ("actual_mw", D, 1), ("lo_mw", D, 1), ("hi_mw", D, 1), ("level", S, 1)]),
    "Planted event": ("gold_event_grade", "The anomalies the generator planted, graded: matured, caught, alerts.", [
        ("event_id", S, 0), ("feeder_id", S, 1), ("event_type", S, 1), ("event_label", S, 0), ("strength", S, 0), ("start_hour", DT, 0), ("end_hour", DT, 0),
        ("start_date", DT, 1), ("start_index", I, 1), ("end_index", I, 1), ("duration_h", I, 0), ("factor", D, 1), ("in_window", B, 1),
        ("is_matured", B, 1), ("is_caught", B, 0), ("alerts_n", I, 0), ("first_alert_lag_h", D, 0)]),
    "Model metric": ("gold_model_metric", "Forecast metrics from the backtest, with intervals.", [
        ("metric", S, 0), ("model", S, 0), ("value", D, 1), ("ci_low", D, 1), ("ci_high", D, 1), ("n", I, 1), ("scope", S, 0), ("run_id", S, 1)]),
    "Detector metric": ("gold_detector_metric", "Detector grading figures and the control.", [
        ("metric", S, 0), ("value", D, 1), ("n", I, 1), ("note", S, 0), ("cutoff", DT, 1)]),
    "Feeder": ("feeder", "48 feeders and their main distribution substation (KQL table feeder).", [
        ("feeder_id", S, 0), ("feeder_no", I, 1), ("feeder_name", S, 0), ("substation_id", S, 1), ("substation_name", S, 0), ("district", S, 0),
        ("feeder_type", S, 0), ("type_code", S, 1), ("rated_peak_mw", D, 0)]),
    "Date": ("gold_dim_date", "Calendar 24 Oct 2025 to 23 Nov 2026 with day type and public holidays (KL and Selangor).", [
        ("date", DT, 0), ("day_index", I, 1), ("day_type", S, 0), ("holiday_name", S, 0), ("is_holiday", B, 0), ("is_festive_week", B, 0),
        ("weekday_name", S, 0), ("weekday_no", I, 1), ("day_label", S, 0), ("week_start", DT, 0), ("month_start", DT, 1), ("month_label", S, 0)]),
    "Hour": ("gold_dim_hour", "24 hours of the day.", [("hour_of_day", I, 0), ("hour_label", S, 0), ("period", S, 0)]),
}
SORT = {("Date", "day_label"): "date", ("Date", "weekday_name"): "weekday_no", ("Date", "month_label"): "month_start",
        ("Hour", "hour_label"): "hour_of_day", ("Feeder", "feeder_name"): "feeder_no"}
FMT = {D: "#,0.00", I: "0", DT: "dd mmm yyyy hh:nn"}
RELS = [("Reading", "feeder_id", "Feeder", "feeder_id"), ("Reading", "reading_date", "Date", "date"), ("Reading", "hour_of_day", "Hour", "hour_of_day"),
        ("Alert", "feeder_id", "Feeder", "feeder_id"), ("Alert", "reading_date", "Date", "date"), ("Alert", "hour_of_day", "Hour", "hour_of_day"),
        ("Forecast", "feeder_id", "Feeder", "feeder_id"), ("Forecast", "target_date", "Date", "date"), ("Forecast", "hour_of_day", "Hour", "hour_of_day"),
        ("Forecast group", "target_date", "Date", "date"), ("Forecast group", "hour_of_day", "Hour", "hour_of_day"),
        ("Planted event", "feeder_id", "Feeder", "feeder_id"), ("Planted event", "start_date", "Date", "date")]

# measures: (table, name, dax, format, folder, description)
MEAS = [
    ("Reading", "Cut-off", "CALCULATE ( MAX ( Reading[reading_hour] ), REMOVEFILTERS () )", "dd mmm yyyy hh:nn", "Base", "Last reading hour in the model; every 'last 24 hours' figure counts back from it."),
    ("Reading", "Demand MW", "SUM ( Reading[demand_mw] )", "#,0.0", "Load", "Sum of hourly demand for the selection; at one hour it is MW, over a day it is MWh."),
    ("Reading", "Usual MW", "SUM ( Reading[usual_mw] )", "#,0.0", "Load", "Sum of the usual load (median for the feeder, hour and day type over the 12 weeks before)."),
    ("Reading", "Peak demand MW", "MAXX ( VALUES ( Reading[reading_hour] ), [Demand MW] )", "#,0.0", "Load", "Highest hourly sum for the selection: the max of hourly sums, not the sum of peaks."),
    ("Alert", "Alert hours", "COUNTROWS ( Alert )", "#,0", "Alerts", "Feeder-hours with an alert."),
    ("Alert", "Incidents", "DISTINCTCOUNT ( Alert[incident_id] )", "#,0", "Alerts", "Runs of alerts on one feeder in back-to-back hours; one quiet hour ends an incident."),
    ("Alert", "Incidents last 24 h", "VAR c = [Cut-off]\n\t\t\tRETURN\n\t\t\t\tCOALESCE ( CALCULATE ( [Incidents], Alert[reading_hour] > c - 1, REMOVEFILTERS ( 'Date' ) ), 0 )", "#,0", "Alerts", "Incidents with an alert hour in the 24 hours up to the cut-off."),
    ("Alert", "Incidents last 7 days", "VAR c = [Cut-off]\n\t\t\tRETURN\n\t\t\t\tCOALESCE ( CALCULATE ( [Incidents], Alert[reading_hour] > c - 7, REMOVEFILTERS ( 'Date' ) ), 0 )", "#,0", "Alerts", "Incidents with an alert hour in the 7 days up to the cut-off."),
    ("Alert", "Incidents previous 7 days", "VAR c = [Cut-off]\n\t\t\tRETURN\n\t\t\t\tCOALESCE ( CALCULATE ( [Incidents], Alert[reading_hour] > c - 14, Alert[reading_hour] <= c - 7, REMOVEFILTERS ( 'Date' ) ), 0 )", "#,0", "Alerts", "Incidents in the 7 days before the last 7."),
    ("Alert", "Alert hours last 7 days", "VAR c = [Cut-off]\n\t\t\tRETURN\n\t\t\t\tCALCULATE ( [Alert hours], Alert[reading_hour] > c - 7, REMOVEFILTERS ( 'Date' ) )", "#,0", "Alerts", "Alert hours in the last 7 days."),
    ("Alert", "Feeders with alerts 7 days", "VAR c = [Cut-off]\n\t\t\tRETURN\n\t\t\t\tCOALESCE ( CALCULATE ( DISTINCTCOUNT ( Alert[feeder_id] ), Alert[reading_hour] > c - 7, REMOVEFILTERS ( 'Date' ) ), 0 )", "#,0", "Alerts", "Feeders with any alert in the last 7 days."),
    ("Alert", "Switching share 7 days", "VAR c = [Cut-off]\n\t\t\tVAR sw = CALCULATE ( [Alert hours], Alert[cause] = \"Planned switching\", Alert[reading_hour] > c - 7, REMOVEFILTERS ( 'Date' ) )\n\t\t\tRETURN\n\t\t\t\tDIVIDE ( sw, [Alert hours last 7 days] )", "0%", "Alerts", "Share of last-7-day alert hours that a logged load transfer covers."),
    ("Planted event", "Events matured", "COALESCE ( CALCULATE ( COUNTROWS ( 'Planted event' ), 'Planted event'[in_window] = TRUE (), 'Planted event'[is_matured] = TRUE () ), 0 )", "#,0", "Detector", "Planted events in the grading window that ended at least a day before the cut-off."),
    ("Planted event", "Events caught", "COALESCE ( CALCULATE ( COUNTROWS ( 'Planted event' ), 'Planted event'[in_window] = TRUE (), 'Planted event'[is_matured] = TRUE (), 'Planted event'[is_caught] = TRUE () ), 0 )", "#,0", "Detector", "Matured events with at least one alert inside the event window."),
    ("Planted event", "Recall", "DIVIDE ( [Events caught], [Events matured] )", "0%", "Detector", "Events caught over events matured; matured only, never blended with young events."),
    ("Alert", "Planted share of alert hours", "VAR m = CALCULATE ( [Alert hours], Alert[is_matured] = TRUE () )\n\t\t\tVAR p = CALCULATE ( [Alert hours], Alert[is_matured] = TRUE (), Alert[grade_cause] = \"Planted event\" )\n\t\t\tRETURN\n\t\t\t\tDIVIDE ( p, m )", "0%", "Detector", "Matured alert hours that fall inside a planted event (precision against the answer key)."),
    ("Detector metric", "Control hits", "CALCULATE ( SUM ( 'Detector metric'[value] ), 'Detector metric'[metric] = \"Control hits\" )", "#,0", "Detector", "Control windows (planted windows moved later) that drew any alert."),
    ("Detector metric", "Control windows", "CALCULATE ( SUM ( 'Detector metric'[value] ), 'Detector metric'[metric] = \"Control windows\" )", "#,0", "Detector", "Number of control windows checked."),
    ("Forecast", "Forecast day", "CALCULATE ( MAX ( Forecast[target_date] ), REMOVEFILTERS () )", "dd mmm yyyy", "Base", "The day the latest forecast is for."),
    ("Forecast", "Forecast MW", "SUM ( Forecast[forecast_mw] )", "#,0.0", "Forecast", "Sum of feeder forecasts for the selection."),
    ("Forecast", "Actual MW", "SUM ( Forecast[actual_mw] )", "#,0.0", "Forecast", "Sum of actual load on backtest rows."),
    ("Forecast", "Same hour last week MW", "SUM ( Forecast[naive_mw] )", "#,0.0", "Forecast", "The benchmark: the reading one week earlier."),
    ("Forecast", "Tomorrow MWh", "VAR d = [Forecast day]\n\t\t\tRETURN\n\t\t\t\tCALCULATE ( [Forecast MW], Forecast[target_date] = d, REMOVEFILTERS ( 'Date' ) )", "#,0", "Forecast", "Forecast energy for the forecast day."),
    ("Forecast", "Tomorrow peak MW", "VAR d = [Forecast day]\n\t\t\tRETURN\n\t\t\t\tCALCULATE ( MAXX ( VALUES ( Hour[hour_of_day] ), [Forecast MW] ), Forecast[target_date] = d, REMOVEFILTERS ( 'Date' ) )", "#,0.0", "Forecast", "Highest hourly forecast for the selection on the forecast day."),
    ("Forecast", "Tomorrow peak hour", "VAR d = [Forecast day]\n\t\t\tVAR t = CALCULATETABLE ( ADDCOLUMNS ( VALUES ( Hour[hour_of_day] ), \"@mw\", [Forecast MW] ), Forecast[target_date] = d, REMOVEFILTERS ( 'Date' ) )\n\t\t\tVAR pk = MAXX ( t, [@mw] )\n\t\t\tRETURN\n\t\t\t\tMINX ( FILTER ( t, [@mw] = pk ), Hour[hour_of_day] )", "0", "Forecast", "Hour of the peak on the forecast day; ties take the earliest hour."),
    ("Forecast", "Range low MW", "VAR nF = DISTINCTCOUNT ( Feeder[feeder_id] )\n\t\t\tVAR nS = DISTINCTCOUNT ( Feeder[substation_id] )\n\t\t\tRETURN\n\t\t\t\tSWITCH (\n\t\t\t\t\tTRUE (),\n\t\t\t\t\tnF = 1, SUM ( Forecast[lo_mw] ),\n\t\t\t\t\tnF = 48, CALCULATE ( SUM ( 'Forecast group'[lo_mw] ), REMOVEFILTERS ( 'Forecast group'[group_key], 'Forecast group'[level], 'Forecast group'[fold], 'Forecast group'[is_backtest] ), 'Forecast group'[level] = \"System\" ),\n\t\t\t\t\tnS = 1 && nF = 6, CALCULATE ( SUM ( 'Forecast group'[lo_mw] ), REMOVEFILTERS ( 'Forecast group'[group_key], 'Forecast group'[level], 'Forecast group'[fold], 'Forecast group'[is_backtest] ), 'Forecast group'[level] = \"Substation\", TREATAS ( VALUES ( Feeder[substation_id] ), 'Forecast group'[group_key] ) )\n\t\t\t\t)", "#,0.0", "Forecast", "Low end of the range (10th to 90th percentile of past relative misses) for one feeder, one substation or all feeders; blank for other selections."),
    ("Forecast", "Range high MW", "VAR nF = DISTINCTCOUNT ( Feeder[feeder_id] )\n\t\t\tVAR nS = DISTINCTCOUNT ( Feeder[substation_id] )\n\t\t\tRETURN\n\t\t\t\tSWITCH (\n\t\t\t\t\tTRUE (),\n\t\t\t\t\tnF = 1, SUM ( Forecast[hi_mw] ),\n\t\t\t\t\tnF = 48, CALCULATE ( SUM ( 'Forecast group'[hi_mw] ), REMOVEFILTERS ( 'Forecast group'[group_key], 'Forecast group'[level], 'Forecast group'[fold], 'Forecast group'[is_backtest] ), 'Forecast group'[level] = \"System\" ),\n\t\t\t\t\tnS = 1 && nF = 6, CALCULATE ( SUM ( 'Forecast group'[hi_mw] ), REMOVEFILTERS ( 'Forecast group'[group_key], 'Forecast group'[level], 'Forecast group'[fold], 'Forecast group'[is_backtest] ), 'Forecast group'[level] = \"Substation\", TREATAS ( VALUES ( Feeder[substation_id] ), 'Forecast group'[group_key] ) )\n\t\t\t\t)", "#,0.0", "Forecast", "High end of the range; same rule as the low end."),
    ("Forecast", "Forecast error", "VAR e = CALCULATE ( SUMX ( Forecast, ABS ( Forecast[actual_mw] - Forecast[forecast_mw] ) ), Forecast[is_backtest] = TRUE () )\n\t\t\tVAR a = CALCULATE ( [Actual MW], Forecast[is_backtest] = TRUE () )\n\t\t\tRETURN\n\t\t\t\tDIVIDE ( e, a )", "0.0%", "Forecast", "Pooled WAPE over backtest rows: total absolute miss over total actual."),
    ("Forecast", "Same hour last week error", "VAR e = CALCULATE ( SUMX ( Forecast, ABS ( Forecast[actual_mw] - Forecast[naive_mw] ) ), Forecast[is_backtest] = TRUE () )\n\t\t\tVAR a = CALCULATE ( [Actual MW], Forecast[is_backtest] = TRUE () )\n\t\t\tRETURN\n\t\t\t\tDIVIDE ( e, a )", "0.0%", "Forecast", "Pooled WAPE of the benchmark over the same rows."),
    ("Forecast", "Gain pts", "VAR m = [Forecast error]\n\t\t\tVAR n = [Same hour last week error]\n\t\t\tRETURN\n\t\t\t\tIF ( NOT ISBLANK ( m ) && NOT ISBLANK ( n ), ( n - m ) * 100 )", "0.0", "Forecast", "Benchmark error minus model error, in percentage points."),
    ("Model metric", "Gain interval low", "IF ( DISTINCTCOUNT ( Feeder[feeder_id] ) = 48, CALCULATE ( SUM ( 'Model metric'[ci_low] ), 'Model metric'[metric] = \"Gain, points\" ) )", "0.0", "Forecast", "Low end of the 95% weekly block bootstrap interval of the gain; all feeders only."),
    ("Model metric", "Gain interval high", "IF ( DISTINCTCOUNT ( Feeder[feeder_id] ) = 48, CALCULATE ( SUM ( 'Model metric'[ci_high] ), 'Model metric'[metric] = \"Gain, points\" ) )", "0.0", "Forecast", "High end of the 95% interval of the gain; all feeders only."),
    ("Model metric", "System range coverage", "CALCULATE ( SUM ( 'Model metric'[value] ), 'Model metric'[metric] = \"Range coverage\", 'Model metric'[model] = \"System\" )", "0%", "Forecast", "Share of backtest hours (folds 7 to 9, out of sample) inside the all-feeders range; the range aims at 80%."),
]


def _m(*lines):
    return "\n\t\t\t".join(lines)


# Page measures and the narrative (owner rule: no number typed into report text; titles are DAX). Added in Build, 2026-11-23.
MEAS += [
    ("Alert", "Alert hours, last 30 days", _m("VAR c = [Cut-off]", "VAR win = FILTER ( VALUES ( 'Date'[date] ), 'Date'[date] > c - 30 && 'Date'[date] <= c )", "RETURN",
         "\tIF ( NOT ISEMPTY ( win ), COALESCE ( CALCULATE ( [Alert hours], win ), 0 ) )"),
     "#,0", "Alerts", "Alert hours over the days in context that fall in the 30 days up to the cut-off; blank when none do (works by date or by weekday)."),
    ("Alert", "Alert hours by day, last 7 days", _m("VAR c = [Cut-off]", "VAR win = FILTER ( VALUES ( 'Date'[date] ), 'Date'[date] > c - 7 && 'Date'[date] <= c )", "RETURN",
         "\tIF ( NOT ISEMPTY ( win ), COALESCE ( CALCULATE ( [Alert hours], win ), 0 ) )"),
     "#,0", "Alerts", "Alert hours over the days in context that fall in the 7 days up to the cut-off; blank when none do (works by date or by weekday)."),
    ("Reading", "Demand MW, last 7 days", _m("VAR c = [Cut-off]", "RETURN", "\tIF ( MAX ( Reading[reading_hour] ) > c - 7, [Demand MW] )"),
     "#,0.00", "Load", "Hourly demand in the 7 days up to the cut-off; blank before them (chart axis)."),
    ("Reading", "Usual MW, last 7 days", _m("VAR c = [Cut-off]", "RETURN", "\tIF ( MAX ( Reading[reading_hour] ) > c - 7, [Usual MW] )"),
     "#,0.00", "Load", "Usual load for the same hours."),
    ("Reading", "Peak demand MW, last 7 days", _m("VAR c = [Cut-off]", "RETURN", "\tCALCULATE ( [Peak demand MW], Reading[reading_hour] > c - 7, REMOVEFILTERS ( 'Date' ) )"),
     "#,0.0", "Load", "Highest hourly demand for the selection in the last 7 days."),
    ("Feeder", "Rated peak MW", "SUM ( Feeder[rated_peak_mw] )", "#,0.0", "Load", "Rated peak of the selected feeders."),
    ("Forecast", "Forecast MW, forecast day", _m("VAR d = [Forecast day]", "RETURN", "\tCALCULATE ( [Forecast MW], 'Date'[date] = d )"),
     "#,0.0", "Forecast", "Forecast for the forecast day (chart by hour)."),
    ("Forecast", "Range low MW, forecast day", _m("VAR d = [Forecast day]", "RETURN", "\tCALCULATE ( [Range low MW], 'Date'[date] = d )"),
     "#,0.0", "Forecast", "Low end of the range on the forecast day; one feeder, one substation or all feeders."),
    ("Forecast", "Range high MW, forecast day", _m("VAR d = [Forecast day]", "RETURN", "\tCALCULATE ( [Range high MW], 'Date'[date] = d )"),
     "#,0.0", "Forecast", "High end of the range on the forecast day."),
    ("Alert", "Disclaimer", _m("\"Synthetic data for a fictional distributor. Readings up to \" & FORMAT ( [Cut-off], \"d mmm yyyy hh:nn\" )", "\t& \", Malaysia time. Demand in MW, energy in MWh.\""),
     None, "Narrative", "Footer on every page: synthetic data and the cut-off, read from the data."),
    ("Alert", "Eyebrow Home", "\"As of \" & FORMAT ( [Cut-off], \"d mmm yyyy, hh:nn\" )", None, "Narrative", "Home: the as-of hour, read from the data."),
    ("Alert", "Subtitle Home", _m("VAR nf = CALCULATE ( DISTINCTCOUNT ( Feeder[feeder_id] ), REMOVEFILTERS () )",
                                 "VAR ns = CALCULATE ( DISTINCTCOUNT ( Feeder[substation_id] ), REMOVEFILTERS () )", "RETURN",
                                 "\tnf & \" feeders across \" & ns & \" main distribution substations report every hour. A reading far from the feeder's usual load \"",
                                 "\t& \"raises an alert as it arrives. A day-ahead forecast gives tomorrow's demand hour by hour, with a range.\""),
     None, "Narrative", "Home: what the report watches, counts read from the data."),
    ("Alert", "Title Meter Watch", _m("VAR i24 = [Incidents last 24 h]",
                                     "VAR t = TOPN ( 1, VALUES ( Feeder[substation_name] ), [Alert hours last 7 days], DESC )",
                                     "VAR topName = MAXX ( t, Feeder[substation_name] )",
                                     "VAR topHours = COALESCE ( MAXX ( t, [Alert hours last 7 days] ), 0 )",
                                     "VAR sw = COALESCE ( [Switching share 7 days], 0 )", "RETURN",
                                     "\tFORMAT ( i24, \"#,0\" ) & IF ( i24 = 1, \" incident\", \" incidents\" ) & \" in the last 24 hours. \"",
                                     "\t& IF ( topHours > 0, topName & \" had the most alert hours this week (\" & FORMAT ( topHours, \"#,0\" ) & \"); \" & FORMAT ( sw, \"0%\" )",
                                     "\t\t& \" of this week's alert hours fall in planned switching.\", \"No alert hours this week.\" )"),
     None, "Narrative", "Meter Watch takeaway: last-24-hour incidents, the busiest substation this week and the switching share."),
    ("Forecast", "Title Demand Forecast", _m("VAR pk = [Tomorrow peak MW]", "VAR h = [Tomorrow peak hour]", "VAR m = [Forecast error]",
                                            "VAR n = [Same hour last week error]", "RETURN",
                                            "\tFORMAT ( [Forecast day], \"ddd d mmm\" ) & \" peaks at \" & FORMAT ( pk, \"#,0.0\" ) & \" MW at \" & FORMAT ( h, \"00\" ) & \":00. \"",
                                            "\t& \"Backtest error \" & FORMAT ( m, \"0.0%\" ) & \", same hour last week \" & FORMAT ( n, \"0.0%\" )",
                                            "\t& \"; the range held \" & FORMAT ( [System range coverage], \"0%\" ) & \" of hours.\""),
     None, "Narrative", "Demand Forecast takeaway: tomorrow's peak and hour, and the backtest error against the benchmark."),
    ("Forecast", "Title Feeder Detail", _m("VAR nF = DISTINCTCOUNT ( Feeder[feeder_id] )", "VAR nm = SELECTEDVALUE ( Feeder[feeder_name] )",
                                          "VAR ah = COALESCE ( [Alert hours last 7 days], 0 )", "VAR pk = [Peak demand MW, last 7 days]", "VAR rp = [Rated peak MW]", "RETURN",
                                          "\tIF (", "\t\tnF = 1,",
                                          "\t\tnm & \": \" & FORMAT ( ah, \"#,0\" ) & IF ( ah = 1, \" alert hour\", \" alert hours\" ) & \" in the last 7 days; highest hour \"",
                                          "\t\t\t& FORMAT ( pk, \"0.0\" ) & \" MW against a rated peak of \" & FORMAT ( rp, \"0.0\" ) & \" MW.\",",
                                          "\t\tnF & \" feeders selected. Pick one feeder in the slicer to see its own load, alerts and forecast range.\"", "\t)"),
     None, "Narrative", "Feeder Detail takeaway for one feeder; asks for one feeder when several are selected."),
]


def tmdl_table(name, src, desc, cols):
    q = "'%s'" % name if " " in name else name
    L = ["/// " + desc, "table %s" % q, "\tlineageTag: %s" % tag(name), ""]
    for t, mname, dax, fmt, folder, mdesc in MEAS:
        if t != name:
            continue
        mq = "'%s'" % mname if any(c in mname for c in " -") else mname
        L.append("\t/// " + mdesc)
        if "\n" in dax:
            L.append("\tmeasure %s =" % mq)
            L.append("\t\t\t" + dax)
        else:
            L.append("\tmeasure %s = %s" % (mq, dax))
        if fmt:
            L.append("\t\tformatString: %s" % fmt)
        L.append("\t\tdisplayFolder: %s" % folder)
        L.append("\t\tlineageTag: %s" % tag(name, "m", mname))
        L.append("")
    for c, typ, hidden in cols:
        L.append("\tcolumn %s" % c)
        L.append("\t\tdataType: %s" % typ)
        if hidden:
            L.append("\t\tisHidden")
        if typ in FMT and typ != I:
            L.append("\t\tformatString: %s" % FMT[typ])
        L.append("\t\tsummarizeBy: none")
        L.append("\t\tsourceColumn: %s" % c)
        if (name, c) in SORT:
            L.append("\t\tsortByColumn: %s" % SORT[(name, c)])
        L.append("\t\tlineageTag: %s" % tag(name, c))
        L.append("")
    L += ["\tpartition %s = entity" % q, "\t\tmode: directLake", "\t\tsource", "\t\t\tentityName: %s" % src,
          "\t\t\texpressionSource: '%s'" % EXPR, ""]
    return "\n".join(L)


def crlf(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\r\n", "\n").replace("\n", "\r\n"))


def build():
    d = os.path.join(M, "definition")
    crlf(os.path.join(d, "database.tmdl"), "database SM_SinarLembah\n\tcompatibilityLevel: 1606\n\tcompatibilityMode: powerBI\n\tlanguage: 1033\n\n")
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tdiscourageImplicitMeasures",
             "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
             "annotation __PBI_ServiceStoredInTmdl = reserved", ""] + ["ref table %s" % ("'%s'" % t if " " in t else t) for t in TABLES] + [""]
    crlf(os.path.join(d, "model.tmdl"), "\n".join(model))
    crlf(os.path.join(d, "expressions.tmdl"),
         "/// Direct Lake binding to LH_SinarLembah via OneLake (Lakehouse without schemas; shape from P30 and P34).\n"
         "expression '%s' =\n\t\tlet\n\t\t    Source = AzureStorage.DataLake(\"https://onelake.dfs.fabric.microsoft.com/%s/%s\", [HierarchicalNavigation=true])\n\t\tin\n\t\t    Source\n\n" % (EXPR, WS, LH))
    for name, (src, desc, cols) in TABLES.items():
        crlf(os.path.join(d, "tables", name + ".tmdl"), tmdl_table(name, src, desc, cols))
    rel = []
    for a, ac, b, bc in RELS:
        qa = "'%s'" % a if " " in a else a; qb = "'%s'" % b if " " in b else b
        rel += ["relationship %s" % tag("rel", a, ac), "\tfromColumn: %s.%s" % (qa, ac), "\ttoColumn: %s.%s" % (qb, bc), ""]
    crlf(os.path.join(d, "relationships.tmdl"), "\n".join(rel))
    with open(os.path.join(M, "definition.pbism"), "w", encoding="utf-8", newline="\n") as f:
        f.write('{\n  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",\n  "version": "4.2",\n  "settings": {}\n}\n')
    with open(os.path.join(M, ".platform"), "w", encoding="utf-8", newline="\n") as f:
        f.write('{\n  "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",\n'
                '  "metadata": {"type": "SemanticModel", "displayName": "SM_SinarLembah", "description": "P37 Direct Lake model: readings, alerts, detector grading, forecast."},\n'
                '  "config": {"version": "2.0", "logicalId": "37a00000-0000-4000-8000-000000000006"}\n}\n')


if __name__ == "__main__":
    build()
    n = len(MEAS); print("tables", len(TABLES), "relationships", len(RELS), "measures", n)
