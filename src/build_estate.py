"""build_estate.py - P37: write the Fabric estate as Git item folders (repo-first, brief Rev 2) into <out>/fabric/.

Items: VL_SinarLembah (first), EH_SinarLembah (+ .children KQL database with our DatabaseSchema.kql), LH_SinarLembah
(8 OneLake shortcuts to the KQL tables), NB_SinarLembah_Seed / _Gold / _Forecast, PL_SinarLembah_Daily, and the
parameter.yml that rebinds the Dev ids in a new workspace (fabric-cicd 1.4.0 find_replace, SETTLED S215).
The semantic model and the report are written by their own builders into the same folder.
Shapes: notebook-content.py and .platform from _probe/w12 (W12, deployed); Eventhouse, KQL database and Lakehouse
parts from Dev's own getDefinition (02_Build/readback_dev); pipeline activities from P34's PL_RimbunCredit_Refresh.
"""
import json, os, shutil, sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "estate"
RB = sys.argv[2] if len(sys.argv) > 2 else "readback_dev"
F = os.path.join(OUT, "fabric")
WS = "aaaaaaaa-0000-4000-8000-000000000001"
LH_ID = "aaaaaaaa-0000-4000-8000-000000000002"
KDB_ID = "aaaaaaaa-0000-4000-8000-000000000003"
EH_ID = "aaaaaaaa-0000-4000-8000-000000000004"
LID = {"VL_SinarLembah": "37a00000-0000-4000-8000-000000000001", "EH_SinarLembah.Eventhouse": "37a00000-0000-4000-8000-000000000002",
       "EH_SinarLembah.KQLDatabase": "37a00000-0000-4000-8000-000000000003", "LH_SinarLembah": "37a00000-0000-4000-8000-000000000004",
       "PL_SinarLembah_Daily": "37a00000-0000-4000-8000-000000000005"}
NB = {"NB_SinarLembah_Gold": "37a00000-0000-4000-8000-0000000000a1", "NB_SinarLembah_Forecast": "37a00000-0000-4000-8000-0000000000a2",
      "NB_SinarLembah_Seed": "37a00000-0000-4000-8000-0000000000a3"}
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"
SHORTCUTS = ["meter_reading", "reading_scored", "reading_alert", "feeder", "planted_event", "switching_log", "calendar_day", "weather_hourly"]


def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8", newline="\n").write(text)


def wj(path, obj):
    w(path, json.dumps(obj, indent=2) + "\n")


def platform(folder, typ, name, desc, logical):
    wj(os.path.join(folder, ".platform"), {"$schema": SCHEMA, "metadata": {"type": typ, "displayName": name, "description": desc},
                                            "config": {"version": "2.0", "logicalId": logical}})


def build():
    if os.path.exists(F):
        shutil.rmtree(F)
    # 1 Variable Library (deployed first)
    sys.path.insert(0, os.environ.get("ENGINE_LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kit")))
    vl = os.path.join(F, "VL_SinarLembah.VariableLibrary")
    vschema = "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/"
    variables = [("kql_database", "String", "EH_SinarLembah", "KQL database name in every environment"),
                 ("grade_from", "String", "2026-09-21", "first day of the detector grading window"),
                 ("z_threshold", "Number", 5.0, "alert when the reading is this many spreads from usual"),
                 ("flat_hours", "Integer", 6, "equal readings in a row that make a flat-meter alert"),
                 ("baseline_weeks", "Integer", 12, "weeks of history behind the usual load")]
    wj(os.path.join(vl, "variables.json"), {"$schema": vschema + "variables/1.0.0/schema.json",
                                             "variables": [{"name": n, "type": t, "value": v, "note": note} for n, t, v, note in variables]})
    wj(os.path.join(vl, "settings.json"), {"$schema": vschema + "settings/1.0.0/schema.json", "valueSetsOrder": []})
    platform(vl, "VariableLibrary", "VL_SinarLembah", "P37 settings: detector rules and the grading window. Ids are rebound by parameter.yml.", LID["VL_SinarLembah"])
    # 2 Eventhouse + KQL database child (our schema, not Fabric's export: the export drops the mirroring policy)
    eh = os.path.join(F, "EH_SinarLembah.Eventhouse")
    wj(os.path.join(eh, "EventhouseProperties.json"), {})
    platform(eh, "Eventhouse", "EH_SinarLembah", "P37 hot path: hourly feeder readings, scoring and alerts (KQL).", LID["EH_SinarLembah.Eventhouse"])
    kd = os.path.join(eh, ".children", "EH_SinarLembah.KQLDatabase")
    wj(os.path.join(kd, "DatabaseProperties.json"), {"databaseType": "ReadWrite", "parentEventhouseItemId": LID["EH_SinarLembah.Eventhouse"],
                                                      "oneLakeCachingPeriod": "P36500D", "oneLakeStandardStoragePeriod": "P36500D"})
    # The item definition accepts only create-merge table / functions / a few policies (update, retention, caching,
    # streamingingestion, ...): mirroring is refused (ScriptContainsUnsupportedCommand, P37 Build exit 2026-11-23). The
    # update policies stay out too, so the seed loads history and backfill BEFORE they exist, as Dev did. The seed
    # notebook sets mirroring (before the load) and the update policies (after the backfill).
    src = open(os.path.join("kql", "DatabaseSchema.kql"), encoding="utf-8").read().split("\n")
    keep = [l for l in src if not (l.startswith(".alter table") and (" policy mirroring " in l or " policy update " in l))]
    open(os.path.join(kd, "DatabaseSchema.kql"), "w", encoding="utf-8", newline="\n").write("\n".join(keep))
    platform(kd, "KQLDatabase", "EH_SinarLembah", "", LID["EH_SinarLembah.KQLDatabase"])
    # 3 Lakehouse with the 8 shortcuts
    lh = os.path.join(F, "LH_SinarLembah.Lakehouse")
    wj(os.path.join(lh, "lakehouse.metadata.json"), {})
    shutil.copy(os.path.join(RB, "LH_SinarLembah.Lakehouse", "alm.settings.json"), os.path.join(lh, "alm.settings.json"))
    wj(os.path.join(lh, "shortcuts.metadata.json"), [{"name": t, "path": "/Tables", "target": {"type": "OneLake", "oneLake": {
        "path": "Tables/" + t, "itemId": KDB_ID, "workspaceId": WS}}} for t in SHORTCUTS])
    platform(lh, "Lakehouse", "LH_SinarLembah", "P37 cold path: shortcuts to the KQL tables, Gold tables, forecast outputs.", LID["LH_SinarLembah"])
    # 4 notebooks
    sys.path.insert(0, "nb")
    import build_notebooks as bn
    bn.ROOT = F
    here = "nb"
    gold = open(os.path.join(here, "gold_module.py")).read(); fc = open(os.path.join(here, "forecast_module.py")).read()
    oh = open(os.path.join(here, "offline_features_hash.txt")).read().strip()
    from seed_driver import SEED_DRIVER
    out = [bn.write_nb("NB_SinarLembah_Seed", "NB_SinarLembah_Seed (P37)\n\nBuilds the KQL schema and generates the data when the KQL database is empty (deployment plan post-action). Exits with a verdict JSON.",
                       open(os.path.join(here, "seed_module.py")).read(), SEED_DRIVER),
           bn.write_nb("NB_SinarLembah_Gold", "NB_SinarLembah_Gold (P37)\n\nDate and hour tables, alerts as incidents, detector grading. Exits with a verdict JSON.", gold, bn.GOLD_DRIVER),
           bn.write_nb("NB_SinarLembah_Forecast", "NB_SinarLembah_Forecast (P37, route R5)\n\nDay-ahead forecast, 9-fold backtest, kill criteria K0-K8, ranges, MLflow. Exits with a verdict JSON.",
                       fc, bn.FORECAST_DRIVER.replace("%%OFFLINE_HASH%%", oh))]
    # 5 pipeline: Gold, gate, Forecast, gate (verdict gates, SETTLED S179)
    acts = []
    prev = None
    for step, nb in (("Gold", "NB_SinarLembah_Gold"), ("Forecast", "NB_SinarLembah_Forecast")):
        run = {"name": "Run" + step, "type": "TridentNotebook", "dependsOn": [] if prev is None else [{"activity": prev, "dependencyConditions": ["Succeeded"]}],
               "policy": {"timeout": "0.02:00:00", "retry": 0, "retryIntervalInSeconds": 30, "secureOutput": False, "secureInput": False},
               "typeProperties": {"notebookId": NB[nb], "workspaceId": "00000000-0000-0000-0000-000000000000"}}   # Git form for "this workspace": the importer then resolves the notebook logicalIds inside the payload (P37 Build exit run 3)
        gate = {"name": "Gate" + step, "type": "IfCondition", "dependsOn": [{"activity": "Run" + step, "dependencyConditions": ["Succeeded"]}],
                "typeProperties": {"expression": {"type": "Expression", "value":
                    "@and(not(equals(pipeline().parameters.p_block_at, '%s')), endswith(string(json(activity('Run%s').output.result.exitValue).verdict), '_OK'))" % (step, step)},
                    "ifTrueActivities": [], "ifFalseActivities": [{"name": "Fail" + step, "type": "Fail", "dependsOn": [], "typeProperties": {
                        "message": {"type": "Expression", "value": "@concat('%s blocked: ', substring(string(activity('Run%s').output.result.exitValue), 0, min(400, length(string(activity('Run%s').output.result.exitValue)))))" % (step, step, step)},
                        "errorCode": "P37_%s_BLOCKED" % step.upper()}}]}}
        acts += [run, gate]
        prev = "Gate" + step
    pl = os.path.join(F, "PL_SinarLembah_Daily.DataPipeline")
    wj(os.path.join(pl, "pipeline-content.json"), {"properties": {"activities": acts, "parameters": {"p_block_at": {"type": "string", "defaultValue": ""}}}})
    platform(pl, "DataPipeline", "PL_SinarLembah_Daily", "P37 daily: Gold, then the day-ahead forecast; a verdict gate after each notebook.", LID["PL_SinarLembah_Daily"])
    # 6 parameter.yml for a new workspace (fabric-cicd find_replace, S215)
    w(os.path.join(F, "parameter.yml"), """# P37 parameter.yml - rebinds the Dev ids when the estate is deployed into another workspace (SETTLED S215).
# Dev values are the find_value; fabric-cicd resolves the replace_value in the target workspace.
find_replace:
  - find_value: "%s"
    replace_value:
      _ALL_: "$workspace.$id"
  - find_value: "%s"
    replace_value:
      _ALL_: "$items.Lakehouse.LH_SinarLembah.$id"
  - find_value: "%s"
    replace_value:
      _ALL_: "$items.KQLDatabase.EH_SinarLembah.$id"
  - find_value: "%s"
    replace_value:
      _ALL_: "$items.Eventhouse.EH_SinarLembah.$id"
""" % (WS, LH_ID, KDB_ID, EH_ID))
    return out


if __name__ == "__main__":
    for x in build():
        print(x)
    n = sum(len(fs) for _, _, fs in os.walk(F))
    print("files", n)
