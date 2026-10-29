"""League table of every forecast source, backtest plus live, for the public page.

Headline: nMAE, the mean absolute error of each area's hourly total (DK1, DK2) as a percentage of installed capacity,
the wind industry's standard day-ahead measure. Capacity is our proxy: per zone the 99.5th percentile of hourly output
over the previous 60 days, known before the day (common.capacity_proxy). Denmark = both areas' errors over both
areas' capacity. Skill score against ECMWF IFS and against Energinet = 1 minus our error over theirs, in %, on the same
days. Secondary: accuracy = 100% minus summed zone errors over summed output. Days are ranked by nMAE.
Backtest: reports/testpred_<model>.csv, out-of-sample predictions on 19 Jul to 18 Oct 2026 from mappings trained
before 19 Jul; J4catDK from its frozen 2026 test (reports/e3_test_preds.csv, trained on 2025 only). Live: hourly_scores.csv from score.py (forecasts committed before each day). Each day ranks only the sources
that covered at least 20 of its hours; the score uses the hours every ranked source covered.

Usage: python3 live/league.py [--live-scores path/to/hourly_scores.csv]  ->  site/data.json"""
import argparse, json, sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BLEND, LIVE, LIVE_MODELS, ZONES

NAMES = {"blend": "4-model average", "energinet": "Energinet (bias-corrected)", "ifs": "ECMWF IFS",
         "aifs": "ECMWF AIFS (AI)", "harmonie": "DMI HARMONIE", "icon": "DWD ICON-EU", "gfs": "NOAA GFS",
         "knmi": "KNMI HARMONIE", "icon_d2": "DWD ICON-D2", "ukmo": "UK Met Office", "metno": "MET Norway Nordic",
         "icon_global": "DWD ICON global", "gem": "Canada GEM", "jma": "Japan JMA", "cma": "China CMA GRAPES",
         "bom": "Australia BOM ACCESS", "ukmo_2km": "UK Met Office 2 km", "graphcast": "Google GraphCast (AI)",
         "arpege": "Meteo-France ARPEGE", "ifs_9km": "ECMWF IFS 9 km", "j4catdk": "J4catDK (my own model)", "j4cat": "J4cat (mine, without DKcast)",
         "energinet_da": "Energinet (raw)", "energinet_da_debiased": "Energinet (bias-corrected)"}


AREAS = {"DK1": ["DK1_offshore", "DK1_onshore"], "DK2": ["DK2_offshore", "DK2_onshore"]}


def backtest_hourly():
    """Long hourly frame (hour, day, source, zone, pred, actual, cap) from the out-of-sample test predictions."""
    preds, act, en = {}, None, None
    for short, model in LIVE_MODELS.items():
        f = LIVE / "reports" / f"testpred_{model}.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f, index_col=0, parse_dates=True)
        preds[short] = d[ZONES]
        act = d[[f"actual_{z}" for z in ZONES]].set_axis(ZONES, axis=1)
        en = d[[f"energinet_{z}" for z in ZONES]].set_axis(ZONES, axis=1)
    if all(m in preds for m in BLEND):
        preds["blend"] = sum(preds[m] for m in BLEND) / len(BLEND)
    preds["energinet"] = en
    # J4catDK: its frozen 2026 test predictions (trained on 2025 only, studies/e3_test.py), the 92 days of this window
    f = LIVE / "reports" / "e3_test_preds.csv"
    if f.exists():
        j = pd.read_csv(f, header=[0, 1], index_col=0, parse_dates=True)["j4catdk_c"]
        preds["j4catdk"] = j[ZONES].reindex(act.index)
    cap = pd.read_csv(LIVE / "reports" / "capacity_backtest.csv", index_col=0, parse_dates=True).reindex(act.index)
    px = pd.read_csv(LIVE / "reports" / "prices_backtest.csv", index_col=0, parse_dates=True).reindex(act.index)
    long = []
    for s, p in preds.items():
        for z in ZONES:
            long.append(pd.DataFrame({"hour": act.index, "source": s, "zone": z, "pred": p[z].reindex(act.index).values,
                                      "actual": act[z].values, "cap": cap[z].values,
                                      "spot": px[f"spot_{z[:3]}"].values, "imb": px[f"imb_{z[:3]}"].values}))
    df = pd.concat(long, ignore_index=True)
    df["day"] = df.hour.dt.tz_convert("Europe/Copenhagen").dt.date.astype(str)
    return df


def live_hourly(path):
    if not path or not Path(path).exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df = df[df.source != "energinet_da"].replace({"source": {"energinet_da_debiased": "energinet"}})
    df["hour"] = pd.to_datetime(df.hour_utc).dt.tz_localize("UTC")
    for c in ("spot", "imb"):
        if c not in df:
            df[c] = float("nan")
    return df[["hour", "day", "source", "zone", "pred", "actual", "cap", "spot", "imb"]]


def daily(df):
    """Per day and source, on the hours every ranked source covered: summed zone errors and output (for accuracy),
    and per area the summed absolute error of the area total and the summed capacity (for % of capacity)."""
    rows = []
    for day, g in df.groupby("day"):
        w = g.pivot_table(index=["hour", "source"], columns="zone", values=["pred", "actual", "cap", "spot", "imb"],
                          dropna=False)
        full = w["pred"].notna().all(axis=1) & w["actual"].notna().all(axis=1) & w["cap"].notna().all(axis=1)
        w = w[full]
        n = w.reset_index().groupby("source").hour.nunique()
        ranked = n[n >= 20].index
        if len(ranked) == 0:
            continue
        hrs = None
        for s in ranked:
            h = set(w.xs(s, level="source").index)
            hrs = h if hrs is None else hrs & h
        if len(hrs) < 20:
            continue
        for s in ranked:
            x = w.xs(s, level="source").loc[sorted(hrs)]
            r = dict(day=day, source=s, hours=len(hrs),
                     err=(x["pred"] - x["actual"]).abs().to_numpy().sum(), act=x["actual"].to_numpy().sum())
            for a, zs in AREAS.items():
                r[f"aerr_{a}"] = (x["pred"][zs].sum(axis=1) - x["actual"][zs].sum(axis=1)).abs().sum()
                r[f"cap_{a}"] = x["cap"][zs].sum(axis=1).sum()
                # imbalance: the area's error settled at (spot minus imbalance price), hours with both prices only
                F, A = x["pred"][zs].sum(axis=1), x["actual"][zs].sum(axis=1)
                dp = x["spot"][zs[0]] - x["imb"][zs[0]]
                ok = dp.notna()
                r[f"cost_{a}"], r[f"cact_{a}"] = float(((A - F) * dp)[ok].sum()), float(A[ok].sum())
            rows.append(r)
    d = pd.DataFrame(rows)
    d["acc"] = 100 * (1 - d.err / d.act)
    d["nmae"] = 100 * (d.aerr_DK1 + d.aerr_DK2) / (d.cap_DK1 + d.cap_DK2)
    d["rank"] = d.groupby("day").nmae.rank(method="min").astype(int)
    return d


def summary(d):
    """Period totals per source; skill against IFS and Energinet on the days both were ranked."""
    tot = d.groupby("source").agg(err=("err", "sum"), act=("act", "sum"), days=("day", "nunique"),
                                  a1=("aerr_DK1", "sum"), a2=("aerr_DK2", "sum"), c1=("cap_DK1", "sum"),
                                  c2=("cap_DK2", "sum"), k1=("cost_DK1", "sum"), k2=("cost_DK2", "sum"),
                                  m1=("cact_DK1", "sum"), m2=("cact_DK2", "sum"), wins=("rank", lambda r: int((r == 1).sum())),
                                  top3=("rank", lambda r: int((r <= 3).sum())))
    tot["acc"] = 100 * (1 - tot.err / tot.act)
    tot["nmae_DK1"], tot["nmae_DK2"] = 100 * tot.a1 / tot.c1, 100 * tot.a2 / tot.c2
    tot["nmae"] = 100 * (tot.a1 + tot.a2) / (tot.c1 + tot.c2)
    # imbalance cost against a perfect forecast, EUR per MWh of actual output (positive = cost)
    tot["imb_eur_mwh"] = (tot.k1 + tot.k2) / (tot.m1 + tot.m2).where(lambda v: v > 0)
    ae = d.assign(ae=d.aerr_DK1 + d.aerr_DK2).pivot_table(index="day", columns="source", values="ae")
    for ref in ("ifs", "energinet"):
        if ref in ae:
            tot[f"skill_{ref}"] = [100 * (1 - ae[s][ae[ref].notna()].sum() / ae[ref][ae[s].notna()].sum())
                                   if s in ae else float("nan") for s in tot.index]
    return tot.sort_values("nmae")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-scores", help="hourly_scores.csv from score.py")
    a = ap.parse_args()
    out = {}
    for kind, h in (("backtest", backtest_hourly()), ("live", live_hourly(a.live_scores))):
        if h.empty:
            continue
        d = daily(h)
        if d.empty:
            continue
        tot = summary(d)
        r2 = lambda v: None if v != v else round(float(v), 2)
        out[kind] = {"from": d.day.min(), "to": d.day.max(), "days": int(d.day.nunique()),
                     "overall": [dict(source=s, name=NAMES.get(s, s), acc=r2(r.acc), nmae=r2(r.nmae),
                                      nmae_DK1=r2(r.nmae_DK1), nmae_DK2=r2(r.nmae_DK2),
                                      skill_ifs=r2(r.get("skill_ifs", float("nan"))),
                                      skill_energinet=r2(r.get("skill_energinet", float("nan"))),
                                      imb_eur_mwh=r2(r.imb_eur_mwh),
                                      days=int(r.days), wins=int(r.wins), top3=int(r.top3)) for s, r in tot.iterrows()],
                     "daily": [dict(day=r.day, source=r.source, acc=round(r.acc, 2), nmae=round(r.nmae, 2), rank=int(r["rank"]))
                               for _, r in d.sort_values(["day", "rank"]).iterrows()]}
        print(f"\n== {kind}: {out[kind]['days']} days, {out[kind]['from']} to {out[kind]['to']}")
        print(tot[["nmae", "nmae_DK1", "nmae_DK2", "acc", "imb_eur_mwh"] + [c for c in tot if c.startswith("skill")] + ["wins", "top3"]].round(2).to_string())
    out["band"] = {}
    for kind, f in (("backtest", LIVE / "reports" / "band_backtest.csv"), ("live", LIVE / "band_scores.csv")):
        if not f.exists():
            continue
        b = pd.read_csv(f)
        b["t"] = pd.to_datetime(b["hour_utc"], utc=True)
        b["inside"] = (b.actual >= b.lo) & (b.actual <= b.hi)
        b["width"] = b.hi - b.lo
        last = b[b.t >= b.t.max() - pd.Timedelta(days=7)]
        out["band"][kind] = {"hours": len(b), "coverage": round(100 * b.inside.mean(), 1),
                             "width": round(b.width.mean()), "from": f"{b.t.min():%Y-%m-%d}", "to": f"{b.t.max():%Y-%m-%d}",
                             "series": [dict(t=f"{r.t:%Y-%m-%dT%H}", p=round(r.point), lo=round(r.lo), hi=round(r.hi),
                                             a=round(r.actual)) for r in last.itertuples()]}
        if "spread" in b:
            calm = b.spread <= b.spread.median()
            out["band"][kind].update(width_calm=round(b.width[calm].mean()), width_unsettled=round(b.width[~calm].mean()),
                                     cov_calm=round(100 * b.inside[calm].mean(), 1),
                                     cov_unsettled=round(100 * b.inside[~calm].mean(), 1))
        print(f"band {kind}: coverage {out['band'][kind]['coverage']}% over {len(b)} hours")
    # health line for the page: the newest committed forecast and the newest scored day
    fc = sorted((LIVE / "forecasts").glob("*.json"))
    h = {"generated_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%MZ")}
    if fc:
        last = json.load(open(fc[-1]))
        h.update(last_forecast_day=last["target_day_cph"], last_forecast_issued_utc=last["issued_utc"],
                 last_forecast_missing=last.get("missing", []))
    if "live" in out:
        h["last_scored_day"] = out["live"]["to"]
    out["health"] = h
    site = LIVE / "site"
    site.mkdir(exist_ok=True)
    json.dump(out, open(site / "data.json", "w"), indent=0)


if __name__ == "__main__":
    main()
