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
previews, source receipts and Sentinel-2 context selected for each radar date.
Optical dates can fall outside the radar pair; one optical scene is explicitly not a before/after pair.
AOI cloud scores do not guarantee that the selected point is visible. These
images are not labels or proof of cause. The optional shared review API stores
verdicts and image basis in SQLite when deployed; comments remain in the browser.
If the shared API is not configured or reachable, the interface reports that the
review was not sent. Public deployment requires a separate API service; the static
site alone does not provide one. See `docs/api.md`.
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


## Review rotation (15 November 2026)

The main review button rotates study areas, not individual nearby cells. The five
rural Amazon candidates share one area; seven existing NASA-published rural image
comparisons each have their own area. Every available area appears once before
starting another round, with no consecutive area repeat when alternatives exist.
Individual Amazon cells rotate between rounds. Rotation history persists in the
browser and is pruned when datasets or shared moderation state remove cards.
Urban radar windows remain outside this rural discovery rotation.

Published comparisons are explicitly labelled as external NASA examples, never
OffBeat detections. Dates, image receipts and sources remain in
`data/observed-events/index.json`. These examples do not supply georeferenced
OffBeat detections or accuracy labels. Shared review decisions use image SHA-256
fingerprints so that changing an image pair starts a separate review record.
Review and evidence download controls have been removed from the UI. Comments
are neither collected in these cards nor transmitted to another reviewer.

Validation: `node scripts/test_review_rotation.mjs` exercises 80 visits over ten
rounds, region isolation, per-area cell rotation, reloadable state and removals;
`python -m unittest api.test_reviews` checks shared queue decisions and undo.
