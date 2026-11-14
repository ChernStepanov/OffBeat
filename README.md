# OffBeat

NISAR change finder for NASA Space Apps 2026, challenge “Dancing with the SARs”.

Rice paddies, swamps and forests each have their own backscatter rhythm. OffBeat compares every
NISAR pixel with nearby pixels of the same ESA WorldCover class, flags the ones that fall out of
step (z-score against peers), names the shape of the change and lets you hear it.

| Style | Signal | Usual cause |
|---|---|---|
| HV drop | sharp fall in HV | clearing, fire |
| HH jump | HH rises by double bounce | flooded vegetation |
| Slow drift | phase drifts over months (GUNW) | subsidence |
| Step | displacement jumps on one date | earthquake |

## Real data status

The default application uses real NISAR subsets for Mexico: measured HH/HV on
29 dates from 2025-10-30 through 2026-10-13, plus an exploratory relative GUNW LOS pair. The prepared
case works without login. Earthdata authorization is needed only to re-extract
source data. Missing and quality-rejected measurements remain unavailable.
See [download, processing and provenance instructions](docs/real-nisar.md).

Разреженные демо теперь содержат z-score и предварительные формы изменения:
Мехико — без найденных форм, Амазония — 6 HV drop, Каракас — 1 HV drop и 3 HH jump.
Это кандидаты по форме сигнала; причины изменений независимо не подтверждены.
[Метод, результаты и проверка десяти кандидатов](docs/preview-analysis.md).
[Проверка шести кандидатов Амазонии по RGB и DETER/GLAD](docs/amazon-validation.md):
подтверждённых вырубок нет; три изменения открытого покрытия, один вероятный
ложный change point и два сигнала с неустановленной причиной.
[Положительный контроль по GLAD](docs/amazon-positive-eval.md): пять точек,
ноль срабатываний; у единственной уверенно видимой расчистки недостаточна
радарная история «до», поэтому чувствительность к вырубкам пока не установлена.
Пересчёт сохранённых измерений без сети: `python scripts/analyze_preview.py`.
Нужны `numpy`, `scipy`, `pyproj`; исходные измерения и ось GUNW сохраняются.

## Run

No build step. Any static server:

```bash
python3 -m http.server 8765
```

Then open http://localhost:8765/#mexico (also `#amazon`, `#venezuela`).

«Поиск локаций» accepts place, region and forest names or decimal `latitude, longitude`.
Names in any script are sent only on submit to Open-Meteo / GeoNames, with Photon / Komoot as fallback based on
OpenStreetMap; requests are cached during the session and limited to one per second
per browser. The demo endpoint may throttle or go offline. Operators can set
`window.OB_GEOCODER_URL` before loading `js/app.js` to use a suitable Photon endpoint.
Set window.OB_MULTILINGUAL_GEOCODER_URL to replace the primary Open-Meteo endpoint. Unicode names and right-to-left scripts are preserved; matching depends on provider name coverage. Coordinate searches are local. A search outside the prepared NISAR areas shows
geographic context and explicitly marks the measurement series as unavailable.
The selected site and searched coordinates are retained in the URL across reloads.
The NISAR archive panel searches NASA CMR across ASF NISAR collections for the
point at the map centre. Results include official granule records and original
file links when available. File downloads may require Earthdata Login. Pixel
charts and sonification use the prepared measured cases.
The last map centre and zoom are also remembered locally in the same browser;
an explicitly selected site or coordinates in a link take precedence.

Справа можно выбрать датированную RGB-вырезку Sentinel-2 или контекстную
мозаику Esri. Режим Auto выбирает подготовленный снимок, ближайший к дате
изменения выбранной точки; без неё — к последней дате NISAR.
Облачность указана для всего тайла, а не для участка. Облака и тени не удалены.
Подробности: [подготовка оптических снимков](docs/optical.md).

## Layout

- `index.html`, `css/offbeat.css` — the page, desktop-2005 look on purpose.
- `js/data.js` — loads measured site JSON files; rejects synthetic sources or missing provenance.
- `scripts/subset_nisar.py` — local authenticated extraction, GUNW quality filtering and provenance.
- `js/chart.js` — HH/HV and displacement plots against the peer band.
- `js/sonify.js` — WebAudio: peers keep the beat, the pixel plays its curve, slips late and sour when it strays.
- `js/app.js` — maps (Leaflet), pixel card, top list, player.

## Pipeline

Python, in `pipeline/`. Set up once:

```bash
python3 -m venv .venv && .venv/bin/pip install numpy scipy h5py rasterio pyproj earthaccess asf_search requests pillow pytest
```

Re-extract the small real cases used by the page (local interactive Earthdata login):

```bash
.venv/Scripts/python.exe scripts/subset_nisar.py
.venv/Scripts/python.exe scripts/build_real_demos.py
```

| Step | Module | What it does |
|---|---|---|
| search, read | `nisar.py` | CMR search by AOI and track; reads only the AOI window of each remote HDF5 (GCOV backscatter, GUNW phase, coherence, LOS vectors) |
| land cover | `cover.py` | ESA WorldCover 2021 straight from the public COGs on AWS |
| peers | `peers.py` | per class and date: median and 1.4826 x MAD in 1 km blocks, averaged over 3 km |
| styles | `classify.py` | one change point per pixel; HV drop, HH jump, displacement step or steady drift |
| InSAR | `insar.py` | chains GUNW pairs into displacement; ascending + descending -> vertical and east; coherence loss in built-up areas -> damage proxy |
| context | `context_amazon.py` | NASA FIRMS fires and INPE DETER alerts; checks OffBeat's clearings against them |
| export | `export.py` | `meta.json`, `grid.bin`, `peers.bin`, per-pixel series in 32 x 32 tiles |

The research pipeline can also export full real-data grids with `python -m pipeline.run <site>`.
It has no synthetic mode. The browser uses the prepared small cases above, rather than these
optional binary exports. Missing or quality-rejected samples remain unavailable.

Проверки интерфейса: `node scripts/test_data.mjs`, `node scripts/test_search.mjs`,
`node scripts/test_optical.mjs`, `node scripts/test_navigation.mjs` и
`node scripts/test_tour.mjs`. Проверки пайплайна:
`.venv/bin/python -m pytest pipeline/tests -q -m "not network"`.
Результат ручного QA: [тур, поиск и карты](docs/qa-2026-11-14.md).

## Data

The left map loads a rolling 12-day NISAR GCOV radar mosaic from NASA GIBS.
Newer tiles take precedence, and transparent coverage gaps show the Esri
basemap. OffBeat aggregates the GIBS browse image into square cells and maps
image brightness to blue through red. Clicking a cell outlines its bounds on
both maps. The local measured HV overlay uses its own dB scale, with pixel
charts available in the prepared cases.

NASA-ISRO NISAR (L2 GCOV, L2 GUNW) via ASF DAAC and ESA WorldCover 10 m.
Both panes use Esri World Imagery for matching detail, grey under NISAR on the left
and colour on the right. Place labels and metric scales help orientation.
Imagery dates vary by location; this is context, not date-matched optical validation.

## Font

W95FA by Alina Sava, a pixel re-creation of MS Sans Serif, SIL Open Font License 1.1 (`fonts/W95FA-OFL.txt`).
It sits on its pixel grid at 12.5px (80 font units = 1px), so the UI uses that size. The font has no `— – · ≥ ² … ▶`,
so the UI writes `-`, `>=`, `...` and `sq km` instead.
