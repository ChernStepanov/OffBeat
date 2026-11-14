# OffBeat

Explore real NISAR radar samples, compare them with nearby samples of the same historical land-cover class, and hear the measured curves. Curve shapes are candidates for checking, not automatic event diagnoses.

[Demo](https://offbeat.chern.su/) | [Repository](https://github.com/ChernStepanov/OffBeat)

## Что сделано и что осталось

Состояние на 14 ноября 2026; актуальные статусы и обсуждение — в [issues](https://github.com/ChernStepanov/OffBeat/issues). Подробные результаты и ограничения приведены в [аудите задач](docs/issue-audit.md).

**Сделано:** подключены реальные выборки NISAR и ссылки на гранулы; рассчитаны сравнения с соседями и предварительные формы кривых; добавлены датированные снимки Sentinel-2 и переключение дат. Исправлены проверка дат лесных alert и смешение кэшированных версий сайта. Подготовлены [научный разбор](docs/science-review.md), [черновик заявки](docs/submission-draft.md) и [слайды](docs/submission/offbeat-draft.pptx). Отсутствующие данные показываются явно.

**Частично сделано:** z-score рассчитан для разреженных точек, но плотного растра ещё нет ([#14](https://github.com/ChernStepanov/OffBeat/issues/14)); выполнена сверка точек с alert и пожарами, но проверка площадных пятен и их площади не завершена ([#18](https://github.com/ChernStepanov/OffBeat/issues/18)). Есть простые базовые сравнения для ML, но погодная коррекция и независимая оценка ещё не готовы ([#33](https://github.com/ChernStepanov/OffBeat/issues/33)).

**Осталось:** обработать HLS ([#13](https://github.com/ChernStepanov/OffBeat/issues/13)), дополнительные ряды GUNW ([#16](https://github.com/ChernStepanov/OffBeat/issues/16), [#17](https://github.com/ChernStepanov/OffBeat/issues/17)) и продукты OPERA ([#35](https://github.com/ChernStepanov/OffBeat/issues/35), [#36](https://github.com/ChernStepanov/OffBeat/issues/36)); для загрузки нужен Earthdata Login. Также не завершены проверка правил и лицензии ([#24](https://github.com/ChernStepanov/OffBeat/issues/24)), QA на устройствах и прослушивание ([#26](https://github.com/ChernStepanov/OffBeat/issues/26)), запись видео ([#27](https://github.com/ChernStepanov/OffBeat/issues/27)).

Проверены 36 научных тестов и сценарии данных, поиска и тура; шесть сетевых тестов не запускались. Заявку и видео ещё не сдавали.

## Run in five minutes

No build or NASA login is needed for the prepared demo. Clone the repository, serve its root with Python 3, then open http://localhost:8765/:

```sh
python -m http.server 8765
```

Choose a prepared site for measured HH/HV charts. The default global NASA GIBS map is a browse mosaic coloured by acquisition date, not calibrated backscatter. The optional local analysis layer displays sparse sample points, never a continuous event raster or event area. Use the optical selector for dated Sentinel-2 previews. Missing observations are explicit; the Esri mosaic is geographic context only. External map tiles and search require internet. Audio starts after a user click.

Search accepts Unicode names through Open-Meteo/GeoNames and Photon fallback. Names are sent only on submit, cached in the session and throttled. Coordinate searches are local. Operators can override `OB_MULTILINGUAL_GEOCODER_URL` and `OB_GEOCODER_URL` before app.js. Translated-name coverage depends on the providers.

## Actual prepared data

| Site | GCOV dates | Accepted GUNW samples | Optical matches |
|---|---|---|---|
| Mexico City | 29, 2025-10-30 to 2026-10-13 | 357/1024, one 12-day pair | 29/29 radar dates |
| Itupiranga, Para | 6, 2026-07-18 to 2026-09-28 | 0 | 6/6 radar dates |
| Caracas | 6, 2025-11-09 to 2026-01-08 | 0 | 5/6 radar dates |

Each site has 1024 sparse nearest-native sample locations. Missing and rejected observations stay null. GUNW has a separate date axis; its first zero is a reference convention. No vertical velocity, building-damage map, confirmed clearing area or forecast accuracy is claimed.

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

Re-extracting NISAR/OPERA requires Earthdata Login. Keep credentials outside version control; enter them only locally, never in chat, issues or PRs. No credentials are bundled. Without login, catalogue overlap is checkable but OPERA velocities and numerical C/L comparisons remain unavailable.

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

NISAR GCOV/GUNW: NASA-ISRO via ASF DAAC / Earthdata; preserve granule attribution and metadata. Sentinel-2: Copernicus Sentinel data via Earth Search. ESA WorldCover 2021 v200: CC BY 4.0, historical context. Fires/alerts retain their NASA FIRMS, INPE or UMD GLAD source. OPERA is catalogue evidence only until actual additional measurements are processed.

Esri imagery/labels are attributed online context services, not redistributed imagery. Photon uses OpenStreetMap (ODbL); Open-Meteo geocoding uses GeoNames. W95FA font uses SIL OFL 1.1, see `fonts/W95FA-OFL.txt`.

No software LICENSE is currently declared. Public visibility does not itself grant an open-source licence; copyright holders must choose one before claiming OSI licensing for submission.
