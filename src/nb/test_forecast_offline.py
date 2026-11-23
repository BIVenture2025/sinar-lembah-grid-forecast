import json, time
from offline_tables import tables
import forecast_module as fm
t0 = time.time(); T = tables()
out, v, final, tr = fm.run(T, alert_hours=set())
print(json.dumps(v, indent=1)); print({k: len(x) for k, x in out.items()}, round(time.time() - t0, 1), "s")
print(out["gold_model_metric"].to_string())
s = out["gold_forecast_group"]; tm = s[(s.level == "System") & (s.fold == 0)]
print("tomorrow system peak", tm.forecast_mw.max().round(1), "at", int(tm.loc[tm.forecast_mw.idxmax(), "hour_of_day"]), "range", tm.loc[tm.forecast_mw.idxmax(), ["lo_mw", "hi_mw"]].round(1).tolist())
open("offline_features_hash.txt", "w").write(v["features_hash"])
