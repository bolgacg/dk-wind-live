#!/bin/bash
# Laptop cron: when a weather model's history is complete (download lane writes "MODEL DONE <model>" in
# COORDINATION.md), train its own live mapping once, then push models and code to gene. One job at a time.
cd /home/bolgac/projects/dk-wind-blend || exit 1
exec 9>/tmp/dk-live-queue.lock; flock -n 9 || exit 0
for m in ecmwf_aifs025_single icon_eu; do
  [ -f live/models/$m/meta.json ] && continue
  grep -q "MODEL DONE $m" COORDINATION.md || continue
  echo "=== $(date -u +%FT%TZ) training $m"
  nice -n 10 python3 -W ignore live/train.py --weather $m --final || { echo "train $m FAILED"; continue; }
  echo "- $(date '+%d %b %H:%M') projects-97: live mapping trained for $m, test report live/reports/test_$m.csv" >> COORDINATION.md
done
rsync -a --exclude reports/ --exclude forecasts/ --exclude .git/ --exclude scores.csv --exclude SCOREBOARD.md --exclude docs/ --exclude site/data.json --exclude live-public/ \
  live/ gene:dk-wind-live/live/ && echo "$(date -u +%FT%TZ) synced to gene"
mkdir -p live/reports; ls live/reports/testpred_*.csv >/dev/null 2>&1 && \
  rsync -a live/reports/testpred_*.csv gene:dk-wind-live/live/reports/
