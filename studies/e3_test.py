"""E3 frozen test: the one and only 2026 run of J4catDK with offshore curtailment, against the live recipe, ECMWF IFS
and Energinet. The spec was fixed from the 2025 validation (joint.py, reports/joint_val*.json) before this file ran.

Spec (frozen 29 Oct 2026):
  train   18 Feb to 31 Dec 2025 (hours with all four members and DKcast; DKcast starts 1 Mar 2025)
  test    1 Jan to 18 Oct 2026, read once
  model   J4catDK: the four members' speed and u/v at 34 sites side by side, plus DKcast mean and spread at 22 sites,
          hour, day of year; LightGBM as train.py, final fit averaged over 5 seeds
  stage 2 curtailment on DK1_offshore and DK2_offshore only: L1 model of (actual/cap minus stage 1) on stage-1
          forecasts made out of fold (6 folds over the training months), hour, weekday, holiday and the day-ahead
          prices known at 10:30 on D-1
  refs    B4 = live recipe (each member through its own power model, averaged), IFS through its own power model,
          Energinet day-ahead rescaled by its actual/forecast ratio over the previous 60 days
Scales: MAE of each area's hourly total as % of installed capacity (capacity = the live proxy), skill against IFS and
Energinet, imbalance cost in EUR per MWh produced ((actual minus forecast) x (spot minus imbalance price), as
experiments/imbalance.py), accuracy as an extra. All on the hours every source covers.

Usage: OMP_NUM_THREADS=4 nice -n 10 python3 live/studies/e3_test.py [--smoke]  ->  live/reports/e3_test.json, e3_test_preds.csv"""
import json, sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BLEND, LIVE, ROOT, ZONES, capacity_proxy
from train import PARAMS, N_ROUNDS, load_actuals, load_energinet_da
from joint import add_time, dkcast, joint_cat, member_frames, prices, stage2_inputs, HOLIDAYS
import joint

TRAIN0, TEST0, TEST1 = (pd.Timestamp(x, tz="UTC") for x in ("2025-02-18", "2026-01-01", "2026-10-19"))
SEEDS, K = 5, 6
if "--smoke" in sys.argv:  # code check on 2025 only (train to Oct, "test" Nov and Dec 2025, 1 seed); no 2026 read
    TEST0, TEST1, SEEDS = pd.Timestamp("2025-11-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC"), 1
OFFSHORE = ["DK1_offshore", "DK2_offshore"]
AREAS = {"DK1": ["DK1_offshore", "DK1_onshore"], "DK2": ["DK2_offshore", "DK2_onshore"]}
HOL26 = pd.to_datetime(["2026-01-01", "2026-04-02", "2026-04-03", "2026-04-05", "2026-04-06", "2026-05-14",
                        "2026-05-24", "2026-05-25", "2026-06-05", "2026-12-24", "2026-12-25", "2026-12-26"]).date


def fit(X, y, Xp, seed=0, rounds=N_ROUNDS):
    m = lgb.train({**PARAMS, "seed": seed, "num_threads": 4}, lgb.Dataset(X, y), rounds)
    return pd.Series(m.predict(Xp), index=Xp.index)


def main():
    joint.END = TEST1  # the frozen run reads 2026 up to the end of the test window
    HOLIDAYS.update(HOL26)
    fr = member_frames()
    Y = load_actuals()
    Y = Y[Y.index < TEST1]
    cap = capacity_proxy(Y)
    pr = prices()
    JX = add_time(joint_cat(fr)).join(dkcast(), how="inner")
    idx = JX.index.intersection(Y.dropna().index).intersection(cap.dropna().index)
    for f in fr.values():
        idx = idx.intersection(f.index)
    tr, te = idx[(idx >= TRAIN0) & (idx < TEST0)], idx[(idx >= TEST0) & (idx < TEST1)]
    print(f"train {tr.min()} to {tr.max()} ({len(tr)} h), test {te.min()} to {te.max()} ({len(te)} h)", flush=True)
    cf = {z: (Y[z] / cap[z]).clip(0, 1.2) for z in ZONES}
    P = {}
    # references: each member through its own power model (single fit, as live), B4 = their mean
    mem = {}
    for m, f in fr.items():
        X = add_time(f)
        mem[m] = pd.DataFrame({z: fit(X.loc[tr], cf[z].loc[tr], X.loc[te]).clip(0, None) for z in ZONES})
        print(f"  member {m} done", flush=True)
    P["blend"] = sum(mem.values()) / len(mem)
    P["ifs"] = mem["ifs"]
    # J4catDK stage 1: out-of-fold on the training months (for stage 2), 5-seed final fit for the test
    folds = np.array_split(np.arange(len(tr)), K)
    oof, s1 = pd.DataFrame(index=tr), pd.DataFrame(index=te)
    for z in ZONES:
        o = pd.Series(0.0, index=tr)
        for f in folds:
            keep = np.setdiff1d(np.arange(len(tr)), f)
            o.iloc[f] = fit(JX.loc[tr[keep]], cf[z].loc[tr[keep]], JX.loc[tr[f]]).clip(0, None).to_numpy()
        oof[z] = o
        s1[z] = sum(fit(JX.loc[tr], cf[z].loc[tr], JX.loc[te], seed=k) for k in range(SEEDS)).clip(0, None) / SEEDS
        print(f"  J4catDK {z} done", flush=True)
    S_tr, S_te = stage2_inputs(oof, tr, pr), stage2_inputs(s1, te, pr)
    ok = S_tr[[c for c in S_tr if c.startswith("p_")]].notna().all(axis=1).to_numpy()
    s2 = s1.copy()
    for z in OFFSHORE:
        r = cf[z].loc[tr] - oof[z]
        s2[z] = (s1[z] + fit(S_tr[ok], r[ok], S_te, rounds=300)).clip(0, None)
    P["j4catdk"], P["j4catdk_c"] = s1, s2
    P = {k: v * cap.loc[te] for k, v in P.items()}  # capacity factor to MW
    da = load_energinet_da()
    en = {}
    for z in ZONES:
        j = pd.concat([Y[z], da[z]], axis=1, keys=["a", "f"], sort=True).dropna()
        k = (j.a.rolling("60D").sum() / j.f.rolling("60D").sum()).resample("D").last().shift(1)
        en[z] = (da[z] * k.reindex(da[z].index, method="ffill")).reindex(te)
    P["energinet"] = pd.DataFrame(en)
    # scoring on the hours every source covers
    A = Y.loc[te, ZONES]
    ok = A.notna().all(axis=1)
    for v in P.values():
        ok &= v.notna().all(axis=1)
    ip = pd.read_parquet(ROOT / "data" / "clean" / "ImbalancePrice.parquet",
                         columns=["TimeUTC", "PriceArea", "ImbalancePriceEUR", "SpotPriceEUR"])
    ip["t"] = pd.to_datetime(ip.TimeUTC).dt.floor("h").dt.tz_localize("UTC")
    ip = ip.groupby(["t", "PriceArea"])[["SpotPriceEUR", "ImbalancePriceEUR"]].mean().unstack()
    hrs = te[ok.to_numpy()]
    easter = hrs[(hrs >= pd.Timestamp("2026-04-04", tz="UTC")) & (hrs < pd.Timestamp("2026-04-08", tz="UTC"))]

    def scales(h):
        res = {}
        for s, p in P.items():
            p, a, c = p.loc[h], A.loc[h], cap.loc[h]
            r = {"accuracy": 100 * (1 - (p - a).abs().to_numpy().sum() / a.to_numpy().sum())}
            aerr, csum, cost, prod = 0.0, 0.0, 0.0, 0.0
            for ar, zs in AREAS.items():
                e = (p[zs].sum(axis=1) - a[zs].sum(axis=1)).abs()
                r[f"mae_pct_cap_{ar}"] = 100 * e.sum() / c[zs].sum(axis=1).sum()
                aerr, csum = aerr + e.sum(), csum + c[zs].sum(axis=1).sum()
                dp = (ip[("SpotPriceEUR", ar)] - ip[("ImbalancePriceEUR", ar)]).reindex(h)
                m = dp.notna()
                cost += float(((a[zs].sum(axis=1) - p[zs].sum(axis=1)) * dp)[m].sum())
                prod += float(a[zs].sum(axis=1)[m].sum())
            r["mae_pct_cap_DK"], r["area_abs_err"] = 100 * aerr / csum, aerr
            r["imbalance_eur_per_mwh"] = cost / prod if prod else None
            res[s] = r
        for s in res:
            for ref in ("ifs", "energinet"):
                res[s][f"skill_vs_{ref}"] = 100 * (1 - res[s]["area_abs_err"] / res[ref]["area_abs_err"])
        return {s: {k: round(v, 3) for k, v in r.items() if k != "area_abs_err"} for s, r in res.items()}

    out = {"spec": "J4catDK + offshore curtailment, frozen 29 Oct 2026", "train": [str(tr.min()), str(tr.max())],
           "test": [str(hrs.min()), str(hrs.max())], "test_hours": len(hrs), "easter_hours": len(easter),
           "test_2026": scales(hrs), "easter_2026": scales(easter) if len(easter) else None}
    tag = "e3_smoke" if "--smoke" in sys.argv else "e3_test"
    json.dump(out, open(LIVE / "reports" / f"{tag}.json", "w"), indent=1)
    pd.concat({k: v.loc[hrs] for k, v in P.items()} | {"actual": A.loc[hrs]}, axis=1).to_csv(
        LIVE / "reports" / f"{tag}_preds.csv", index_label="hour_utc")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
