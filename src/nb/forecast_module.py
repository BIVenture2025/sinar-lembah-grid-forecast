"""forecast_module.py - P37 NB_SinarLembah_Forecast (Skill 3 route R5, regression). Pandas in, pandas out.

Spec: Design Package, forecast tab, with the 2026-11-23 review applied:
  * issue time = after the day's last hourly batch, so lag 24 is known for every target hour (review item 15)
  * forecast temperature from weather_hourly.temp_fc_c, never the actual (item 9)
  * 9 weekly folds 2026-09-21 .. 2026-11-22, refit per fold; hours with an alert dropped from training
  * one window and one definition everywhere: pooled WAPE over the 63 backtest days; gain = naive - model;
    weekly block bootstrap (9 blocks), 2,000 draws, seed 7; also without holiday-affected days (item 10)
  * ranges per level (feeder, substation, system) from that level's own residual quantiles, fitted on folds 1-6 and
    checked on folds 7-9 (item 8)
Kill criteria K0 K2 K3 K4 K6 K7 (spec dated 2026-11-23) are evaluated here; K8 (AutoML) in the notebook.
Code review 2026-11-23 (second pass) applied: K0 checks the inputs are complete (one row per feeder-hour, 48 x 9,480,
weather and calendar cover the forecast day) and stops the run; lags join on (feeder, hour - k) instead of shifting rows;
readings at or after the forecast day are ignored; the champion is the benchmark whenever K2, K3, K4 or K7 fires, and its
ranges come from its own residuals; K6 acts (scale factor fitted inside folds 1-6, checked on 7-9); the K7 hash covers
days 332-395 with the row count; no groupby.apply(include_groups=...) so Fabric Runtime 1.3 (pandas 2.1) also runs it.
"""
import hashlib
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

START = pd.Timestamp("2025-10-24")
FOLD0_DAY, LAST_DAY, FC_DAY = 332, 394, 395
N_FEEDERS, N_HOURS = 48, FC_DAY * 24
FEATS = ["lag24", "lag168", "mean4w", "hour", "dow", "dt_code", "hol", "fest", "ft_code", "feeder_no", "temp_fc"]


def completeness(meter_reading, feeder, calendar_day, weather_hourly):
    """K0 input checks. Returns a dict of named checks, each True when it holds."""
    mr = meter_reading[meter_reading["hour_index"] < N_HOURS]
    keys = mr[["feeder_id", "hour_index"]]
    wx = set(weather_hourly["hour_index"].astype(int))
    return {
        "feeders": int(feeder["feeder_id"].nunique()) == N_FEEDERS and len(feeder) == N_FEEDERS,
        "reading_rows": len(mr) == N_FEEDERS * N_HOURS,
        "one_row_per_feeder_hour": not keys.duplicated().any(),
        "hour_range": int(mr["hour_index"].min()) == 0 and int(mr["hour_index"].max()) == N_HOURS - 1,
        "no_null_demand": bool(mr["demand_mw"].notna().all()),
        "weather_hours": all(h in wx for h in range(N_HOURS + 24)) and not weather_hourly["hour_index"].duplicated().any(),
        "calendar_days": set(range(FC_DAY + 1)) <= set(calendar_day["day_index"].astype(int)) and not calendar_day["day_index"].duplicated().any(),
    }


def frame(meter_reading, feeder, calendar_day, weather_hourly):
    f = feeder[["feeder_id", "feeder_no", "substation_id", "feeder_type"]].copy()
    mr = meter_reading[["feeder_id", "hour_index", "demand_mw"]].copy()
    mr = mr[mr["hour_index"] < N_HOURS].drop_duplicates(["feeder_id", "hour_index"])   # review item 4
    # the forecast day: rows with no reading yet
    fc = pd.DataFrame([(fid, h) for fid in f["feeder_id"] for h in range(FC_DAY * 24, FC_DAY * 24 + 24)], columns=["feeder_id", "hour_index"])
    df = pd.concat([mr, fc], ignore_index=True).merge(f, on="feeder_id")
    df["day"] = df["hour_index"] // 24
    df["hour"] = (df["hour_index"] % 24).astype("int64")
    cal = calendar_day[["day_index", "day_type", "holiday_name", "is_festive"]].rename(columns={"day_index": "day"})
    df = df.merge(cal, on="day", how="left")
    df = df.merge(weather_hourly[["hour_index", "temp_fc_c"]].rename(columns={"temp_fc_c": "temp_fc"}), on="hour_index", how="left")
    base = df[["feeder_id", "hour_index", "demand_mw"]]
    for k in (24, 168, 336, 504, 672):   # join on the hour, not the row position (review item 3)
        lag = base.assign(hour_index=base["hour_index"] + k).rename(columns={"demand_mw": "lag%d" % k})
        df = df.merge(lag, on=["feeder_id", "hour_index"], how="left")
    df = df.sort_values(["feeder_id", "hour_index"]).reset_index(drop=True)
    assert not df.duplicated(["feeder_id", "hour_index"]).any(), "duplicate feeder-hour after the joins"
    df["mean4w"] = df[["lag168", "lag336", "lag504", "lag672"]].mean(axis=1)
    df["dow"] = ((df["day"] + START.weekday()) % 7).astype("int64")
    df["dt_code"] = df["day_type"].map({"Weekday": 0, "Saturday": 1, "Sunday or holiday": 2}).astype("int64")
    df["hol"] = (df["holiday_name"].fillna("") != "").astype("int64")
    df["fest"] = df["is_festive"].astype("int64")
    df["ft_code"] = df["feeder_type"].map({"Residential": 0, "Commercial": 1, "Industrial": 2, "Mixed": 3}).astype("int64")
    return df


def features_hash(df):
    """K7: hash of the features and target over the whole backtest and the forecast day (days 332-395), row count included."""
    x = df[(df["day"] >= FOLD0_DAY) & (df["day"] <= FC_DAY)].sort_values(["feeder_id", "hour_index"])[["feeder_id", "hour_index"] + FEATS + ["demand_mw"]]
    x = x.assign(demand_mw=x["demand_mw"].fillna(-1.0)).round(6)
    return hashlib.sha256(("rows=%d\n" % len(x) + x.to_csv(index=False)).encode()).hexdigest()


def model():
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08, random_state=7)


def backtest(df, alert_hours):
    """alert_hours: set of (feeder_id, hour_index) dropped from training."""
    res = []
    bad = df.set_index(["feeder_id", "hour_index"]).index.isin(list(alert_hours)) if alert_hours else np.zeros(len(df), bool)
    for k in range(9):
        lo, hi = FOLD0_DAY + 7 * k, min(FOLD0_DAY + 7 * k + 7, LAST_DAY + 1)
        tr = df[(df["day"] < lo) & df["lag672"].notna() & df["demand_mw"].notna() & ~bad]
        m = model().fit(tr[FEATS], tr["demand_mw"])
        te = df[(df["day"] >= lo) & (df["day"] < hi)].copy()
        te["forecast_mw"] = m.predict(te[FEATS]); te["naive_mw"] = te["lag168"]; te["fold"] = k + 1
        res.append(te)
    return pd.concat(res, ignore_index=True)


def wape(a, f):
    return float(np.abs(a - f).sum() / a.sum())


def daily(bt):
    e = bt.assign(act=bt["demand_mw"], err_m=(bt["demand_mw"] - bt["forecast_mw"]).abs(), err_n=(bt["demand_mw"] - bt["naive_mw"]).abs())
    return e.groupby("day")[["act", "err_m", "err_n"]].sum()


def block_boot(d, draws=2000, seed=7):
    """Weekly block bootstrap of the pooled-WAPE gain (naive - model), in points. d = daily frame with a week column."""
    rng = np.random.default_rng(seed)
    weeks = sorted(d["week"].unique())
    by = {w: d[d["week"] == w] for w in weeks}
    vals = []
    for _ in range(draws):
        pick = pd.concat([by[w] for w in rng.choice(weeks, len(weeks), replace=True)])
        vals.append(100 * (pick["err_n"].sum() - pick["err_m"].sum()) / pick["act"].sum())
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def _resid(bt, level_key):
    g = bt.groupby(level_key + ["hour_index", "hour", "fold"], as_index=False)[["demand_mw", "forecast_mw"]].sum()
    g["r"] = (g["demand_mw"] - g["forecast_mw"]) / g["forecast_mw"]
    return g, ["hour"] + ([c for c in level_key if c == "feeder_type"])


def _quant(g, by_cols, folds):
    return g[g["fold"].isin(folds)].groupby(by_cols)["r"].quantile([0.1, 0.9]).unstack().rename(columns={0.1: "q10", 0.9: "q90"}).reset_index()


def _cover(g, q, by_cols, folds, c=1.0):
    chk = g[g["fold"].isin(folds)].merge(q, on=by_cols)
    return float(((chk["r"] >= c * chk["q10"]) & (chk["r"] <= c * chk["q90"])).mean())


def ranges(bt, level_key, c=1.0):
    """Relative residual quantiles (10%, 90%) by hour for one level, fitted on folds 1-6, times the K6 factor c;
    coverage on folds 7-9 (out of sample)."""
    g, by_cols = _resid(bt, level_key)
    q = _quant(g, by_cols, range(1, 7))
    cov = _cover(g, q, by_cols, range(7, 10), c)
    q = q.assign(q10=q["q10"] * c, q90=q["q90"] * c)
    return q, cov


def k6_factor(bt):
    """K6 action: a width factor for the system range, fitted inside folds 1-6 (quantiles from folds 1-4, factor so that
    folds 5-6 cover 80%), so the check on folds 7-9 stays out of sample."""
    g, by_cols = _resid(bt.assign(all_="All"), ["all_"])
    q = _quant(g, by_cols, range(1, 5))
    grid = np.round(np.arange(0.5, 3.001, 0.01), 2)
    covs = [_cover(g, q, by_cols, (5, 6), c) for c in grid]
    return float(grid[int(np.argmin([abs(x - 0.80) for x in covs]))])


def run(tables, alert_hours, offline_hash=None):
    """Returns (outputs or None, verdict, final model or None, training frame or None). Outputs are None when K0 stops."""
    chk = completeness(tables["meter_reading"], tables["feeder"], tables["calendar_day"], tables["weather_hourly"])
    v = {"K0_checks": chk}
    if not all(chk.values()):
        v.update({"K0": "FIRED", "verdict": "FORECAST_KILLED", "register": False, "champion": None})
        return None, v, None, None
    df = frame(tables["meter_reading"], tables["feeder"], tables["calendar_day"], tables["weather_hourly"])
    fh = features_hash(df)
    bt = backtest(df, alert_hours)
    v.update({"features_hash": fh, "rows_backtest": len(bt)})
    # K0: data sufficiency on top of the completeness checks
    days = bt["day"].nunique(); feeders_per_fold = bt.groupby("fold")["feeder_id"].nunique().min()
    v["K0"] = "PASS" if days >= 56 and feeders_per_fold == 48 else "FIRED"
    fs = bt.assign(err=(bt["demand_mw"] - bt["forecast_mw"]).abs()).groupby("fold")[["err", "demand_mw"]].sum()
    fold_w = fs["err"] / fs["demand_mw"]
    v["K2"] = "FIRED" if (fold_w < 0.02).any() else "PASS"
    w_m, w_n = wape(bt["demand_mw"], bt["forecast_mw"]), wape(bt["demand_mw"], bt["naive_mw"])
    v["K3"] = "PASS" if w_m < w_n else "FIRED"
    d = daily(bt).reset_index(); d["week"] = (d["day"] - FOLD0_DAY) // 7
    lo, hi = block_boot(d)
    v["K4"] = "PASS" if lo > 0 else "FIRED"
    cal = tables["calendar_day"]
    hol_days = set(cal.loc[cal["holiday_name"].fillna("") != "", "day_index"].astype(int))
    affected = hol_days | {h + 7 for h in hol_days}
    d2 = d[~d["day"].isin(affected)]
    lo2, hi2 = block_boot(d2)
    v["K7"] = "PASS" if (offline_hash is None or offline_hash == fh) else "FIRED"
    champion = "Gradient boosting" if all(v[k] == "PASS" for k in ("K2", "K3", "K4", "K7")) else "Same hour last week"   # review item 5
    # ranges per level, from the champion's own residuals (review item 6)
    f = tables["feeder"][["feeder_id", "substation_id", "feeder_type"]]
    bt = bt.merge(f[["feeder_id"]], on="feeder_id")
    rb = bt if champion == "Gradient boosting" else bt.assign(forecast_mw=bt["naive_mw"])
    q_t, cov_t = ranges(rb.assign(all_="All"), ["all_"])
    c6 = 1.0
    v["K6"] = "PASS" if 0.70 <= cov_t <= 0.90 else "FIRED"
    if v["K6"] == "FIRED":   # review item 7: act, then check again on folds 7-9
        c6 = k6_factor(rb)
        q_t, cov_t2 = ranges(rb.assign(all_="All"), ["all_"], c6)
        v["K6_action"] = {"factor": c6, "coverage_before": round(cov_t, 3), "coverage_after": round(cov_t2, 3),
                          "result": "WITHIN_70_90" if 0.70 <= cov_t2 <= 0.90 else "STILL_OUTSIDE"}
        cov_t = cov_t2
    q_f, cov_f = ranges(rb, ["feeder_id", "feeder_type"], c6)
    q_s, cov_s = ranges(rb, ["substation_id"], c6)
    # final model and the forecast day
    alert_ix = df.set_index(["feeder_id", "hour_index"]).index.isin(list(alert_hours)) if alert_hours else np.zeros(len(df), bool)
    tr = df[(df["day"] <= LAST_DAY) & df["lag672"].notna() & df["demand_mw"].notna() & ~alert_ix]
    final = model().fit(tr[FEATS], tr["demand_mw"])
    tm = df[df["day"] == FC_DAY].copy()
    tm["forecast_mw"] = final.predict(tm[FEATS]); tm["naive_mw"] = tm["lag168"]; tm["fold"] = 0
    allr = pd.concat([bt.drop(columns=[c for c in bt.columns if c not in tm.columns]), tm], ignore_index=True)
    if champion != "Gradient boosting":
        allr["forecast_mw"] = allr["naive_mw"]
    # feeder-level ranges
    allr = allr.merge(q_f, on=["hour", "feeder_type"], how="left")
    allr["lo_mw"] = allr["forecast_mw"] * (1 + allr["q10"]); allr["hi_mw"] = allr["forecast_mw"] * (1 + allr["q90"])
    allr["target_hour"] = START + pd.to_timedelta(allr["hour_index"], unit="h")
    allr["target_date"] = allr["target_hour"].dt.normalize()
    fh_out = pd.DataFrame({
        "feeder_id": allr["feeder_id"], "target_date": allr["target_date"], "hour_of_day": allr["hour"].astype("int64"),
        "target_hour": allr["target_hour"], "hour_index": allr["hour_index"].astype("int64"),
        "forecast_mw": allr["forecast_mw"].round(4), "lo_mw": allr["lo_mw"].round(4), "hi_mw": allr["hi_mw"].round(4),
        "naive_mw": allr["naive_mw"].round(4), "actual_mw": allr["demand_mw"], "fold": allr["fold"].astype("int64"),
        "is_backtest": allr["fold"] > 0, "model_name": champion})
    # group levels: substation and system, ranges from their own residuals
    grp = []
    s = fh_out.merge(f[["feeder_id", "substation_id"]], on="feeder_id")
    for level, key, q in (("Substation", "substation_id", q_s), ("System", None, q_t)):
        k = s.assign(group_key=s[key] if key else "All")
        a = k.groupby(["group_key", "target_date", "hour_of_day", "target_hour", "hour_index", "fold", "is_backtest"], as_index=False).agg(
            forecast_mw=("forecast_mw", "sum"), naive_mw=("naive_mw", "sum"), actual_mw=("actual_mw", lambda x: x.sum(min_count=len(x))))
        a = a.merge(q.rename(columns={"hour": "hour_of_day"}), on="hour_of_day", how="left")
        a["lo_mw"] = (a["forecast_mw"] * (1 + a["q10"])).round(4); a["hi_mw"] = (a["forecast_mw"] * (1 + a["q90"])).round(4)
        a["level"] = level
        grp.append(a.drop(columns=["q10", "q90"]))
    fg = pd.concat(grp, ignore_index=True)
    metrics = [
        ("Forecast error", "Gradient boosting", w_m, None, None, days, "Backtest 9 weeks, pooled WAPE"),
        ("Forecast error", "Same hour last week", w_n, None, None, days, "Backtest 9 weeks, pooled WAPE"),
        ("Gain, points", "Gradient boosting", 100 * (w_n - w_m), lo, hi, days, "Backtest 9 weeks; 95% weekly block bootstrap"),
        ("Gain, points, without holiday-affected days", "Gradient boosting",
         100 * (d2["err_n"].sum() - d2["err_m"].sum()) / d2["act"].sum(), lo2, hi2, len(d2), "Days on or one week after a public holiday left out"),
        ("Range coverage", "Feeder", cov_f, None, None, 3, "Folds 7-9, 80% range"),
        ("Range coverage", "Substation", cov_s, None, None, 3, "Folds 7-9, 80% range"),
        ("Range coverage", "System", cov_t, None, None, 3, "Folds 7-9, 80% range"),
    ]
    mm = pd.DataFrame(metrics, columns=["metric", "model", "value", "ci_low", "ci_high", "n", "scope"])
    v.update({"wape_model": round(w_m, 5), "wape_naive": round(w_n, 5), "gain_ci": [round(lo, 3), round(hi, 3)],
              "gain_ci_no_holiday": [round(lo2, 3), round(hi2, 3)], "coverage": [round(cov_f, 3), round(cov_s, 3), round(cov_t, 3)],
              "champion": champion, "range_factor": c6, "rows_forecast": len(fh_out), "rows_group": len(fg)})
    register = v["K2"] == "PASS" and v["K7"] == "PASS" and v["K3"] == "PASS"
    v["register"] = register
    v["verdict"] = "FORECAST_OK" if v["K0"] == "PASS" and v["K7"] == "PASS" and v["K2"] == "PASS" else "FORECAST_KILLED"
    return {"gold_forecast_hourly": fh_out, "gold_forecast_group": fg, "gold_model_metric": mm}, v, final, tr
