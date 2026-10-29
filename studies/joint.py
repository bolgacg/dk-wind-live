"""E3: our own power model, developed on 2025 only. Bo's test plan (29 Oct): every new model meets the 2026 test once,
on 2 Nov, together. So this script never reads 2026: train Feb to Aug 2025, validate Sep to Dec 2025.

Candidates, all scored with the league's accuracy (100% minus summed absolute error over summed output, four zones):
  B4        the live recipe: each of the four members through its own power model, averaged
  J4ms      one joint model; per point the members' mean u/v/speed and their spread (170 inputs)
  J4cat     one joint model; every member's speed and u/v side by side (410 inputs)
  each +C   plus a curtailment stage: target = actual/cap minus the stage-1 forecast, objective L1, inputs = stage-1
            forecast per zone and for Denmark, hour, weekday, Danish holiday, and day-ahead prices known at 10:30 on
            D-1 (same hour yesterday, yesterday's minimum). Trained on stage-1 forecasts made out of sample (six
            contiguous folds over the training months), so it never learns from too-good in-sample forecasts.

History: a first version (kept in reports/2026look_29oct/) scored J4ms on the 2026 test before the test-once plan
reached this session; see COORDINATION.md 29 Oct 16:24.

Optional --only J4msDK or J4cat,J4catDK: the joint model plus projects-5a's DKcast station wind (22 sites), next to B4 on the same hours.
Usage: OMP_NUM_THREADS=2 nice -n 10 python3 live/studies/joint.py [--only J4msDK]  ->  live/reports/joint_val.json, joint_val_*.csv"""
import gzip, json, sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BLEND, LIVE, LIVE_MODELS, POINTS, ROOT, ZONES, capacity_proxy, features
from train import PARAMS, N_ROUNDS, load_actuals, load_weather

HOLIDAYS = set(pd.to_datetime([
    "2025-01-01", "2025-04-17", "2025-04-18", "2025-04-20", "2025-04-21", "2025-05-29", "2025-06-08", "2025-06-09",
    "2025-06-05", "2025-12-24", "2025-12-25", "2025-12-26", "2025-12-31"]).date)
VAL_START = pd.Timestamp("2025-09-01", tz="UTC")
END = pd.Timestamp("2026-01-01", tz="UTC")  # nothing from 2026 is read past this line
K = 6


def member_frames():
    out = {}
    for m in BLEND:
        sp, di = load_weather(LIVE_MODELS[m])
        X = features(sp, di).drop(columns=["hour", "doy"])
        X = X[sp.notna().mean(axis=1) > 0.9]
        out[m] = X[X.index < END]
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
    """Hourly day-ahead price per area: Elspotprices to Sep 2025, then DayAheadPrices (15-minute, averaged)."""
    r = json.load(gzip.open(ROOT / "data" / "raw" / "energinet" / "Elspotprices" / "2024-12_2025-09.json.gz"))["records"]
    a = pd.DataFrame(r)
    a["t"] = pd.to_datetime(a.HourUTC).dt.tz_localize("UTC")
    a = a.pivot_table(index="t", columns="PriceArea", values="SpotPriceEUR")
    p = pd.read_parquet(ROOT / "data" / "clean" / "DayAheadPrices.parquet")
    p["t"] = pd.to_datetime(p.TimeUTC).dt.tz_localize("UTC").dt.floor("h")
    b = p.groupby(["t", "PriceArea"]).DayAheadPriceEUR.mean().unstack()
    out = pd.concat([a[a.index < b.index.min()], b]).sort_index()
    return out[out.index < END]


def stage2_inputs(s1, idx, pr):
    """s1: stage-1 capacity factors per zone. Only information known at 10:30 on D-1."""
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
    return pd.Series(m.predict(Xte), index=Xte.index)


def accuracy(pred, act):
    ok = pred.notna().all(axis=1) & act.notna().all(axis=1)
    return round(100 * (1 - (pred[ok] - act[ok]).abs().to_numpy().sum() / act[ok].to_numpy().sum()), 2), int(ok.sum())


def stage1(Xs, y, tr, va):
    """Xs: one feature frame, or a list of frames to average (B4). Returns out-of-fold CF on tr, CF on va."""
    Xs = Xs if isinstance(Xs, list) else [Xs]
    folds = np.array_split(np.arange(len(tr)), K)
    oof, val = pd.Series(0.0, index=tr), pd.Series(0.0, index=va)
    for X in Xs:
        for f in folds:
            keep = np.setdiff1d(np.arange(len(tr)), f)
            oof.iloc[f] += fit_pred(X.loc[tr[keep]], y.loc[tr[keep]], X.loc[tr[f]]).clip(0, None).to_numpy() / len(Xs)
        val += fit_pred(X.loc[tr], y.loc[tr], X.loc[va]).clip(0, None) / len(Xs)
    return oof, val


def stage2(oof, val, Y, cap, tr, va, pr, use_prices=True):
    S_tr, S_va = stage2_inputs(oof, tr, pr), stage2_inputs(val, va, pr)
    if not use_prices:  # ablation: is the gain curtailment (prices) or just a level correction?
        S_tr, S_va = S_tr.drop(columns=[c for c in S_tr if c.startswith("p_")]), S_va.drop(columns=[c for c in S_va if c.startswith("p_")])
    ok = S_tr[[c for c in S_tr if c.startswith("p_")]].notna().all(axis=1).to_numpy()
    out = val.copy()
    for z in ZONES:
        r = (Y[z] / cap[z]).clip(0, 1.2).loc[tr] - oof[z]
        out[z] = (val[z] + fit_pred(S_tr[ok], r[ok], S_va, rounds=300)).clip(0, None)
    return out


def dkcast():
    """projects-5a's DKcast 10 m station wind at 22 of the 34 sites: mean and spread, out of fold for 2025."""
    d = pd.read_parquet(ROOT / "experiments" / "results" / "dkcast_wind_export_points.parquet")
    d["time"] = pd.to_datetime(d.time).dt.tz_localize("UTC")
    w = d.pivot_table(index="time", columns="point", values=["dk_mu", "dk_sd"])
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    return w[w.index < END]


def main():
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    tag = "_" + "_".join(only) if only else ""
    fr = member_frames()
    Y = load_actuals()
    Y = Y[Y.index < END]
    cap = capacity_proxy(Y)
    pr = prices()
    cands = {"B4": [add_time(f) for f in fr.values()], "J4ms": add_time(joint_ms(fr)), "J4cat": add_time(joint_cat(fr))}
    idx = cands["J4cat"].index
    if only:
        for base in ("J4ms", "J4cat"):
            if base + "DK" in only:
                cands[base + "DK"] = cands[base].join(dkcast(), how="inner")
                idx = idx.intersection(cands[base + "DK"].index)
        cands = {k: v for k, v in cands.items() if k in only or k == "B4"}  # B4 always, on the same hours
    idx = idx.intersection(Y.dropna().index).intersection(cap.dropna().index)
    tr, va = idx[idx < VAL_START], idx[idx >= VAL_START]
    print(f"train {tr.min()} to {tr.max()} ({len(tr)} h), validate {va.min()} to {va.max()} ({len(va)} h)", flush=True)
    report, preds = {}, {}
    for name, X in cands.items():
        oof, val = pd.DataFrame(index=tr), pd.DataFrame(index=va)
        for z in ZONES:
            y = (Y[z] / cap[z]).clip(0, 1.2)
            oof[z], val[z] = stage1(X, y, tr, va)
            print(f"  {name} {z} done", flush=True)
        val2 = stage2(oof, val, Y, cap, tr, va, pr)
        val2np = stage2(oof, val, Y, cap, tr, va, pr, use_prices=False)
        val2off = val.copy()  # curtailment stage on the offshore zones only
        for z in ("DK1_offshore", "DK2_offshore"):
            val2off[z] = val2[z]
        for lab, cf in ((name, val), (name + "+C", val2), (name + "+Cnoprice", val2np), (name + "+Coffshore", val2off)):
            mw = cf * cap.loc[va]
            preds[lab] = mw
            report[lab], n = accuracy(mw, Y.loc[va])
            report[lab + "_by_zone"] = {z: accuracy(mw[[z]], Y.loc[va, [z]])[0] for z in ZONES}
        report["hours"] = n
        print(json.dumps({k: v for k, v in report.items() if "_by_zone" not in k}), flush=True)
        json.dump(report, open(LIVE / "reports" / f"joint_val{tag}.json", "w"), indent=1)
    pd.concat(preds, axis=1).to_csv(LIVE / "reports" / f"joint_val{tag}_preds.csv", index_label="hour_utc")


if __name__ == "__main__":
    main()
