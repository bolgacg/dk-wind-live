"""Score every issued forecast whose day is over against Energinet's realtime output, and Energinet's own day-ahead
forecast against the same hours. Writes live/scores.csv (one row per day, zone, source) and live/SCOREBOARD.md,
then commits both.

Usage: python3 live/score.py"""
import json, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LIVE, ZONES, realtime_actuals


def energinet_da_frame(start, end):
    from forecast import energinet_da
    out = {}
    for z, v in energinet_da(start, end).items():
        out[z] = pd.Series(v["day_ahead"], index=pd.to_datetime(v["hours"]).tz_localize("UTC"), dtype=float)
    return out


def main():
    now = pd.Timestamp(datetime.now(timezone.utc))
    rows = []
    for f in sorted((LIVE / "forecasts").glob("*.json")):
        r = json.load(open(f))
        hours = pd.to_datetime(r["hours_utc"]).tz_localize("UTC")
        if hours[-1] + pd.Timedelta(hours=1) > now - pd.Timedelta(minutes=30):
            continue
        act = realtime_actuals(f"{hours[0]:%Y-%m-%d}", f"{hours[-1] + pd.Timedelta(days=1):%Y-%m-%d}").reindex(hours)
        sources = dict(r["forecast_mw"])
        snap = r["energinet_snapshot"]
        if not snap or not any(x is not None for v in snap.values() for x in v["day_ahead"]):
            # not published at our issue time: take Energinet's final day-ahead value, flagged in the rows
            from forecast import energinet_da
            snap = energinet_da(hours[0], hours[-1] + pd.Timedelta(hours=1))
            sources_note = "energinet_da_fetched_at_scoring"
        else:
            sources_note = "energinet_da_snapshot"
        en = {z: dict(zip(v["hours"], v["day_ahead"])) for z, v in snap.items()}
        sources["energinet_da"] ={z: [en.get(z, {}).get(h.strftime("%Y-%m-%dT%H:%M:%S")) for h in hours] for z in ZONES}
        # Energinet scaled by actual/forecast over the 60 days before the target day (its DK1 offshore series is
        # capped near 1,000 MW and covers only part of the fleet, so the raw series is not a skill bar there)
        a0 = hours[0] - pd.Timedelta(days=60)
        past_act = realtime_actuals(f"{a0:%Y-%m-%d}", f"{hours[0]:%Y-%m-%d}")
        past_en = energinet_da_frame(a0, hours[0])
        db = {}
        for z in ZONES:
            j = pd.concat([past_act.get(z), past_en.get(z)], axis=1, keys=["a", "f"], sort=True).dropna()
            k = j.a.sum() / j.f.sum() if len(j) > 24 * 20 and j.f.sum() > 0 else float("nan")
            db[z] = [None if v is None or k != k else v * k for v in sources["energinet_da"][z]]
        sources["energinet_da_debiased"] = db
        for src, zs in sources.items():
            for z in ZONES:
                p = pd.Series(zs.get(z, [None] * len(hours)), index=hours, dtype=float)
                ok = p.notna() & act[z].notna()
                if ok.sum() < 20:
                    continue
                err = p[ok] - act[z][ok]
                rows.append(dict(day=r["target_day_cph"], zone=z, source=src, hours=int(ok.sum()),
                                 actual_mwh=round(act[z][ok].sum()), mae_mw=round(err.abs().mean(), 1),
                                 bias_mw=round(err.mean(), 1),
                                 note=sources_note if src.startswith("energinet") else ""))
    if not rows:
        print("nothing to score yet")
        return
    band_rows = []
    for f in sorted((LIVE / "forecasts").glob("*.json")):
        r = json.load(open(f))
        b = r.get("band_total_mw")
        if not b:
            continue
        hours = pd.to_datetime(r["hours_utc"]).tz_localize("UTC")
        if hours[-1] + pd.Timedelta(hours=1) > now - pd.Timedelta(minutes=30):
            continue
        act = realtime_actuals(f"{hours[0]:%Y-%m-%d}", f"{hours[-1] + pd.Timedelta(days=1):%Y-%m-%d}").reindex(hours)
        tot = act[ZONES].sum(axis=1, min_count=4)
        for h, p_, lo, hi, a in zip(hours, b["point"], b["lo"], b["hi"], tot):
            if a == a:
                band_rows.append(dict(day=r["target_day_cph"], hour_utc=h.strftime("%Y-%m-%dT%H:%M"), point=p_,
                                      lo=lo, hi=hi, actual=round(float(a), 1), inside=int(lo <= a <= hi)))
    if band_rows:
        pd.DataFrame(band_rows).to_csv(LIVE / "band_scores.csv", index=False)
    df = pd.DataFrame(rows)
    df.to_csv(LIVE / "scores.csv", index=False)
    # scoreboard: mean absolute error summed over the four zones, per day and source
    piv = df.groupby(["day", "source"]).mae_mw.sum().unstack()
    days = len(piv)
    tot = piv.mean().sort_values()
    lines = ["# Live scoreboard", "",
             f"Updated {now:%Y-%m-%d %H:%M} UTC. Error = mean absolute error in MW, summed over DK1/DK2 offshore and",
             "onshore wind. Lower is better. energinet_da is Energinet's own day-ahead forecast; energinet_da_debiased scales it"
             ,"by its actual/forecast ratio over the previous 60 days, the fair bar to beat.", "",
             f"Days scored: {days}", "", "| source | mean error, MW |", "|---|---|"]
    lines += [f"| {s} | {v:.0f} |" for s, v in tot.items()]
    if band_rows:
        bd = pd.DataFrame(band_rows)
        lines += ["", f"80% band, total Denmark: actual inside the band in {bd.inside.mean():.0%} of "
                  f"{len(bd)} scored hours (target 80%), mean width {(bd.hi - bd.lo).mean():.0f} MW."]
    lines += ["", "Per day:", "", piv.round(0).to_markdown()]
    (LIVE / "SCOREBOARD.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    subprocess.run(["git", "-C", str(LIVE), "add", "scores.csv", "SCOREBOARD.md"]
                   + (["band_scores.csv"] if (LIVE / "band_scores.csv").exists() else []), check=True)
    subprocess.run(["git", "-C", str(LIVE), "commit", "-q", "-m", f"scores through {piv.index.max()}"], check=False)


if __name__ == "__main__":
    main()
