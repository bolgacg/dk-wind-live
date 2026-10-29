"""E3: our own power model. One joint LightGBM that sees all four members' winds at once, then a second stage that
learns how much of the forecast output gets switched off (curtailment) from what a desk knows at 10:30 the day before.

Stage 1, joint model, two variants:
  J4cat  every member's speed and u/v at the 34 points side by side (416 inputs)
  J4ms   per point the members' mean u/v/speed and their spread (std of speed), 170 inputs
Stage 2, curtailment: target = actual/cap minus the stage-1 forecast, objective L1, inputs = stage-1 forecast for the
zone and for all of Denmark, hour, weekday, Danish holiday, and the day-ahead prices already known at 10:30 on D-1
(same hour yesterday, yesterday's minimum, from yesterday's auction). 5a's negprice.py found that a negative-price
probability alone does not help; this lets the second stage learn the size of the cut directly.

Honesty: stage 2 is trained on stage-1 predictions made out of sample (six contiguous folds over the training
period), so it never learns from in-sample, too-good forecasts. Test = 19 Jul to 18 Oct 2026, the league's 92 days,
scored with the league's accuracy (100% minus summed absolute error over summed output, four zones). Easter (4 to 7
Apr 2026) is scored from the fold that held it out, for both stages.

Usage: nice -n 10 python3 live/studies/joint.py   ->  live/reports/joint_*.csv, live/reports/joint.json"""
import json, sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BLEND, LIVE, LIVE_MODELS, POINTS, ROOT, ZONES, capacity_proxy, features
from train import PARAMS, N_ROUNDS, TEST_START, load_actuals, load_weather

HOLIDAYS = set(pd.to_datetime([
    "2025-01-01", "2025-04-17", "2025-04-18", "2025-04-20", "2025-04-21", "2025-05-29", "2025-06-08", "2025-06-09",
    "2025-06-05", "2025-12-24", "2025-12-25", "2025-12-26", "2025-12-31",
    "2026-01-01", "2026-04-02", "2026-04-03", "2026-04-05", "2026-04-06", "2026-05-14", "2026-05-24", "2026-05-25",
    "2026-06-05", "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31"]).date)
EASTER = (pd.Timestamp("2026-04-04", tz="UTC"), pd.Timestamp("2026-04-08", tz="UTC"))
END = pd.Timestamp("2026-10-19", tz="UTC")
K = 6


def member_frames():
    out = {}
    for m in BLEND:
        sp, di = load_weather(LIVE_MODELS[m])
        X = features(sp, di).drop(columns=["hour", "doy"])
        out[m] = X[sp.notna().mean(axis=1) > 0.9]
    return out


def joint_cat(fr):
    X = pd.concat({m: f for m, f in fr.items()}, axis=1, join="inner")
    X.columns = [f"{m}|{c}" for m, c in X.columns]
    return X


def joint_ms(fr):
    idx = None
    for f in fr.values():
        idx = f.index if idx is None else idx.intersection(f.index)
    cols = {}
    for p in POINTS:
        for k in ("s", "u", "v"):
            cols[f"{k}_{p}"] = sum(f.loc[idx, f"{k}_{p}"] for f in fr.values()) / len(fr)
        cols[f"sd_{p}"] = pd.concat([f.loc[idx, f"s_{p}"] for f in fr.values()], axis=1).std(axis=1)
    return pd.DataFrame(cols, index=idx)


def add_time(X):
    X = X.copy()
    X["hour"], X["doy"] = X.index.hour, X.index.dayofyear
    return X


def prices():
    p = pd.read_parquet(ROOT / "data" / "clean" / "DayAheadPrices.parquet")
    p["t"] = pd.to_datetime(p.TimeUTC).dt.tz_localize("UTC").dt.floor("h")
    return p.groupby(["t", "PriceArea"]).DayAheadPriceEUR.mean().unstack()


def stage2_inputs(s1, idx, pr):
    """s1: stage-1 capacity factors per zone (DataFrame). Only information known at 10:30 on D-1."""
    X = pd.DataFrame(index=idx)
    for z in ZONES:
        X[f"cf_{z}"] = s1[z].reindex(idx)
    X["cf_all"] = X[[f"cf_{z}" for z in ZONES]].mean(axis=1)
    X["hour"], X["dow"] = idx.hour, idx.dayofweek
    X["holiday"] = np.isin(idx.tz_convert("Europe/Copenhagen").date, list(HOLIDAYS)).astype(int)
    day = idx.tz_convert("Europe/Copenhagen").normalize()
    for a in ("DK1", "DK2"):
        s = pr[a]
        X[f"p_lag24_{a}"] = s.reindex(idx - pd.Timedelta("24h")).to_numpy()
        dmin = s.groupby(s.index.tz_convert("Europe/Copenhagen").normalize()).min()
        X[f"p_min_prev_{a}"] = dmin.reindex(day - pd.Timedelta("1D")).to_numpy()
    return X


def fit_pred(Xtr, ytr, Xte, rounds=N_ROUNDS):
    m = lgb.train(PARAMS, lgb.Dataset(Xtr, ytr), rounds)
    return pd.Series(np.clip(m.predict(Xte), 0, None), index=Xte.index)


def accuracy(pred, act):
    ok = pred.notna().all(axis=1) & act.notna().all(axis=1)
    return 100 * (1 - (pred[ok] - act[ok]).abs().to_numpy().sum() / act[ok].to_numpy().sum()), int(ok.sum())


def run_variant(name, X, Y, cap, pr):
    idx = X.index.intersection(Y.dropna().index).intersection(cap.dropna().index)
    idx = idx[idx < END]
    X, Y, cap = X.loc[idx], Y.loc[idx], cap.loc[idx]
    tr, te = idx[idx < TEST_START], idx[idx >= TEST_START]
    folds = np.array_split(np.arange(len(tr)), K)
    oof, test1 = pd.DataFrame(index=tr, columns=ZONES, dtype=float), pd.DataFrame(index=te, columns=ZONES, dtype=float)
    for z in ZONES:
        y = (Y[z] / cap[z]).clip(0, 1.2)
        for f in folds:
            keep = np.setdiff1d(np.arange(len(tr)), f)
            oof.loc[tr[f], z] = fit_pred(X.loc[tr[keep]], y.loc[tr[keep]], X.loc[tr[f]]).to_numpy()
        test1[z] = fit_pred(X.loc[tr], y.loc[tr], X.loc[te])
        print(f"  {name} stage 1 {z} done", flush=True)
    # stage 2 on out-of-fold stage-1 forecasts, only where prices are known (from Oct 2025)
    S_tr, S_te = stage2_inputs(oof, tr, pr), stage2_inputs(test1, te, pr)
    has_p = S_tr[["p_lag24_DK1", "p_min_prev_DK1"]].notna().all(axis=1)
    test2, oof2 = pd.DataFrame(index=te, columns=ZONES, dtype=float), oof.copy()
    tr2 = tr[has_p.to_numpy()]
    folds2 = [tr[f].intersection(tr2) for f in folds]
    for z in ZONES:
        r = (Y[z] / cap[z]).clip(0, 1.2) - oof[z]
        for f in folds2:
            if len(f) == 0:
                continue
            keep = tr2.difference(f)
            oof2.loc[f, z] = (oof.loc[f, z] + fit_pred_signed(S_tr.loc[keep], r.loc[keep], S_tr.loc[f])).clip(0, None)
        test2[z] = (test1[z] + fit_pred_signed(S_tr.loc[tr2], r.loc[tr2], S_te)).clip(0, None)
    mw = lambda cf, ix: cf.loc[ix].astype(float) * cap.loc[ix]
    res = {"test_hours": len(te)}
    for lab, cf in (("stage1", test1), ("stage2", test2)):
        res[f"test_{lab}"], _ = accuracy(mw(cf, te), Y.loc[te])
    e = tr[(tr >= EASTER[0]) & (tr < EASTER[1])]
    for lab, cf in (("stage1", oof), ("stage2", oof2)):
        res[f"easter_{lab}"], res["easter_hours"] = accuracy(mw(cf, e), Y.loc[e])
    out = pd.concat({"s1": mw(test1, te), "s2": mw(test2, te)}, axis=1)
    out.columns = [f"{a}_{z}" for a, z in out.columns]
    out.to_csv(LIVE / "reports" / f"joint_{name}_test.csv", index_label="hour_utc")
    pd.concat({"s1": mw(oof, e), "s2": mw(oof2, e), "actual": Y.loc[e]}, axis=1).to_csv(
        LIVE / "reports" / f"joint_{name}_easter.csv", index_label="hour_utc")
    return res, out


def fit_pred_signed(Xtr, ytr, Xte):
    m = lgb.train(PARAMS, lgb.Dataset(Xtr, ytr), 300)
    return pd.Series(m.predict(Xte), index=Xte.index)


def main():
    fr = member_frames()
    Y = load_actuals()
    cap = capacity_proxy(Y)
    pr = prices()
    # the reference: the live blend, average of the four members' own mappings, same hours
    ref = {}
    for m in BLEND:
        d = pd.read_csv(LIVE / "reports" / f"testpred_{LIVE_MODELS[m]}.csv", index_col=0, parse_dates=True)
        ref[m] = d[ZONES]
    blend = sum(ref.values()) / len(ref)
    report = {}
    for name, X in (("J4ms", add_time(joint_ms(fr))), ("J4cat", add_time(joint_cat(fr)))):
        print(f"{name}: {X.shape[1]} inputs", flush=True)
        res, out = run_variant(name, X, Y, cap, pr)
        ix = out.index.intersection(blend.dropna().index)
        res["blend_same_hours"], _ = accuracy(blend.loc[ix], Y.loc[ix])
        res["stage1_same_hours"], _ = accuracy(out.loc[ix, [f"s1_{z}" for z in ZONES]].set_axis(ZONES, axis=1), Y.loc[ix])
        res["stage2_same_hours"], res["same_hours"] = accuracy(
            out.loc[ix, [f"s2_{z}" for z in ZONES]].set_axis(ZONES, axis=1), Y.loc[ix])
        report[name] = res
        print(name, json.dumps(res, indent=1), flush=True)
    json.dump(report, open(LIVE / "reports" / "joint.json", "w"), indent=1)


if __name__ == "__main__":
    main()
