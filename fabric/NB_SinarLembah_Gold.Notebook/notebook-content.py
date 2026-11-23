# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "aaaaaaaa-0000-4000-8000-000000000002",
# META       "default_lakehouse_name": "LH_SinarLembah",
# META       "default_lakehouse_workspace_id": "aaaaaaaa-0000-4000-8000-000000000001",
# META       "known_lakehouses": [
# META         {
# META           "id": "aaaaaaaa-0000-4000-8000-000000000002"
# META         }
# META       ]
# META     }
# META   }
# META }

# MARKDOWN ********************

# NB_SinarLembah_Gold (P37)
#
# Date and hour tables, alerts as incidents, detector grading. Exits with a verdict JSON.

# CELL ********************

"""gold_module.py - P37 NB_SinarLembah_Gold: dimensions, alerts as incidents, detector grading. Pandas in, pandas out.

Inputs (DataFrames read from the Lakehouse shortcuts): calendar_day, planted_event, reading_alert, switching_log.
Outputs: dim_date, dim_hour, alert, event_grade, detector_metric.
Rules (Design Package, detector tab, with the 2026-11-23 review applied):
  * an incident (episode) is a run of alerts on one feeder in back-to-back hours (one quiet hour ends it); a Flat alert
    makes the whole incident Flat (review item 7); incident_id = feeder + first hour
  * cause shown to operators: "Planned switching" when the switching log covers the hour, else "Not explained";
    the planted-event match is kept apart in grade_cause for the detector-quality block (review, design row 2)
  * matured = ended 24 hours or more before the end of the cut-off hour (cut_end = last reading hour + 1 h); the same
    exclusive-end rule for alert hours and events (second review, item 11)
  * control: every planted window moved by its own duration + 7 days on the same feeder; drifts left out (item 4);
    maturity of a control window is measured from the cut-off, not from the last alert (second review, item 10)
  * run() first checks its inputs are complete (row counts against the KQL database, the cut-off hour); a failed
    check gives GOLD_CHECK_FAILED and the driver keeps the previous Gold tables (second review, items 3 and 5)
"""
import hashlib
import json

import numpy as np
import pandas as pd

START = pd.Timestamp("2025-10-24")
GRADE_FROM = pd.Timestamp("2026-09-21")
LAST_HOUR = 9479                      # hour_index of the last reading (22 Nov 2026 23:00)
SCORED_ROWS = 48 * (LAST_HOUR + 1 - 7968)


def cut_end(cutoff):
    return cutoff + pd.Timedelta(hours=1)


def dim_date(calendar_day):
    d = calendar_day.copy()
    d["date"] = pd.to_datetime(d["date"])
    out = pd.DataFrame({
        "date": d["date"],
        "day_index": d["day_index"].astype("int64"),
        "day_type": d["day_type"],
        "holiday_name": d["holiday_name"].fillna(""),
        "is_holiday": d["holiday_name"].fillna("") != "",
        "is_festive_week": d["is_festive"].astype(bool),
        "weekday_name": d["date"].dt.strftime("%a"),
        "weekday_no": (d["date"].dt.weekday + 1).astype("int64"),
        "day_label": d["date"].dt.strftime("%a %d %b"),
        "week_start": (d["date"] - pd.to_timedelta(d["date"].dt.weekday, unit="D")),
        "month_start": d["date"].dt.to_period("M").dt.to_timestamp(),
        "month_label": d["date"].dt.strftime("%b %Y"),
    })
    return out.sort_values("date").reset_index(drop=True)


def dim_hour():
    h = np.arange(24, dtype="int64")
    period = np.select([h < 6, h < 12, h < 18], ["Night", "Morning", "Afternoon"], "Evening")
    return pd.DataFrame({"hour_of_day": h, "hour_label": ["%02d:00" % x for x in h], "period": period})


def _incidents(a):
    a = a.sort_values(["feeder_id", "hour_index", "alert_type"]).copy()
    new = (a["feeder_id"] != a["feeder_id"].shift()) | (a["hour_index"] - a["hour_index"].shift() > 1)
    a["inc_no"] = new.cumsum()
    first = a.groupby("inc_no")["hour_index"].transform("min")
    a["incident_id"] = a["feeder_id"] + "-" + first.astype(str)
    has_flat = a.groupby("inc_no")["alert_type"].transform(lambda s: (s == "Flat").any())
    major = a.groupby("inc_no")["alert_type"].transform(lambda s: s.value_counts().idxmax())
    a["incident_type"] = np.where(has_flat, "Flat", major)
    a["incident_hours"] = a.groupby("inc_no")["hour_index"].transform(lambda s: s.max() - s.min() + 1).astype("int64")
    a["is_incident_start"] = a["hour_index"] == first
    return a.drop(columns=["inc_no"])


def gold_alert(reading_alert, planted_event, cutoff):
    a = reading_alert.copy()
    a = a.sort_values("detected_at").drop_duplicates("alert_id", keep="first")
    # one row per feeder-hour: a Flat and a Drop in the same hour are one alert hour, Flat first (item 7)
    a["_rank"] = a["alert_type"].map({"Flat": 0, "Drop": 1, "Spike": 1})
    a = a.sort_values(["feeder_id", "hour_index", "_rank"]).drop_duplicates(["feeder_id", "hour_index"], keep="first").drop(columns="_rank")
    a = _incidents(a)
    a["switch_id"] = a["switch_id"].fillna("")
    a["cause"] = np.where(a["switch_id"] != "", "Planned switching", "Not explained")
    ev = planted_event[["event_id", "feeder_id", "start_index", "end_index"]]
    m = a[["alert_id", "feeder_id", "hour_index"]].merge(ev, on="feeder_id")
    m = m[(m["hour_index"] >= m["start_index"]) & (m["hour_index"] < m["end_index"])]
    m = m.sort_values("event_id").drop_duplicates("alert_id", keep="last")
    a = a.merge(m[["alert_id", "event_id"]], on="alert_id", how="left")
    a["event_id"] = a["event_id"].fillna("")
    a["grade_cause"] = np.where(a["event_id"] != "", "Planted event", np.where(a["switch_id"] != "", "Planned switching", "Not explained"))
    a["reading_hour"] = pd.to_datetime(a["reading_hour"])
    a["is_matured"] = a["reading_hour"] + pd.Timedelta(hours=1) <= cut_end(cutoff) - pd.Timedelta(hours=24)
    a["z"] = a["z"].astype("float64")
    cols = ["alert_id", "incident_id", "feeder_id", "reading_hour", "reading_date", "hour_of_day", "hour_index", "alert_type",
            "incident_type", "incident_hours", "is_incident_start", "z", "demand_mw", "usual_mw", "spread_mw", "switch_id", "cause",
            "event_id", "grade_cause", "is_matured", "source", "batch_id"]
    out = a[cols].copy()
    out["reading_date"] = pd.to_datetime(out["reading_date"])
    for c in ("hour_of_day", "hour_index"):
        out[c] = out[c].astype("int64")
    return out.sort_values(["reading_hour", "feeder_id"]).reset_index(drop=True)


def event_grade(planted_event, alert, cutoff, start_index_cut):
    e = planted_event.copy()
    e["start_hour"] = pd.to_datetime(e["start_hour"]); e["end_hour"] = pd.to_datetime(e["end_hour"])
    e["start_date"] = pd.to_datetime(e["start_date"])
    e["in_window"] = e["start_index"] >= start_index_cut
    e["is_matured"] = e["end_hour"] <= cut_end(cutoff) - pd.Timedelta(hours=24)
    hits = alert[alert["event_id"] != ""].groupby("event_id").agg(alerts_n=("alert_id", "count"), first_alert=("hour_index", "min"))
    e = e.merge(hits, left_on="event_id", right_index=True, how="left")
    e["alerts_n"] = e["alerts_n"].fillna(0).astype("int64")
    e["is_caught"] = e["alerts_n"] > 0
    e["first_alert_lag_h"] = (e["first_alert"] - e["start_index"]).astype("float64")
    weak = e["event_type"].isin(["Spike", "Drop"]) & e["factor"].between(0.6, 1.5)
    e["strength"] = np.select([e["event_type"] == "Drift", e["event_type"] == "Flat", weak], ["Slow", "Stuck meter", "Weak"], "Strong")
    e["event_label"] = e["event_type"].map({"Spike": "Spike", "Drop": "Drop", "Flat": "Flat meter", "Drift": "Slow drift"})
    e["duration_h"] = (e["end_index"] - e["start_index"]).astype("int64")
    cols = ["event_id", "feeder_id", "event_type", "event_label", "strength", "start_hour", "end_hour", "start_date", "start_index",
            "end_index", "duration_h", "factor", "in_window", "is_matured", "is_caught", "alerts_n", "first_alert_lag_h"]
    return e[cols].sort_values("start_index").reset_index(drop=True)


def detector_metric(alert, grade, planted_event, switching_log, cutoff, start_index_cut):
    ma = alert[alert["is_matured"]]
    me = grade[grade["in_window"] & grade["is_matured"]]
    rows = []
    def add(metric, value, n, note):
        rows.append({"metric": metric, "value": float(value) if value is not None else None, "n": int(n), "note": note})
    add("Alert hours, matured", len(ma), len(ma), "alert hours at least a day before the cut-off")
    add("Incidents, matured", ma["incident_id"].nunique(), ma["incident_id"].nunique(), "runs of alerts on one feeder")
    add("Planted share of alert hours", (ma["grade_cause"] == "Planted event").mean() if len(ma) else None, len(ma), "precision against the answer key")
    add("Explained share of alert hours", (ma["grade_cause"] != "Not explained").mean() if len(ma) else None, len(ma), "planted or planned switching")
    add("Events matured", len(me), len(me), "planted events in the grading window, ended a day before the cut-off")
    add("Events caught", int(me["is_caught"].sum()), len(me), "at least one alert inside the event window")
    add("Recall", me["is_caught"].mean() if len(me) else None, len(me), "caught / matured")
    for lab, g in me.groupby("strength"):
        add("Recall, %s" % lab.lower(), g["is_caught"].mean(), len(g), "caught / matured, %s events" % lab.lower())
    # control: shift each non-drift window by its duration + 7 days (168 h) on the same feeder
    ev = planted_event[(planted_event["event_type"] != "Drift") & (planted_event["start_index"] >= start_index_cut)].copy()
    ev["s2"] = ev["start_index"] + (ev["end_index"] - ev["start_index"]) + 168
    ev["e2"] = ev["end_index"] + (ev["end_index"] - ev["start_index"]) + 168
    real = planted_event[["feeder_id", "start_index", "end_index"]]
    cut_index = int((cut_end(cutoff) - START) / pd.Timedelta(hours=1))   # exclusive end of the cut-off hour
    ev = ev[ev["e2"] <= cut_index - 24]
    # leave out shifted windows that touch a real event or a logged switch on the same feeder
    def clean(r):
        rr = real[(real["feeder_id"] == r.feeder_id) & (real["start_index"] < r.e2) & (real["end_index"] > r.s2)]
        sw = switching_log[((switching_log["from_feeder_id"] == r.feeder_id) | (switching_log["to_feeder_id"] == r.feeder_id))
                           & (switching_log["start_index"] < r.e2) & (switching_log["end_index"] > r.s2)]
        return rr.empty and sw.empty
    ev = ev[[clean(r) for r in ev.itertuples()]] if len(ev) else ev
    hits = 0
    for r in ev.itertuples():
        hits += int(((alert["feeder_id"] == r.feeder_id) & (alert["hour_index"] >= r.s2) & (alert["hour_index"] < r.e2)).any())
    add("Control windows", len(ev), len(ev), "planted windows moved by their length + 7 days; drifts and overlaps left out")
    add("Control hits", hits, len(ev), "control windows with any alert: should be near 0")
    add("Control hit rate", hits / len(ev) if len(ev) else None, len(ev), "hits / control windows")
    out = pd.DataFrame(rows)
    out["cutoff"] = cutoff
    return out


def run(tables, expected=None):
    """tables: dict of DataFrames. expected: row counts read from the KQL database for the shortcut tables
    ({"reading_alert": n, "reading_scored": n, ...}); None offline. Returns (outputs dict, verdict dict)."""
    ra = tables["reading_alert"].copy()
    ra["reading_hour"] = pd.to_datetime(ra["reading_hour"])
    rs = tables["reading_scored"]
    cutoff = pd.to_datetime(rs["reading_hour"]).max()
    inputs = {"cutoff_hour": cutoff == START + pd.Timedelta(hours=LAST_HOUR),
              }
    if "rows" in rs.columns:
        inputs["reading_scored_rows"] = int(rs["rows"].iloc[0]) == SCORED_ROWS
    for t, n in (expected or {}).items():
        have = len(tables[t]) if t in tables and "rows" not in tables[t].columns else int(tables[t]["rows"].iloc[0])
        inputs["%s_matches_kql" % t] = have == n
    start_cut = int((GRADE_FROM - pd.Timestamp("2025-10-24")) / pd.Timedelta(hours=1))
    pe = tables["planted_event"].copy()
    out = {"gold_dim_date": dim_date(tables["calendar_day"]), "gold_dim_hour": dim_hour()}
    out["gold_alert"] = gold_alert(ra, pe, cutoff)
    out["gold_event_grade"] = event_grade(pe, out["gold_alert"], cutoff, start_cut)
    out["gold_detector_metric"] = detector_metric(out["gold_alert"], out["gold_event_grade"], pe, tables["switching_log"], cutoff, start_cut)
    m = out["gold_detector_metric"].set_index("metric")["value"]
    checks = {
        "dim_date_rows": len(out["gold_dim_date"]), "alert_hours": len(out["gold_alert"]),
        "alerts_in": len(ra), "incidents": int(out["gold_alert"]["incident_id"].nunique()),
        "events_matured": int(m.get("Events matured", 0)), "events_caught": int(m.get("Events caught", 0)),
        "control_hits": int(m.get("Control hits", 0)), "control_windows": int(m.get("Control windows", 0)),
        "cutoff": str(cutoff),
    }
    ok = checks["dim_date_rows"] == 396 and checks["alert_hours"] > 0 and checks["events_matured"] > 0 and all(inputs.values())
    verdict = dict(checks, inputs=inputs, verdict="GOLD_OK" if ok else "GOLD_CHECK_FAILED")
    return out, verdict

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


import json, time, traceback
import pandas as pd
import requests
from pyspark.sql import functions as F
import sempy.fabric as fabric
spark.conf.set("spark.sql.session.timeZone", "UTC")

def write_table(name, pdf):
    sdf = spark.createDataFrame(pdf)
    for c, t in sdf.dtypes:
        if t in ("double", "float"):
            sdf = sdf.withColumn(c, F.when(F.isnan(F.col(c)), F.lit(None)).otherwise(F.col(c)))
    sdf.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable(name)
    return spark.read.table(name).count()

def kql_counts(tables):
    # Row counts straight from the KQL database (the source of the shortcuts), through the workspace's own Eventhouse
    ws = fabric.get_workspace_id(); client = fabric.FabricRestClient()
    kdb = [i for i in client.get("/v1/workspaces/%s/items?type=KQLDatabase" % ws).json()["value"] if i["displayName"] == "EH_SinarLembah"][0]
    cluster = client.get("/v1/workspaces/%s/kqlDatabases/%s" % (ws, kdb["id"])).json()["properties"]["queryServiceUri"]
    tok = notebookutils.credentials.getToken(cluster)
    out = {}
    for t in tables:   # database by item id: the display name can be shared with the Eventhouse's default database
        r = requests.post(cluster + "/v1/rest/query", json={"db": kdb["id"], "csl": "%s | count" % t},
                          headers={"Authorization": "Bearer " + tok}, timeout=120)
        r.raise_for_status()
        out[t] = int(r.json()["Tables"][0]["Rows"][0][0])
    return out

def wait_for_shortcuts(tables, max_minutes=20):
    # OneLake availability lags the KQL write (target latency 5 min): wait until every shortcut shows the KQL row count
    want = kql_counts(tables)
    t0 = time.time()
    while True:
        have = {t: spark.read.table(t).count() for t in tables}
        if have == want or time.time() - t0 > max_minutes * 60:
            return want, have, round(time.time() - t0)
        time.sleep(60)

def finish(R):
    # A verdict that is not *_OK fails the notebook run (review 2026-11-23 item 2); the pipeline gate is the second check
    if not str(R.get("verdict", "")).endswith("_OK"):
        raise RuntimeError(json.dumps(R, default=str, sort_keys=True)[:4000])
    notebookutils.notebook.exit(json.dumps(R, default=str, sort_keys=True))

R = {"verdict": "GOLD_START"}
try:
    want, have, waited = wait_for_shortcuts(["reading_alert", "reading_scored", "planted_event", "switching_log", "calendar_day"])
    T = {t: spark.read.table(t).toPandas() for t in ["calendar_day", "planted_event", "reading_alert", "switching_log"]}
    T["reading_scored"] = spark.read.table("reading_scored").agg(F.max("reading_hour").alias("reading_hour"), F.count("*").alias("rows")).toPandas()
    out, R = run(T, expected=want)
    R["shortcut_wait"] = {"kql": want, "lakehouse": have, "seconds": waited}
    if R["verdict"] == "GOLD_OK":        # a failed check keeps the previous Gold tables (review item 5)
        R["readback"] = {n: write_table(n, pdf) for n, pdf in out.items()}
        R["readback_match"] = all(R["readback"][n] == len(out[n]) for n in out)
        if not R["readback_match"]:
            R["verdict"] = "GOLD_READBACK_MISMATCH"
except Exception as e:
    R = {"verdict": "GOLD_FAILED", "error": str(e)[:1200], "tb": traceback.format_exc()[-1500:]}
finish(R)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
