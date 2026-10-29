"""80% uncertainty band for total Danish wind, from how much the blend's four members disagree.

Spread = standard deviation of the four members' total-Denmark forecasts for the hour. The band is
blend + [q10, q90] x scale, with scale = spread + 0.15 x blend + 100 MW, so it widens when the members disagree and
when more wind is forecast. q10 and q90 are percentiles of (actual minus blend) / scale. A first version with five
fixed spread bins covered only 73% on the check window (fitted on calm summer weeks); a spread-only scale gave 75%;
this one 79%. Those were the only three variants tried. Fitted on the
out-of-sample test predictions (reports/testpred_*.csv, 19 Jul to 18 Oct 2026, mappings trained before 19 Jul).

Honest check first: fit on 19 Jul to 3 Sep, measure coverage on 4 Sep to 18 Oct. Then refit on the whole window and
write models/band.json for the live forecast. Writes reports/band_backtest.csv (hourly rows of the check window).

Usage: python3 live/band.py"""
import json, sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BLEND, LIVE, LIVE_MODELS, ZONES

LO_Q, HI_Q = 0.10, 0.90
LEVEL_K, FLOOR_MW = 0.15, 100.0
SPLIT = pd.Timestamp("2026-09-04", tz="UTC")


def members_total():
    tot, act = {}, None
    for m in BLEND:
        d = pd.read_csv(LIVE / "reports" / f"testpred_{LIVE_MODELS[m]}.csv", index_col=0, parse_dates=True)
        tot[m] = d[ZONES].sum(axis=1, min_count=4)
        act = d[[f"actual_{z}" for z in ZONES]].sum(axis=1, min_count=4)
    df = pd.DataFrame(tot)
    df["actual"] = act
    return df.dropna()


def scale(members, point):
    return members.std(axis=1) + LEVEL_K * point + FLOOR_MW


def fit(df):
    point = df[BLEND].mean(axis=1)
    r = (df.actual - point) / scale(df[BLEND], point)
    return {"lo": float(np.quantile(r, LO_Q)), "hi": float(np.quantile(r, HI_Q)), "q": [LO_Q, HI_Q],
            "level_k": LEVEL_K, "floor_mw": FLOOR_MW, "members": BLEND}


def apply(band, members: pd.DataFrame, cap_total=None):
    """members: one column per blend member, total-Denmark MW per hour. Returns point, lo, hi."""
    m = members[band["members"]]
    point = m.mean(axis=1)
    sc = m.std(axis=1) + band["level_k"] * point + band["floor_mw"]
    lo = (point + band["lo"] * sc).clip(lower=0)
    hi = point + band["hi"] * sc
    if cap_total is not None:
        hi = hi.clip(upper=cap_total)
    return point, lo, hi


def main():
    df = members_total()
    tr, te = df[df.index < SPLIT], df[df.index >= SPLIT]
    band = fit(tr)
    point, lo, hi = apply(band, te)
    inside = (te.actual >= lo) & (te.actual <= hi)
    width = (hi - lo)
    # a band of fixed width with the same average coverage, to show what the spread adds
    resid_tr = tr.actual - tr[BLEND].mean(axis=1)
    flo, fhi = np.quantile(resid_tr, LO_Q), np.quantile(resid_tr, HI_Q)
    f_inside = (te.actual >= point + flo) & (te.actual <= point + fhi)
    spread_te = te[BLEND].std(axis=1)
    calm = spread_te <= spread_te.median()
    print(f"check window {te.index.min():%d %b} to {te.index.max():%d %b}: {len(te)} hours")
    print(f"  spread band: coverage {inside.mean():.1%} (target 80%), mean width {width.mean():.0f} MW, "
          f"calm half {width[calm].mean():.0f} MW, unsettled half {width[~calm].mean():.0f} MW")
    print(f"  fixed band:  coverage {f_inside.mean():.1%}, width {fhi - flo:.0f} MW everywhere")
    print(f"  coverage in calm half {inside[calm].mean():.1%}, unsettled half {inside[~calm].mean():.1%}; "
          f"fixed band {f_inside[calm].mean():.1%} and {f_inside[~calm].mean():.1%}")
    out = pd.DataFrame({"point": point, "lo": lo, "hi": hi, "actual": te.actual, "spread": spread_te})
    out.to_csv(LIVE / "reports" / "band_backtest.csv", index_label="hour_utc")
    final = fit(df)
    final["check"] = {"from": str(te.index.min()), "to": str(te.index.max()), "hours": len(te),
                      "coverage": float(inside.mean()), "mean_width_mw": float(width.mean()),
                      "fixed_band_coverage": float(f_inside.mean()), "fixed_band_width_mw": float(fhi - flo)}
    json.dump(final, open(LIVE / "models" / "band.json", "w"), indent=1)
    print("final band (fit on all test hours): lo", round(final["lo"], 3), "hi", round(final["hi"], 3))


if __name__ == "__main__":
    main()
