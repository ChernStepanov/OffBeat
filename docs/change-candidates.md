# Two-date dense radar candidates

This is an exploratory visual inspection layer, not an event detector, validated
accuracy estimate, operational alert service, or inference of cause or area.
The markers are native-grid radar cells chosen from connected candidate groups;
they are not the sparse time-series samples used elsewhere in OffBeat. Their
fixed radar dates do not change when the map's acquisition slider moves.

| Site | GCOV pair | Grid spacing | Groups | Displayed |
| --- | --- | ---: | ---: | ---: |
| Amazon | 2026-08-23 / 2026-09-04 | 20 m | 5 | 5 |
| Mexico City | 2025-10-30 / 2025-11-11 | 10 m | 30 | 30 |
| Caracas | 2025-11-09 / 2025-11-21 | 10 m | 74 | 30 |
| Delhi | 2025-11-21 / 2025-12-03 | 10 m | 74 | 30 |
| Tokyo | 2025-10-31 / 2025-11-12 | 10 m | 57 | 30 |
| Nairobi | 2026-06-30 / 2026-07-12 | 10 m | 100 | 30 |
| Sydney | 2026-06-25 / 2026-07-07 | 10 m | 100 | 30 |

The two provisional GCOV subsets per site retain original HHHH/HVHV power and
mask, native georeferencing, source granule/CMR IDs, dates, URLs and SHA-256 in
`data/subsets/<site>-dense/` (Amazon: `data/subsets/amazon-dense/`). The matching
pair must have identical grids, track, frame and DHDH polarization. Other
prepared areas, dates, polarizations and locations are not inferred.

For each cell valid in both images, `10*log10(HV_after/HV_before)` is calculated.
The existing mask rule accepts values 1..254 and finite positive power. A 3×3
median requires at least five valid cells; a 31×31 local median is subtracted.
For the local-background filter only, unusable intermediate cells are filled
with the median of usable filtered cells; they remain excluded from scoring and
the preview. This approximation can affect estimates near data gaps and edges.
Cells with absolute residual at least 2.5 times the global robust MAD scale are
grouped with eight-connectivity; groups of six or more receive one marker at the
strongest cell. Up to 30 groups are displayed per site. The two native spacings
make the physical footprints of both filters different across sites; scores and
counts are not directly comparable between sites. The thresholds are exploratory
and retrospective. Moisture, speckle, local background subtraction and differing
viewing conditions can cause false positives or missed changes. Group size is not
confirmed event area. Missing data stay transparent.

The package in `data/change-candidates/` contains hash-versioned reports, radar
previews, source receipts and selected Sentinel-2 context. Optical dates can be
outside the radar pair; one optical scene is explicitly not a before/after pair.
AOI cloud scores do not guarantee that the selected point is visible. These
images are not labels or proof of cause. Reviews are stored in the user's browser
and may be exported; there is no shared review database or multi-user backend.
The service worker caches only content-versioned candidate files and hash-tagged
optical images after their first successful load. Cache availability and lifetime
depend on the browser; initial access requires the files to be reachable.

Reproduce locally with the project Python dependencies installed:

```sh
python scripts/detect_dense_changes.py --site amazon
python scripts/detect_dense_changes.py --site mexico
```

The script writes experimental results to `.work-audit/`; it does not publish or
replace the versioned site data. Other sites are `venezuela`, `delhi`, `tokyo`,
`nairobi`, and `sydney`. To retrieve the original windows again, see
`scripts/extract_world_dense.py`; authenticated Earthdata access is required and
credentials must stay local. Never commit tokens, signed URLs or credentials.
