"""Fill the gap between the 2026 test (ends 18 Oct) and the first live forecast (31 Oct): J4catDK as the 10:30 run
would have made it, with the live models (trained on data up to 18 Oct, so these days are unseen), the archived
day-ahead weather runs and DKcast's export cut into the feed format. Labelled "replayed" on the page, never "live".

Usage: DKCAST_FEED=<scratch dir> python3 live/studies/replay_gap.py 2026-10-19 2026-10-27
  ->  reports/replay_gap.csv (hour_utc, zone, source, pred, cap), every source; days already in the file are kept
For days past the weather archive: --api fetches the same day-before runs from Open-Meteo's previous-runs API, and
DKCAST_EXPORT points at projects-5a's backfill (same format as the export, made the same way)."""
import os, sys, time, urllib.parse
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BLEND, LIVE, LIVE_MODELS, POINTS, ROOT, ZONES, capacity_proxy, get_json, realtime_actuals
from train import load_weather
import forecast
import json
import lightgbm as lgb
import numpy as np
from common import features


def api_weather(model, d0, d1, level=100):
    """The runs issued the day before (_previous_day1), as in the archive the models were trained on."""
    names = list(POINTS)
    q = urllib.parse.urlencode({"latitude": ",".join(str(POINTS[p][0]) for p in names),
                                "longitude": ",".join(str(POINTS[p][1]) for p in names),
                                "hourly": f"wind_speed_{level}m_previous_day1,wind_direction_{level}m_previous_day1", "models": model,
                                "wind_speed_unit": "ms", "timezone": "GMT", "start_date": d0, "end_date": d1})
    d = get_json(f"https://previous-runs-api.open-meteo.com/v1/forecast?{q}")
    sp, di = {}, {}
    for p, loc in zip(names, d):
        h = loc["hourly"]
        t = pd.to_datetime(h["time"]).tz_localize("UTC")
        sp[p] = pd.Series(h[f"wind_speed_{level}m_previous_day1"], index=t, dtype=float)
        di[p] = pd.Series(h[f"wind_direction_{level}m_previous_day1"], index=t, dtype=float)
    return pd.DataFrame(sp), pd.DataFrame(di)


def main():
    d0, d1 = sys.argv[1], sys.argv[2]
    feed = Path(os.environ["DKCAST_FEED"])
    feed.mkdir(parents=True, exist_ok=True)
    exp = pd.read_parquet(os.environ.get("DKCAST_EXPORT", ROOT / "experiments" / "results" / "dkcast_wind_export_points.parquet"))
    exp["time"] = pd.to_datetime(exp.time).dt.tz_localize("UTC")
    # every live source with its own mapping (the competitors), plus the four blend members, as forecast.py does
    maps = {}
    for short, model in LIVE_MODELS.items():
        mdir = LIVE / "models" / model
        if (mdir / "meta.json").exists():
            maps[short] = mdir
        elif short in BLEND:
            maps[short] = LIVE / "models" / "ecmwf_ifs025"
    w0, w1 = f"{pd.Timestamp(d0) - pd.Timedelta(days=1):%Y-%m-%d}", f"{pd.Timestamp(d1) + pd.Timedelta(days=1):%Y-%m-%d}"
    weather = {}
    for short, mdir in maps.items():
        lvl = json.load(open(mdir / "meta.json")).get("level", 100)
        if "--api" in sys.argv:
            time.sleep(6)  # Open-Meteo counts each of the 34 locations as a call
            weather[short] = api_weather(LIVE_MODELS[short], w0, w1, lvl)
        else:
            weather[short] = load_weather(LIVE_MODELS[short], level=lvl)
    act = realtime_actuals(f"{pd.Timestamp(d0) - pd.Timedelta(days=65):%Y-%m-%d}", f"{pd.Timestamp(d1) + pd.Timedelta(days=1):%Y-%m-%d}")
    cap = capacity_proxy(act)  # known the day before, as live
    rows = []
    for d in pd.date_range(d0, d1).strftime("%Y-%m-%d"):
        day = pd.Timestamp(d).date()
        start = pd.Timestamp(d, tz="Europe/Copenhagen").tz_convert("UTC")
        hours = pd.date_range(start, pd.Timestamp(day + pd.Timedelta(days=1), tz="Europe/Copenhagen").tz_convert("UTC"),
                              freq="h", inclusive="left")
        cut = exp[exp.time.isin(hours)].copy()
        cut["time"] = cut.time.dt.tz_convert(None)
        cut.to_parquet(feed / f"dkcast_wind_{day}.parquet")
        frames = {m: (weather[m][0].reindex(hours), weather[m][1].reindex(hours)) for m in BLEND}
        cap_now = cap[cap.index < start].iloc[-1]  # the newest value known before the day, like the 10:30 run
        preds = {}
        for short, mdir in maps.items():
            meta = json.load(open(mdir / "meta.json"))
            X = features(*weather[short]).reindex(hours)[meta["features"]].dropna()
            if len(X) < len(hours):
                continue  # a source enters only with every hour, as in the league
            preds[short] = {z: pd.Series(np.clip(lgb.Booster(model_file=str(mdir / f"{z}.txt")).predict(X), 0, None) * cap_now[z],
                                         index=X.index) for z in ZONES}
        if all(m in preds for m in BLEND):
            preds["blend"] = {z: sum(preds[m][z] for m in BLEND) / len(BLEND) for z in ZONES}
        try:
            preds["j4catdk"] = forecast.j4_forecast(frames, hours, cap_now, day)
        except forecast.FeedNotReady as e:
            print(d, "feed not ready:", e, flush=True)
        for src, out in preds.items():
            for z in ZONES:
                for h, v in out[z].items():
                    rows.append(dict(hour_utc=f"{h:%Y-%m-%dT%H:%M}", zone=z, source=src, pred=round(float(v), 1),
                                     cap=round(float(cap_now[z]), 1)))
        print(d, "ok", sorted(preds), flush=True)
    out, f = pd.DataFrame(rows), LIVE / "reports" / "replay_gap.csv"
    if f.exists() and len(out):
        old = pd.read_csv(f)
        if "source" in old:
            out = pd.concat([old[~old.hour_utc.isin(out.hour_utc)], out])
    out.sort_values(["hour_utc", "source", "zone"]).to_csv(f, index=False)


if __name__ == "__main__":
    main()
