"""League table: daily accuracy of every forecast source, backtest plus live, for the public page.

Accuracy for one day = 100% minus (sum of absolute hourly errors over the four zones) / (sum of actual output).
Backtest: reports/testpred_<model>.csv, out-of-sample predictions on 19 Jul to 18 Oct 2026 from mappings trained
before 19 Jul. Live: scores.csv from score.py (forecasts committed before each day). Each day ranks only the sources
that covered at least 20 of its hours; the score uses the hours every ranked source covered.

Usage: python3 live/league.py [--live-scores path/to/scores.csv]  ->  site/data.json"""
import argparse, json, sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BLEND, LIVE, LIVE_MODELS, ZONES

NAMES = {"blend": "Our blend", "energinet": "Energinet (bias-corrected)", "ifs": "ECMWF IFS",
         "aifs": "ECMWF AIFS (AI)", "harmonie": "DMI HARMONIE", "icon": "DWD ICON-EU", "gfs": "NOAA GFS",
         "knmi": "KNMI HARMONIE", "icon_d2": "DWD ICON-D2", "ukmo": "UK Met Office", "metno": "MET Norway Nordic",
         "energinet_da": "Energinet (raw)", "energinet_da_debiased": "Energinet (bias-corrected)"}


def backtest():
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
    rows = []
    days = act.index.tz_convert("Europe/Copenhagen").date
    for day, idx in pd.Series(act.index, index=act.index).groupby(days):
        a = act.loc[idx]
        ok = {s: p.reindex(idx).notna().all(axis=1) for s, p in preds.items()}
        ranked = [s for s in preds if ok[s].sum() >= 20]
        common = a.notna().all(axis=1)
        for s in ranked:
            common &= ok[s]
        if common.sum() < 20:
            continue
        for s in ranked:
            err = (preds[s].loc[idx][common] - a[common]).abs().to_numpy().sum()
            rows.append(dict(day=str(day), source=s, acc=100 * (1 - err / a[common].to_numpy().sum()),
                             err=err, act=a[common].to_numpy().sum(), kind="backtest"))
    return pd.DataFrame(rows)


def live(path):
    if not path or not Path(path).exists():
        return pd.DataFrame()
    s = pd.read_csv(path)
    s = s[s.source != "energinet_da"].replace({"source": {"energinet_da_debiased": "energinet"}})
    s["err"] = s.mae_mw * s.hours
    g = s.groupby(["day", "source"]).agg(err=("err", "sum"), act=("actual_mwh", "sum"),
                                         zones=("zone", "count")).reset_index()
    g = g[g.zones == 4]
    g["acc"] = 100 * (1 - g.err / g.act)
    g["kind"] = "live"
    return g[["day", "source", "acc", "err", "act", "kind"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-scores")
    a = ap.parse_args()
    df = pd.concat([backtest(), live(a.live_scores)], ignore_index=True)
    df["rank"] = df.groupby("day").acc.rank(ascending=False, method="min").astype(int)
    out = {}
    for kind, d in df.groupby("kind"):
        tot = d.groupby("source").agg(err=("err", "sum"), act=("act", "sum"), days=("day", "nunique"),
                                      wins=("rank", lambda r: int((r == 1).sum())),
                                      top3=("rank", lambda r: int((r <= 3).sum())))
        tot["acc"] = 100 * (1 - tot.err / tot.act)
        tot = tot.sort_values("acc", ascending=False)
        out[kind] = {"from": d.day.min(), "to": d.day.max(), "days": int(d.day.nunique()),
                     "overall": [dict(source=s, name=NAMES.get(s, s), acc=round(r.acc, 2), days=int(r.days),
                                      wins=int(r.wins), top3=int(r.top3)) for s, r in tot.iterrows()],
                     "daily": [dict(day=r.day, source=r.source, acc=round(r.acc, 2), rank=int(r["rank"]))
                               for _, r in d.sort_values(["day", "rank"]).iterrows()]}
        print(f"\n== {kind}: {out[kind]['days']} days, {out[kind]['from']} to {out[kind]['to']}")
        print(tot[["acc", "days", "wins", "top3"]].round(2).to_string())
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
    site = LIVE / "site"
    site.mkdir(exist_ok=True)
    json.dump(out, open(site / "data.json", "w"), indent=0)


if __name__ == "__main__":
    main()
