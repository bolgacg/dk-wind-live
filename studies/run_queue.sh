#!/bin/bash
# overnight study queue for the live lane, one at a time, niced
cd /home/bolgac/projects/dk-wind-blend || exit 1
for s in points_needed disagreement; do
  echo "=== $(date -u +%FT%TZ) start $s"
  OMP_NUM_THREADS=2 nice -n 10 python3 -W ignore live/studies/$s.py || echo "FAILED $s exit $?"
done
echo "=== $(date -u +%FT%TZ) QUEUE DONE"
