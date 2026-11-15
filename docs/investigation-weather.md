# Weather context match for Mexico and Amazon NISAR dates

## Scope and source check

This is a new temporal match to coarse reanalysis, not a re-run of the earlier Amazon single-cell ERA5 rain table. I read `docs/research-summary.md`, the prior Amazon ERA5 context and benchmark, and used the existing 29-date Mexico and six-date Amazon site series. No maps, front-end, or external-label outcomes were changed.

On 2026-11-15, small Archive API requests returned HTTP 200 for ERA5 and ERA5-Land dates at both sites. Full histories were then requested from 14 days before the first acquisition through 3 days after the last. ERA5 daily precipitation, 2 m mean temperature, and max 10 m wind were populated; ERA5-Land supplied hourly 0–7 cm soil moisture and 0–7 / 7–28 cm soil temperature. In the sample Mexico request ERA5-Land precipitation and wind were null, and hourly ERA5-Land 10 m wind had 0 valid values; those fields are therefore taken from ERA5 for rain/temp/wind, not silently filled from ERA5-Land. `soil_temperature_0cm` had `undefined` units and was excluded. Soil variables retained the returned units. Each response, exact query URL, UTC retrieval time, returned grid point/elevation, nominal resolution, and SHA-256 is recorded in `data/investigation/weather.json`; unmodified response bodies are in `data/investigation/weather-raw/`.

ERA5 nominal grid spacing is 0.25° (about 25 km at Mexico latitude, about 28 km in Amazon); ERA5-Land is 0.1° (about 10 km). The API snaps the requested center to a grid point. These are **AOI-scale weather covariates, not measurements of any 20 m SAR pixel**. Precipitation windows sum full UTC days immediately before acquisition, exclude acquisition day, and are 1/3/7/14 days. Three future days are retained as a negative-time control. This is retrospective reanalysis, not an operationally available-at-the-time forecast.

## Candidate/date context

The full per-acquisition weather table (including all dates, rain windows, soil moisture/temperature, 2 m temperature and wind) is `sites.mexico.dates` and `sites.amazon.dates` in `data/investigation/weather.json`. Same-site candidates on the same acquisition share the same coarse weather row; there is no defensible finer spatial assignment here.

| Site/date | Prior rain (1 / 3 / 7 / 14 d, mm) | 2 m mean °C | ERA5-Land 0–7 cm soil moisture | Interpretation context |
|---|---:|---:|---:|---|
| Amazon 2026-07-18 | 0 / 12 / 17.1 / 19.9 | 27.0 | 0.217 | First SAR date; 3/7/14-day rainfall elevated relative to next acquisitions |
| Amazon 2026-08-11 | 0 / 0 / 0.1 / 1.0 | 27.4 | 0.100 | Dry interval |
| Amazon 2026-08-23 | 0 / 0 / 0.5 / 0.6 | 28.4 | 0.099 | Dry interval |
| Amazon 2026-09-04 | 0 / 0.1 / 0.4 / 0.6 | 28.5 | 0.101 | Dry interval |
| Amazon 2026-09-16 | 0 / 0 / 0.4 / 0.9 | 29.3 | 0.098 | Dry interval |
| Amazon 2026-09-28 | 0.2 / 0.3 / 0.3 / 0.6 | 29.3 | 0.100 | Late HH/HV rebound occurred without a corresponding rise in preceding rain or modeled surface moisture |
| Mexico 2026-06-15 | 0 / 11.6 / 83.8 / 118.1 | 19.5 | 0.362 | Wet-season pulse; 3/7/14-day windows differ strongly |
| Mexico 2026-08-26 | 16.4 / 65.4 / 81.9 / 91.3 | 18.1 | 0.415 | Large short-window rain pulse |
| Mexico 2026-09-07 | 7.1 / 8.3 / 30.9 / 98.1 | 17.2 | 0.426 | Wet 14-day antecedent period |
| Mexico 2026-09-19 | 0.1 / 1.0 / 14.8 / 59.6 | 18.1 | 0.353 | Recent 1/3-day dry, longer antecedent still wet |
| Mexico 2026-10-13 | 5.5 / 29.9 / 69.0 / 124.8 | 18.4 | 0.415 | Strong 14-day antecedent rain and high modeled surface moisture |

For exact candidate lookup and all 29 Mexico acquisitions use the JSON date rows; values are not copied into separate pixel-specific rows because weather grid support does not distinguish candidates within an AOI.

## New findings (exploratory)

### Краткий вывод по погодным связям

Сильная Mexico temperature–HV level-корреляция (Pearson *r*=−0,664; Spearman ρ=−0,673) **не выдерживает targeted falsification как простая погодная связь**: для соседних первых разностей *r*=0,131 (28 пар наблюдений; интервалы между датами не считались равными скоростями); после удаления линейного тренда и одной годовой sin/cos сезонной компоненты *r*=0,220, ρ=0,273; будущая 3-дневная температура как negative control тоже сильно связана с HV (*r*=−0,571; ρ=−0,547). Следовательно, уровеньная связь в основном совместима с общей сезонностью/временным ходом и не позволяет сказать, что температура объясняет SAR change. Простая сезонная регрессия использует один цикл и имеет мало эффективной информации; это проверка чувствительности, не доказательство отсутствия физического эффекта.

Аналогично, 7-дневный дождь против прежнего point-own-baseline HH forest summary давал *r*=0,447, но этот summary оставляет общую date-компоненту. После настоящего удаления общего режима остаются ассоциации *r*=0,335 для WorldCover 10 (12 ячеек), *r*=0,172 для grassland 30 (49) и *r*=−0,320 для built-up 50 (955); сам `g_t` имеет *r*=0,147. Это описательные, разнородные по классам связи, не подтверждение дождевого механизма; общая поддержка остается 29 дат, а не число пикселей. В 7-дневном окне отдельно не следует выбирать «лучший лаг» среди проверенных 1/3/7/14 дней.

### Определения и точные Mexico sensitivities

Сохранённые поля `*_cover_*_cell_median_residual` — это прежний summary **только после вычитания собственной temporal median точки**. Они не удаляют scene/date common mode. Для точного разложения добавлено:

`d_it = x_it − median_t(x_i)`; `g_t = median_i(d_it)`; `r_it = d_it − g_t`; далее class summary — `median_i(r_it)` внутри WorldCover-класса.

Новые массивы `*_g_t_scene_common_mode_of_point_baseline_deviations` и `*_cover_*_common_mode_removed_local_residual` содержат этот разбор; `*_point_own_baseline_class_median` явно именует старый summary. Ни одно исходное SAR observation не перезаписано. `common_mode_removed_weather_correlations` сравнивает погодные связи с `g_t` и истинными остатками; `class_support` задаёт число ячеек/использование класса.

| Mexico, 29 acquisition dates | Pearson r | Spearman ρ | LOO Pearson range |
|---|---:|---:|---:|
| 7-day rain vs HH `g_t` | 0.147 | 0.212 | 0.028…0.310 |
| 7-day rain vs HH common-mode-removed class residual, cover 10 (n=12) | 0.335 | 0.529 | 0.240…0.485 |
| 7-day rain vs HH residual, cover 30 (n=49) | 0.172 | 0.330 | 0.131…0.280 |
| 7-day rain vs HH residual, cover 50 (n=955) | −0.320 | −0.517 | −0.393…−0.272 |
| 7-day rain vs HV `g_t` | −0.155 | −0.274 | −0.325…−0.092 |
| 7-day rain vs HV residual, cover 10 (n=12) | 0.298 | 0.575 | 0.226…0.508 |
| 7-day rain vs HV residual, cover 30 (n=49) | −0.035 | −0.123 | −0.163…0.040 |
| 7-day rain vs HV residual, cover 50 (n=955) | 0.097 | 0.211 | 0.045…0.197 |

Для температуры Mexico: level HV median против contemporaneous temperature *r*=−0.664, ρ=−0.673 (LOO −0.742…−0.613); `g_t` против температуры *r*=−0.636, ρ=−0.561 (LOO −0.727…−0.579). Первые разности: HV median *r*=0.131, ρ=0.140 (LOO 0.051…0.192); `g_t` *r*=0.177, ρ=0.193 (LOO 0.107…0.232). После trend + годовых sin/cos: HV median *r*=0.220, ρ=0.273 (in-sample residual, приблизительно 25 остаточных df; LOO с повторным fit 0.088…0.302); `g_t` *r*=0.262, ρ=0.275. Future 3-day temperature control: HV median *r*=−0.571, ρ=−0.547 (LOO −0.604…−0.536); `g_t` *r*=−0.554, ρ=−0.459. Эти контроли делают season/trend-confounding правдоподобным объяснением большей части level-связи, но не устанавливают конкретный источник.

Pearson/Spearman, LOO и все исходные погодные окна доступны в JSON. LOO диапазоны не являются доверительными интервалами; они не учитывают временную автокорреляцию. Сравнение классов тоже не имеет независимой репликации внутри даты: у всех ячеек одной сцены одна и та же крупномасштабная погода.

For the Amazon rebound, the available context is an informative **limitation**: prior 7-day rain is low on all five later dates (0.1, 0.5, 0.4, 0.4, 0.3 mm), and ERA5-Land surface moisture is nearly constant from Aug 11 to Sep 28 (0.100, 0.099, 0.101, 0.098, 0.100 m³/m³). The Sept 28 joint SAR rebound therefore is not accompanied by a local-grid modeled wetting pulse. But this does not rule out rainfall/water effects: the model is coarse, can miss local convective rain/flooding, and has no pixel-scale soil/water observation. With only six dates, the Amazon correlations (and their very wide/sign-changing LOO ranges) are descriptive and not evidence of a weather relationship.

WorldCover code counts in the Mexico 1,024-cell site are 12 tree cover (10), 49 grassland (30), 955 built-up (50), and 8 other. Thus “forest vs grass” is technically calculable but underpowered and ecologically questionable in this largely urban footprint; the contrast is a lead for map review, not a general class conclusion. On Amazon, counts are 575 tree cover and 449 grassland, but there are only six independent acquisition dates.

## Physical checks to prioritize on maps

1. For Amazon Sep 28, inspect candidate/cell locations against rivers, floodplain channels, wet bare ground and contemporaneous optical/water layers; check whether the SAR rebound is geographically aligned with those features despite the absence of an ERA5-Land wetting signal.
2. Compare Mexico HH and HV candidate clusters with the computed `g_t`, true `r_it`, and urban/built-up context. The level HV-temperature correlation does **not** survive as a comparably strong first-difference relationship and is also present for future temperature; check season-wide/acquisition/processing effects rather than attributing the SAR change to temperature.
3. For the small Mexico WorldCover-10 and -30 groups, inspect actual map support and class purity; verify the handful of tree-cover candidates independently rather than relying on class-level correlations.
4. Confirm the strongest Mexico rain pulses (especially Aug 26, Sep 7, Oct 13) with a second rainfall product or station/local hydrology data, and verify soil moisture/flood state on the ground or with higher-resolution independent observations.

**Что имеющаяся погода не объясняет:** она не объясняет причину Amazon Sep 28 rebound (нет modeled wetting pulse, но модель coarse); не устанавливает, что Mexico HH/HV изменения вызваны дождём или температурой (association исчезает/ослабевает при другой временной декомпозиции и имеет сильные future controls); не различает причины на масштабе отдельных пикселей или кандидатов. Это ограничения доступного weather evidence, а не доказательство отсутствия гидрологических/термических эффектов.

Новые вычисления по умолчанию используют hash-проверенные сохранённые ответы и не скачивают API повторно; `--refresh` принудительно запрашивает заново. Тесты: `PYTHONPATH=scripts /tmp/opencode/nasa-venv/bin/python -m unittest scripts.test_investigate_weather -v`.
