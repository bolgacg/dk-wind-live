"""Replay simulation of the live chain (Bo, 29 Oct): for past days in the 2026 test, cut a feed file from the DKcast
export in the live feed format, run forecast.j4_forecast on archived day-ahead weather exactly as the 10:30 run does,
and compare with the frozen test's predictions for the same hours (reports/e3_test_preds.csv). Uses models retrained
to the frozen spec on 2025 only (train_j4.py --until 2026-01-01 --out models_e3), so the two should agree.

Usage: J4_MODELS=live/models_e3 DKCAST_FEED=<dir> python3 live/studies/replay.py  ->  reports/replay.json"""
import json, os, sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BLEND, LIVE, LIVE_MODELS, ROOT, ZONES, capacity_proxy
from train import load_actuals, load_weather
import forecast

DAYS = ["2026-01-20", "2026-02-14", "2026-03-15", "2026-04-05", "2026-06-10", "2026-08-20", "2026-10-10"]


def main():
    feed = Path(os.environ["DKCAST_FEED"])
    feed.mkdir(parents=True, exist_ok=True)
    exp = pd.read_parquet(ROOT / "experiments" / "results" / "dkcast_wind_export_points.parquet")
    exp["time"] = pd.to_datetime(exp.time).dt.tz_localize("UTC")
    weather = {m: load_weather(LIVE_MODELS[m]) for m in BLEND}
    Y = load_actuals()
    cap = capacity_proxy(Y)
    ref = pd.read_csv(LIVE / "reports" / "e3_test_preds.csv", header=[0, 1], index_col=0, parse_dates=True)["j4catdk_c"]
    rows = []
    for d in DAYS:
        day = pd.Timestamp(d).date()
        start = pd.Timestamp(d, tz="Europe/Copenhagen").tz_convert("UTC")
        hours = pd.date_range(start, start + pd.Timedelta(days=1), freq="h", inclusive="left")
        cut = exp[exp.time.isin(hours)].copy()
        cut["time"] = cut.time.dt.tz_convert(None)  # the feed's format: naive UTC, like the export
        cut.to_parquet(feed / f"dkcast_wind_{day}.parquet")
        frames = {m: (sp.reindex(hours), di.reindex(hours)) for m, (sp, di) in weather.items()}
        capd = {z: cap[z].reindex(hours) for z in ZONES}
        try:
            out = forecast.j4_forecast(frames, hours, capd, day)
        except forecast.FeedNotReady as e:
            rows.append(dict(day=d, status=f"feed not ready: {e}"))
            continue
        sim = pd.DataFrame(out)
        r = ref.reindex(sim.index)[ZONES]
        ok = r.notna().all(axis=1)
        diff = (sim[ok] - r[ok]).abs()
        act = Y.reindex(sim.index[ok])[ZONES]
        acc = lambda p: round(100 * (1 - (p - act).abs().to_numpy().sum() / act.to_numpy().sum()), 2)
        rows.append(dict(day=d, status="ok", hours=int(ok.sum()), max_abs_diff_mw=round(float(diff.max().max()), 3),
                         mean_abs_diff_mw=round(float(diff.mean().mean()), 4),
                         total_sim_mwh=round(float(sim[ok].sum().sum())), total_test_mwh=round(float(r[ok].sum().sum())),
                         accuracy_sim=acc(sim[ok]), accuracy_test=acc(r[ok])))
        print(rows[-1], flush=True)
    json.dump(rows, open(LIVE / "reports" / "replay.json", "w"), indent=1)


if __name__ == "__main__":
    main()
