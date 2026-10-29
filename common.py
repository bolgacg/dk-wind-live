"""Shared pieces for the live lane: points, zones, loaders. Points are a frozen copy of collect/dl.py POINTS as of
28 Oct 2026, so the trained models keep their feature layout even if the download lane adds points."""
import gzip, json, time, urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LIVE = ROOT / "live"

POINTS = {
    "horns_rev1": (55.48, 7.84), "horns_rev2": (55.60, 7.58), "horns_rev3": (55.70, 7.68), "thor": (56.35, 7.70),
    "vesterhav_nord": (56.45, 8.08), "vesterhav_syd": (55.95, 8.05), "anholt": (56.60, 11.21),
    "kriegers_flak": (55.03, 12.92), "rodsand": (54.56, 11.62), "samso": (55.72, 10.58), "sprogo": (55.33, 10.97),
    "frederikshavn": (57.44, 10.56), "middelgrunden": (55.69, 12.67),
    "ringkobing": (56.05, 8.35), "lemvig": (56.55, 8.30), "thisted": (56.95, 8.70), "hjorring": (57.45, 9.98),
    "herning": (56.25, 8.80), "varde": (55.62, 8.48), "tonder": (54.95, 8.86), "vesthimmerland": (56.80, 9.40),
    "djursland": (56.40, 10.70), "aabenraa": (55.04, 9.42), "skive": (56.57, 9.03), "jammerbugt": (57.15, 9.55),
    "fyn": (55.30, 10.40), "viborg": (56.45, 9.40), "horsens": (55.85, 9.85),
    "lolland": (54.80, 11.40), "falster": (54.80, 11.90), "w_zealand": (55.45, 11.25), "s_zealand": (55.25, 11.75),
    "n_zealand": (55.95, 12.00), "bornholm": (55.10, 14.90),
}
ZONES = ["DK1_offshore", "DK1_onshore", "DK2_offshore", "DK2_onshore"]
# Weather models compared live. All take the same trained power mapping, so the only difference is the weather.
LIVE_MODELS = {"ifs": "ecmwf_ifs025", "aifs": "ecmwf_aifs025_single", "harmonie": "dmi_harmonie_arome_europe",
               "icon": "icon_eu", "gfs": "gfs_global", "knmi": "knmi_harmonie_arome_europe", "icon_d2": "icon_d2",
               "ukmo": "ukmo_global_deterministic_10km", "metno": "metno_nordic"}
# Our custom model: equal-weight mean of these four, fixed on 28 Oct 2026. The rest are competitors only.
BLEND = ["ifs", "aifs", "harmonie", "icon"]
# Models whose archive and live feed have no 100 m wind use 10 m.
LEVEL = {"ukmo": 10, "metno": 10}
CAP_WINDOW_DAYS = 60
CAP_Q = 0.995


def get_json(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dk-wind-blend live"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"  retry {i + 1}: {e}", flush=True)
            time.sleep(20 * (i + 1))
    raise RuntimeError(f"gave up on {url}")


def features(speed: pd.DataFrame, direction: pd.DataFrame) -> pd.DataFrame:
    """speed/direction: index UTC hour, one column per point (m/s, degrees)."""
    cols = {}
    for p in POINTS:
        s = speed[p]
        cols[f"s_{p}"] = s
        rad = np.deg2rad(direction[p])
        cols[f"u_{p}"] = -s * np.sin(rad)
        cols[f"v_{p}"] = -s * np.cos(rad)
    X = pd.DataFrame(cols, index=speed.index)
    X["hour"] = X.index.hour
    X["doy"] = X.index.dayofyear
    return X


def realtime_actuals(start: str, end: str) -> pd.DataFrame:
    """Hourly mean MW per zone from Energinet's 5-minute realtime feed, [start, end) in UTC dates."""
    d = get_json(f"https://api.energidataservice.dk/dataset/ElectricityProdex5MinRealtime?start={start}T00:00"
                 f"&end={end}T00:00&timezone=UTC&limit=0")
    df = pd.DataFrame(d["records"])
    if df.empty:
        return pd.DataFrame(columns=ZONES)
    df["t"] = pd.to_datetime(df["Minutes5UTC"]).dt.floor("h")
    out = {}
    for area in ("DK1", "DK2"):
        a = df[df.PriceArea == area].groupby("t")
        out[f"{area}_offshore"] = a["OffshoreWindPower"].mean()
        out[f"{area}_onshore"] = a["OnshoreWindPower"].mean()
        n = a.size()
        for z in (f"{area}_offshore", f"{area}_onshore"):
            out[z] = out[z][n >= 10]  # require at least 10 of 12 five-minute values
    res = pd.DataFrame(out)
    res.index = res.index.tz_localize("UTC") if res.index.tz is None else res.index
    return res


def capacity_proxy(actual: pd.DataFrame) -> pd.DataFrame:
    """Per zone, the 99.5th percentile of hourly output over the previous 60 days, known before each day starts.
    Stands in for installed capacity, which grows (Thor offshore) and is not published hourly."""
    caps = {}
    for z in ZONES:
        s = actual[z]
        q = s.rolling(f"{CAP_WINDOW_DAYS}D", min_periods=24 * 20).quantile(CAP_Q)
        # value at the last hour of each day, applied to the whole next day
        last = q.resample("D").last().shift(1)
        caps[z] = last.reindex(actual.index, method="ffill") if len(actual) else last
    return pd.DataFrame(caps)
