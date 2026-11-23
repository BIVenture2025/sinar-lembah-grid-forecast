#!/usr/bin/env python3
"""stats_check.py - the statistics check a model or test result passes before it reaches a page (W4 A5, guide 212f).

WHY. P34's Risk page says "the ML model ranks slightly better" on test AUC 0.709 against 0.692, a difference of
0.017 with no interval (W4 design review, finding 8). A claim of "better", "higher" or "calibrated" on a page needs
an interval. Standard library only, so it runs in the cloud container, on the device VM and in a Fabric notebook.

WHAT IT CHECKS (hold-out rows only: label 0/1 and one or two score columns)
  events     positives and negatives >= --min-events (default 30) each, else INSUFFICIENT_EVENTS
  auc        AUC (rank based, ties averaged) with a percentile bootstrap 95% interval (--boot, default 1000, seed 7)
  compare    with two scores: the paired bootstrap interval of AUC(b) - AUC(a). "b better" only when the whole interval
             is above 0; otherwise NO_DIFFERENCE_SHOWN (the page may say "about the same", not "better")
  calib      for scores read as probabilities: Brier, expected calibration error (10 equal-count bins), mean predicted
             against the observed rate with its Wilson 95% interval; MISCALIBRATED when the mean is outside it
REGRESSION MODE (P37, 2026-11-23: a forecast against a benchmark)
  wape       pooled WAPE per prediction column (sum |actual - pred| / sum actual) with a BLOCK bootstrap 95% interval;
             blocks are a column (a week, a fold), resampled whole so autocorrelation inside a block is kept
  compare    with two predictions: the paired block-bootstrap interval of WAPE(a) - WAPE(b) in points. "b better" only
             when the whole interval is above 0; otherwise NO_DIFFERENCE_SHOWN
  coverage   with --lo/--hi: share of rows inside the range, Wilson 95% interval, against --nominal (default 0.8)
  floor      fewer than --min-blocks (default 5) blocks gives INSUFFICIENT_BLOCKS
USAGE
  python3 stats_check.py --csv holdout.csv --label y --score score_a [--score score_b] [--prob] [--json out.json]
  python3 stats_check.py --regression --csv bt.csv --actual y --pred naive --pred model --block week [--lo lo --hi hi]
  python3 stats_check.py --selftest
EXIT 0 checked (read the verdicts) | 2 bad input | 3 nothing read
The installed statistical-analysis skill is loaded at the same gate to word the result (Skill 3, A5)."""
import csv
import json
import math
import random
import sys


def auc(y, s):
    pairs = sorted(zip(s, y))
    n = len(pairs)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = r
        i = j + 1
    pos = sum(1 for _, t in pairs if t == 1)
    neg = n - pos
    if pos == 0 or neg == 0:
        return float("nan")
    rsum = sum(r for r, (_, t) in zip(ranks, pairs) if t == 1)
    return (rsum - pos * (pos + 1) / 2.0) / (pos * neg)


def _pct(v, q):
    v = sorted(x for x in v if not math.isnan(x))
    if not v:
        return float("nan")
    k = (len(v) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def boot_auc(y, scores, b=1000, seed=7):
    """Paired bootstrap: the same resampled rows for every score. Returns per-score AUC lists."""
    rnd = random.Random(seed)
    n = len(y)
    out = [[] for _ in scores]
    for _ in range(b):
        idx = [rnd.randrange(n) for _ in range(n)]
        yy = [y[i] for i in idx]
        for j, s in enumerate(scores):
            out[j].append(auc(yy, [s[i] for i in idx]))
    return out


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def calibration(y, p, bins=10):
    n = len(y)
    brier = sum((pi - yi) ** 2 for yi, pi in zip(y, p)) / n
    order = sorted(range(n), key=lambda i: p[i])
    ece = 0.0
    for b in range(bins):
        idx = order[b * n // bins:(b + 1) * n // bins]
        if idx:
            ece += len(idx) / n * abs(sum(p[i] for i in idx) / len(idx) - sum(y[i] for i in idx) / len(idx))
    lo, hi = wilson(sum(y), n)
    mean_p = sum(p) / n
    return {"brier": brier, "ece": ece, "mean_predicted": mean_p, "observed_rate": sum(y) / n,
            "observed_ci": [lo, hi], "verdict": "CALIBRATED_IN_THE_MEAN" if lo <= mean_p <= hi else "MISCALIBRATED"}


def check(y, scores, names, prob=False, min_events=30, b=1000, seed=7):
    pos = sum(y)
    neg = len(y) - pos
    R = {"rows": len(y), "positives": pos, "negatives": neg, "scores": {}}
    if pos < min_events or neg < min_events:
        R["verdict"] = "INSUFFICIENT_EVENTS"
        return R
    bs = boot_auc(y, scores, b, seed)
    for nm, s, dist in zip(names, scores, bs):
        R["scores"][nm] = {"auc": auc(y, s), "auc_ci": [_pct(dist, 0.025), _pct(dist, 0.975)]}
        if prob:
            R["scores"][nm]["calibration"] = calibration(y, s)
    if len(scores) == 2:
        d = [b2 - a2 for a2, b2 in zip(bs[0], bs[1])]
        lo, hi = _pct(d, 0.025), _pct(d, 0.975)
        R["compare"] = {"diff": R["scores"][names[1]]["auc"] - R["scores"][names[0]]["auc"], "diff_ci": [lo, hi]}
        R["verdict"] = (f"{names[1].upper()}_BETTER" if lo > 0 else f"{names[0].upper()}_BETTER" if hi < 0
                        else "NO_DIFFERENCE_SHOWN")
    else:
        R["verdict"] = "CHECKED"
    return R


def wape(a, f):
    den = sum(a)
    return sum(abs(x - y) for x, y in zip(a, f)) / den if den else float("nan")


def check_regression(actual, preds, names, blocks, lo=None, hi=None, nominal=0.8, min_blocks=5, b=1000, seed=7):
    keys = sorted(set(blocks))
    R = {"rows": len(actual), "blocks": len(keys), "preds": {}}
    if len(keys) < min_blocks:
        R["verdict"] = "INSUFFICIENT_BLOCKS"
        return R
    # per block: sum of actual, and sum of absolute error per prediction (WAPE is pooled, so block sums are enough)
    agg = {k: [0.0] + [0.0] * len(preds) for k in keys}
    for i, k in enumerate(blocks):
        agg[k][0] += actual[i]
        for j, f in enumerate(preds):
            agg[k][j + 1] += abs(actual[i] - f[i])
    rnd = random.Random(seed)
    dist = [[] for _ in preds]
    for _ in range(b):
        pick = [agg[rnd.choice(keys)] for _ in keys]
        den = sum(x[0] for x in pick)
        for j in range(len(preds)):
            dist[j].append(sum(x[j + 1] for x in pick) / den)
    for j, nm in enumerate(names):
        R["preds"][nm] = {"wape": wape(actual, preds[j]), "wape_ci": [_pct(dist[j], 0.025), _pct(dist[j], 0.975)]}
    if len(preds) == 2:
        d = [100 * (x - y) for x, y in zip(dist[0], dist[1])]          # points; > 0 means the second prediction is better
        lo_d, hi_d = _pct(d, 0.025), _pct(d, 0.975)
        R["compare"] = {"gain_points": 100 * (R["preds"][names[0]]["wape"] - R["preds"][names[1]]["wape"]), "gain_ci": [lo_d, hi_d]}
        R["verdict"] = (f"{names[1].upper()}_BETTER" if lo_d > 0 else f"{names[0].upper()}_BETTER" if hi_d < 0
                        else "NO_DIFFERENCE_SHOWN")
    else:
        R["verdict"] = "CHECKED"
    if lo is not None and hi is not None:
        k = sum(1 for a_, l_, h_ in zip(actual, lo, hi) if l_ <= a_ <= h_)
        w = wilson(k, len(actual))
        R["coverage"] = {"inside": k, "rows": len(actual), "share": k / len(actual), "ci": list(w), "nominal": nominal,
                         "verdict": "COVERAGE_OK" if w[0] <= nominal <= w[1] else ("TOO_WIDE" if w[0] > nominal else "TOO_NARROW")}
    return R


def _synthetic(n, strength, seed):
    rnd = random.Random(seed)
    y, s = [], []
    for _ in range(n):
        t = 1 if rnd.random() < 0.2 else 0
        y.append(t)
        s.append(rnd.gauss(strength * t, 1.0))
    return y, s


def selftest():
    fails = 0

    def ok(c, m):
        nonlocal fails
        print(("  ok   " if c else "  FAIL ") + m)
        fails += 0 if c else 1
    ok(abs(auc([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]) - 0.75) < 1e-12, "auc: the textbook 4-row case is 0.75")
    ok(abs(auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) - 0.5) < 1e-12, "auc: all ties give 0.5")
    y, a = _synthetic(2000, 0.6, 1)
    rnd = random.Random(2)
    b = [v + rnd.gauss(0.9 * t, 0.3) for v, t in zip(a, y)]           # clearly stronger
    R = check(y, [a, b], ["a", "b"], b=300)
    ok(R["verdict"] == "B_BETTER", f"positive: a clearly stronger score is called better ({R['verdict']}, diff {R['compare']['diff']:.3f})")
    c = [v + rnd.gauss(0, 0.05) for v in a]                              # the same score plus noise
    R2 = check(y, [a, c], ["a", "c"], b=300)
    ok(R2["verdict"] == "NO_DIFFERENCE_SHOWN", f"false positive: a near-copy is NOT called better ({R2['verdict']}, "
       f"diff {R2['compare']['diff']:.4f}, CI {R2['compare']['diff_ci'][0]:.4f} to {R2['compare']['diff_ci'][1]:.4f})")
    R3 = check(y[:100], [a[:100]], ["a"], b=50)
    ok(R3["verdict"] == "INSUFFICIENT_EVENTS", f"floor: 100 rows with ~20 events stop at INSUFFICIENT_EVENTS ({R3['positives']})")
    p_good = [0.2] * len(y)
    p_bad = [0.6] * len(y)
    ok(calibration(y, p_good)["verdict"] == "CALIBRATED_IN_THE_MEAN" and calibration(y, p_bad)["verdict"] == "MISCALIBRATED",
       "calibration: the base rate passes in the mean, three times it fails")
    # regression mode (P37): 12 weekly blocks of 168 hourly rows
    rnd = random.Random(11)
    act, wk, nv, gd, cp, lo_, hi_ = [], [], [], [], [], [], []
    for w in range(12):
        for h in range(168):
            base = 100 + 30 * math.sin(h / 24 * 2 * math.pi)
            a_ = base * (1 + rnd.gauss(0, 0.05))
            act.append(a_); wk.append(w)
            nv.append(base * (1 + rnd.gauss(0, 0.08)))                     # benchmark: wider error
            g_ = a_ * (1 + rnd.gauss(0, 0.03)); gd.append(g_)              # model: clearly closer
            cp.append(nv[-1] * (1 + rnd.gauss(0, 0.002)))                  # a near-copy of the benchmark
            lo_.append(g_ * (1 - 0.0385)); hi_.append(g_ * (1 + 0.0385))   # +-1.2816 sd of 3%: about 80% coverage
    R4 = check_regression(act, [nv, gd], ["naive", "model"], wk, lo_, hi_, b=400)
    ok(R4["verdict"] == "MODEL_BETTER", f"regression positive: a clearly closer forecast is called better ({R4['verdict']}, "
       f"gain {R4['compare']['gain_points']:.2f} pts, CI {R4['compare']['gain_ci'][0]:.2f} to {R4['compare']['gain_ci'][1]:.2f})")
    R5 = check_regression(act, [nv, cp], ["naive", "copy"], wk, b=400)
    ok(R5["verdict"] == "NO_DIFFERENCE_SHOWN", f"regression false positive: a near-copy is NOT called better ({R5['verdict']}, "
       f"gain {R5['compare']['gain_points']:.3f} pts)")
    ok(R4["coverage"]["verdict"] == "COVERAGE_OK", f"coverage: an 80% range covers about 80% ({R4['coverage']['share']:.3f}, {R4['coverage']['verdict']})")
    R6 = check_regression(act[:168 * 3], [nv[:168 * 3]], ["naive"], wk[:168 * 3], b=50)
    ok(R6["verdict"] == "INSUFFICIENT_BLOCKS", f"floor: 3 weekly blocks stop at INSUFFICIENT_BLOCKS ({R6['blocks']})")
    print(f"[scan] selftest ran 10 controls, {10 - fails} passed")
    return 1 if fails else 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    opt = lambda k: argv[argv.index(k) + 1] if k in argv else None  # noqa: E731
    if "--regression" in argv:
        path, act_c, blk = opt("--csv"), opt("--actual"), opt("--block")
        pn = [argv[i + 1] for i, a in enumerate(argv) if a == "--pred"]
        if not path or not act_c or not blk or not 1 <= len(pn) <= 2:
            print("usage: --regression --csv FILE --actual COL --pred COL [--pred COL] --block COL [--lo COL --hi COL] [--json OUT]")
            return 2
        rows = [r for r in csv.DictReader(open(path, encoding="utf-8-sig")) if r.get(act_c) not in (None, "")]
        print(f"[scan] {len(rows)} row(s) with an actual read from {path}")
        if not rows:
            return 3
        try:
            a_ = [float(r[act_c]) for r in rows]
            P_ = [[float(r[n]) for r in rows] for n in pn]
            lo_c, hi_c = opt("--lo"), opt("--hi")
            L_ = [float(r[lo_c]) for r in rows] if lo_c else None
            H_ = [float(r[hi_c]) for r in rows] if hi_c else None
        except (KeyError, ValueError) as e:
            print(f"bad input: {e}")
            return 2
        R = check_regression(a_, P_, pn, [r[blk] for r in rows], L_, H_, nominal=float(opt("--nominal") or 0.8),
                             min_blocks=int(opt("--min-blocks") or 5), b=int(opt("--boot") or 1000))
        print(json.dumps(R, indent=1))
        if opt("--json"):
            json.dump(R, open(opt("--json"), "w"), indent=1)
        return 0
    path, label = opt("--csv"), opt("--label")
    names = [argv[i + 1] for i, a in enumerate(argv) if a == "--score"]
    if not path or not label or not 1 <= len(names) <= 2:
        print("usage: --csv FILE --label COL --score COL [--score COL] [--prob] [--json OUT]")
        return 2
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    print(f"[scan] {len(rows)} row(s) read from {path}")
    if not rows:
        return 3
    try:
        y = [int(float(r[label])) for r in rows]
        scores = [[float(r[n]) for r in rows] for n in names]
    except (KeyError, ValueError) as e:
        print(f"bad input: {e}")
        return 2
    R = check(y, scores, names, prob="--prob" in argv, min_events=int(opt("--min-events") or 30),
              b=int(opt("--boot") or 1000))
    print(json.dumps(R, indent=1))
    if opt("--json"):
        json.dump(R, open(opt("--json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
