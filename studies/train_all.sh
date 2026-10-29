#!/bin/bash
# train every weather model's own mapping (test report + out-of-sample predictions + final model), one at a time
cd /home/bolgac/projects/dk-wind-blend || exit 1
for spec in ecmwf_ifs025:100 ecmwf_aifs025_single:100 icon_eu:100 dmi_harmonie_arome_europe:100 gfs_global:100 \
            knmi_harmonie_arome_europe:100 icon_d2:100 ukmo_global_deterministic_10km:10 metno_nordic:10; do
  m=${spec%%:*}; l=${spec##*:}
  echo "=== $(date -u +%FT%TZ) $m level $l"
  OMP_NUM_THREADS=2 nice -n 10 python3 -W ignore live/train.py --weather $m --level $l --final 2>&1 | grep -v Warning | tail -6 || echo "FAILED $m"
done
echo "=== $(date -u +%FT%TZ) TRAIN ALL DONE"
