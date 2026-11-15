# Amazon external static / historical map context

## Кратко (RU)

Из уже сохранённых native-массивов собраны три геопривязанных RGBA PNG: `hansen-lossyear-2001-2024.png`, `hansen-treecover2000.png` и `aws-terrain-elevation.png`. Метаданные `overlays` в `data/investigation/external-maps.json` содержат путь, SHA-256, `bounds_wgs84` (`[west, south, east, north]`), легенду, период, оговорку о разрешении и ключ исходного слоя. PNG перепроецированы из EPSG:32722 с правильным transform, где `x_first/y_first` — центры native-пикселей; Hansen/treecover используют nearest, DEM — bilinear. Hansen code 0 отображён отдельным непрозрачным цветом как «нет loss, нанесённого до 2024», а не nodata и не 2026. Nodata остаётся прозрачным. Это исторические/статические слои, не ground truth сегодняшнего покрова, воды или события. Сборка не загружает новые данные и не меняет native NPZ, UI или существующие поля manifest.

## Scope and interpretation

This analysis adds two independently sourced map layers to the *entire* dense native window (141 × 141, EPSG:32722, 20 m cells), then joins the exact native rows/columns from `data/investigation/map-candidates.json`. It keeps the four visually selected HV candidates distinct from the four controls and from full-grid/background statistics. The four candidates were selected from an all-grid HV screen; **they are not four independent validation sites**. Controls were selected from WorldCover-2021 class 10 and are not class-matched to the candidates.

An important class check: candidates 01/04 are WorldCover 2021 class 10 (tree cover), candidates 02/03 are class 30 (grassland), and all four controls are class 10. Therefore 02/03 must not be described as forest-class errors, and the 4/4 candidate versus 4/4 control comparison is not land-cover matched. Their class-30 label is consistent with the available 2021 map; whether that map captures current 2026 cover is a separate question. The candidate screen used HV changes across all grid cells, not a forest-only eligibility filter.

## Hansen Global Forest Change — bounded window, Landsat-derived

Fetched `treecover2000` and `lossyear` from Hansen GFC 2024 v1.12, 00N_050W, public Google Cloud Storage URLs. GDAL opened the public GeoTIFFs with HTTP range reads and decoded only the ~103 × 103 source-pixel AOI windows (each band window checksum and source URL are recorded in `data/investigation/external-maps.json`). These files are striped 1 × 40000, **not tiled COGs**; HTTP range support is available, but actual transferred bytes can exceed the decoded window. No credentials were used. Source resolution is approximately 30 m (1 arc-second); nearest-neighbor sampling maps values to all native 20 m cells, so neighboring native cells can repeat a source pixel. Raw extracted source windows and full-grid outputs are in `data/investigation/layers/amazon-hansen-native.npz`; file and window hashes are in the JSON receipt. Both native-grid NPZs contain per-cell longitude/latitude derived from the stored EPSG:32722 grid origin and 20 m steps.

The Hansen product is Landsat-derived. `treecover2000` is canopy cover around 2000, not present-day canopy. In `lossyear`, 0 is a valid “no mapped loss” code; 1–24 represent 2001–2024. The endpoint/product does not provide 2025/2026 loss years: do not call this a 2026 event, infer a precise clearing date from a pixel, or treat no mapped loss as proof that no earlier clearing occurred. CC BY 4.0; retain Hansen/UMD/Google attribution.

### Exact point matches

| Point | Coordinates (lat, lon) | HV median shift (dB) | WorldCover 2021 | Tree cover 2000 (%) | Hansen loss year | Distance to unlike WorldCover cell (m) |
|---|---|---:|---:|---:|---:|---:|
| candidate-01 | -4.767560, -49.275796 | -8.480 | 10 | 100 | 2006 | 44.7 |
| candidate-02 | -4.768674, -49.287331 | -8.052 | 30 | 21 | 0 (none mapped) | 72.1 |
| candidate-03 | -4.768434, -49.263715 | -7.913 | 30 | 70 | 0 (none mapped) | 82.5 |
| candidate-04 | -4.785643, -49.274849 | -6.935 | 10 | 51 | 2016 | 189.7 |
| control-01 | -4.781469, -49.269451 | +0.000 | 10 | 97 | 0 (none mapped) | 121.7 |
| control-02 | -4.781673, -49.278465 | -0.001 | 10 | 99 | 0 (none mapped) | 126.5 |
| control-03 | -4.767366, -49.270749 | -0.001 | 10 | 51 | 2021 | 20.0 |
| control-04 | -4.773196, -49.287500 | -0.001 | 10 | 97 | 0 (none mapped) | 140.0 |

3×3 native neighborhoods add local context: candidate-01 has 9/9 cells with loss code 6 (2006) and WorldCover 10; candidate-04 has 6/9 with code 16 (2016), 3/9 no mapped loss, all WorldCover 10. Candidate-02 and -03 each have 9/9 cells with no mapped Hansen loss; their 3×3 WorldCover cells are all class 30. These are historical spatial coincidences, not event labels. In particular, candidate-01’s 2006 code does not itself explain its 2026 radar change, while candidate-02/-03’s 0 code neither confirms nor disproves the dated optical observation.

### Separate full-grid, background, and selected-point summaries

| Support | n | Median tree cover 2000 (%) | Hansen loss code >0 | WorldCover class counts |
|---|---:|---:|---:|---|
| Entire native grid | 19,881 | 97 | 8,948 (45.01%) | 10: 11,265; 20: 2; 30: 8,614 |
| Grid background excluding the eight selected cells | 19,873 | 97 | 8,945 (45.01%) | 10: 11,259; 20: 2; 30: 8,612 |
| Four visual candidates | 4 | 60.5 | 2 (years 2006, 2016) | 10: 2; 30: 2 |
| Four displayed controls | 4 | 97 | 1 (2021) | 10: 4 |

All-grid class strata are recorded in the JSON. Within class 10, median circa-2000 canopy is 99% and 4,399/11,265 cells (39.05%) have a nonzero loss year; within class 30, median is 76% and 4,549/8,614 (52.81%) have a nonzero loss year. This overlap is not a map-accuracy estimate: Hansen’s old canopy/loss definitions, regrowth, differing observation dates/resolutions, and WorldCover’s 2021 classes differ. Four selected points and four selected controls are descriptive, not an inferential comparison. The visual review in `docs/investigation-map-candidates.md` reports existing openings/edges visible by July 3, 2026 for the high-shift candidates; together with their HV-only selection this motivates a *testable hypothesis* of established land-cover structure or radar state, not a causal finding or proof of stale mapping.

Distance to unlike WorldCover class is an Euclidean distance on the nearest-neighbor 20 m class grid. It is **not a current boundary measurement**. Dated 2026 optical previews provide qualitative contemporary context, but no quantitative current land-cover classification was generated here. A possible water/seasonal response also remains untested by these static layers.

## Elevation / slope context

Fetched one AWS Terrain Tiles / Mapzen terrain GeoTIFF, zoom 12, x=1487/y=2102, for the full AOI. It is 108,327 bytes (512 × 512; approximately 19 m/pixel at this latitude); the public URL returned HTTP 206 for a byte-range probe. The raw tile is saved as `data/investigation/layers/aws-terrain-z12-1487-2102.tif`. The complete native output `amazon-dem-native.npz` includes elevation, slope, WorldCover classes, and distance-to-class arrays. Elevation was bilinearly reprojected to the native grid; slope is a simple 20 m finite-difference estimate. Terrain is a mixed-source compilation; Mapzen Terrain Tiles CC BY 4.0 attribution is retained. It is not hydrologically conditioned and does not establish channels, water extent, flooding, or event timing.

The full native grid spans 76.00–126.81 m elevation and 0–19.65° slope. Candidate elevations/slopes are 01: 86.44 m/7.26°; 02: 82.98 m/2.47°; 03: 83.55 m/1.62°; 04: 100.75 m/18.53°. Controls: 01: 102.11 m/13.88°; 02: 106.88 m/2.40°; 03: 90.52 m/2.20°; 04: 104.91 m/3.37°. The points span both low and higher relief; this is context only, not an explanation for any HV shift.

## Sources not acquired / existing local event context

- **JRC Global Surface Water occurrence/seasonality:** the public explorer exposes styled map tiles, but this run did not verify a numeric, bounded raster window. No colors were decoded as values. These products would be historical context, not event truth.
- **OSM infrastructure/waterways:** a small Overpass bbox query was attempted; public endpoints returned 406/429 or timed out. No road/river distance is reported. OSM is ODbL and would require attribution/query date.
- **Dynamic World:** not acquired. It is Sentinel-2-derived, so cloud, acquisition timing, and optical seasonality apply; it is not independent of the visual optical evidence.
- **INPE/PRODES/DETER, MapBiomas/MapBiomas Alerta:** this task did not fetch or spatially match event registries, per coordination. Existing local archives remain untouched: `data/amazon/alerts.geojson` (373 archived features; mixed GLAD-L/DETER context, not a complete event inventory), `data/amazon-external-audit-v3-raw/deter_page_1.json` (7 returned records, partial page), and the earlier `data/amazon/dense-validation.json`. The separate dated-event/optical-validation team can reuse these, while checking original dates, completeness, and geometry coverage before treating them as labels. No existing record is promoted to an event match here.

## Reproduction and tests

```sh
/tmp/opencode/nasa-venv/bin/python scripts/investigate_external_maps.py
/tmp/opencode/nasa-venv/bin/python -m pytest scripts/test_investigate_external_maps.py -q
```

`scripts/build_external_map_overlays.py` reads only cached NPZ arrays and adds the `overlays` key while retaining existing manifest keys and values. It writes PNGs under `data/investigation/layers/`; no network access or native NPZ rewrite occurs. Frontend integration/default-off behavior is separate. Tests check pixel-center georeferencing, bounds, alpha, year codes, and hashes:

```sh
/tmp/opencode/nasa-venv/bin/python scripts/build_external_map_overlays.py
/tmp/opencode/nasa-venv/bin/python -m pytest scripts/test_build_external_map_overlays.py -q
```
