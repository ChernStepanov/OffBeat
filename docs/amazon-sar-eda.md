# Amazon SAR exploratory analysis (issue #33)

Reproduce from the repository root with `python scripts/eda_amazon_sar.py` (NumPy required); offline inputs only. The JSON output includes granule IDs, dates, coordinates, per-date availability, WorldCover counts, complete candidate values and control statistics. The unit checks are `python -m pytest scripts/test_eda_amazon_sar.py -q`.

## Scope and provenance

This is the prepared **Amazon / Itupiranga, Pará** SAR sample (not Sarov), using local NISAR L2 GCOV provisional subsets. The `amazon-series` directory contains NPZ data for **2026-08-23, 09-04, 09-16 and 09-28**. The script also audited `data/subsets/amazon/nisar-0.npz` (06-24) and `nisar-1.npz` (07-06): both match exact lat/lon arrays, shapes, grid metadata (EPSG, spacing, window, paths) and SAR signature (track 146, ascending, frame 175, DHDH, A); both are included. Grid spacing is 20 m, window `[6394,6529,13150,13286]`; arrays store linear gamma0 power, converted as `10 log10(power)`. A shared validity mask excludes mask codes 0 and 255, non-finite values, and non-positive power for both polarizations and all calculations. WorldCover shape is checked, but its CRS/geotransform cannot be verified from the local NPZ and is explicitly reported as unverified. Mask bit semantics other than the 0/255 exclusions are also unverified. The clipped grid is not regional coverage.

Candidate **r5 c15** maps to **(-4.766796875, -49.275390625)**; WorldCover 2021 class **10 (tree cover)**. Across this clipped subset, class 10 has 575 cells and class 30 (grassland) 449; these are sampled-cell counts, not land-cover area estimates. WorldCover 2021 is stale context, not contemporaneous validation.

## Candidate signal and peer comparison

| Date | HH dB | HV dB |
|---|---:|---:|
| 2026-06-24 | -6.22 | -12.02 |
| 2026-07-06 | unavailable | unavailable |
| 2026-08-23 | -3.89 | -9.79 |
| 2026-09-04 | -14.24 | -17.21 |
| 2026-09-16 | -13.94 | -17.04 |
| 2026-09-28 | -3.64 | -15.87 |

The 2026-07-06 acquisition has 0/1,024 valid HH/HV pixels under the shared mask, so the candidate is unavailable. The raw 2026-08-23 → 09-04 change is **HH −10.35 dB; HV −7.42 dB**. On 09-28 HH is back near 08-23 (+0.26 dB relative to that date); HV remains −6.08 dB below it. This is a transient-looking HH change and a persistent sampled HV reduction, not evidence of a cause or alert confirmation. Relative to the earliest valid target date (06-24), 09-28 changes are +2.58 dB HH and −3.85 dB HV; this baseline comparison is not the event-window estimate.

Peer correction is the raw target change minus the **median individual change** of same-WorldCover neighbors available on both dates; the candidate is excluded. Every radius uses the same paired-date criterion. Small-window controls are sparse:

| Neighborhood | paired neighbors | median HH change | corrected HH | median HV change | corrected HV |
|---|---:|---:|---:|---:|---:|
| 3×3 | 5 | −2.58 | −7.76 | −4.00 | −3.42 |
| 5×5 | 12 | −2.63 | −7.72 | −2.28 | −5.14 |
| 9×9 | 30 | −1.39 | −8.96 | −1.11 | −6.31 |

All values are dB. The radius sensitivity retains a notable decrease, but the control neighborhood is heterogeneous and the paired counts are small. Counts/medians/IQRs for each radius and polarization are in script output. This is not a calibrated anomaly score. The comparison is consistent with looking beyond a simple before/after baseline, but does not establish disturbance.

## Context and limitations

The local alert file has 17 DETER `DESMATAMENTO_CR` and 354 GLAD-L `glad_confirmed` records dated no later than the last SAR date (these counts are records, not candidate intersections). The script reports their metadata without spatially matching polygon geometries to this pixel. Neither type of alert confirms a SAR change. An alert's recorded date is not evidence that the alert was publicly available on that date; retrospective availability/vintage is not established. Alert dates later than 2026-09-28 are excluded only as a date filter, not as proof of contemporaneous availability.

### One-off external Sentinel-2 context (not locally reproducible)

A separate, one-time network check of Earth Search Sentinel-2 L2A Scene Classification Layer (SCL) at candidate **r5 c15**, coordinate order **longitude, latitude** `(-49.275390625, -4.766796875)`, returned: 2026-08-24=5, 09-03=5, 09-06=8, 09-11=9, 09-13=9, 09-16=9, 09-21=5, 09-23=9, 09-26=3. STAC API endpoint: `https://earth-search.aws.element84.com/v1`; scene ID for 2026-09-21: `S2C_22MFV_20260921_0_L2A`. Method: query the endpoint's STAC Search for Sentinel-2 L2A items covering the coordinate/date, retrieve the SCL asset, and inspect the SCL class at the containing pixel (not a radiometric index). SCL class 5 is not vegetation; it does **not** prove absence of forest. Classes 8/9 indicate cloud (medium/high probability), and 3 indicates cloud shadow. The 2026-09-21 observation is after the SAR change interval and is not evidence of its cause. This network check is not performed by `scripts/eda_amazon_sar.py` and cannot currently be reproduced from the checked-in inputs. Sentinel-2 radiometric assets advertise `scale=0.0001` and `offset=-0.1`; do not calculate or publish indices from raw DN without applying those metadata.

No date-matched weather observation was present in the prepared local Amazon subset. The separately documented SCL query is limited to cloud/scene classification and is not optical corroboration of land-cover change. Therefore there is no weather model or causal attribution; evidence remains insufficient to determine disturbance. Six acquisitions are available overall (one has no valid pixels), below the script's minimum n=10 for Pearson correlations, so the correlation is suppressed. No training is performed. Sparse sampled pixels are never converted into mapped area. Nominal SAR grid spacing is 20 m, but the extracted 32×32 subset spans 2.72×2.74 km, about 87 m per sampled cell on average; it is a sparse sample, not a contiguous 20 m raster suitable for fine-scale spatial claims.

## Files

- `scripts/eda_amazon_sar.py` — deterministic offline analysis and JSON output.
- `scripts/test_eda_amazon_sar.py` — correlation-threshold and data/control regression tests.
