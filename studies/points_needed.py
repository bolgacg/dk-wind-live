"""How much weather does a day-ahead wind forecast need? (Question borrowed from Ingolfsson, Bhatia, Zeppelin et al.,
J Phys Chem B 2020: how much compositional complexity a membrane model needs before more stops helping.)

Target: total Danish wind output (four zones summed), normalised by the summed capacity proxy. Inputs: IFS
previous_day1 100 m wind at k of the 34 points. Train before 1 Apr 2026, choose on 1 Apr to 18 Jul 2026, report on
19 Jul to 18 Oct 2026 (the live lane's test window). Two ladders:
  random: k in 1,2,3,5,8,13,21,34, five random subsets each
  greedy: add the point that most lowers validation error, up to 10 points
Writes live/reports/points_needed.json and prints a table.
"""
import json, random, sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import LIVE, POINTS, ZONES, capacity_proxy, features
from train import load_actuals, load_weather

VAL0, TEST0 = pd.Timestamp("2026-04-01", tz="UTC"), pd.Timestamp("2026-07-19", tz="UTC")
P = dict(objective="l1", learning_rate=0.05, num_leaves=15, min_data_in_leaf=50, feature_fraction=0.8,
         bagging_fraction=0.8, bagging_freq=1, verbose=-1, num_threads=2, seed=1)
ROUNDS = 400


def main():
    sp, di = load_weather("ecmwf_ifs025")
    X = features(sp, di)
    Y = load_actuals()
    cap = capacity_proxy(Y)
    tot, ctot = Y[ZONES].sum(axis=1), cap[ZONES].sum(axis=1)
    idx = X.index.intersection(tot.dropna().index).intersection(ctot.dropna().index)
    X, y, c, act = X.loc[idx], (tot / ctot).loc[idx].clip(0, 1.2), ctot.loc[idx], tot.loc[idx]
    tr, va, te = idx < VAL0, (idx >= VAL0) & (idx < TEST0), idx >= TEST0

    def cols(pts):
        return [f"{a}_{p}" for p in pts for a in ("s", "u", "v")] + ["hour", "doy"]

    def fit(pts, split_eval):
        m = lgb.train(P, lgb.Dataset(X.loc[tr, cols(pts)], y[tr]), ROUNDS)
        mask = split_eval
        pred = np.clip(m.predict(X.loc[mask, cols(pts)]), 0, None) * c[mask]
        return float((pred - act[mask]).abs().mean())

    names = list(POINTS)
    out = {"mean_total_output_test_mw": float(act[te].mean()), "random": [], "greedy": []}
    rng = random.Random(7)
    for k in (1, 2, 3, 5, 8, 13, 21, 34):
        reps = 1 if k == 34 else 5
        maes = [fit(rng.sample(names, k), te) for _ in range(reps)]
        out["random"].append({"k": k, "test_mae_mean": float(np.mean(maes)), "test_mae_min": float(min(maes)),
                              "test_mae_max": float(max(maes))})
        print(f"random k={k:2d}: test MAE {np.mean(maes):.0f} MW (range {min(maes):.0f} to {max(maes):.0f})", flush=True)
    chosen = []
    for step in range(10):
        best = min((fit(chosen + [p], va), p) for p in names if p not in chosen)
        chosen.append(best[1])
        t = fit(chosen, te)
        out["greedy"].append({"k": len(chosen), "added": best[1], "val_mae": best[0], "test_mae": t})
        print(f"greedy k={len(chosen):2d} +{best[1]:15s} val {best[0]:.0f}  test {t:.0f} MW", flush=True)
        json.dump(out, open(LIVE / "reports" / "points_needed.json", "w"), indent=1)
    print("DONE points_needed", flush=True)


if __name__ == "__main__":
    main()
