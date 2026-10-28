"""Train the live power mapping: forecast weather at 34 points -> hourly wind output per zone (DK1/DK2 x on/offshore).

Inputs, read-only from the download lane: Open-Meteo Previous Runs for ECMWF IFS (`*_previous_day1`, the forecast as it
stood one day earlier, so lead roughly 24 to 48 h, matching a day-ahead decision) and Energinet settlement.
Target is output divided by a capacity proxy known before the day (common.capacity_proxy), so the fleet growth does not
leak. Test = the last 3 months; Energinet's own day-ahead forecast is the bar.

Usage: python3 live/train.py [--weather ecmwf_ifs025] [--final]
--final refits on everything and writes live/models/; without it only the test report is written."""
import argparse, gzip, json, pickle, sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LIVE, POINTS, RAW, ZONES, capacity_proxy, features

TEST_START = pd.Timestamp("2026-07-19", tz="UTC")


def load_weather(model, lead=1):
    sp, di = {}, {}
    for p in POINTS:
        parts = []
        for f in sorted((RAW / "openmeteo" / model).glob(f"{p}_*.json.gz")):
            d = json.load(gzip.open(f))
            if "hourly" not in d:
                continue
            h = d["hourly"]
            parts.append(pd.DataFrame({"s": h[f"wind_speed_100m_previous_day{lead}"],
                                       "d": h[f"wind_direction_100m_previous_day{lead}"]},
                                      index=pd.to_datetime(h["time"]).tz_localize("UTC"), dtype=float))
        if not parts:
            raise SystemExit(f"no {model} data for {p} yet")
        df = pd.concat(parts)
        sp[p], di[p] = df["s"], df["d"]
    return pd.DataFrame(sp), pd.DataFrame(di)


def load_actuals():
    recs = []
    for f in sorted((RAW / "energinet" / "ProductionConsumptionSettlement").glob("*.json.gz")):
        recs += json.load(gzip.open(f))["records"]
    df = pd.DataFrame(recs)
    df["t"] = pd.to_datetime(df["HourUTC"]).dt.tz_localize("UTC")
    df["off"] = df["OffshoreWindLt100MW_MWh"].fillna(0) + df["OffshoreWindGe100MW_MWh"].fillna(0)
    df["on"] = df["OnshoreWindLt50kW_MWh"].fillna(0) + df["OnshoreWindGe50kW_MWh"].fillna(0)
    out = {}
    for a in ("DK1", "DK2"):
        x = df[df.PriceArea == a].drop_duplicates("t").set_index("t").sort_index()
        out[f"{a}_offshore"], out[f"{a}_onshore"] = x["off"], x["on"]
    return pd.DataFrame(out)


def load_energinet_da():
    recs = []
    for f in sorted((RAW / "energinet" / "Forecasts_Hour").glob("*.json.gz")):
        recs += json.load(gzip.open(f))["records"]
    df = pd.DataFrame(recs)
    df = df[df.ForecastType.isin(["Offshore Wind", "Onshore Wind"])]
    df["t"] = pd.to_datetime(df["HourUTC"]).dt.tz_localize("UTC")
    df["z"] = df.PriceArea + "_" + df.ForecastType.str.split().str[0].str.lower()
    return df.pivot_table(index="t", columns="z", values="ForecastDayAhead")


PARAMS = dict(objective="l1", learning_rate=0.03, num_leaves=31, min_data_in_leaf=50, feature_fraction=0.7,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1, num_threads=2)
N_ROUNDS = 800


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", default="ecmwf_ifs025")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--since", help="drop training hours before this UTC date (for like-for-like model duels)")
    a = ap.parse_args()
    sp, di = load_weather(a.weather)
    X = features(sp, di)
    X = X[sp.notna().mean(axis=1) > 0.9]  # hours before a model's archive starts are all empty
    if a.since:
        X = X[X.index >= pd.Timestamp(a.since, tz="UTC")]
    Y = load_actuals()
    cap = capacity_proxy(Y)
    da = load_energinet_da()
    idx = X.index.intersection(Y.dropna().index).intersection(cap.dropna().index)
    X, Y, cap = X.loc[idx], Y.loc[idx], cap.loc[idx]
    print(f"{a.weather}: {len(idx)} hours, {idx.min()} to {idx.max()}")
    tr, te = idx < TEST_START, idx >= TEST_START
    rows = []
    for z in ZONES:
        y = (Y[z] / cap[z]).clip(0, 1.2)
        m = lgb.train(PARAMS, lgb.Dataset(X[tr], y[tr]), N_ROUNDS)
        pred = np.clip(m.predict(X[te]), 0, None) * cap[z][te]
        act = Y[z][te]
        common = act.index.intersection(da[z].dropna().index)
        mae_ours = (pred.loc[common] - act.loc[common]).abs().mean()
        mae_en = (da[z].loc[common] - act.loc[common]).abs().mean()
        # Energinet with its own bias removed: scale by actual/forecast over the previous 60 days (known before the day)
        j = pd.concat([Y[z], da[z]], axis=1, keys=["a", "f"], sort=True).dropna()
        r = (j.a.rolling("60D").sum() / j.f.rolling("60D").sum()).resample("D").last().shift(1)
        en_db = da[z] * r.reindex(da[z].index, method="ffill")
        mae_db = (en_db.loc[common] - act.loc[common]).abs().mean()
        rows.append(dict(zone=z, hours=len(common), mean_output=act.loc[common].mean(), mae_ours=mae_ours,
                         mae_energinet=mae_en, mae_energinet_debiased=mae_db, ratio_raw=mae_ours / mae_en,
                         ratio_debiased=mae_ours / mae_db))
        if a.final:
            mf = lgb.train(PARAMS, lgb.Dataset(X, y), N_ROUNDS)
            mdir = LIVE / "models" / a.weather
            mdir.mkdir(parents=True, exist_ok=True)
            mf.save_model(str(mdir / f"{z}.txt"))
    rep = pd.DataFrame(rows)
    print(rep.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    out = LIVE / "reports"
    out.mkdir(exist_ok=True)
    rep.to_csv(out / f"test_{a.weather}{'_since' + a.since if a.since else ''}.csv", index=False)
    if a.final:
        json.dump({"weather": a.weather, "hours": len(idx), "from": str(idx.min()), "to": str(idx.max()),
                   "params": PARAMS, "rounds": N_ROUNDS, "features": list(X.columns)},
                  open(LIVE / "models" / a.weather / "meta.json", "w"), indent=1)


if __name__ == "__main__":
    main()
