"""Does disagreement between the AI weather model (AIFS) and the physics model (IFS) carry information?

Both models' day-ahead 100 m winds (previous_day1) go through their own mapping to total Danish wind output, trained
before 1 Jan 2026. On 1 Jan to 18 Oct 2026 (out of sample):
  Q1 spread-skill: does |P_ifs - P_aifs| predict the size of the error of their average, and of Energinet's error?
  Q2 market: does it predict the DK1 balancing spread |imbalance price - spot| ?
  Q3 sign: when our DK1 forecast is above Energinet's (scaled by its 60-day actual/forecast ratio), is DK1 imbalance
     price below spot (system long, too much wind)? Hit rate and mean signed spread.
Each answer is shown for Jan to May and Jun to Oct separately, to see whether it holds in both halves.
Writes live/reports/disagreement.json and prints tables.
"""
import gzip, json, sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import LIVE, RAW, ZONES, capacity_proxy, features
from train import load_actuals, load_energinet_da, load_weather

T0, T1 = pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-10-19", tz="UTC")
P = dict(objective="l1", learning_rate=0.03, num_leaves=31, min_data_in_leaf=50, feature_fraction=0.7,
         bagging_fraction=0.8, bagging_freq=1, verbose=-1, num_threads=2, seed=1)


def mapped(model, Y, cap, zones):
    sp, di = load_weather(model)
    X = features(sp, di)
    X = X[sp.notna().mean(axis=1) > 0.9]
    tot, ctot = Y[zones].sum(axis=1), cap[zones].sum(axis=1)
    idx = X.index.intersection(tot.dropna().index).intersection(ctot.dropna().index)
    idx = idx[idx >= pd.Timestamp("2025-02-18", tz="UTC")]  # same training window for both models
    tr, te = idx[idx < T0], idx[(idx >= T0) & (idx < T1)]
    m = lgb.train(P, lgb.Dataset(X.loc[tr], (tot / ctot).loc[tr].clip(0, 1.2)), 800)
    return pd.Series(np.clip(m.predict(X.loc[te]), 0, None) * ctot.loc[te], index=te)


def imbalance():
    recs = []
    for f in sorted((RAW / "energinet" / "ImbalancePrice").glob("*.json.gz")):
        recs += [r for r in json.load(gzip.open(f))["records"] if r["PriceArea"] == "DK1"]
    df = pd.DataFrame(recs)
    df["t"] = pd.to_datetime(df["TimeUTC"]).dt.tz_localize("UTC").dt.floor("h")
    df["spread"] = df.ImbalancePriceEUR - df.SpotPriceEUR
    return df.groupby("t").spread.mean()


def by_quintile(key, cols, d):
    q = pd.qcut(d[key], 5, labels=["Q1 low", "Q2", "Q3", "Q4", "Q5 high"])
    return d.groupby(q, observed=True)[cols].mean()


def main():
    Y = load_actuals()
    cap = capacity_proxy(Y)
    da = load_energinet_da()
    res = {}
    # total Denmark for Q1, DK1 for Q2/Q3
    for scope, zones in (("DK", ZONES), ("DK1", ["DK1_offshore", "DK1_onshore"])):
        pi, pa = mapped("ecmwf_ifs025", Y, cap, zones), mapped("ecmwf_aifs025_single", Y, cap, zones)
        act = Y[zones].sum(axis=1)
        en = da[zones].sum(axis=1, min_count=len(zones))
        j = pd.concat([act.rename("a"), en.rename("f")], axis=1, sort=True).dropna()
        k = (j.a.rolling("60D").sum() / j.f.rolling("60D").sum()).resample("D").last().shift(1)
        en_db = en * k.reindex(en.index, method="ffill")
        d = pd.concat({"ifs": pi, "aifs": pa, "act": act, "en": en_db}, axis=1, sort=True).dropna()
        d["disagree"] = (d.ifs - d.aifs).abs()
        d["avg"] = (d.ifs + d.aifs) / 2
        d["err_avg"] = (d.avg - d.act).abs()
        d["err_en"] = (d.en - d.act).abs()
        res[scope] = {"hours": len(d), "mae_ifs": float((d.ifs - d.act).abs().mean()),
                      "mae_aifs": float((d.aifs - d.act).abs().mean()), "mae_avg": float(d.err_avg.mean()),
                      "mae_energinet_debiased": float(d.err_en.mean())}
        print(f"\n== {scope}: {len(d)} hours, MAE ifs {res[scope]['mae_ifs']:.0f}, aifs {res[scope]['mae_aifs']:.0f}, "
              f"average {res[scope]['mae_avg']:.0f}, Energinet debiased {res[scope]['mae_energinet_debiased']:.0f} MW")
        if scope == "DK":
            for half, m in (("Jan-May", d.index < pd.Timestamp("2026-06-01", tz="UTC")),
                            ("Jun-Oct", d.index >= pd.Timestamp("2026-06-01", tz="UTC"))):
                t = by_quintile("disagree", ["disagree", "err_avg", "err_en"], d[m])
                print(f"Q1 spread-skill {half}\n{t.round(0).to_string()}")
                res[scope][f"q1_{half}"] = t.round(1).to_dict()
                res[scope][f"q1_spearman_{half}"] = float(d[m].disagree.corr(d[m].err_avg, method="spearman"))
        else:
            sp = imbalance()
            d = d.join(sp.rename("spread"), how="inner")
            d["abs_spread"] = d.spread.abs()
            d["edge"] = d.avg - d.en  # >0: we expect more DK1 wind than Energinet
            for half, m in (("Jan-May", d.index < pd.Timestamp("2026-06-01", tz="UTC")),
                            ("Jun-Oct", d.index >= pd.Timestamp("2026-06-01", tz="UTC"))):
                t = by_quintile("disagree", ["disagree", "abs_spread"], d[m])
                print(f"Q2 balancing spread by disagreement {half}\n{t.round(1).to_string()}")
                res[scope][f"q2_{half}"] = t.round(2).to_dict()
                t3 = by_quintile("edge", ["edge", "spread"], d[m])
                big = d[m][d[m].edge.abs() > d[m].edge.abs().quantile(0.8)]
                hit = float(((big.edge > 0) == (big.spread < 0)).mean())
                print(f"Q3 signed spread by our-minus-Energinet {half}\n{t3.round(1).to_string()}\n"
                      f"   top 20% |edge| hours: sign hit rate {hit:.2f} over {len(big)} hours")
                res[scope][f"q3_{half}"] = t3.round(2).to_dict()
                res[scope][f"q3_hit_{half}"] = hit
    json.dump(res, open(LIVE / "reports" / "disagreement.json", "w"), indent=1, default=str)
    print("DONE disagreement", flush=True)


if __name__ == "__main__":
    main()
