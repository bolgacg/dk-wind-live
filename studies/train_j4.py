"""Final fit of J4catDK (and J4cat, the same model without DKcast, a separate entrant) for the live forecast, with the same
spec as the frozen 2026 test (studies/e3_test.py), trained on every hour from 18 Feb 2025 up to the newest settlement
data, so the models have seen a winter.

Writes live/models/<name>/: <zone>_s<k>.txt (stage 1, 5 seeds), stage2_<zone>.txt (offshore curtailment) and
meta.json (feature order, seeds, training hours).

Usage: OMP_NUM_THREADS=4 nice -n 10 python3 live/studies/train_j4.py [--until 2026-01-01 --out models_e3 --only j4catdk]"""
import json, sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LIVE, ZONES, capacity_proxy
from train import PARAMS, N_ROUNDS, load_actuals
from joint import add_time, dkcast, joint_cat, member_frames, prices, stage2_inputs, HOLIDAYS
from e3_test import HOL26, OFFSHORE, SEEDS, K, TRAIN0
import joint

STAGE2_ROUNDS = 300


def booster(X, y, seed=0, rounds=N_ROUNDS):
    return lgb.train({**PARAMS, "seed": seed, "num_threads": 4}, lgb.Dataset(X, y), rounds)


def main():
    # --until 2026-01-01 --out models_e3 --only j4catdk reproduces the frozen test's model, for the replay simulation
    arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    until, outroot, only = pd.Timestamp(arg("--until", "2100-01-01"), tz="UTC"), arg("--out", "models"), arg("--only", None)
    joint.END = until
    HOLIDAYS.update(HOL26)
    fr = member_frames()
    Y = load_actuals()
    cap = capacity_proxy(Y)
    pr = prices()
    JC = add_time(joint_cat(fr))
    for name, X in (("j4catdk", JC.join(dkcast(), how="inner")), ("j4cat", JC)):
        if only and name != only:
            continue
        idx = X.index.intersection(Y.dropna().index).intersection(cap.dropna().index)
        tr = idx[(idx >= TRAIN0) & (idx < until)]
        print(f"{name}: {X.shape[1]} inputs, {len(tr)} h, {tr.min()} to {tr.max()}", flush=True)
        out = LIVE / outroot / name
        out.mkdir(parents=True, exist_ok=True)
        folds = np.array_split(np.arange(len(tr)), K)
        oof = pd.DataFrame(index=tr)
        for z in ZONES:
            y = (Y[z] / cap[z]).clip(0, 1.2).loc[tr]
            o = pd.Series(0.0, index=tr)
            for f in folds:
                keep = np.setdiff1d(np.arange(len(tr)), f)
                o.iloc[f] = np.clip(booster(X.loc[tr[keep]], y.iloc[keep]).predict(X.loc[tr[f]]), 0, None)
            oof[z] = o
            for k in range(SEEDS):
                booster(X.loc[tr], y, seed=k).save_model(str(out / f"{z}_s{k}.txt"))
            print(f"  {name} {z} done", flush=True)
        S = stage2_inputs(oof, tr, pr)
        ok = S[[c for c in S if c.startswith("p_")]].notna().all(axis=1).to_numpy()
        for z in OFFSHORE:
            r = (Y[z] / cap[z]).clip(0, 1.2).loc[tr] - oof[z]
            booster(S[ok], r[ok], rounds=STAGE2_ROUNDS).save_model(str(out / f"stage2_{z}.txt"))
        json.dump({"name": name, "features": list(X.columns), "stage2_features": list(S.columns), "seeds": SEEDS,
                   "offshore_stage2": OFFSHORE, "hours": len(tr), "from": str(tr.min()), "to": str(tr.max()),
                   "params": PARAMS, "rounds": N_ROUNDS, "stage2_rounds": STAGE2_ROUNDS,
                   "spec": "as studies/e3_test.py (frozen 29 Oct 2026, 2026 test 5.56% of capacity)"},
                  open(out / "meta.json", "w"), indent=1)


if __name__ == "__main__":
    main()
