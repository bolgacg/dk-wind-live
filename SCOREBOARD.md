# Live scoreboard

Updated 2026-10-31 06:30 UTC. Error = mean absolute error in MW, summed over DK1/DK2 offshore and
onshore wind. Lower is better. energinet_da is Energinet's own day-ahead forecast; energinet_da_debiased scales it
by its actual/forecast ratio over the previous 60 days, the fair bar to beat.

Days scored: 1

| source | mean error, MW |
|---|---|
| blend | 191 |
| ifs | 233 |
| energinet_da | 252 |
| harmonie | 287 |
| energinet_da_debiased | 294 |
| aifs | 321 |
| icon | 373 |

Per day:

| day        |   aifs |   blend |   energinet_da |   energinet_da_debiased |   harmonie |   icon |   ifs |
|:-----------|-------:|--------:|---------------:|------------------------:|-----------:|-------:|------:|
| 2026-10-30 |    321 |     191 |            252 |                     294 |        287 |    373 |   233 |
