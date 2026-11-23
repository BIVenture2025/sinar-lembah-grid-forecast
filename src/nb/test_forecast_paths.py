"""Review 2026-11-23 regression tests: K0 stops on incomplete inputs; the K6 factor widens a too-narrow range."""
import numpy as np, pandas as pd
from offline_tables import tables
import forecast_module as fm
T = tables()
for name, mut in (("missing hour", lambda m: m.drop(m.index[5000])), ("duplicate hour", lambda m: pd.concat([m, m.iloc[[7]]])),
                  ("day-395 reading", lambda m: pd.concat([m, m.iloc[[0]].assign(hour_index=9480)]))):
    T2 = dict(T, meter_reading=mut(T["meter_reading"]))
    out, v, _, _ = fm.run(T2, set())
    expect_stop = name != "day-395 reading"
    print(name, "->", v["K0"] if out is None else "ran", {k: x for k, x in v["K0_checks"].items() if not x})
    assert (out is None) == expect_stop, name
    if not expect_stop:
        break   # a day-395 row is ignored, not fatal; the full run is the offline test
# K6: residuals twice as wide out of sample as in sample -> factor > 1
rng = np.random.default_rng(1)
rows = []
for fold in range(1, 10):
    for h in range(24 * 7):
        sd = 0.02 if fold <= 4 else 0.05
        rows.append({"hour_index": fold * 1000 + h, "hour": h % 24, "fold": fold, "demand_mw": 100 * (1 + rng.normal(0, sd)), "forecast_mw": 100.0})
bt = pd.DataFrame(rows)
c = fm.k6_factor(bt)
q, cov = fm.ranges(bt.assign(all_="All"), ["all_"], c)
q1, cov1 = fm.ranges(bt.assign(all_="All"), ["all_"], 1.0)
print("K6 factor", c, "coverage folds 7-9 before", round(cov1, 3), "after", round(cov, 3))
assert c > 1.5 and cov > cov1
print("PASS")
