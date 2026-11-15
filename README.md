# OffBeat

Explore real NISAR radar samples, compare them with nearby samples of the same historical land-cover class, and hear the measured curves. OffBeat is an exploratory prototype for changes in NISAR radar signals. Automatically identifying the physical causes of events is future work; candidate curve shapes are not verified event diagnoses.

[Demo](https://offbeat.chern.su/) | [Repository](https://github.com/ChernStepanov/OffBeat)

## What is done and what is left

Status on 15 November 2026; live status and discussion are in the [issues](https://github.com/ChernStepanov/OffBeat/issues), results and limits in the [issue audit](docs/issue-audit.md).

**Done:** real NISAR samples at 7 sites with granule links; neighbour comparisons and exploratory curve shapes; dated Sentinel-2 images and a date slider that recolours the map samples, the counter, the table and the pixel card. The page opens with **What the data says**: [`scripts/findings.py`](scripts/findings.py) runs statistical tests on the measured samples and writes [`data/findings.json`](data/findings.json):

- in Mexico City 114 samples drift steadily away from their neighbours over 29 dates (Kendall trend test, 5% false discovery rate), the best candidates for real gradual change ([#33](https://github.com/ChernStepanov/OffBeat/issues/33));
- off-beat samples in Mexico City form connected patches (permutation test, p = 0.007); at the other sites they are scattered like noise;
- HH and HV flag mostly different samples: only 5-28% of off-beat samples depart in both channels, so the two polarisations together find more candidates (Mexico City: 63 significant trends in HH, 57 in HV);
- GNSS station MMX1 sinks 28.9 +/- 1.0 cm/year vertically, while OPERA DISP-S1 20 m away shows -4.8 +/- 4.5 cm/year of relative line-of-sight motion; references and geometry differ, so they are not directly comparable and the cause of the difference is not established ([sensitivity audit](docs/independent-signal-investigation.md), [#36](https://github.com/ChernStepanov/OffBeat/issues/36), [#16](https://github.com/ChernStepanov/OffBeat/issues/16));
- anchored at that station (median of 18 samples within 200 m), OPERA suggests the sampled part of Mexico City sinks about 15-20 cm/year along the radar line, with 95% of points sinking; this is an estimate with stated assumptions, shown as a separate map layer;
- the neighbour band is calibrated (92-94% of measurements inside against the designed 95%), 12-day noise is 1.2-1.9 dB (90th percentile up to 4.2 dB), and scattering physics and coherence by land cover agree with theory;
- scene-wide shifts (Mexico City 2026-01-22, Caracas 2025-11-21) are separated from local change.

Every finding has **Why might this happen?** with labelled hypotheses about physical drivers (construction and double bounce in HH, vegetation and volume scattering in HV, groundwater pumping under Mexico City, moisture and processing updates); they are hypotheses, not verified causes. Playing a sample also animates the map through the acquisition dates in time with the sound. A [29.6-second video](docs/submission/offbeat-video.mp4) plays on the site in a Win98-style player.

The Khimki site was removed because its GCOV values failed physical plausibility checks (HV above HH and above 0 dB, swings of about 10 dB in 12 days). The interface was simplified: 3D terrain opens from its button, layers and the legend are collapsed. See the [science review](docs/science-review.md), [submission draft](docs/submission-draft.md) and [reviewed slides](docs/submission/offbeat-reviewed.pptx). Missing data is always shown as missing.

**Partly done:** z-scores exist for the sparse samples and one bounded dense Amazon window; there is no global dense raster ([#14](https://github.com/ChernStepanov/OffBeat/issues/14)). Samples were checked against dated alerts and fires, but patch areas are not validated ([#18](https://github.com/ChernStepanov/OffBeat/issues/18)). Persistent change is searched for, but weather correction and an independent labelled evaluation set are not ready ([#33](https://github.com/ChernStepanov/OffBeat/issues/33)). The OPERA/GNSS difference is measured and a one-station anchored estimate exists; a validated vertical rate needs per-pixel look vectors, several stations and atmospheric correction ([#36](https://github.com/ChernStepanov/OffBeat/issues/36), [#16](https://github.com/ChernStepanov/OffBeat/issues/16)).

**Blocked by data:** Caracas has no usable optical image for one date; the best HLS mosaic is only 46.65% cloud-free against an 80% threshold ([#13](https://github.com/ChernStepanov/OffBeat/issues/13)). In the GUNW pair across the earthquake and the three pairs before it, 0/1024 samples pass the full quality filter ([#17](https://github.com/ChernStepanov/OffBeat/issues/17)). Thresholds were not relaxed to get a picture. The Amazon OPERA RTC-S1 series and its limits are described [separately](docs/amazon-opera-rtc-comparison.md).

**Licence:** OffBeat's code and documentation are under the [Apache License 2.0](LICENSE); third-party data, fonts and libraries keep their own terms ([NOTICE](NOTICE)).

**Left for people:** final rules check ([#24](https://github.com/ChernStepanov/OffBeat/issues/24)), testing on physical devices and listening to the sound ([#26](https://github.com/ChernStepanov/OffBeat/issues/26)), and submitting by 15 November, 23:59 local time.

103 Python tests (6 network tests not run) and 20 JS scenarios for data, search, maps, tour and style pass.

## AI tools (Super Intelligence)

OffBeat was built with OpenAI Codex and Anthropic Claude (Claude Code) as coding and analysis assistants; people chose the idea, handled data credentials, reviewed every change and made the decisions. No image, video or music generation model was used, and no measurement or statistic was produced by an AI model. Who did what: [docs/ai-use.md](docs/ai-use.md).

## Run in five minutes

No build or NASA login is needed for the prepared demo. Clone the repository, serve its root with Python 3, then open http://localhost:8765/:

```sh
python -m http.server 8765
```

Choose a prepared site to see its measured HH/HV. The left map shows a grayscale satellite basemap, NISAR coverage coloured by date and the sparse measured samples; sample colour is the departure from neighbours, not a continuous raster or an event area. The right map shows Esri optical context by default; a dated Sentinel-2 image can be chosen in its selector. Gaps are shown explicitly. External tiles and search need internet. Sound starts after a click.

The historical GLAD/RGB audit from an earlier research branch is kept in the
[experiment archive](archive/preview-2026-11-14/README.md); it is not an evaluation of the current detector.

Search accepts Unicode names through Open-Meteo/GeoNames and Photon fallback. Names are sent only on submit, cached in the session and throttled. Coordinate searches are local. Operators can override `OB_MULTILINGUAL_GEOCODER_URL` and `OB_GEOCODER_URL` before app.js. Translated-name coverage depends on the providers.
For programmatic read-only access, run `python3 -m api.server` and see the [HTTP API documentation](docs/api.md).

For dataset inventory, endpoint checks and safe catalogue discovery, see the
[operations guide](docs/operations.md). These tools do not automatically publish new measurements.


## Actual prepared data

| Site | GCOV dates | Accepted GUNW samples | Optical matches |
|---|---|---|---|
| Mexico City | 29, 2025-10-30 to 2026-10-13 | 357/1024, one 12-day pair | 29/29 radar dates |
| Itupiranga, Para | 6, 2026-07-18 to 2026-09-28 | 0 | 6/6 radar dates |
| Caracas | 6, 2025-11-09 to 2026-01-08 | 0 | 5/6 radar dates |
| New Delhi, India | 2, 2025-11-21 to 2025-12-03 | 0 | 2 radar dates, one distinct optical image |
| Tokyo, Japan | 2, 2025-10-31 to 2025-11-12 | 803/1024, one 12-day pair | 2 distinct optical images |
| Nairobi, Kenya | 2, 2026-06-30 to 2026-07-12 | 593/1024, one 12-day pair | 2 radar dates, one distinct optical image |
| Sydney, Australia | 2, 2026-06-25 to 2026-07-07 | 573/1024, one 12-day pair | 2 radar dates, one distinct optical image |

Each site has 1024 sparse nearest-native sample locations. Missing and rejected observations stay null. GUNW has a separate date axis; its first zero is a reference convention. No vertical velocity, building-damage map, confirmed clearing area or forecast accuracy is claimed.

The Delhi and Tokyo sites each cover a small 0.025° × 0.025° window, not the whole city. Their two GCOV dates are insufficient for curve-shape classification or a trend. Tokyo's GUNW pair is an apparent relative LOS change, not an independently validated ground-motion rate; no Delhi GUNW samples passed the quality mask. The Esri mosaic is context only; dated Sentinel-2 previews are separate.

Nairobi and Sydney likewise cover only small 0.025° × 0.025° windows, with two GCOV dates; accepted Nairobi and Sydney pairs show apparent relative LOS change, not validated rates. Two dates are insufficient to classify curve shapes or determine a trend. Dated optical previews are context, not independently confirmed event evidence. A Khimki site was removed: its GCOV values failed physical plausibility checks (HV above HH and above 0 dB, about 10 dB swings in 12 days).

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

## 3D terrain and expandable windows

The interactive 3D terrain opens below the two maps from **3D terrain** in the map title bar. The panel can be maximized independently. Terrain streams worldwide as the camera moves and is not cropped to the study areas. NISAR samples retain their measured coordinates. Rendering starts near the viewport and pauses when the panel is out of view. A direct local link is `http://localhost:8765/?site=venezuela&view=scene`.

The surface and dense terrain point cloud load visible elevation tiles from
[Mapzen Terrain Tiles on AWS](https://registry.opendata.aws/terrain-tiles/).
Detail adapts to scale. **World** shows the overview, **Study area** returns to
the selected measurements, and **Map centre** opens the current 2D location.
The 3D window shares its centre with the upper maps and also accepts place names or `latitude, longitude`; coordinates
are processed locally, and names are sent to the same geocoders as the 2D search.
Changing location does not infer or manufacture additional NISAR coverage.
The default surface displays Esri topographic map tiles draped over DEM elevations; other render modes use elevation colours. Map dates vary, and map imagery is not a NISAR measurement. The separate **1,024 NISAR dots**
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

NISAR GCOV/GUNW: NASA-ISRO via ASF DAAC / Earthdata; preserve granule attribution and metadata. Sentinel-2: Copernicus Sentinel data via Earth Search. ESA WorldCover 2021 v200: CC BY 4.0, historical context. Fires/alerts retain their NASA FIRMS, INPE or UMD GLAD source. Amazon OPERA RTC-S1 provides sampled C-band measurements; Mexico OPERA DISP-S1 includes a quality-masked relative LOS series, with atmospheric and reference limitations.

Esri imagery/labels are attributed online context services, not redistributed imagery. Photon uses OpenStreetMap (ODbL); Open-Meteo geocoding uses GeoNames. W95FA by Alina Sava and Ark Pixel 12px proportional by TakWolf (version 2026.11.10, https://github.com/TakWolf/ark-pixel-font) use SIL OFL 1.1; see `fonts/W95FA-OFL.txt` and `fonts/ark-pixel-OFL.txt`. Ark Pixel supplies Cyrillic glyphs only.

Terrain: Mapzen Terrain Tiles, including USGS SRTM/GMTED2010, NOAA ETOPO1,
Mexico INEGI Continental relief (2016) and other regional upstream datasets.
Full attribution and terms:
[Tilezen/Joerd](https://github.com/tilezen/joerd/blob/master/docs/attribution.md).
Three.js is MIT-licensed; its notice is preserved in `js/vendor/THREE-LICENSE.txt`.

OffBeat's own code and documentation are licensed under the [Apache License 2.0](LICENSE); see [NOTICE](NOTICE). Third-party data, imagery, fonts and libraries listed above keep their own terms and are not relicensed.
