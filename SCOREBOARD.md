# Live scoreboard

Updated 2026-11-07 06:30 UTC. Error = mean absolute error in MW, summed over DK1/DK2 offshore and
onshore wind. Lower is better. energinet_da is Energinet's own day-ahead forecast; energinet_da_debiased scales it
by its actual/forecast ratio over the previous 60 days, the fair bar to beat.

Days scored: 8

| source | mean error, MW |
|---|---|
| j4catdk | 224 |
| ifs | 242 |
| aifs | 252 |
| icon | 265 |
| icon_d2 | 284 |
| ukmo | 296 |
| gfs | 297 |
| knmi | 302 |
| harmonie | 302 |
| energinet_da_debiased | 311 |
| energinet_da | 351 |

80% band, total Denmark: actual inside the band in 88% of 168 scored hours (target 80%), mean width 527 MW.

Per day:

| day        |   aifs |   energinet_da |   energinet_da_debiased |   gfs |   harmonie |   icon |   icon_d2 |   ifs |   j4catdk |   knmi |   ukmo |
|:-----------|-------:|---------------:|------------------------:|------:|-----------:|-------:|----------:|------:|----------:|-------:|-------:|
| 2026-10-30 |    321 |            252 |                     294 |   nan |        287 |    373 |       nan |   233 |       nan |    nan |    nan |
| 2026-10-31 |    124 |            158 |                     192 |   203 |        183 |    169 |       169 |   119 |       182 |    174 |    153 |
| 2026-11-01 |    346 |            302 |                     264 |   518 |        296 |    281 |       372 |   342 |       219 |    298 |    318 |
| 2026-11-02 |    552 |           1043 |                     404 |   571 |        838 |    507 |       775 |   558 |       438 |    846 |    611 |
| 2026-11-03 |    184 |            412 |                     423 |   209 |        296 |    273 |       168 |   218 |       198 |    284 |    399 |
| 2026-11-04 |    110 |            164 |                     258 |   152 |        161 |    131 |       103 |   102 |       140 |    151 |    112 |
| 2026-11-05 |    148 |            187 |                     183 |   193 |        128 |    163 |       180 |   152 |       170 |    148 |    192 |
| 2026-11-06 |    234 |            292 |                     473 |   235 |        228 |    221 |       224 |   210 |       220 |    214 |    290 |
