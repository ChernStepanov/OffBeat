# Real NISAR integration — Mexico first

Status: **real GCOV and GUNW subsets are connected and browser-verified**.
The Mexico GCOV series contains all 29 PROVISIONAL catalogue acquisitions on
track 019A/011 from 2025-10-30 to 2026-10-13. Re-run `scripts/extend_mexico.py` to verify it; each
additional acquisition is an independently verified, hashed HDF5 subset. The
GUNW panel retains its separate original pair dates and is not extrapolated.
The first case covers about 2.6 × 2.8 km in Mexico City with 1024 preview locations,
two acquisitions (2025-10-30 and 2025-11-11), and their GUNW pair. All 1024 locations
have HH/HV on both dates; 357 GUNW locations pass the selected quality filters.
This is an exploratory pair result, not a validated subsidence rate.

## Real-only demo replacement (2026-11-14)

All large binary exports inherited from the former pipeline were actually marked
`source: synthetic`. They and the browser/Python synthetic generators have been
removed. The browser now loads only provenance-backed measured site JSON files
and rejects a synthetic source. Offline scientific test fixtures remain in tests.

| Case | Acquisitions | Valid HH/HV per date | Accepted GUNW samples |
|---|---|---|---|
| Mexico City | 29 dates, 2025-10-30 to 2026-10-13 | 1024 each date | 357 (one pair) |
| Itupiranga, Pará | 6 dates, 2026-07-18 to 2026-09-28 | 1024 each date | 0 |
| Caracas | 6 dates, 2025-11-09 to 2026-01-08 | 1024 each date | 0 |

The last two cases have real GCOV and real downloaded GUNW subsets, but none of
their GUNW samples pass the unchanged quality filters. Displacement stays null;
there is no synthetic curve and no reference zero for a rejected sample. The
24-day Amazon pair spans an acquisition gap. The earlier candidate (2026-06-24 /
2026-07-06) had zero power throughout the second GCOV subset and was rejected.
Its numeric subsets/receipts are retained as evidence, not loaded by the UI.
The selected Amazon track is 146A/175; 045A does not cover this smaller AOI.
Caracas uses 162A/007; its dates do not support an earthquake attribution.

`data/<site>-manifest.json`, `data/<site>.json` and `data/subsets/` preserve the
exact selection, source IDs, dates, native windows, quality flags and SHA-256.
Recreate the additional cases with `python scripts/build_real_demos.py`; the
default Amazon pair index is 2, Venezuela 0. `--site` and `--pair-index` allow
explicit catalogue selection without changing quality thresholds.

`scripts/extend_sites.py` adds up to four later PROVISIONAL GCOV dates per site
per invocation, with CMR query, granule identifiers, native windows and SHA-256
recorded in each receipt. The original GUNW date axis remains independent.
For Caracas, a separate GUNW subset for 2026-06-13 to 2026-06-25 is in
`data/subsets/venezuela-gunw/`. None of its 1024 samples meet the unchanged quality
filters: 81 meet coherence >=0.7, but none meet ionosphere uncertainty <=1 rad.
No displacement or stable reference has been estimated from this pair.

## Catalogue evidence (2026-11-14)

`data/mexico-manifest.json` records stable HTTPS source links, CMR concept IDs,
collection IDs, acquisition times, product sizes and footprint polygons. CMR
returned 29 GCOV and 28 GUNW products for track 019, ascending, frame 011, all
PROVISIONAL. GCOV filenames specify 4005 DHDH (frequency A HH/HV); GUNW specifies
4000 SH (frequency A HH). The initial selection is the first two GCOV acquisitions,
2025-10-30 and 2025-11-11, with their GUNW pair. The total download is 15,753.6 MiB.
The selected HDF5 products were read through authenticated HTTP Range requests.
Their metadata confirms track 19 ascending, frame 11, version 1.0.11, frequency A,
EPSG:32614, GCOV 10 m posting, GUNW 80 m posting, and matching pair dates.
`data/mexico-inspection.json` preserves the dataset inventory and attributes.

Initial inputs:

- GCOV `G4271586102-ASF`; see manifest for the second acquisition and full producer IDs.
- The exact GUNW concept and producer IDs are also in the manifest.
- Catalogue AOI W,S,E,N: `-99.25,19.25,-98.9,19.6`.
- Extracted case AOI: `-99.09,19.415,-99.065,19.44`.

An unauthenticated range GET of the first HDF5 URL redirected to
`urs.earthdata.nasa.gov` and returned HTML. HEAD alone was insufficient: it returned
a redirect to a signed CloudFront URL. Signed URLs and credentials are not checked in.

## Local authorization and download

Use Python 3.12+ in a local terminal from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements.txt
.\.venv\Scripts\python.exe scripts/subset_nisar.py
.\.venv\Scripts\python.exe -m http.server 8765
```

Open `http://localhost:8765/#mexico`. Enter Earthdata credentials only into the
local interactive prompt; the password is hidden. `persist=False` does not save
credentials. Do not paste secrets into chat, command arguments, source files or
Git. Raw full products and the local environment are ignored. The recommended
script downloads only needed HDF5 windows; it does not require 15.4 GiB for the
complete products. `data/subsets/` contains the extracted numeric arrays as NPZ
and JSON receipts recording source IDs, native window bounds, CRS, dates and SHA-256.
Those files are included so the shipped case works without an Earthdata login.
`download_nisar.py` remains an optional full-product downloader. `prepare_nisar.py`
is an older GCOV-only preparer and will replace the case with a partial result;
use `subset_nisar.py` for the connected GCOV/GUNW case.

The subset pipeline rechecks saved hashes and samples frequency A `HHHH` and
`HVHV` at 32×32 preview locations. Coordinates
are transformed using the product's EPSG and nearest native cells. Outside-grid,
nonfinite, fill and nonpositive values become `null`; valid gamma0 power becomes
`10*log10(power)` dB. GCOV mask 0 and 255 are rejected. These are sparse samples,
not area averages and not a native-resolution map. No anomaly area is reported.

`data/mexico.json` is replaced atomically only after successful processing. It
contains provenance with input hashes, dates, source URLs, processing steps and
limitations. `data/mexico-inspection.json` preserves the HDF5 inventory.

## GUNW processing and limitations

- Read `frequencyA/unwrappedInterferogram/HH`: phase, coherence, components,
  ionosphere screen and uncertainty, plus the parent mask. Require coherence >=0.7,
  nonwater valid subswaths, no RSLC anomaly flags, finite ionosphere screen and
  screen uncertainty <=1 rad. Keep only the connected component of the reference.
- Bit 24 flags product-interpolated ionosphere corrections. Initially rejecting
  that flag removed every high-coherence sample here: unflagged samples had maximum
  coherence 0.596. The chosen exploratory result retains the official product's
  interpolated screen, explicitly marks it in each pixel and shows its uncertainty.
  These correction values are not independent measurements.
- Subtract the ionosphere phase screen, then the spatial reference phase, and
  multiply by `-c/(4*pi*f)*100`, using measured `f=1239000000 Hz`. ISCE3 forms
  reference × conjugate(secondary); positive output is toward the sensor. Both
  ellipsoidal and topographic flattening flags are True. Troposphere and tides
  are not removed. Remaining apparent LOS change may contain nondeformation signal.
- The highest-coherence accepted sample is the explicit spatial reference;
  coordinates and component are in provenance. It is not proven stable. First
  epoch zero is a reference definition, not an independently measured displacement.
- ESA WorldCover 2021 v200 tile N18W102 supplies historical classes. Peers are
  actual sampled same-class locations within 1 km, excluding the selected point;
  require 10 valid samples per channel/date. Band is median ±2×1.4826 MAD. Peer
  counts vary with date/channel and are stored per pixel. No fixed generated spread.
- z-score, change styles and patch areas remain unavailable. Two acquisitions
  cannot establish a slow trend. The map instead shows latest measured HV gamma0,
  blue -25 to red 0 dB. Playback compares only measured HH/HV and measured peers.
- HH/HV use acquisition dates; displacement has its own date axis. JSON `null`
  means unavailable, never zero. Plot lines and bands break at missing entries.
- Both panes use the same colour Esri World Imagery basemap (with NISAR overlaid
  on the left), with matching zoom limits, optional place labels, study-area outlines
  and metric scales. Dates vary by location; imagery is not date-matched validation.
  The measured NISAR grid is unchanged; sharper context does not increase its resolution.

Next: validate reference stability and atmospheric corrections, extend the temporal
network before interpreting subsidence, then expand to other sites. The browser
check confirmed the real map layer, measured peer counts, GUNW quality flags,
available plot canvases, enabled audio control and explicit unclassified state.

## Primary references

- [ASF Earthaccess and authentication](https://nisar-docs.asf.alaska.edu/earthaccess/)
- [ASF GCOV: gamma0, dataset names and posting](https://nisar-docs.asf.alaska.edu/gcov/)
- [ASF GUNW: phase, components and unapplied corrections](https://nisar-docs.asf.alaska.edu/gunw/)
- [ISCE3 cross-multiplication convention](https://github.com/isce-framework/isce3/blob/develop/cxx/isce3/signal/Crossmul.cpp)
- [ESA WorldCover sources and attribution](https://esa-worldcover.org/en/data-access)

© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021)
processed by ESA WorldCover consortium.

The catalogue normalization helper currently reads local raw CMR snapshots from
`data/catalog/`. The exact queries needed to recreate those snapshots are in the
manifest. Raw snapshots are excluded from Git; stable normalized records are included.
