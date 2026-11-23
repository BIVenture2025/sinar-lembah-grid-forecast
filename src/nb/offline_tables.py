"""Build the notebook input tables from the generator oracle (the offline replay, S160)."""
import sys, datetime as dt
sys.path.insert(0, "..")
import pandas as pd
from gen_oracle import generate, day_info, weather, switching_log, START, DAYS, HOURS
def tables():
    fs, infos, evs, rows = generate()
    feeder = pd.DataFrame(fs)
    cal = []
    for k in range(DAYS + 1):
        date, dtp, hol, fest, _, _ = day_info(k)
        cal.append({"day_index": k, "date": pd.Timestamp(date), "day_type": dtp, "holiday_name": hol, "is_festive": bool(fest), "month": date.month})
    cal = pd.DataFrame(cal)
    infos2 = [day_info(d) for d in range(DAYS + 1)]
    w = [weather(i, infos2[i // 24]) for i in range(HOURS + 24)]
    wx = pd.DataFrame({"hour_index": range(HOURS + 24), "temp_c": [x[0] for x in w], "temp_fc_c": [x[1] for x in w]})
    mr = pd.DataFrame(rows, columns=["feeder_id", "hour_index", "demand_mw"])
    mr["reading_hour"] = pd.Timestamp(START) + pd.to_timedelta(mr["hour_index"], unit="h")
    pe = pd.DataFrame([{"event_id": e["event_id"], "feeder_id": "F%02d" % e["feeder_no"], "event_type": e["event_type"], "start_index": e["start_index"],
                        "end_index": e["end_index"], "start_hour": pd.Timestamp(START) + pd.Timedelta(hours=e["start_index"]),
                        "end_hour": pd.Timestamp(START) + pd.Timedelta(hours=e["end_index"]),
                        "start_date": (pd.Timestamp(START) + pd.Timedelta(hours=e["start_index"])).normalize(), "factor": e["factor"]} for e in evs])
    sw = pd.DataFrame([{"switch_id": x["switch_id"], "from_feeder_id": "F%02d" % x["from_feeder_no"], "to_feeder_id": "F%02d" % x["to_feeder_no"],
                        "start_index": x["start_index"], "end_index": x["end_index"], "share": x["share"]} for x in switching_log()])
    return {"feeder": feeder, "calendar_day": cal, "weather_hourly": wx, "meter_reading": mr, "planted_event": pe, "switching_log": sw}
