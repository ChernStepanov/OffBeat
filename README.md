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

## Исследование matching и абляций

[Указатель экспериментов и данных](docs/experiment-index.md) объединяет отчёты,
протоколы, данные, скрипты и страницы результатов.

Отдельная страница [Research results](research.html) доступна также из меню
дашборда. Она отделяет наблюдаемое согласие NISAR/OPERA RTC-S1 от устойчивости
пространственных аномалий при изменении метода обработки. Это разведочный
анализ одного участка Амазонии, **не оценка точности детектора событий**.

[Человекочитаемый итог](docs/research-summary.md) |
[Протокол и критерии вывода](docs/research-protocol.md). Численные результаты,
таблицы сопоставления и provenance сохраняются в `data/research/`, а расчёты —
в `scripts/research_*.py`. Подробные отчёты связаны со страницей исследования.
Для просмотра достаточно того же статического сервера, что и для дашборда.

Продолжение — [находки на карте](candidates.html): географические карточки
SAR-кандидатов и контролей, новые датированные оптические окна, история
лесного покрова Hansen, рельеф, погода ERA5/ERA5-Land и независимый
резервуарный ряд VIIRS. Региональные INPE DETER-полигоны с оптическими
проверками показаны отдельно: они вне подготовленного SAR-окна и не
выдаются за NISAR-обнаружения. Два выбранных региональных случая имеют
дополнительное локальное снижение NDVI относительно окрестности; третий
такой проверки не выдержал. [Человекочитаемый разбор](docs/investigation-summary.md)
и [протокол](docs/investigation-protocol.md); данные и provenance —
`data/investigation/`.

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

## 3D terrain and expandable windows

Click **3D terrain** in the map title bar. The workspace combines the existing
synchronized maps with a real WebGL elevation map and NISAR samples registered
to its surface. Terrain now streams worldwide as the camera moves; the map is
not cropped to the study areas. Opening from the 2D overview keeps its centre.
A direct local link is `http://localhost:8765/?site=venezuela&view=scene`.

The surface and dense terrain point cloud load visible elevation tiles from
[Mapzen Terrain Tiles on AWS](https://registry.opendata.aws/terrain-tiles/).
Detail adapts to scale. **World** shows the overview, **Study area** returns to
the selected measurements, and **Map centre** opens the current 2D location.
The 3D window also accepts place names or `latitude, longitude`; coordinates
are processed locally, and names are sent to the same geocoders as the 2D search.
Changing location does not infer or manufacture additional NISAR coverage.
Surface colour represents elevation in metres. The separate **1,024 NISAR dots**
keep their actual lat/lon; their colour represents the selected HH/HV backscatter,
not elevation. Changing acquisition or polarization does not move them vertically.
No extra NISAR observations are invented. **Height 1x / 2x / 4x / 8x** changes only
visual exaggeration; elevation readouts remain physical metres.

Choose **Relief + cloud**, **Solid relief** or **Point cloud**; toggle contours,
NISAR dots and the static CRT grain. Drag to orbit, Shift-drag/right-drag to pan,
scroll or use **+ / -** to zoom. **Top view**, **Reset view**, keyboard arrows and
**0** are available. Click a visible NISAR point to update both maps, the pixel
card and its measured history. The 3D window has its own synchronized acquisition
slider, including when it occupies the whole screen. On phones the panels stack.

Every instrument window, including each map separately, has title-bar buttons for
**Enlarge window**, **Maximize window** and **Browser fullscreen**. Press the same
size button or **Esc** to restore it. Double-click a title bar to maximize it.
Browser fullscreen uses the browser's native Fullscreen API; leaving it restores
the preceding window size. Map instances, data, input and selection are retained.

The 3D renderer uses locally vendored Three.js r160.1 (MIT). Detailed global
terrain needs internet, with no Earthdata login or API key. A measured coarse
world tile is bundled so coverage remains visible if the provider is unavailable;
failed tiles are identified and can be retried. Downloads are limited to five
at once, decoded memory to 96 cached tiles, and visible geometry to 64 tiles.
Obsolete requests are cancelled when the view changes. Web Mercator covers
latitudes up to about 85.05 degrees north/south and wraps at the date line.

Prepared local DEM contexts remain optional and never restrict navigation.
Rebuild them with `python3 scripts/prepare_terrain.py`. Original tile receipts
are retained in `data/terrain/*.json`; the bundled world PNG has its own hash.
The DEM is historical context;
resampling and a denser mesh do not increase the source's ground resolution.
See [terrain processing and validation](docs/terrain-scene.md).

Run `node scripts/test_point_cloud.mjs` for numeric DEM integrity, physical
registration, date/channel independence, missing samples and exaggeration checks.
Run `node scripts/test_terrain_tiles.mjs` for global addressing, tile budgets,
decoding, cancellation races, cache bounds, fallback and retry checks.

After editing JS or CSS, run `node scripts/version_assets.mjs` before committing.
The generated content hashes prevent the browser from combining new HTML with
old cached scripts; optical PNG URLs use their recorded SHA-256 as well.

## Sources and licences

NISAR GCOV/GUNW: NASA-ISRO via ASF DAAC / Earthdata; preserve granule attribution and metadata. Sentinel-2: Copernicus Sentinel data via Earth Search. ESA WorldCover 2021 v200: CC BY 4.0, historical context. Fires/alerts retain their NASA FIRMS, INPE or UMD GLAD source. Amazon OPERA RTC-S1 provides sampled C-band measurements; Mexico OPERA DISP-S1 remains catalogue evidence only.

Esri imagery/labels are attributed online context services, not redistributed imagery. Photon uses OpenStreetMap (ODbL); Open-Meteo geocoding uses GeoNames. W95FA by Alina Sava and Ark Pixel 12px proportional by TakWolf (version 2026.11.10, https://github.com/TakWolf/ark-pixel-font) use SIL OFL 1.1; see `fonts/W95FA-OFL.txt` and `fonts/ark-pixel-OFL.txt`. Ark Pixel supplies Cyrillic glyphs only.

Terrain: Mapzen Terrain Tiles, including USGS SRTM/GMTED2010, NOAA ETOPO1,
Mexico INEGI Continental relief (2016) and other regional upstream datasets.
Full attribution and terms:
[Tilezen/Joerd](https://github.com/tilezen/joerd/blob/master/docs/attribution.md).
Three.js is MIT-licensed; its notice is preserved in `js/vendor/THREE-LICENSE.txt`.

No software LICENSE is currently declared. Public visibility does not itself grant an open-source licence; copyright holders must choose one before claiming OSI licensing for submission.
