"""build_kql.py - P37: write the Eventhouse scripts from the generator oracle (gen_oracle.py).

Outputs (folder kql/):
  01_schema.kql      tables (OneLake availability set at creation, 5-minute latency), streaming ingestion off, functions
  02_reference.kql   reference and ground-truth tables from the oracle (datatables, exact float literals)
  03_history.kql     history load 2025-10-24 .. 2026-11-15 in 30-day chunks
  04_backfill.kql    baseline B1, scored readings and alerts for the grading window (21 Sep .. 15 Nov), baseline B2
  05_policies.kql    two chained update policies (meter_reading -> reading_scored -> reading_alert)
  06_replay.kql      168 hourly batches (16 .. 22 Nov) + the flat-meter scan after each
  07_controls.kql    control totals
  DatabaseSchema.kql the Git copy of the schema (01 + 05)
Blocks are separated by lines '//--' (kusto_run.py). Every number in the KQL arithmetic follows gen_oracle.py's order.
"""
import json, os
from gen_oracle import (feeders, planted_events, switching_log, SHAPE, MONTH_TEMP, HOUR_TEMP, TYPE_COOL, TYPE_FESTIVE,
                        HOLIDAYS, FESTIVE, START, DAYS, HOURS, day_info, generate)

OUT = "kql"
os.makedirs(OUT, exist_ok=True)
REPLAY_FROM = 388 * 24          # 2026-11-16 00:00
GRADE_FROM, B1_FROM = 332, 248  # day indexes: 2026-09-21, 2026-06-29 (12-week baselines, review item 6)
SEP = "\n//--\n"


def lit(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return "real(%r)" % v if v != int(v) else "real(%r)" % v
    if isinstance(v, int):
        return "long(%d)" % v
    return "'%s'" % str(v).replace("'", "\\'")


def datatable(schema, rows):
    body = ",\n  ".join(", ".join(lit(v) if not (isinstance(v, str) and v.startswith("datetime(")) else v for v in r) for r in rows)
    return "datatable(%s) [\n  %s\n]" % (schema, body)


MIRROR = "policy mirroring dataformat=parquet with (IsEnabled=true, TargetLatencyInMinutes=5)"
TABLES = [
    ("feeder", "feeder_id:string, feeder_no:long, feeder_name:string, substation_id:string, substation_name:string, district:string, feeder_type:string, type_code:string, rated_peak_mw:real"),
    ("calendar_day", "day_index:long, ['date']:datetime, day_type:string, holiday_name:string, is_festive:bool, month:long"),
    ("load_shape", "type_code:string, day_type:string, hour_of_day:long, shape:real"),
    ("month_temp", "month:long, mean_c:real"),
    ("hour_temp", "hour_of_day:long, hour_offset:real"),
    ("type_param", "type_code:string, cool_k:real, festive_k:real"),
    ("planted_event", "event_id:string, feeder_id:string, event_type:string, start_index:long, end_index:long, start_hour:datetime, end_hour:datetime, start_date:datetime, factor:real, stuck_mw:real"),
    ("switching_log", "switch_id:string, from_feeder_id:string, to_feeder_id:string, start_index:long, end_index:long, start_hour:datetime, end_hour:datetime, share:real"),
    ("switching_hour", "feeder_id:string, hour_index:long, switch_id:string"),
    ("weather_hourly", "hour_index:long, reading_hour:datetime, reading_date:datetime, hour_of_day:long, temp_c:real, temp_fc_c:real"),
    ("meter_reading", "feeder_id:string, reading_hour:datetime, reading_date:datetime, hour_of_day:long, hour_index:long, demand_mw:real, batch_id:string, loaded_at:datetime"),
    ("baseline_profile", "baseline_id:string, feeder_id:string, day_type:string, hour_of_day:long, usual_mw:real, spread_mw:real, p25_mw:real, p75_mw:real, n:long, valid_from_index:long, valid_to_index:long"),
    ("reading_scored", "feeder_id:string, reading_hour:datetime, reading_date:datetime, hour_of_day:long, hour_index:long, demand_mw:real, day_type:string, usual_mw:real, spread_mw:real, z:real, switch_id:string, baseline_id:string, batch_id:string"),
    ("reading_alert", "alert_id:string, feeder_id:string, reading_hour:datetime, reading_date:datetime, hour_of_day:long, hour_index:long, alert_type:string, z:real, demand_mw:real, usual_mw:real, spread_mw:real, switch_id:string, source:string, batch_id:string, detected_at:datetime"),
]
MIRRORED = {"weather_hourly", "feeder", "calendar_day", "planted_event", "switching_log", "meter_reading", "reading_scored", "reading_alert"}

FUNCS = []
FUNCS.append(r'''.create-or-alter function with (folder = "gen", docstring = "Uniform [0,1) from three longs: 32-bit mixing hash, exact copy of gen_oracle.u", skipvalidation = "true") fn_u(a:long, b:long, c:long) {
    let x0 = binary_and(binary_xor(binary_xor(a * 73856093, b * 19349663), c * 83492791), 4294967295);
    let x1 = binary_and(binary_xor(binary_shift_right(x0, 16), x0) * 73244475, 4294967295);
    let x2 = binary_and(binary_xor(binary_shift_right(x1, 16), x1) * 73244475, 4294967295);
    let x3 = binary_xor(binary_shift_right(x2, 16), x2);
    todouble(x3) / 4294967296.0
}''')
FUNCS.append(r'''.create-or-alter function with (folder = "gen", docstring = "Clean demand (MW) for all feeders, hour_index in [from_index, to_index): gen_oracle.base_demand", skipvalidation = "true") fn_clean(from_index:long, to_index:long) {
    range hour_index from from_index to to_index - 1 step 1
    | extend day_index = hour_index / 24, hour_of_day = hour_index % 24
    | lookup kind=inner calendar_day on day_index
    | extend tnoise = (fn_u(day_index, 1, 11) - 0.5) * 2.4, rain = fn_u(day_index, 2, 13) < 0.35
    | lookup kind=inner month_temp on month
    | lookup kind=inner hour_temp on hour_of_day
    | extend off = iff(rain and hour_of_day >= 13 and hour_of_day <= 18, hour_offset * 0.4, hour_offset)
    | extend temp_c = mean_c + tnoise + off
    | extend k = 1
    | join kind=inner (feeder | project feeder_id, feeder_no, type_code, rated_peak_mw, k = 1) on k
    | lookup kind=inner type_param on type_code
    | lookup kind=inner load_shape on type_code, day_type, hour_of_day
    | extend cool = 1.0 + cool_k * (temp_c - 27.0) / 10.0
    | extend growth = 1.0 + 0.03 * hour_index / 8760.0
    | extend festive_f = iff(is_festive, festive_k, 1.0)
    | extend noise = 1.0 + 0.10 * (fn_u(feeder_no, hour_index, 1) + fn_u(feeder_no, hour_index, 2) + fn_u(feeder_no, hour_index, 3) - 1.5)
    | extend dayf = 1.0 + 0.08 * (fn_u(feeder_no, day_index, 4) - 0.5)
    | extend clean_mw = rated_peak_mw * shape * cool * growth * festive_f * noise * dayf
    | project feeder_id, hour_index, day_index, hour_of_day, clean_mw
}''')
FUNCS.append(r'''.create-or-alter function with (folder = "gen", docstring = "Hourly weather in [from_index, to_index): actual temperature and its day-ahead forecast (gen_oracle.weather)", skipvalidation = "true") fn_weather(from_index:long, to_index:long) {
    range hour_index from from_index to to_index - 1 step 1
    | extend day_index = hour_index / 24, hour_of_day = hour_index % 24
    | lookup kind=inner calendar_day on day_index
    | extend tnoise = (fn_u(day_index, 1, 11) - 0.5) * 2.4, rain = fn_u(day_index, 2, 13) < 0.35
    | lookup kind=inner month_temp on month
    | lookup kind=inner hour_temp on hour_of_day
    | extend off = iff(rain and hour_of_day >= 13 and hour_of_day <= 18, hour_offset * 0.4, hour_offset)
    | extend temp_c = mean_c + tnoise + off
    | extend temp_fc_c = temp_c + (fn_u(day_index, 5, 53) - 0.5) * 2.0 + (fn_u(hour_index, 6, 59) - 0.5) * 0.6
    | extend reading_hour = datetime(2025-10-24) + hour_index * 1h
    | project hour_index, reading_hour, reading_date = startofday(reading_hour), hour_of_day, temp_c, temp_fc_c
}''')
FUNCS.append(r'''.create-or-alter function with (folder = "gen", docstring = "Generated readings for hour_index in [from_index, to_index): switching transfers, then planted events (last event wins), rounded to 0.001 MW", skipvalidation = "true") fn_gen(from_index:long, to_index:long) {
    let c = fn_clean(from_index, to_index);
    let sw = switching_log
        | mv-expand hour_index = range(start_index, end_index - 1, 1) to typeof(long)
        | where hour_index >= from_index and hour_index < to_index
        | project from_feeder_id, to_feeder_id, hour_index, share;
    let moved = sw
        | join kind=inner (c | project from_feeder_id = feeder_id, hour_index, clean_mw) on from_feeder_id, hour_index
        | extend m = clean_mw * share;
    let delta = union (moved | project feeder_id = from_feeder_id, hour_index, d = -m), (moved | project feeder_id = to_feeder_id, hour_index, d = m);
    let ev = planted_event
        | mv-expand hour_index = range(start_index, end_index - 1, 1) to typeof(long)
        | where hour_index >= from_index and hour_index < to_index
        | summarize arg_max(event_id, event_type, factor, start_index, end_index, stuck_mw) by feeder_id, hour_index;
    c
    | join kind=leftouter delta on feeder_id, hour_index
    | extend series = iff(isnull(d), clean_mw, clean_mw + d)
    | join kind=leftouter ev on feeder_id, hour_index
    | extend out_mw = case(event_type in ("Spike", "Drop"), series * factor,
                           event_type == "Flat", stuck_mw,
                           event_type == "Drift", series * (1.0 + (factor - 1.0) * (hour_index - start_index) / (end_index - start_index)),
                           series)
    | extend reading_hour = datetime(2025-10-24) + hour_index * 1h
    | project feeder_id, reading_hour, reading_date = startofday(reading_hour), hour_of_day, hour_index, demand_mw = round(out_mw, 3)
}''')
FUNCS.append(r'''.create-or-alter function with (folder = "detect", docstring = "Usual load (median) and robust spread by feeder x day type x hour over days [from_day, to_day)", skipvalidation = "true") fn_baseline(bid:string, from_day:long, to_day:long, valid_from_index:long, valid_to_index:long) {
    meter_reading
    | where hour_index >= from_day * 24 and hour_index < to_day * 24
    | extend day_index = hour_index / 24
    | lookup kind=inner calendar_day on day_index
    | summarize percentiles(demand_mw, 25, 50, 75), n = count() by feeder_id, day_type, hour_of_day
    | project baseline_id = bid, feeder_id, day_type, hour_of_day, usual_mw = percentile_demand_mw_50,
              spread_mw = max_of((percentile_demand_mw_75 - percentile_demand_mw_25) / 1.349, 0.03 * percentile_demand_mw_50),
              p25_mw = percentile_demand_mw_25, p75_mw = percentile_demand_mw_75, n, valid_from_index, valid_to_index
}''')
SCORE_BODY = r'''    | extend day_index = hour_index / 24
    | lookup kind=inner (calendar_day | project day_index, day_type) on day_index
    | lookup kind=leftouter (baseline_profile | where baseline_id == bid | project feeder_id, day_type, hour_of_day, usual_mw, spread_mw) on feeder_id, day_type, hour_of_day
    | lookup kind=leftouter switching_hour on feeder_id, hour_index
    | extend z = (demand_mw - usual_mw) / spread_mw
    | project feeder_id, reading_hour, reading_date, hour_of_day, hour_index, demand_mw, day_type, usual_mw, spread_mw, z,
              switch_id = coalesce(switch_id, ""), baseline_id = bid, batch_id'''
FUNCS.append(r'''.create-or-alter function with (folder = "detect", docstring = "Score readings in [from_index, to_index) against baseline bid (backfill)", skipvalidation = "true") fn_score_range(from_index:long, to_index:long, bid:string) {
    meter_reading
    | where hour_index >= from_index and hour_index < to_index
''' + SCORE_BODY + "\n}")
FUNCS.append(r'''.create-or-alter function with (folder = "detect", docstring = "Update policy 1: score each new batch against the baseline valid for its hours; rows outside every baseline are skipped", skipvalidation = "true") fn_score_policy() {
    let b = baseline_profile | summarize by baseline_id, valid_from_index, valid_to_index;
    meter_reading
    | extend k = 1
    | join kind=inner (b | extend k = 1) on k
    | where hour_index >= valid_from_index and hour_index < valid_to_index
    | project-away k, k1, valid_from_index, valid_to_index
    | extend day_index = hour_index / 24
    | lookup kind=inner (calendar_day | project day_index, day_type) on day_index
    | lookup kind=leftouter (baseline_profile | project baseline_id, feeder_id, day_type, hour_of_day, usual_mw, spread_mw) on baseline_id, feeder_id, day_type, hour_of_day
    | lookup kind=leftouter switching_hour on feeder_id, hour_index
    | extend z = (demand_mw - usual_mw) / spread_mw
    | project feeder_id, reading_hour, reading_date, hour_of_day, hour_index, demand_mw, day_type, usual_mw, spread_mw, z,
              switch_id = coalesce(switch_id, ""), baseline_id, batch_id
}''')
ALERT_PROJ = r'''    | where abs(z) >= 5.0
    | project alert_id = strcat(feeder_id, "-", tostring(hour_index), "-", iff(z > 0, "S", "D")), feeder_id, reading_hour, reading_date, hour_of_day, hour_index,
              alert_type = iff(z > 0, "Spike", "Drop"), z, demand_mw, usual_mw, spread_mw, switch_id, source = src, batch_id, detected_at = now()'''
FUNCS.append(r'''.create-or-alter function with (folder = "detect", docstring = "Spike and drop alerts from scored readings in [from_index, to_index) (backfill)", skipvalidation = "true") fn_alert_range(from_index:long, to_index:long) {
    let src = "Backfill";
    reading_scored
    | where hour_index >= from_index and hour_index < to_index
''' + ALERT_PROJ + "\n}")
FUNCS.append(r'''.create-or-alter function with (folder = "detect", docstring = "Update policy 2: spike and drop alerts from each newly scored batch", skipvalidation = "true") fn_alert_policy() {
    let src = "Update policy";
    reading_scored
''' + ALERT_PROJ + "\n}")
FUNCS.append(r'''.create-or-alter function with (folder = "detect", docstring = "Flat-meter alerts: the hour in [from_index, to_index) at which a feeder has repeated one reading for 6 hours (one alert per episode)", skipvalidation = "true") fn_flat_range(from_index:long, to_index:long, src:string) {
    meter_reading
    | where hour_index >= from_index - 6 and hour_index < to_index
    | summarize arg_max(loaded_at, *) by feeder_id, hour_index
    | order by feeder_id asc, hour_index asc
    | extend same = prev(feeder_id) == feeder_id and prev(hour_index) == hour_index - 1 and abs(demand_mw - prev(demand_mw)) < 0.0005
    | extend run = row_cumsum(iff(same, 1, 0), not(same))
    | where run == 5 and hour_index >= from_index
    | extend day_index = hour_index / 24
    | lookup kind=inner (calendar_day | project day_index, day_type) on day_index
    | lookup kind=leftouter switching_hour on feeder_id, hour_index
    | project alert_id = strcat(feeder_id, "-", tostring(hour_index), "-F"), feeder_id, reading_hour, reading_date, hour_of_day, hour_index,
              alert_type = "Flat", z = real(null), demand_mw, usual_mw = real(null), spread_mw = real(null), switch_id = coalesce(switch_id, ""),
              source = src, batch_id, detected_at = now()
}''')


def schema_blocks():
    b = []
    for name, cols in TABLES:
        b.append(".create-merge table %s (%s) with (folder = \"%s\")" % (name, cols, "stream" if name in ("meter_reading", "reading_scored", "reading_alert") else ("detect" if name == "baseline_profile" else "reference")))
        if name in MIRRORED:
            b.append(".alter table %s %s" % (name, MIRROR))
    for name in ("meter_reading", "reading_scored", "reading_alert"):
        b.append(".alter table %s policy streamingingestion disable" % name)
    b += FUNCS
    return b


POLICIES = [
    ".alter table reading_scored policy update @'[{\"IsEnabled\": true, \"Source\": \"meter_reading\", \"Query\": \"fn_score_policy()\", \"IsTransactional\": true, \"PropagateIngestionProperties\": true}]'",
    ".alter table reading_alert policy update @'[{\"IsEnabled\": true, \"Source\": \"reading_scored\", \"Query\": \"fn_alert_policy()\", \"IsTransactional\": true, \"PropagateIngestionProperties\": true}]'",
]


def dt(x):
    return "datetime(%s)" % x.strftime("%Y-%m-%d %H:%M")


def reference_blocks():
    import datetime as d
    fs = feeders()
    rows = [(f["feeder_id"], f["feeder_no"], f["feeder_name"], f["substation_id"], f["substation_name"], f["district"], f["feeder_type"], f["type_code"], float(f["rated_peak_mw"])) for f in fs]
    b = [".set-or-replace feeder <| " + datatable(TABLES[0][1], rows)]
    cal = []
    for k in range(DAYS + 1):  # + the forecast day
        date, day_type, hol, fest, _, _ = day_info(k)
        cal.append((k, "datetime(%s)" % date.isoformat(), day_type, hol, bool(fest), date.month))
    b.append(".set-or-replace calendar_day <| " + datatable(TABLES[1][1], cal))
    shp = [(t, dtp, h, float(v)) for (t, dtp), vals in sorted(SHAPE.items()) for h, v in enumerate(vals)]
    b.append(".set-or-replace load_shape <| " + datatable(TABLES[2][1], shp))
    b.append(".set-or-replace month_temp <| " + datatable(TABLES[3][1], [(m + 1, float(v)) for m, v in enumerate(MONTH_TEMP)]))
    b.append(".set-or-replace hour_temp <| " + datatable(TABLES[4][1], [(h, float(v)) for h, v in enumerate(HOUR_TEMP)]))
    b.append(".set-or-replace type_param <| " + datatable(TABLES[5][1], [(t, float(TYPE_COOL[t]), float(TYPE_FESTIVE[t])) for t in "RCIM"]))
    # stuck values for flat events: the oracle's own reading at the event's first hour (= round(series[start], 3))
    fs2, infos, evs, rows_all = generate()
    val = {(r[0], r[1]): r[2] for r in rows_all}
    stuck = {e["event_id"]: val[("F%02d" % e["feeder_no"], e["start_index"])] for e in evs if e["event_type"] == "Flat"}
    swl = switching_log()
    evr = []
    for e in evs:
        s = START + d.timedelta(hours=e["start_index"]); t = START + d.timedelta(hours=e["end_index"])
        evr.append((e["event_id"], "F%02d" % e["feeder_no"], e["event_type"], e["start_index"], e["end_index"], dt(s), dt(t),
                    "datetime(%s)" % s.date().isoformat(), float(e["factor"]), float(stuck.get(e["event_id"], 0.0))))
    b.append(".set-or-replace planted_event <| " + datatable(TABLES[6][1], evr))
    swr = []
    for w in swl:
        s = START + d.timedelta(hours=w["start_index"]); t = START + d.timedelta(hours=w["end_index"])
        swr.append((w["switch_id"], "F%02d" % w["from_feeder_no"], "F%02d" % w["to_feeder_no"], w["start_index"], w["end_index"], dt(s), dt(t), float(w["share"])))
    b.append(".set-or-replace switching_log <| " + datatable(TABLES[7][1], swr))
    b.append(".set-or-replace switching_hour <| switching_log | extend f = pack_array(from_feeder_id, to_feeder_id) | mv-expand feeder_id = f to typeof(string) "
             "| mv-expand hour_index = range(start_index, end_index - 1, 1) to typeof(long) | summarize switch_id = take_any(switch_id) by feeder_id, hour_index")
    return b, stuck


def history_blocks():
    b = []
    for lo in range(0, REPLAY_FROM, 720):
        hi = min(lo + 720, REPLAY_FROM)
        tag = "H%04d" % (lo // 24)
        b.append(".set-or-append meter_reading with (tags = '[\"ingest-by:%s\"]', ingestIfNotExists = '[\"%s\"]') <| fn_gen(%d, %d) | extend batch_id = '%s', loaded_at = now()" % (tag, tag, lo, hi, tag))
    return b


def backfill_blocks():
    return [
        ".set-or-append baseline_profile with (tags = '[\"ingest-by:BL_B1\"]', ingestIfNotExists = '[\"BL_B1\"]') <| fn_baseline('B1', %d, %d, %d, %d)" % (B1_FROM, GRADE_FROM, GRADE_FROM * 24, REPLAY_FROM),
        ".set-or-append reading_scored with (tags = '[\"ingest-by:BF_SCORED\"]', ingestIfNotExists = '[\"BF_SCORED\"]') <| fn_score_range(%d, %d, 'B1')" % (GRADE_FROM * 24, REPLAY_FROM),
        ".set-or-append reading_alert with (tags = '[\"ingest-by:BF_ALERT\"]', ingestIfNotExists = '[\"BF_ALERT\"]') <| fn_alert_range(%d, %d)" % (GRADE_FROM * 24, REPLAY_FROM),
        ".set-or-append reading_alert with (tags = '[\"ingest-by:BF_FLAT\"]', ingestIfNotExists = '[\"BF_FLAT\"]') <| fn_flat_range(%d, %d, 'Backfill')" % (GRADE_FROM * 24, REPLAY_FROM),
        ".set-or-append baseline_profile with (tags = '[\"ingest-by:BL_B2\"]', ingestIfNotExists = '[\"BL_B2\"]') <| fn_baseline('B2', %d, %d, %d, %d)" % (REPLAY_FROM // 24 - 84, REPLAY_FROM // 24, REPLAY_FROM, HOURS + 24),
    ]


def replay_blocks():
    b = []
    for h in range(REPLAY_FROM, HOURS):
        tag = "R%05d" % h
        b.append(".set-or-append meter_reading with (tags = '[\"ingest-by:%s\"]', ingestIfNotExists = '[\"%s\"]') <| fn_gen(%d, %d) | extend batch_id = '%s', loaded_at = now()" % (tag, tag, h, h + 1, tag))
        b.append(".set-or-append reading_alert with (tags = '[\"ingest-by:F%s\"]', ingestIfNotExists = '[\"F%s\"]') <| fn_flat_range(%d, %d, 'Hourly scan')" % (tag, tag, h, h + 1))
    return b


CONTROLS = [
    "meter_reading | summarize rows = count(), feeders = dcount(feeder_id), hours = dcount(hour_index), sum_mw = sum(demand_mw), min_h = min(hour_index), max_h = max(hour_index)",
    "meter_reading | summarize rows = count(), sum_mw = sum(demand_mw) by day = hour_index / 24 | order by day asc",
    "reading_scored | summarize rows = count(), scored = countif(isnotnull(z)) by baseline_id",
    "reading_alert | summarize n = count() by source, alert_type | order by source asc, alert_type asc",
    "union withsource = t feeder, calendar_day, load_shape, month_temp, hour_temp, type_param, planted_event, switching_log, switching_hour, baseline_profile | summarize n = count() by t | order by t asc",
]

if __name__ == "__main__":
    sch = schema_blocks()
    ref, stuck = reference_blocks()
    import gen_oracle as g
    newev = [e for e in g.planted_events() if e["event_id"] in ("E062", "E063", "E064")]
    import datetime as d
    nev = []
    for e in newev:
        st = START + d.timedelta(hours=e["start_index"]); en = START + d.timedelta(hours=e["end_index"])
        nev.append((e["event_id"], "F%02d" % e["feeder_no"], e["event_type"], e["start_index"], e["end_index"], dt(st), dt(en),
                    "datetime(%s)" % st.date().isoformat(), float(e["factor"]), 0.0))
    wt = [x for x in TABLES if x[0] == "weather_hourly"][0]
    patch = [".create-merge table weather_hourly (%s) with (folder = \"reference\")" % wt[1], ".alter table weather_hourly %s" % MIRROR,
             [f for f in FUNCS if "fn_weather" in f][0],
             ".set-or-append weather_hourly with (tags = '[\"ingest-by:WX\"]', ingestIfNotExists = '[\"WX\"]') <| fn_weather(0, %d)" % (HOURS + 24),
             ".set-or-append planted_event with (tags = '[\"ingest-by:EV_WEAK\"]', ingestIfNotExists = '[\"EV_WEAK\"]') <| " + datatable(TABLES[[t[0] for t in TABLES].index("planted_event")][1], nev),
             "weather_hourly | summarize n = count(), t = sum(temp_c), f = sum(temp_fc_c)", "planted_event | summarize n = count()"]
    files = {"08_patch_weather_events.kql": patch, "01_schema.kql": sch, "02_reference.kql": ref, "03_history.kql": history_blocks(), "04_backfill.kql": backfill_blocks(),
             "05_policies.kql": POLICIES, "06_replay.kql": replay_blocks(), "07_controls.kql": CONTROLS}
    for n, blocks in files.items():
        open(os.path.join(OUT, n), "w", encoding="utf-8", newline="\n").write(SEP.join(blocks) + "\n")
        print(n, len(blocks), "blocks", sum(len(x) for x in blocks), "chars")
    # Git copy: one script, statements one after another (DatabaseSchema.kql shape, P30)
    open(os.path.join(OUT, "DatabaseSchema.kql"), "w", encoding="utf-8", newline="\n").write(
        "// KQL script\n// P37 EH_SinarLembah schema: tables (OneLake availability at creation), streaming off, functions, update policies\n\n" + "\n".join(sch + POLICIES) + "\n")
    json.dump(stuck, open(os.path.join(OUT, "stuck_values.json"), "w"), indent=1)
