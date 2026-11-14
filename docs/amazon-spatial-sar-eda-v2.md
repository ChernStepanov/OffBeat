# Amazon SAR candidates: revised spatial/date EDA

Reproduce with `/tmp/opencode/nasa-venv/bin/python scripts/eda_amazon_spatial_v2.py`; test with `/tmp/opencode/nasa-venv/bin/python -m pytest scripts/test_eda_amazon_spatial_v2.py -q`. This is a separate offline analysis; it does not edit or use the existing spatial-only validation as confirmation.

## Data and procedure

The input pair is local **NISAR L2 GCOV provisional** NPZ/JSON under `data/subsets/amazon-series/`, track 146, frame 175, ascending, grid EPSG:32722. Exact acquisition intervals from granule IDs are **2026-08-23 09:04:09–09:04:43 UTC** and **2026-09-04 09:04:08–09:04:43 UTC** (not just calendar dates). Both arrays have matching coordinates/grid metadata and 1,024 paired valid cells. Linear gamma0 power changes are converted to dB as `10*log10(after/before)` after excluding mask 0/255, non-finite and non-positive HH/HV.

The revised strong criterion requires **both** HH and HV changes < 0 and ranks by RMS `sqrt((dHH²+dHV²)/2)`. Controls include three seeded-random cells (seed 33017) and the three smallest RMS changes; this cannot hide opposing-channel changes by averaging signed values. Selected cells are kept at least 3 row/column cells apart, which reduces local duplication but does not make events independent. Analysis is retrospective, **not preregistered**.

The revised strong rows/columns are **5,15; 12,20; 8,11; 7,30**. The first two are unchanged from the earlier signed-mean selection; **11,10 and 13,7 are replaced** by 8,11 and 7,30. The seeded-random controls remain **19,13; 26,16; 26,26**. The old low-change controls **15,28; 0,6; 17,21** are replaced with **16,12; 5,27; 17,3** because the former signed average could cancel polarization changes. Prior full candidate values and their roles are retained in `data/amazon-spatial-sar-eda-v2-original-selection.json`; machine-readable old/new overlaps are in the regenerated report.

The offline summary uses Shapely `make_valid` on invalid GeoJSON polygons and boundary-inclusive `covers(Point)` for point-in-polygon. The checked-in 373-feature set contains 200 invalid geometries; repairs produce 198 MultiPolygons and 2 GeometryCollections, all valid. Date-only GLAD/DETER records on either SAR calendar date are labeled time-ambiguous, not `within_pair`. Full geometry repair details, dated matching, Sentinel context and external source caveats are in `docs/amazon-external-audit-v2.md` and `data/amazon-spatial-external-audit-v2.json`.

## Availability and limits

This offline script makes no network request; dated SCL and external checks are in the separate network-dependent audit. SAR remains provisional and clipped/sampled, not wall-to-wall coverage or an area estimate. Controls are descriptive, not causal matched controls. No model training, cause attribution, or event confirmation is performed.

The deterministic selection and source matching can be rerun locally; the result depends on the checked-in input versions. WorldCover is not used to claim class alignment because its local subset lacks verifiable transform/CRS. No external source availability was assumed beyond checked-in files.
