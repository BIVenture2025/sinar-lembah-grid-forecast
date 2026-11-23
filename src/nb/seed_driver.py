SEED_DRIVER = """
import json, traceback
import sempy.fabric as fabric
R = {"verdict": "SEED_START"}
try:
    ws = fabric.get_workspace_id()
    client = fabric.FabricRestClient()
    # The KQL database is addressed by its ITEM ID: a display name can be shared with the Eventhouse's own default
    # database on the same cluster, and then a lookup by name fails (P37 Build exit, SinarLembah-Scratch)
    items = client.get("/v1/workspaces/%s/items?type=KQLDatabase" % ws).json()["value"]
    kdb = [i for i in items if i["displayName"] == "EH_SinarLembah"][0]
    cluster = client.get("/v1/workspaces/%s/kqlDatabases/%s" % (ws, kdb["id"])).json()["properties"]["queryServiceUri"]
    get_token = lambda: notebookutils.credentials.getToken(cluster)
    R = seed(cluster, kdb["id"], get_token, lambda p, d: print(p, d))
    R["kql_database"] = kdb["id"]
    R["workspace"] = ws
except Exception as e:
    R = {"verdict": "SEED_FAILED", "error": str(e)[:1200], "tb": traceback.format_exc()[-1500:]}
# A failed verdict must fail the run: the deployment plan's post-action has no verdict gate (review 2026-11-23 item 2)
if not str(R.get("verdict", "")).endswith("_OK"):
    raise RuntimeError(json.dumps(R, default=str, sort_keys=True)[:4000])
notebookutils.notebook.exit(json.dumps(R, default=str, sort_keys=True))
"""
