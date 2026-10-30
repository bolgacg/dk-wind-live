#!/bin/bash
# Laptop cron: when a weather model's history is complete (download lane writes "MODEL DONE <model>" in
# COORDINATION.md), train its own live mapping once, then push models and code to gene. One job at a time.
cd /home/bolgac/projects/dk-wind-blend || exit 1
exec 9>/tmp/dk-live-queue.lock; flock -n 9 || exit 0
# competitor set frozen for the live week 31 Oct to 6 Nov (Bo, 29 Oct); new models are added after it
for m in ecmwf_aifs025_single icon_eu; do
  [ -f live/models/$m/meta.json ] && continue
  [ -f live/models/$m.skip ] && continue
  grep -q "MODEL DONE $m" COORDINATION.md || continue
  # 100 m wind when the archive has it, else 10 m; skip archives that are empty
  lvl=$(python3 -I live/pick_level.py data/raw/openmeteo/$m)
  if [ "$lvl" = none ]; then echo "$m: archive empty, skipped"; date -u > live/models/$m.skip; continue; fi
  echo "=== $(date -u +%FT%TZ) training $m level $lvl"
  OMP_NUM_THREADS=2 nice -n 10 python3 -W ignore live/train.py --weather $m --level $lvl --final || { echo "train $m FAILED"; continue; }
  echo "- $(date '+%d %b %H:%M') projects-97: live mapping trained for $m, test report live/reports/test_$m.csv" >> COORDINATION.md
done
cp site-common/glossary.json live/site/glossary.json  # shared with the study page; projects-97 writes it
rsync -a --exclude reports/ --exclude forecasts/ --exclude tries/ --exclude .git/ --exclude scores.csv --exclude hourly_scores.csv --exclude SCOREBOARD.md --exclude docs/ --exclude site/data.json --exclude site/today.json --exclude site/summary.json --exclude live-public/ \
  live/ gene:dk-wind-live/live/ && echo "$(date -u +%FT%TZ) synced to gene"
mkdir -p live/reports; ls live/reports/testpred_*.csv >/dev/null 2>&1 && \
  rsync -a live/reports/testpred_*.csv live/reports/band_backtest.csv live/reports/capacity_backtest.csv live/reports/prices_backtest.csv live/reports/e3_test_preds.csv gene:dk-wind-live/live/reports/
