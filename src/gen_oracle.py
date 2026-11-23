"""gen_oracle.py - P37 Sinar Lembah Grid: the generator specification as runnable Python (the oracle).

The KQL generator (Build) implements the same arithmetic in the same order. Noise comes from an integer hash, shapes
and temperatures from lookup tables, so both sides produce the same doubles and a row-level comparison is exact
(rounding ties aside). Synthetic, declared: every name and number here is invented.

Period: 2025-10-24 00:00 to 2026-11-22 23:00 MYT (395 days, 9,480 hours), 48 feeders = 455,040 readings.
"""
import datetime as dt
import json

START = dt.datetime(2025, 10, 24)
DAYS = 395
HOURS = DAYS * 24
M32 = 4294967296


MASK = 0xFFFFFFFF


def u(a, b, c):
    """Deterministic uniform in [0,1) from three non-negative ints: a 32-bit mixing hash (xor, shift, multiply).
    Every intermediate stays below 2^63, so KQL long arithmetic (binary_xor, binary_shift_right, binary_and)
    reproduces it exactly."""
    x = ((a * 73856093) ^ (b * 19349663) ^ (c * 83492791)) & MASK
    x = (((x >> 16) ^ x) * 0x45D9F3B) & MASK
    x = (((x >> 16) ^ x) * 0x45D9F3B) & MASK
    x = (x >> 16) ^ x
    return x / M32


SUBSTATIONS = [  # id, fictional name, district, feeder type mix (R residential, C commercial, I industrial, M mixed)
    ("PPU01", "PPU Taman Sinar Jaya", "Petaling Jaya", "CCMMRR"),
    ("PPU02", "PPU Bukit Lembah", "Subang Jaya", "CCMRRI"),
    ("PPU03", "PPU Kota Damai", "Shah Alam", "IIIMRR"),
    ("PPU04", "PPU Pelabuhan Indah", "Klang", "IIIIMR"),
    ("PPU05", "PPU Puchong Permai", "Puchong", "MMRRCI"),
    ("PPU06", "PPU Cheras Murni", "Cheras", "RRRMMC"),
    ("PPU07", "PPU Kepong Hijau", "Kepong", "RRMMIC"),
    ("PPU08", "PPU Ampang Seri", "Ampang", "RRRCMM"),
]
TYPE_NAME = {"R": "Residential", "C": "Commercial", "I": "Industrial", "M": "Mixed"}
TYPE_PEAK = {"R": 4.5, "C": 6.0, "I": 7.5, "M": 5.0}
TYPE_COOL = {"R": 0.25, "C": 0.35, "I": 0.08, "M": 0.20}
TYPE_FESTIVE = {"R": 1.0, "C": 0.85, "I": 0.85, "M": 0.92}

SHAPE = {
    ("R", "Weekday"): [0.55, 0.50, 0.47, 0.45, 0.45, 0.48, 0.55, 0.60, 0.55, 0.50, 0.50, 0.52, 0.55, 0.56, 0.57, 0.58, 0.62, 0.70, 0.82, 0.92, 0.97, 1.00, 0.90, 0.70],
    ("R", "Saturday"): [0.58, 0.53, 0.49, 0.47, 0.46, 0.47, 0.50, 0.56, 0.62, 0.66, 0.68, 0.70, 0.71, 0.71, 0.70, 0.69, 0.71, 0.76, 0.85, 0.93, 0.97, 0.98, 0.90, 0.72],
    ("R", "Sunday or holiday"): [0.60, 0.55, 0.51, 0.48, 0.47, 0.47, 0.49, 0.54, 0.62, 0.68, 0.72, 0.74, 0.75, 0.74, 0.73, 0.72, 0.73, 0.78, 0.86, 0.94, 0.98, 0.97, 0.88, 0.70],
    ("C", "Weekday"): [0.30, 0.28, 0.27, 0.27, 0.28, 0.32, 0.42, 0.60, 0.80, 0.92, 0.97, 1.00, 0.98, 0.99, 1.00, 0.98, 0.95, 0.88, 0.75, 0.62, 0.52, 0.45, 0.38, 0.33],
    ("C", "Saturday"): [0.30, 0.28, 0.27, 0.27, 0.28, 0.30, 0.36, 0.48, 0.62, 0.72, 0.77, 0.80, 0.80, 0.80, 0.79, 0.77, 0.74, 0.69, 0.62, 0.54, 0.47, 0.41, 0.36, 0.32],
    ("C", "Sunday or holiday"): [0.28, 0.27, 0.26, 0.26, 0.26, 0.27, 0.30, 0.36, 0.44, 0.52, 0.57, 0.60, 0.61, 0.61, 0.60, 0.59, 0.57, 0.54, 0.50, 0.45, 0.40, 0.36, 0.32, 0.30],
    ("I", "Weekday"): [0.70, 0.69, 0.68, 0.68, 0.69, 0.72, 0.82, 0.92, 0.97, 0.99, 1.00, 1.00, 0.96, 0.98, 1.00, 0.99, 0.97, 0.93, 0.86, 0.82, 0.80, 0.78, 0.75, 0.72],
    ("I", "Saturday"): [0.68, 0.67, 0.66, 0.66, 0.67, 0.69, 0.75, 0.82, 0.86, 0.88, 0.89, 0.89, 0.86, 0.86, 0.86, 0.85, 0.83, 0.80, 0.76, 0.74, 0.72, 0.71, 0.70, 0.69],
    ("I", "Sunday or holiday"): [0.55, 0.54, 0.53, 0.53, 0.53, 0.54, 0.56, 0.58, 0.60, 0.61, 0.62, 0.62, 0.61, 0.61, 0.61, 0.60, 0.60, 0.59, 0.58, 0.57, 0.57, 0.56, 0.56, 0.55],
}
for dtp in ("Weekday", "Saturday", "Sunday or holiday"):  # Mixed = half residential + half commercial
    SHAPE[("M", dtp)] = [(a + b) / 2.0 for a, b in zip(SHAPE[("R", dtp)], SHAPE[("C", dtp)])]

MONTH_TEMP = [27.2, 27.6, 28.0, 28.4, 28.5, 28.2, 27.9, 27.9, 27.7, 27.6, 27.2, 27.0]  # daily mean, deg C, Jan..Dec
HOUR_TEMP = [-2.6, -2.9, -3.1, -3.3, -3.4, -3.4, -3.0, -1.8, -0.4, 1.0, 2.2, 3.1, 3.7, 4.0, 4.0, 3.6, 2.8, 1.6, 0.4, -0.5, -1.2, -1.7, -2.1, -2.4]

# KL and Selangor public holidays in the period (sources in the design guide); in-lieu days included.
HOLIDAYS = {
    "2025-12-25": "Christmas Day", "2026-01-01": "New Year's Day", "2026-02-01": "Thaipusam and Federal Territory Day",
    "2026-02-02": "Thaipusam holiday", "2026-02-17": "Chinese New Year", "2026-02-18": "Chinese New Year (second day)",
    "2026-03-07": "Nuzul Al-Quran", "2026-03-21": "Hari Raya Aidilfitri", "2026-03-22": "Hari Raya Aidilfitri (second day)",
    "2026-03-23": "Hari Raya Aidilfitri holiday", "2026-05-01": "Labour Day", "2026-05-27": "Hari Raya Haji",
    "2026-05-31": "Wesak Day", "2026-06-01": "Agong's Birthday", "2026-06-17": "Awal Muharram",
    "2026-08-25": "Maulidur Rasul", "2026-08-31": "National Day", "2026-09-16": "Malaysia Day",
    "2026-11-08": "Deepavali", "2026-11-09": "Deepavali holiday",
}
FESTIVE = [("2025-12-24", "2026-01-01"), ("2026-02-16", "2026-02-22"), ("2026-03-19", "2026-03-26")]


def feeders():
    out, n = [], 0
    for sid, sname, district, mix in SUBSTATIONS:
        for k, t in enumerate(mix):
            n += 1
            peak = round(TYPE_PEAK[t] * (0.8 + 0.4 * u(n, 0, 7)), 2)
            out.append({"feeder_id": "F%02d" % n, "feeder_no": n, "feeder_name": "%s F%d" % (sname.replace("PPU ", ""), k + 1),
                        "substation_id": sid, "substation_name": sname, "district": district,
                        "feeder_type": TYPE_NAME[t], "type_code": t, "rated_peak_mw": peak})
    return out


def day_info(d):
    """d = day index 0..DAYS-1 -> date, day_type, holiday name, festive flag, daily temperature noise, rain flag."""
    date = START.date() + dt.timedelta(days=d)
    ds = date.isoformat()
    hol = HOLIDAYS.get(ds, "")
    wd = date.weekday()  # Monday 0
    day_type = "Sunday or holiday" if (wd == 6 or hol) else ("Saturday" if wd == 5 else "Weekday")
    fest = any(a <= ds <= b for a, b in FESTIVE)
    tnoise = (u(d, 1, 11) - 0.5) * 2.4
    rain = u(d, 2, 13) < 0.35
    return date, day_type, hol, fest, tnoise, rain


def temp_c(d, h, info):
    date, _, _, _, tnoise, rain = info
    off = HOUR_TEMP[h]
    if rain and 13 <= h <= 18:
        off = off * 0.4
    return MONTH_TEMP[date.month - 1] + tnoise + off


def base_demand(f, d, h, info):
    """Clean demand in MW before any planted event."""
    date, day_type, _, fest, _, _ = info
    t = f["type_code"]
    shape = SHAPE[(t, day_type)][h]
    cool = 1.0 + TYPE_COOL[t] * (temp_c(d, h, info) - 27.0) / 10.0
    hour_index = d * 24 + h
    growth = 1.0 + 0.03 * hour_index / 8760.0
    festive = TYPE_FESTIVE[t] if fest else 1.0
    n = f["feeder_no"]
    noise = 1.0 + 0.10 * (u(n, hour_index, 1) + u(n, hour_index, 2) + u(n, hour_index, 3) - 1.5)
    dayf = 1.0 + 0.08 * (u(n, d, 4) - 0.5)
    return f["rated_peak_mw"] * shape * cool * growth * festive * noise * dayf


def planted_events():
    """Deterministic event list. Grading window 2026-09-21..2026-11-22 is guaranteed several of each detectable type."""
    ev, k = [], 0
    kinds = ["Spike", "Drop", "Flat"]
    for d in range(10, DAYS - 1, 7):  # one candidate per week
        k += 1
        n = 1 + int(u(k, 3, 17) * 48)
        kind = kinds[k % 3]
        start_h = int(u(k, 4, 19) * 24)
        dur = {"Spike": 1 + int(u(k, 5, 23) * 3), "Drop": 2 + int(u(k, 5, 23) * 5), "Flat": 8 + int(u(k, 5, 23) * 13)}[kind]
        factor = {"Spike": round(1.8 + 0.6 * u(k, 6, 29), 2), "Drop": round(0.05 + 0.3 * u(k, 6, 29), 2), "Flat": 1.0}[kind]
        s = d * 24 + start_h
        ev.append({"event_id": "E%03d" % k, "feeder_no": n, "event_type": kind, "start_index": s, "end_index": min(s + dur, HOURS),
                   "factor": factor})
    # replay week (2026-11-16..22 = days 388..394): four extra events so alerts arrive live
    for j, (d, n, kind, sh, dur, fac) in enumerate([(389, 7, "Spike", 19, 2, 2.1), (391, 22, "Drop", 10, 4, 0.12), (393, 38, "Flat", 6, 14, 1.0), (394, 30, "Spike", 18, 2, 2.0)]):
        k += 1
        ev.append({"event_id": "E%03d" % k, "feeder_no": n, "event_type": kind, "start_index": d * 24 + sh,
                   "end_index": d * 24 + sh + dur, "factor": fac})
    # two slow drifts (21 days, +18% linear): a sharp-change detector sees them late, if at all
    for n, d in ((15, 300), (41, 360)):
        k += 1
        ev.append({"event_id": "E%03d" % k, "feeder_no": n, "event_type": "Drift", "start_index": d * 24,
                   "end_index": min(d * 24 + 21 * 24, HOURS), "factor": 1.18})
    # three weak events in the replay week (review 2026-11-23, item 5): small enough that recall can fall
    for d, n, kind, sh, dur, fac in ((389, 12, "Spike", 14, 2, 1.35), (390, 27, "Drop", 9, 3, 0.72), (392, 44, "Spike", 20, 1, 1.4)):
        k += 1
        ev.append({"event_id": "E%03d" % k, "feeder_no": n, "event_type": kind, "start_index": d * 24 + sh,
                   "end_index": d * 24 + sh + dur, "factor": fac})
    return ev


def weather(i, info):
    """Hourly weather for hour index i: actual temperature and the day-ahead forecast of it (error about +-1 C)."""
    d, h = i // 24, i % 24
    t = temp_c(d, h, info)
    fc = t + (u(d, 5, 53) - 0.5) * 2.0 + (u(i, 6, 59) - 0.5) * 0.6
    return t, fc


def switching_log():
    """Planned load transfers: part of feeder A's load moves to feeder B (same substation) for some hours.
    They are operations, not anomalies, and are logged; the detector is not told about them."""
    out, k = [], 0
    for d in range(13, DAYS, 9):
        k += 1
        sub = int(u(k, 7, 31) * 8)
        a = sub * 6 + 1 + int(u(k, 8, 37) * 6)
        b = sub * 6 + 1 + (a - sub * 6) % 6
        start_h = 8 + int(u(k, 9, 41) * 10)
        dur = 4 + int(u(k, 10, 43) * 9)
        share = round(0.30 + 0.25 * u(k, 11, 47), 2)
        s = d * 24 + start_h
        out.append({"switch_id": "S%03d" % k, "from_feeder_no": a, "to_feeder_no": b, "start_index": s,
                    "end_index": min(s + dur, HOURS), "share": share})
    return out


def generate():
    fs = feeders()
    infos = [day_info(d) for d in range(DAYS)]
    evs = planted_events()
    by_feeder = {}
    for e in evs:
        by_feeder.setdefault(e["feeder_no"], []).append(e)
    rows = []
    clean = {f["feeder_no"]: [base_demand(f, i // 24, i % 24, infos[i // 24]) for i in range(HOURS)] for f in fs}
    moved = {f["feeder_no"]: [0.0] * HOURS for f in fs}
    for w in switching_log():
        for i in range(w["start_index"], w["end_index"]):
            m = clean[w["from_feeder_no"]][i] * w["share"]
            moved[w["from_feeder_no"]][i] -= m
            moved[w["to_feeder_no"]][i] += m
    for f in fs:
        n = f["feeder_no"]
        series = [clean[n][i] + moved[n][i] for i in range(HOURS)]
        out = list(series)
        for e in by_feeder.get(n, []):
            s, t = e["start_index"], e["end_index"]
            for i in range(s, t):
                if e["event_type"] in ("Spike", "Drop"):
                    out[i] = series[i] * e["factor"]
                elif e["event_type"] == "Flat":
                    out[i] = round(series[s], 3)
                elif e["event_type"] == "Drift":
                    out[i] = series[i] * (1.0 + (e["factor"] - 1.0) * (i - s) / (t - s))
        for i in range(HOURS):
            rows.append((f["feeder_id"], i, round(out[i], 3)))
    return fs, infos, evs, rows


if __name__ == "__main__":
    import sys, statistics
    fs, infos, evs, rows = generate()
    tot = sum(r[2] for r in rows)
    print("feeders", len(fs), "rows", len(rows), "sum_mw %.3f" % tot, "events", len(evs))
    json.dump({"feeders": fs, "events": evs, "switching": switching_log()}, open("oracle_meta.json", "w"), indent=1)
