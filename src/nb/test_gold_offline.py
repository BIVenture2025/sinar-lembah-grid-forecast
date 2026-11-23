import json, os, pandas as pd, sys
from offline_tables import tables
import gold_module as gm
U = os.environ.get("P37_EXPORTS", "exports/")   # reading_alert.csv and scored_max.csv exported from the KQL database
T = tables()
ra = pd.read_csv(U + "reading_alert.csv")
for c in ("reading_hour", "reading_date", "detected_at"):
    ra[c] = pd.to_datetime(ra[c]).dt.tz_localize(None)
T["reading_alert"] = ra
T["reading_scored"] = pd.read_csv(U + "scored_max.csv").assign(reading_hour=lambda x: pd.to_datetime(x.reading_hour).dt.tz_localize(None))
out, v = gm.run(T)
print(json.dumps(v, indent=1, default=str))
print(out["gold_detector_metric"][["metric", "value", "n"]].to_string())
a = out["gold_alert"]
print(a.groupby(["grade_cause"]).size().to_dict(), "incidents", a.incident_id.nunique())
last = a[a.reading_hour > a.reading_hour.max() - pd.Timedelta(hours=24)]
print("last24", len(last), last.cause.value_counts().to_dict())
print(out["gold_event_grade"][out["gold_event_grade"].in_window][["event_id","feeder_id","event_type","strength","is_matured","is_caught","alerts_n"]].to_string())
