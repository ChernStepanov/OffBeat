# Issue audit — 14 November 2026

This audit does not claim every issue is fixed. Additional Earthdata downloads
are excluded at the user's request.

| Issue | Status | Acceptance evidence or remaining work |
|---|---|---|
| #10 | Implemented | Per-date Sentinel-2 indexes for all sites; 29/29, 6/6 and 5/6 available |
| #11 | Implemented and visually checked | AOI-only COG reads, SCL mask, exact bbox, fixed stretch/gamma, PNG hashes |
| #12 | Implemented and browser-checked | Dated selector, nearest radar date, source/date/quality and unavailable state |
| #13 | Open | One Caracas date lacks suitable Sentinel-2; HLS extraction requires Earthdata |
| #14 | Implemented | Leave-self-out 1 km same-class peers, >=10 valid samples, latest robust z; sparse points replace an invalid continuous raster |
| #15 | Implemented | 6 Amazon and 4 Venezuela curve shapes; none in Mexico; top-10 examples and deterministic controls |
| #16 | Open | Ascending/descending GUNW series, assessed reference, rates and uncertainties not available |
| #17 | Open | Event-pair receipt exists but 0 samples pass full mask; compatible pre-event baseline not downloaded |
| #18 | Implemented for sparse samples | 6 candidates, 0 dated alert overlaps, 1 fire-context match; no event area or recall |
| #19–22 | Implemented | Recalculated dated values and primary NASA/ESA/USGS/literature sources in science review |
| #23 | Implemented | Tour separates browse, calibrated samples, exploratory shapes and unvalidated LOS |
| #24 | Partial | Sourced submission checklist; final guide, event time zone and software licence need confirmation |
| #26 | Partial | Available-browser and numerical QA; Safari/iPhone and physical-device/listening coverage not claimed |
| #27 | Partial | English recording script; no narrated screen recording produced |
| #28 | Implemented as requested draft | English submission text and six-slide PPTX, with source notes and embedded measured chart values |
| #29 | Implemented | Five-minute static launch, current data, reproduction, sources and licence gaps |
| #33 | Partial | Own-history vs neighbour-relative baselines, candidates and random controls; dense windows, weather, labels and held-out evaluation absent |
| #35 | Open | RTC-S1 footprint overlap proven; no authenticated VV/VH series or numeric C/L contrast |
| #36 | Open | DISP-S1 footprint overlap proven; no inspected displacement series or velocity |

Raw HH/HV, GUNW and original source receipts are preserved. Analysis provenance
hashes its measured input samples. Missing values and zero/undefined peer spread
remain unavailable. No synthetic application measurements were added.
