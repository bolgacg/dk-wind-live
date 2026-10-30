"""One timeline for the page: the last seven days, today and tomorrow, hour by hour, total Denmark in MW.
Measured output (Energinet realtime), my J4catDK forecast and Energinet's own day-ahead forecast (bias-corrected as in
score.py), with each day's error for both as a % of capacity (the league's measure). Days before the first live
forecast (31 Oct) come from studies/replay_gap.py and are labelled "replayed".

Usage: python3 live/timeline.py  ->  site/timeline.json"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LIVE, ZONES, capacity_proxy, realtime_actuals
from league import AREAS, NAMES
from score import energinet_da_frame
from today import debias_factors

CPH = "Europe/Copenhagen"
PAST_DAYS = 7


def day_hours(d):
    """A Copenhagen calendar day's UTC hours (23, 24 or 25 of them)."""
    return pd.date_range(pd.Timestamp(d, tz=CPH).tz_convert("UTC"), pd.Timestamp(d + pd.Timedelta(days=1), tz=CPH).tz_convert("UTC"),
                         freq="h", inclusive="left")


def main():
    now = pd.Timestamp(datetime.now(timezone.utc))
    today = now.tz_convert(CPH).date()
    days = [today + pd.Timedelta(days=k) for k in range(-PAST_DAYS, 2)]
    hours = pd.DatetimeIndex([h for d in days for h in day_hours(d)])
    act = realtime_actuals(f"{hours[0] - pd.Timedelta(days=63):%Y-%m-%d}", f"{now + pd.Timedelta(days=1):%Y-%m-%d}")
    capp = capacity_proxy(act)
    act = act.reindex(hours)[ZONES]
    act[act.index + pd.Timedelta(hours=1) > now] = float("nan")
    rep_all = pd.read_csv(LIVE / "reports" / "replay_gap.csv", parse_dates=["hour_utc"]) if (LIVE / "reports" / "replay_gap.csv").exists() else None
    rep = rep_all[rep_all.source == "j4catdk"].rename(columns={"pred": "j4catdk"}) if rep_all is not None else None
    en_raw = energinet_da_frame(hours[0], hours[-1] + pd.Timedelta(hours=1))
    J = pd.DataFrame(index=hours, columns=ZONES, dtype=float)
    E = pd.DataFrame(index=hours, columns=ZONES, dtype=float)
    out_days, ranks = [], []
    for d in days:
        hs = day_hours(d)
        kind, issued, cap = None, None, None
        f = LIVE / "forecasts" / f"{d}.json"
        r = json.load(open(f)) if f.exists() else None
        if r and "j4catdk" in r.get("forecast_mw", {}):
            for z in ZONES:
                J.loc[hs, z] = pd.Series(r["forecast_mw"]["j4catdk"][z], index=hs, dtype=float)
            kind, issued, cap = "live", r["issued_utc"], r["capacity_proxy_mw"]
        elif rep is not None and (rep.hour_utc.dt.tz_localize("UTC").isin(hs)).any():
            g = rep[rep.hour_utc.dt.tz_localize("UTC").isin(hs)]
            for z in ZONES:
                gz = g[g.zone == z]
                J.loc[pd.DatetimeIndex(gz.hour_utc).tz_localize("UTC"), z] = gz.j4catdk.to_numpy()
            kind, cap = "replayed", g.groupby("zone").cap.first().to_dict()
        if cap is None:
            c = capp[capp.index < hs[0]]
            cap = c.iloc[-1].to_dict() if len(c) else None
        k = debias_factors(str(d), hs[0])
        for z in ZONES:
            if z in en_raw and k.get(z):
                E.loc[hs, z] = en_raw[z].reindex(hs).to_numpy() * k[z]
        # each day's error, as the league: area totals' absolute error over capacity, on hours all three cover
        ok = act.loc[hs].notna().all(axis=1) & J.loc[hs].notna().all(axis=1) & E.loc[hs].notna().all(axis=1)
        h_ok = hs[ok.to_numpy()]
        err = {}
        if len(h_ok) and cap:
            capsum = sum(cap[z] for z in ZONES) * len(h_ok)
            for name, P in (("j4catdk", J), ("energinet", E)):
                err[name] = round(100 * sum((P.loc[h_ok, zs].sum(axis=1) - act.loc[h_ok, zs].sum(axis=1)).abs().sum()
                                            for zs in AREAS.values()) / capsum, 2)
        # replayed days: every source ranked as the league ranks a live day (area totals' error over capacity)
        if kind == "replayed" and d < today and cap:
            g = rep_all[rep_all.hour_utc.dt.tz_localize("UTC").isin(hs)]
            P = {src: gs.pivot(index="hour_utc", columns="zone", values="pred").reindex(columns=ZONES)
                 for src, gs in g.groupby("source")}
            for src in P:
                P[src].index = P[src].index.tz_localize("UTC")
            P["energinet"] = E.loc[hs]
            okh = act.loc[hs].notna().all(axis=1)
            for v in P.values():
                okh &= v.reindex(hs).notna().all(axis=1)
            hh = hs[okh.to_numpy()]
            if len(hh) >= len(hs) - 2:
                capsum = sum(cap[z] for z in ZONES) * len(hh)
                sc = sorted((round(100 * sum((v.loc[hh, zs].sum(axis=1) - act.loc[hh, zs].sum(axis=1)).abs().sum()
                                             for zs in AREAS.values()) / capsum, 3), src) for src, v in P.items())
                ranks.extend(dict(day=str(d), source=src, nmae=e, rank=i + 1, kind="replayed") for i, (e, src) in enumerate(sc))
        out_days.append(dict(day=str(d), kind=kind, issued_utc=issued, hours=len(hs), hours_scored=len(h_ok),
                             complete=bool(d < today and len(h_ok) > 0), err=err))
    tot = lambda P: P.sum(axis=1, min_count=4)
    series = [dict(t=f"{h:%Y-%m-%dT%H}", a=None if pd.isna(a) else round(a), j=None if pd.isna(j) else round(j),
                   e=None if pd.isna(e) else round(e)) for h, a, j, e in zip(hours, tot(act), tot(J), tot(E))]
    out = dict(built_utc=f"{now:%Y-%m-%dT%H:%MZ}", today=str(today), now_utc=f"{now:%Y-%m-%dT%H:%MZ}", days=out_days, series=series, ranks=ranks,
               names={k: v for k, v in NAMES.items()})
    json.dump(out, open(LIVE / "site" / "timeline.json", "w"), indent=0)
    print(json.dumps(out_days, indent=0)[:1800])


if __name__ == "__main__":
    main()
