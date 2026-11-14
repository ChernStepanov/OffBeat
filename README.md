# OffBeat

Explore real NISAR radar samples, compare them with nearby samples of the same historical land-cover class, and hear the measured curves. Curve shapes are candidates for checking, not automatic event diagnoses.

[Demo](https://offbeat.chern.su/) | [Repository](https://github.com/ChernStepanov/OffBeat)

## Что сделано и что осталось

Состояние на 14 ноября 2026; актуальные статусы и обсуждение — в [issues](https://github.com/ChernStepanov/OffBeat/issues). Подробные результаты и ограничения приведены в [аудите задач](docs/issue-audit.md).

**Сделано:** подключены реальные выборки NISAR и ссылки на гранулы; рассчитаны сравнения с соседями и предварительные формы кривых; добавлены датированные снимки Sentinel-2 и переключение дат. Исправлены проверка дат лесных alert и смешение кэшированных версий сайта. Подготовлены [научный разбор](docs/science-review.md), [черновик заявки](docs/submission-draft.md) и [слайды](docs/submission/offbeat-draft.pptx). Отсутствующие данные показываются явно.

**Частично сделано:** z-score рассчитан для разреженных точек, но плотного растра ещё нет ([#14](https://github.com/ChernStepanov/OffBeat/issues/14)); выполнена сверка точек с alert и пожарами, но проверка площадных пятен и их площади не завершена ([#18](https://github.com/ChernStepanov/OffBeat/issues/18)). Есть простые базовые сравнения для ML, но погодная коррекция и независимая оценка ещё не готовы ([#33](https://github.com/ChernStepanov/OffBeat/issues/33)).

**Осталось:** обработать HLS ([#13](https://github.com/ChernStepanov/OffBeat/issues/13)), дополнительные ряды GUNW ([#16](https://github.com/ChernStepanov/OffBeat/issues/16), [#17](https://github.com/ChernStepanov/OffBeat/issues/17)) и данные OPERA DISP-S1 ([#36](https://github.com/ChernStepanov/OffBeat/issues/36)); для загрузки нужен Earthdata Login. Ряд OPERA RTC-S1 для Амазонии и его ограничения описаны [отдельно](docs/amazon-opera-rtc-comparison.md). Также не завершены проверка правил и лицензии ([#24](https://github.com/ChernStepanov/OffBeat/issues/24)), QA на устройствах и прослушивание ([#26](https://github.com/ChernStepanov/OffBeat/issues/26)), запись видео ([#27](https://github.com/ChernStepanov/OffBeat/issues/27)).

Проверены 36 научных тестов и сценарии данных, поиска и тура; шесть сетевых тестов не запускались. Заявку и видео ещё не сдавали.

## Run in five minutes

No build or NASA login is needed for the prepared demo. Clone the repository, serve its root with Python 3, then open http://localhost:8765/:

```sh
python -m http.server 8765
```

Выберите подготовленный участок для просмотра измеренных HH/HV. Слева — светлая карта с отметками демоучастков и разреженными точками измерений. Цвет точек показывает отклонение от соседей; это не сплошной растр и не площадь события. Справа по умолчанию показан оптический контекст Esri; датированный Sentinel-2 выбирается в селекторе. Пропуски показаны явно. Для внешних тайлов и поиска нужен интернет. Звук запускается после нажатия.

Исторический аудит GLAD/RGB из прежней исследовательской ветки сохранён
в [архиве эксперимента](archive/preview-2026-11-14/README.md); он не является оценкой текущего детектора.

Search accepts Unicode names through Open-Meteo/GeoNames and Photon fallback. Names are sent only on submit, cached in the session and throttled. Coordinate searches are local. Operators can override `OB_MULTILINGUAL_GEOCODER_URL` and `OB_GEOCODER_URL` before app.js. Translated-name coverage depends on the providers.
For programmatic read-only access, run `python3 -m api.server` and see the [HTTP API documentation](docs/api.md).


## Actual prepared data

| Site | GCOV dates | Accepted GUNW samples | Optical matches |
|---|---|---|---|
| Mexico City | 29, 2025-10-30 to 2026-10-13 | 357/1024, one 12-day pair | 29/29 radar dates |
| Itupiranga, Para | 6, 2026-07-18 to 2026-09-28 | 0 | 6/6 radar dates |
| Caracas | 6, 2025-11-09 to 2026-01-08 | 0 | 5/6 radar dates |
| New Delhi, India | 2, 2025-11-21 to 2025-12-03 | 0 | not prepared |
| Tokyo, Japan | 2, 2025-10-31 to 2025-11-12 | 803/1024, one 12-day pair | not prepared |
| Khimki, Moscow Oblast, Russia | 2, 2026-06-25 to 2026-07-07 | 0 | not prepared |
| Nairobi, Kenya | 2, 2026-06-30 to 2026-07-12 | 593/1024, one 12-day pair | not prepared |
| Sydney, Australia | 2, 2026-06-25 to 2026-07-07 | 573/1024, one 12-day pair | not prepared |

Each site has 1024 sparse nearest-native sample locations. Missing and rejected observations stay null. GUNW has a separate date axis; its first zero is a reference convention. No vertical velocity, building-damage map, confirmed clearing area or forecast accuracy is claimed.

The Delhi and Tokyo sites each cover a small 0.025° × 0.025° window, not the whole city. Their two GCOV dates are insufficient for curve-shape classification or a trend. Tokyo's GUNW pair is an apparent relative LOS change, not an independently validated ground-motion rate; no Delhi GUNW samples passed the quality mask. Dated optical images are not yet prepared for these two sites; the Esri mosaic is context only.

Khimki, Nairobi and Sydney likewise cover only small 0.025° × 0.025° windows, with two GCOV dates and no dated optical preview. No Khimki GUNW samples passed the quality mask; accepted Nairobi and Sydney pairs show apparent relative LOS change, not validated rates. Two dates are insufficient to classify curve shapes or determine a trend.

- `data/<site>.json`: measured values, leave-one-out peer bands, latest robust z, exploratory curve shapes and GUNW quality/provenance.
- `data/<site>-manifest.json`: producer/CMR IDs, dates, tracks, footprints, polarizations and URLs. `data/subsets/`: numeric subsets and SHA-256 receipts.
- `data/<site>/optical/index.json`: radar/optical date match, scene ID, source COG URLs, AOI mask fractions, calibration, bounds and PNG SHA-256. Several radar dates may share one real image.
- `data/analysis/`: dated class medians, candidate examples, random controls and own-history versus neighbour-relative baselines.
- `data/amazon/validation.json`: dated sparse point/alert and point/fire context matches. No area, recall or accuracy estimate.
- `data/evidence/`: exact OPERA catalogue and USGS query evidence.

[Science review](docs/science-review.md) | [Issue completion audit](docs/issue-audit.md) | [Data contract](docs/data-contract.md) | [Original extraction](docs/real-nisar.md)

## Reproduce

```sh
python -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements.txt
.venv/bin/python -m scripts.analyze_samples
.venv/bin/python scripts/validate_samples.py
.venv/bin/python scripts/optical.py
.venv/bin/python scripts/catalog_checks.py
```

On Windows use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.

Peers use the same WorldCover 2021 class within 1 km, excluding self, with at least 10 valid neighbours. Spread is 1.4826 MAD; zero spread is unavailable. Curve shapes use at least two valid observations per segment. The z-score is a spatial departure, not a Gaussian probability or a weather-corrected change score.

Optical processing searches Earth Search within +/-15 days, checks the local SCL mask, reads only AOI COG windows, and reprojects to the exact site bbox. All dates use reflectance 0 to 0.3 and gamma 2.2; provider harmonisation flags prevent applying the BOA offset twice.

Re-extracting NISAR/OPERA requires Earthdata Login. Keep credentials outside version control; enter them only locally, never in chat, issues or PRs. No credentials are bundled. The prepared Amazon RTC-S1 series and comparison are available offline; no OPERA displacement velocity has been calculated.

```sh
node scripts/test_data.mjs
node scripts/test_search.mjs
node scripts/test_navigation.mjs
node scripts/test_tour.mjs
node scripts/version_assets.mjs --check
.venv/bin/python -m pytest pipeline/tests -q -m "not network"
```

Synthetic numerical fixtures exist only in offline tests, never in application data.

After editing JS or CSS, run `node scripts/version_assets.mjs` before committing.
The generated content hashes prevent the browser from combining new HTML with
old cached scripts; optical PNG URLs use their recorded SHA-256 as well.

## Sources and licences

NISAR GCOV/GUNW: NASA-ISRO via ASF DAAC / Earthdata; preserve granule attribution and metadata. Sentinel-2: Copernicus Sentinel data via Earth Search. ESA WorldCover 2021 v200: CC BY 4.0, historical context. Fires/alerts retain their NASA FIRMS, INPE or UMD GLAD source. Amazon OPERA RTC-S1 provides sampled C-band measurements; Mexico OPERA DISP-S1 remains catalogue evidence only.

Esri imagery/labels are attributed online context services, not redistributed imagery. Photon uses OpenStreetMap (ODbL); Open-Meteo geocoding uses GeoNames. W95FA font uses SIL OFL 1.1, see `fonts/W95FA-OFL.txt`.

No software LICENSE is currently declared. Public visibility does not itself grant an open-source licence; copyright holders must choose one before claiming OSI licensing for submission.
