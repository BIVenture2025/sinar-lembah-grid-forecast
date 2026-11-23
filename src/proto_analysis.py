"""Prototype of the detector and the forecast on the oracle data: numbers for the mockups only (Skill 0 step 2)."""
import json, numpy as np, pandas as pd
from gen_oracle import generate, START, DAYS
from sklearn.ensemble import HistGradientBoostingRegressor
fs, infos, evs, rows = generate()
df = pd.DataFrame(rows, columns=["feeder_id", "i", "mw"])
df["ts"] = pd.Timestamp(START) + pd.to_timedelta(df.i, unit="h")
df["d"] = df.i // 24; df["h"] = df.i % 24
dinfo = pd.DataFrame([{"d": d, "day_type": x[1], "hol": int(bool(x[2])), "fest": int(x[3])} for d, x in enumerate(infos)])
df = df.merge(dinfo, on="d")
fmeta = pd.DataFrame(fs)[["feeder_id", "feeder_no", "substation_name", "feeder_type"]]
df = df.merge(fmeta, on="feeder_id")
temp = {}
from gen_oracle import temp_c
df["temp"] = [temp_c(d, h, infos[d]) for d, h in zip(df.d, df.h)]
D_GRADE, D_REPLAY = 332, 388   # 2026-09-21, 2026-11-16 day indexes
def baseline(lo, hi):
    b = df[(df.d >= lo) & (df.d < hi)].groupby(["feeder_id", "day_type", "h"]).mw.quantile([.25, .5, .75]).unstack()
    b.columns = ["p25", "p50", "p75"]; b = b.reset_index()
    b["sd"] = np.maximum((b.p75 - b.p25) / 1.349, 0.03 * b.p50); return b
def detect(lo, hi, b):
    x = df[(df.d >= lo) & (df.d < hi)].merge(b, on=["feeder_id", "day_type", "h"])
    x["z"] = (x.mw - x.p50) / x.sd
    a = x[(x.z >= 5) | (x.z <= -5)].copy(); a["type"] = np.where(a.z > 0, "Spike", "Drop")
    # flat: >= 6 consecutive identical values
    x = x.sort_values(["feeder_id", "i"]); x["same"] = x.groupby("feeder_id").mw.diff().abs() < 0.0005
    x["run"] = x.groupby(["feeder_id", (~x.same).cumsum()]).same.cumsum()
    fl = x[x.run == 5].copy(); fl["type"] = "Flat"
    return pd.concat([a[["feeder_id", "i", "mw", "z", "type"]], fl[["feeder_id", "i", "mw", "z", "type"]]])
al_g = detect(D_GRADE, D_REPLAY, baseline(D_GRADE - 56, D_GRADE))
al_r = detect(D_REPLAY, DAYS, baseline(D_REPLAY - 56, D_REPLAY))
al = pd.concat([al_g, al_r])
ev = pd.DataFrame(evs); ev["feeder_id"] = ev.feeder_no.map(lambda n: "F%02d" % n)
inwin = ev[(ev.start_index >= D_GRADE * 24)]
def overlaps(a):
    e = ev[ev.feeder_id == a.feeder_id]
    return bool(((e.start_index <= a.i) & (a.i <= e.end_index)).any())
al["true"] = [overlaps(r) for r in al.itertuples()]
from gen_oracle import switching_log
sw = pd.DataFrame(switching_log())
def switched(a):
    n = int(a.feeder_id[1:])
    e = sw[(sw.from_feeder_no == n) | (sw.to_feeder_no == n)]
    return bool(((e.start_index <= a.i) & (a.i < e.end_index)).any())
al["switching"] = [switched(r) for r in al.itertuples()]
asof = DAYS * 24 - 1
al["cause"] = np.where(al["true"], "Planted event", np.where(al.switching, "Switching log", "Unexplained"))
al["day"] = al.i // 24
last24 = al[al.i > asof - 24]; wk = al[al.i >= D_REPLAY * 24]
fm = fmeta.set_index("feeder_id")
out_extra = {"alerts_explained_by_switching": int(al.switching.sum()), "alerts_neither": int((~al["true"] & ~al.switching).sum()),
             "cause_all": al.cause.value_counts().to_dict(), "cause_24h": last24.cause.value_counts().to_dict(),
             "cause_7d": wk.cause.value_counts().to_dict(), "feeders_7d": int(wk.feeder_id.nunique()),
             "alerts_per_day_30": [int((al.day == d).sum()) for d in range(DAYS - 30, DAYS)],
             "alerts_total": len(al), "top_sub_7d": wk.merge(fmeta, on="feeder_id").substation_name.value_counts().head(1).to_dict(),
             "top_sub_7d_cause": wk.merge(fmeta, on="feeder_id").groupby("substation_name").cause.agg(lambda s: s.value_counts().idxmax()).to_dict(),
             "heat_7d": {s: [int(((wk.feeder_id.map(fm.substation_name) == s) & (wk.day == D_REPLAY + k)).sum()) for k in range(7)] for s in sorted(fmeta.substation_name.unique())},
             "latest_alerts_cause": wk.sort_values("i", ascending=False).head(7).cause.tolist(),
             "f38_alerts": al[al.feeder_id == "F38"].sort_values("i", ascending=False).assign(ts=lambda x: (pd.Timestamp(START) + pd.to_timedelta(x.i, unit="h")).astype(str))[["ts", "type", "mw", "z", "cause", "i"]].round(2).to_dict("records"),
             "f38_event": ev[(ev.feeder_id == "F38") & (ev.start_index >= D_REPLAY * 24)][["event_id", "event_type", "start_index", "end_index"]].to_dict("records")}
asof = DAYS * 24 - 1
matured = inwin[inwin.end_index <= asof - 24]
caught = {r.event_id: bool(((al.feeder_id == r.feeder_id) & (al.i >= r.start_index) & (al.i <= r.end_index)).any()) for r in matured.itertuples()}
rec = pd.Series(caught); matured = matured.assign(caught=matured.event_id.map(caught))
out = {"alerts_grade_window": len(al_g), "alerts_replay_week": len(al_r), "alerts_last24": int((al.i > asof - 24).sum()),
       "precision_matured": round(al[al.i <= asof - 24]["true"].mean(), 3), "events_matured": len(matured),
       "recall_by_type": matured.groupby("event_type").caught.mean().round(2).to_dict(),
       "events_by_type": matured.event_type.value_counts().to_dict(),
       "replay_alerts_by_day": al_r.groupby(al_r.i // 24 - D_REPLAY).size().to_dict()}
# ---- forecast prototype
df = df.sort_values(["feeder_id", "i"])
g = df.groupby("feeder_id").mw
df["lag24"] = g.shift(24); df["lag168"] = g.shift(168)
df["lag336"] = g.shift(336); df["lag504"] = g.shift(504); df["lag672"] = g.shift(672)
df["mean4w"] = df[["lag168", "lag336", "lag504", "lag672"]].mean(axis=1)
df["dow"] = (df.d + START.weekday()) % 7
df["dt_code"] = df.day_type.map({"Weekday": 0, "Saturday": 1, "Sunday or holiday": 2})
df["ft_code"] = df.feeder_type.map({"Residential": 0, "Commercial": 1, "Industrial": 2, "Mixed": 3})
df["temp_fc"] = df.temp + 0.5  # crude stand-in for a forecast temperature
feat = ["lag24", "lag168", "mean4w", "h", "dow", "dt_code", "hol", "fest", "ft_code", "feeder_no", "temp_fc"]
res = []
for wk in range(9):
    lo = D_GRADE + 7 * wk; hi = min(lo + 7, DAYS)
    tr = df[(df.d < lo) & df.lag672.notna()]
    m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08, random_state=7).fit(tr[feat], tr.mw)
    te = df[(df.d >= lo) & (df.d < hi)].copy(); te["pred"] = m.predict(te[feat]); te["naive"] = te.lag168
    res.append(te)
bt = pd.concat(res)
daily = bt.groupby("d").apply(lambda x: pd.Series({"wape_m": (x.mw - x.pred).abs().sum() / x.mw.sum(), "wape_n": (x.mw - x.naive).abs().sum() / x.mw.sum()}))
diff = daily.wape_n - daily.wape_m
rng = np.random.default_rng(7); boots = [rng.choice(diff.values, len(diff)).mean() for _ in range(1000)]
tot = bt.groupby(["d", "h"]).agg(mw=("mw", "sum"), pred=("pred", "sum")).reset_index()
out.update({"wape_model": round(daily.wape_m.mean(), 4), "wape_naive": round(daily.wape_n.mean(), 4),
            "gain_ci": [round(np.percentile(boots, 2.5), 4), round(np.percentile(boots, 97.5), 4)],
            "daily_peak_actual_last": round(tot[tot.d == DAYS - 1].mw.max(), 1)})
# tomorrow (approx: reuse last model on next-day features built from lags)
last = df[df.d == DAYS - 1]
out["system_peak_by_day_last7"] = df[df.d >= DAYS - 7].groupby(["d", "h"]).mw.sum().groupby(level=0).max().round(1).tolist()
out["sub_peak_last_day"] = df[df.d == DAYS - 1].groupby(["substation_name", "h"]).mw.sum().groupby(level=0).max().round(1).to_dict()
out["hourly_total_last_day"] = df[df.d == DAYS - 1].groupby("h").mw.sum().round(1).tolist()
out["hourly_pred_last_day"] = tot[tot.d == DAYS - 1].sort_values("h").pred.round(1).tolist()
out["daily_wape_m"] = daily.wape_m.round(4).tolist(); out["daily_wape_n"] = daily.wape_n.round(4).tolist()
out["alerts_by_sub_replay"] = al_r.merge(fmeta, on="feeder_id").groupby("substation_name").size().to_dict()
out["latest_alerts"] = al_r.sort_values("i", ascending=False).head(8).assign(ts=lambda x: (pd.Timestamp(START) + pd.to_timedelta(x.i, unit="h")).astype(str)).merge(fmeta, on="feeder_id")[["ts", "feeder_id", "substation_name", "type", "mw", "z"]].round(2).to_dict("records")
out.update(out_extra)
json.dump(out, open("proto_numbers.json", "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k not in ("daily_wape_m", "daily_wape_n", "latest_alerts", "hourly_total_last_day", "hourly_pred_last_day")}, indent=1, default=str))
