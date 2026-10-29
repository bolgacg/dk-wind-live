"""Provisional score for the day in progress: as soon as Energinet's realtime feed has an hour, put it on the page.
The official score is still score.py at 01:30, once the whole day is in; this file never touches scores.csv.

Picks the newest forecast day that has at least one measured hour, scores every source on the hours measured so far
(as the league: area totals' absolute error as a % of capacity, plus accuracy as an extra), and writes
site/today.json with the running ranking and the hourly series (forecast, 80% band, measured output).

Usage: python3 live/today.py"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LIVE, ZONES, realtime_actuals
from league import AREAS, NAMES

CACHE = LIVE.parent / "cache"


def debias_factors(day, first_hour):
    """Energinet actual/forecast ratio over the 60 days before the day, as score.py does; cached per day."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"debias_{day}.json"
    if f.exists():
        return json.load(open(f))
    from score import energinet_da_frame
    a0 = first_hour - pd.Timedelta(days=60)
    act = realtime_actuals(f"{a0:%Y-%m-%d}", f"{first_hour:%Y-%m-%d}")
    en = energinet_da_frame(a0, first_hour)
    k = {}
    for z in ZONES:
        j = pd.concat([act.get(z), en.get(z)], axis=1, keys=["a", "f"], sort=True).dropna()
        k[z] = float(j.a.sum() / j.f.sum()) if len(j) > 24 * 20 and j.f.sum() > 0 else None
    json.dump(k, open(f, "w"))
    return k


def main():
    # --now 2026-10-30T15:00Z replays the page as it would have looked at that moment (for testing)
    now = pd.Timestamp(sys.argv[sys.argv.index("--now") + 1]) if "--now" in sys.argv else pd.Timestamp(datetime.now(timezone.utc))
    out = {"built_utc": f"{now:%Y-%m-%dT%H:%MZ}"}
    for f in sorted((LIVE / "forecasts").glob("*.json"), reverse=True)[:2]:
        r = json.load(open(f))
        hours = pd.to_datetime(r["hours_utc"]).tz_localize("UTC")
        if hours[0] >= now:
            continue
        act = realtime_actuals(f"{hours[0]:%Y-%m-%d}", f"{min(hours[-1], now) + pd.Timedelta(days=1):%Y-%m-%d}")
        act = act.reindex(hours)[ZONES]
        act[act.index + pd.Timedelta(hours=1) > now] = float("nan")
        done = act.notna().all(axis=1)
        if not done.any():
            continue
        src = dict(r["forecast_mw"])
        snap = r.get("energinet_snapshot") or {}
        if not snap:  # not yet published at our issue time: Energinet's day-ahead as it stands now, as score.py does
            from forecast import energinet_da
            snap = energinet_da(hours[0], hours[-1] + pd.Timedelta(hours=1))
        if snap:
            en = {z: dict(zip(v["hours"], v["day_ahead"])) for z, v in snap.items()}
            k = debias_factors(r["target_day_cph"], hours[0])
            src["energinet"] = {z: [None if (v := en.get(z, {}).get(h.strftime("%Y-%m-%dT%H:%M:%S"))) is None
                                    or k.get(z) is None else v * k[z] for h in hours] for z in ZONES}
        rows = []
        for s, zs in src.items():
            p = pd.DataFrame({z: pd.Series(zs.get(z, [None] * len(hours)), index=hours, dtype=float) for z in ZONES})
            ok = done & p.notna().all(axis=1)
            if ok.sum() < done.sum():  # rank only sources that cover every measured hour
                continue
            err = (p[ok] - act[ok]).abs().to_numpy().sum()
            # headline: area totals' absolute error as a % of capacity (proxy stored in the forecast), as league.py
            aerr = sum((p[ok][zs].sum(axis=1) - act[ok][zs].sum(axis=1)).abs().sum() for zs in AREAS.values())
            capsum = sum(r["capacity_proxy_mw"][z] for z in ZONES) * int(ok.sum())
            rows.append(dict(source=s, name=NAMES.get(s, s), nmae=round(100 * aerr / capsum, 2),
                             acc=round(100 * (1 - err / act[ok].to_numpy().sum()), 2)))
        rows.sort(key=lambda x: x["nmae"])
        for i, x in enumerate(rows):
            x["rank"] = i + 1
        b = r.get("band_total_mw") or {}
        tot_act = act.sum(axis=1, min_count=4)
        blend = pd.DataFrame({z: src["blend"][z] for z in ZONES}, index=hours).sum(axis=1, min_count=4) \
            if "blend" in src else pd.Series(dtype=float)
        series = []
        for i, h in enumerate(hours):
            series.append(dict(t=f"{h:%Y-%m-%dT%H}", p=None if blend.get(h) != blend.get(h) else round(blend[h]),
                               lo=round(b["lo"][i]) if b else None, hi=round(b["hi"][i]) if b else None,
                               a=None if tot_act[h] != tot_act[h] else round(tot_act[h])))
        last = hours[done.to_numpy()][-1]
        out.update(day=r["target_day_cph"], hours_measured=int(done.sum()), hours_total=len(hours),
                   through_utc=f"{last + pd.Timedelta(hours=1):%Y-%m-%dT%H:%MZ}", ranking=rows, series=series)
        break
    (LIVE / "site").mkdir(exist_ok=True)
    json.dump(out, open(LIVE / "site" / "today.json", "w"), indent=0)
    print(json.dumps({k: v for k, v in out.items() if k != "series"}, indent=1)[:1500])


if __name__ == "__main__":
    main()
