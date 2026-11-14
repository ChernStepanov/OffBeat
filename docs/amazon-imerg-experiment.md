# Amazon IMERG access-only audit (issue #33)

Run from the repository root:

```sh
python scripts/experiment_imerg_amazon.py
```

This is **only a catalogue/access/header audit**, not an authenticated downloader
or precipitation extractor. It does not read `.netrc`, Earthdata cookies, or
credentials; it never claims those mechanisms are supported. It queries CMR
for IMERG Early (`GPM_3IMERGHHE_07`), Late (`GPM_3IMERGHHL_07`), and Final
(`GPM_3IMERGHH_07`) and records real granule IDs, timestamps and HDF5 URLs.
For Early/Late it makes an anonymous byte-range GET on a real granule URL. An
HTTP success is not treated as a data success: the returned bytes must have an
HDF5 signature at an allowed signature offset. Even verified HDF5 bytes would
mean **access/header verified only**; this script does not inspect rainfall
variables. `precipitation_mm: null` means unmeasured by this audit, not 0.

The JSON at `data/amazon-imerg-experiment.json` records the **2026-11-14
13:25 UTC** run timestamp,
all CMR query URLs/results, SAR sidecar paths/source IDs and timestamps, access
probe URLs/effective URLs/status/content type, read-byte count and HDF5 header
result. The recorded run was regenerated after this change. Exact acquisition
identification fields are copied from each sidecar only: when `identification`
is absent, track/frame/pass are null and provenance says they were not inferred.

## Time windows and granule coverage

Each 1/3/7-day window is `[SAR start − N days, SAR start)` in UTC. Only whole
30-minute bins contained in the window count; bins overlapping either edge are
excluded, and no information after SAR start is used. A bin beginning exactly
at the window start is included (so an aligned 09:00→09:00 day has 48 bins).
For 2026-09-04 09:04:08 UTC the 1-day window has 49 intersecting granules
including edges, 47 complete bins and 97.9167% temporal coverage; 3-day is
145/143 bins (99.3056%) and 7-day is 337/335 (99.7024%). The two edge bins are
not prorated. The JSON reports the same checks for each acquisition and stream.

For 2026-09-04 the last complete bin is 08:30–09:00 UTC. Example actual CMR
granules:

- Early `G4298225006-GES_DISC`: `https://data.gesdisc.earthdata.nasa.gov/data/GPM_L3/GPM_3IMERGHHE.07/2026/247/3B-HHR-E.MS.MRG.3IMERG.20260904-S083000-E085959.0510.V07C.HDF5`
- Late `G4298685711-GES_DISC`: `https://data.gesdisc.earthdata.nasa.gov/data/GPM_L3/GPM_3IMERGHHL.07/2026/247/3B-HHR-L.MS.MRG.3IMERG.20260904-S083000-E085959.0510.V07C.HDF5`

The anonymous GETs of these files redirected to Earthdata Login and returned
401 during the recorded run. Thus no file bytes or rain values were obtained;
this is an observed access failure, not a claim about what authenticated
access could do. Final has no 2026 granules in CMR (its temporal end is
2025-09-30), which means unavailable coverage, not zero rainfall.

## Acquisition scope / provenance caveat

The audit covers the six GCOV sidecars from the prior EDA and separately flags
2026-07-18 / 2026-08-11 from
`data/subsets/amazon/2026-07-18_2026-08-11/nisar-{0,1}.json`. The additional
sidecars explicitly contain identification metadata; the four `amazon-series`
sidecars do not. Grid metadata (EPSG, spacing, window and dataset paths) is
recorded for each so grid compatibility can be inspected, but missing
track/frame/pass fields are left null rather than filled from assumptions.
Supplementary dates are not silently represented as members of the original
series.

Coordinate: `(-49.275390625, -4.766796875)` (longitude, latitude). CMR
catalogue presence and temporal-bin coverage do not themselves provide
rainfall observations. No daily total, zero substitution, proportional edge
estimate or post-SAR data is used.
