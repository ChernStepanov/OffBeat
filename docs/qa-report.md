# QA report — 14 November 2026

## Checked

- Offline scientific tests, including temporal alert matching, preservation of
  missing values, no-reference GUNW chaining, real-sample recalculation and optical
  calibration/hash/bounds checks. Exact final totals are recorded in the PR.
- Node checks for measured data, peer z arithmetic, preserved source-subset
  checksums, empty/missing charts, multilingual search and script syntax.
- Local browser run at `http://127.0.0.1:8766`: all **8 tour steps** passed after
  repairing a `bringToFront` failure caused by using LayerGroup for point samples.
- Amazon optical date changed from the 14 August to the 3 September observation;
  source, NISAR match, scene ID and AOI cloud fraction updated.
- Caracas 21 November 2025 selected explicitly: no dated image, visible explanation
  and geographic-context fallback. No HLS image is claimed from catalogue metadata.
- Play/Stop controls tested; Stop becomes disabled after stopping. This is a
  functional check, not a subjective assessment of audio comfort.
- Responsive browser viewport 390×844: actual content width 375 px including
  scrollbar, document width 375 px; no horizontal overflow. Maps stack vertically
  and missing-image explanation remains visible. Temporary viewport restored.
- Actual PNGs inspected before and after calibration repair: duplicate BOA offset
  had produced nearly black scenes. Rebuilt previews are readable and use one
  consistent stretch. Both panes aligned after moving optical status below the maps.
- Six-slide draft rendered and visually inspected; embedded editable chart data,
  slide geometry, fonts and package structure checked by the presentation finalizer.

## Explicitly not checked

Safari, Firefox, iPhone, Android physical hardware, OS/device audio output and
subjective listening; Slow 3G network throttling; native PowerPoint opening;
Earthdata-authenticated additional NISAR/OPERA/HLS measurements. These are not
represented as passed tests. No narrated 1080p video has been recorded.

## Remaining risks

NASA browse coverage varies by date and scale and can fail to load; the global
map is not a calibrated physical HH/HV layer. Esri dates vary. WorldCover 2021
may be stale. Two-point classifier segments and six-date series are exploratory.
No independent labelled accuracy estimate, weather correction, event area,
vertical velocity or building-damage attribution is supported by this release.
