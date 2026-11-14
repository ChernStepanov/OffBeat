# Issue audit — 14 November 2026

This audit does not claim every issue is fixed. Earthdata/ASF authentication is available for the processing below.

| Issue | Status | Acceptance evidence or remaining work |
|---|---|---|
| #10 | Implemented | Per-date Sentinel-2 indexes for all sites; 29/29, 6/6 and 5/6 available |
| #11 | Implemented and visually checked | AOI-only COG reads, SCL mask, exact bbox, fixed stretch/gamma, PNG hashes |
| #12 | Implemented and browser-checked | Dated selector, nearest radar date, source/date/quality and unavailable state |
| #13 | Open | One Caracas date lacks suitable Sentinel-2. Twenty HLS T19PGM quality masks were inspected; best clear AOI 40.3% (threshold 80%). Other overlapping HLS tiles remain unexamined; see `data/subsets/venezuela-hls/2025-11-21-quality.json`. |
| #14 | Partial — reopened | Leave-self-out 1 km same-class peers, >=10 valid samples and latest robust z are available for sparse points. The requested continuous real-data z raster has not been produced; it requires dense gridded measurements, not interpolation of the sparse sample points. |
| #15 | Implemented | 6 Amazon and 4 Venezuela curve shapes; none in Mexico; top-10 examples and deterministic controls |
| #16 | Open | Ascending/descending GUNW series, assessed reference, rates and uncertainties not available |
| #17 | Open | Three compatible pre-event GUNW pairs were read; 0/1024 samples in each pass the unchanged mask, including ionosphere uncertainty <=1 rad. The event pair also has 0/1024; a defensible damage proxy is not available. |
| #18 | Partial — reopened | 6 sparse candidates, 0 dated alert overlaps and 1 fire-context match were checked. The requested patch-level validation, defensible area and recall remain unavailable without dense measured coverage. |
| #19–22 | Implemented | Recalculated dated values and primary NASA/ESA/USGS/literature sources in science review |
| #23 | Implemented | Tour separates browse, calibrated samples, exploratory shapes and unvalidated LOS |
| #24 | Partial | Sourced submission checklist; final guide, event time zone and software licence need confirmation |
| #26 | Partial | Available-browser and numerical QA; Safari/iPhone and physical-device/listening coverage not claimed |
| #27 | Partial | English recording script; no narrated screen recording produced |
| #28 | Implemented as requested draft | English submission text and six-slide PPTX, with source notes and embedded measured chart values |
| #29 | Implemented | Five-minute static launch, current data, reproduction, sources and licence gaps |
| #33 | Partial | Own-history vs neighbour-relative baselines, candidates, controls and coarse retrospective ERA5 precipitation context; two native 20 m windows before/after the Amazon candidate were extracted and checked; dense multi-date series, weather-corrected model, labels and held-out evaluation remain absent |
| #35 | Implemented | Existing 86-date RTC-S1 sample series and 219 granule IDs are in `data/amazon/sentinel1.json`; independently recomputed six matched-date, matched-point C/L comparison is in `data/analysis/amazon-c-l-matched.json` (C VH forest–grassland 1.16 dB; L HV 6.15 dB). Exploratory only. |
| #36 | Partial | 15 same-reference OPERA DISP-S1 products were sampled at the Mexico points; recommended-mask-accepted short-wavelength LOS series are shown with provenance and limitations. No validated velocity or vertical motion is claimed. |

Raw HH/HV, GUNW and original source receipts are preserved. Analysis provenance
hashes its measured input samples. Missing values and zero/undefined peer spread
remain unavailable. No synthetic application measurements were added.
