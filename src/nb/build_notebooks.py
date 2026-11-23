"""build_notebooks.py - P37: write the notebook items in Fabric Git format (notebook-content.py + .platform).

Each notebook: cell 1 = its module (gold_module.py / forecast_module.py / seed_module.py), cell 2 = the driver that
reads the Lakehouse tables, runs the module, writes gold_* tables, reads them back and exits with a verdict JSON.
Modules travel inside the notebook (repo-first deploy, no tool-call payload, so the S075 size limit does not apply).
"""
import json, os, sys, uuid, hashlib

ROOT = sys.argv[1] if len(sys.argv) > 1 else "../fabric"
WS = "aaaaaaaa-0000-4000-8000-000000000001"
LH = "aaaaaaaa-0000-4000-8000-000000000002"
LOGICAL = {"NB_SinarLembah_Gold": "37a00000-0000-4000-8000-0000000000a1",
           "NB_SinarLembah_Forecast": "37a00000-0000-4000-8000-0000000000a2",
           "NB_SinarLembah_Seed": "37a00000-0000-4000-8000-0000000000a3"}
DESC = {"NB_SinarLembah_Gold": "P37 Gold: date and hour tables, alerts as incidents with cause, detector grading with a control.",
        "NB_SinarLembah_Forecast": "P37 day-ahead forecast (route R5): backtest, kill criteria, ranges, MLflow register, Gold tables.",
        "NB_SinarLembah_Seed": "P37 seed: builds the KQL schema and generates the data when the KQL database is empty (deployment plan post-action)."}

HEAD = '''# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "%s",
# META       "default_lakehouse_name": "LH_SinarLembah",
# META       "default_lakehouse_workspace_id": "%s",
# META       "known_lakehouses": [
# META         {
# META           "id": "%s"
# META         }
# META       ]
# META     }
# META   }
# META }
''' % (LH, WS, LH)
CELL_META = '''
# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
'''


def cell(src):
    return "\n# CELL ********************\n\n" + src.rstrip("\n") + "\n" + CELL_META


def md(src):
    return "\n# MARKDOWN ********************\n\n" + "\n".join("# " + l if l else "#" for l in src.split("\n")) + "\n"


WRITE_HELPER = '''
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
'''

GOLD_DRIVER = WRITE_HELPER + '''
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
'''

FORECAST_DRIVER = WRITE_HELPER + '''
import mlflow, mlflow.sklearn
OFFLINE_HASH = "%%OFFLINE_HASH%%"
EXPERIMENT, MODEL_NAME = "EXP_SinarLembah_Forecast", "MDL_SinarLembah_DayAhead"
R = {"verdict": "FORECAST_START"}
try:
    mlflow.autolog(disable=True)                                   # S159: before any fit
    want, have, waited = wait_for_shortcuts(["meter_reading", "reading_alert", "weather_hourly", "calendar_day", "feeder"])
    T = {"meter_reading": spark.read.table("meter_reading").select("feeder_id", "hour_index", "demand_mw").toPandas(),
         "feeder": spark.read.table("feeder").toPandas(), "calendar_day": spark.read.table("calendar_day").toPandas(),
         "weather_hourly": spark.read.table("weather_hourly").select("hour_index", "temp_c", "temp_fc_c").toPandas()}
    ah = spark.read.table("reading_alert").select("feeder_id", "hour_index").distinct().toPandas()
    alert_hours = set(zip(ah["feeder_id"], ah["hour_index"].astype(int)))
    t0 = time.time()
    out, R, final, tr = run(T, alert_hours, offline_hash=OFFLINE_HASH)
    R["shortcut_wait"] = {"kql": want, "lakehouse": have, "seconds": waited}
    if out is not None:
        R["seconds_backtest"] = round(time.time() - t0, 1)
        mlflow.set_experiment(EXPERIMENT)
        with mlflow.start_run(run_name="day_ahead_%s" % R.get("features_hash", "")[:8]) as run_:
            mlflow.log_params({"model": "HistGradientBoostingRegressor", "max_iter": 300, "learning_rate": 0.08,
                               "features": ",".join(FEATS), "champion": R["champion"], "range_factor": R["range_factor"]})
            mlflow.log_metrics({"wape_model": R["wape_model"], "wape_naive": R["wape_naive"], "gain_ci_low": R["gain_ci"][0],
                                "gain_ci_high": R["gain_ci"][1], "coverage_system": R["coverage"][2]})
            # K8: AutoML (FLAML) baseline on the last fold only (300 s budget, S217); logged in this run (review item 15)
            try:
                from flaml import AutoML
                df = frame(T["meter_reading"], T["feeder"], T["calendar_day"], T["weather_hourly"])
                bad = df.set_index(["feeder_id", "hour_index"]).index.isin(list(alert_hours))
                lo = FOLD0_DAY + 56
                trn = df[(df["day"] < lo) & df["lag672"].notna() & df["demand_mw"].notna() & ~bad]
                tst = df[(df["day"] >= lo) & (df["day"] <= LAST_DAY)]
                am = AutoML()
                am.fit(trn[FEATS], trn["demand_mw"], task="regression", metric="mae", time_budget=300, seed=7, verbose=0)
                gb = model().fit(trn[FEATS], trn["demand_mw"])
                w_am = wape(tst["demand_mw"], am.predict(tst[FEATS])); w_gb = wape(tst["demand_mw"], gb.predict(tst[FEATS]))
                R["K8"] = {"automl_wape_fold9": round(w_am, 5), "gb_wape_fold9": round(w_gb, 5), "automl_best": str(am.best_estimator),
                           "rule": "AutoML better by more than 0.2 points on fold 9 = challenger noted; champion unchanged in V1",
                           "result": "CHALLENGER_NOTED" if w_am < w_gb - 0.002 else "GB_HOLDS"}
                mlflow.log_metrics({"k8_automl_wape_fold9": w_am, "k8_gb_wape_fold9": w_gb})
                mlflow.log_param("k8_automl_best", str(am.best_estimator))
                out["gold_model_metric"] = pd.concat([out["gold_model_metric"], pd.DataFrame([
                    {"metric": "Forecast error, fold 9", "model": "AutoML (" + str(am.best_estimator) + ")", "value": w_am, "ci_low": None, "ci_high": None, "n": 7, "scope": "Last fold only; FLAML 300 s"},
                    {"metric": "Forecast error, fold 9", "model": "Gradient boosting", "value": w_gb, "ci_low": None, "ci_high": None, "n": 7, "scope": "Last fold only"}])], ignore_index=True)
            except Exception as e:
                R["K8"] = {"result": "NOT_RUN", "error": str(e)[:300]}
            mlflow.log_dict({k: v for k, v in R.items() if k not in ("K0_checks",)}, "verdict.json")
            if R["register"]:
                mlflow.sklearn.log_model(final, "model", registered_model_name=MODEL_NAME, input_example=tr[FEATS].head(5))
            R["mlflow_run_id"] = run_.info.run_id
        for n in ("gold_model_metric", "gold_forecast_hourly", "gold_forecast_group"):
            out[n]["run_id"] = R["mlflow_run_id"]
        if R["verdict"] == "FORECAST_OK":   # a killed verdict keeps the previous Gold tables (review item 5)
            R["readback"] = {n: write_table(n, pdf) for n, pdf in out.items()}
            R["readback_match"] = all(R["readback"][n] == len(out[n]) for n in out)
            if not R["readback_match"]:
                R["verdict"] = "FORECAST_READBACK_MISMATCH"
except Exception as e:
    R = {"verdict": "FORECAST_FAILED", "error": str(e)[:1200], "tb": traceback.format_exc()[-1500:]}
finish(R)
'''


def platform(name, typ, desc, logical):
    return json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                       "metadata": {"type": typ, "displayName": name, "description": desc},
                       "config": {"version": "2.0", "logicalId": logical}}, indent=2) + "\n"


def write_nb(name, title, module_src, driver):
    d = os.path.join(ROOT, name + ".Notebook")
    os.makedirs(d, exist_ok=True)
    body = HEAD + md(title) + cell(module_src) + cell(driver)
    open(os.path.join(d, "notebook-content.py"), "w", encoding="utf-8", newline="\n").write(body)
    open(os.path.join(d, ".platform"), "w", encoding="utf-8", newline="\n").write(platform(name, "Notebook", DESC[name], LOGICAL[name]))
    return d, len(body), hashlib.sha256(body.encode()).hexdigest()[:12]


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    gold = open(os.path.join(here, "gold_module.py")).read()
    fc = open(os.path.join(here, "forecast_module.py")).read()
    oh = open(os.path.join(here, "offline_features_hash.txt")).read().strip()
    print(write_nb("NB_SinarLembah_Gold", "NB_SinarLembah_Gold (P37)\n\nDate and hour tables, alerts as incidents, detector grading. Exits with a verdict JSON.", gold, GOLD_DRIVER))
    print(write_nb("NB_SinarLembah_Forecast", "NB_SinarLembah_Forecast (P37, route R5)\n\nDay-ahead forecast, 9-fold backtest, kill criteria K0-K8, ranges, MLflow. Exits with a verdict JSON.",
                   fc, FORECAST_DRIVER.replace("%%OFFLINE_HASH%%", oh)))
    if os.path.exists(os.path.join(here, "seed_module.py")):
        from seed_driver import SEED_DRIVER
        print(write_nb("NB_SinarLembah_Seed", "NB_SinarLembah_Seed (P37)\n\nBuilds the KQL schema and generates the data when the KQL database is empty. Exits with a verdict JSON.",
                       open(os.path.join(here, "seed_module.py")).read(), SEED_DRIVER))
