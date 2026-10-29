"""Print 100, 10 or none: the wind height a model's archive covers well enough to train on (more than half the hours
at a sample of points). Usage: python3 -I live/pick_level.py data/raw/openmeteo/<model>"""
import gzip, json, sys
from pathlib import Path

files = sorted(Path(sys.argv[1]).glob("*.json.gz"))[::7]
for level in (100, 10):
    n = t = 0
    for f in files:
        try:
            h = json.load(gzip.open(f)).get("hourly", {})
        except Exception:
            continue
        v = h.get(f"wind_speed_{level}m_previous_day1") or []
        n += sum(x is not None for x in v)
        t += len(v)
    if t and n / t > 0.5:
        print(level)
        break
else:
    print("none")
