# Real NISAR integration — Mexico first

Status: **blocked on local Earthdata download; no real raster has been read yet**.
The checked-in application intentionally contains no measurements. This is an
integration scaffold, not a completed subsidence result. Other demos are withheld.

## Catalogue evidence (2026-11-14)

`data/mexico-manifest.json` records stable HTTPS source links, CMR concept IDs,
collection IDs, acquisition times, product sizes and footprint polygons. CMR
returned 29 GCOV and 28 GUNW products for track 019, ascending, frame 011, all
PROVISIONAL. GCOV filenames specify 4005 DHDH (frequency A HH/HV); GUNW specifies
4000 SH (frequency A HH). The initial selection is the first two GCOV acquisitions,
2025-10-30 and 2025-11-11, with their GUNW pair. The total download is 15,753.6 MiB.
These are catalogue observations, **not HDF5 metadata validation**. An intersecting
footprint is not a guarantee of valid samples throughout the AOI.

Initial inputs:

- GCOV `G4271586102-ASF`; see manifest for the second acquisition and full producer IDs.
- The exact GUNW concept and producer IDs are also in the manifest.
- AOI W,S,E,N: `-99.25,19.25,-98.9,19.6`.

An unauthenticated range GET of the first HDF5 URL redirected to
`urs.earthdata.nasa.gov` and returned HTML. HEAD alone was insufficient: it returned
a redirect to a signed CloudFront URL. Signed URLs and credentials are not checked in.

## Local authorization and download

Use Python 3.12+ in a local terminal from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements.txt
.\.venv\Scripts\python.exe scripts/download_nisar.py
.\.venv\Scripts\python.exe scripts/prepare_nisar.py
.\.venv\Scripts\python.exe -m http.server 8765
```

Open `http://localhost:8765/#mexico`. Enter Earthdata credentials only into the
local interactive prompt; the password is hidden. `persist=False` does not save
credentials. Do not paste secrets into chat, command arguments, source files or
Git. Raw products and the local environment are ignored. Allow enough disk space
for the approximately 15.4 GiB initial selection. The downloader checks the HDF5
signature and records SHA-256, source IDs and dates in a download receipt.

The preparer rechecks hashes, inventories all HDF5 dataset paths/shapes/dtypes,
then samples frequency A `HHHH` and `HVHV` at 24×24 preview locations. Coordinates
are transformed using the product's EPSG and nearest native cells. Outside-grid,
nonfinite, fill and nonpositive values become `null`; valid gamma0 power becomes
`10*log10(power)` dB. These are sparse samples, not 24×24 area averages and not a
native-resolution map. No claim of anomaly area is made. Mask/RTC quality checks
are still needed before scientific interpretation.

`data/mexico.json` is replaced atomically only after successful processing. It
contains provenance with input hashes, dates, source URLs, processing steps and
limitations. `data/mexico-inspection.json` preserves the HDF5 inventory.

## Deliberately unavailable until validated

- GUNW is downloaded and inventoried, but no displacement is published until its
  actual HDF5 layout, phase sign, radar frequency, masks/coherence, connected
  components, spatial reference and correction layers have been checked. A phase
  value is not automatically a deformation measurement. Do not integrate unrelated
  components or bridge missing pairs; do not label LOS displacement vertical motion.
- ESA WorldCover is not loaded. Class, peer count, median/MAD, z-score, styles,
  patch areas and audio comparisons remain unavailable. No generated peer band.
- HH/HV use acquisition dates; displacement has its own date axis. JSON `null`
  means unavailable, never zero. Plot lines and bands break at missing entries.
- Optical context remains a **2020 cloudless composite**, not date-matched validation.

Next: inspect the downloaded HDF5 files, implement and validate a spatially
referenced GUNW pair result, add actual WorldCover and robust same-class peers,
verify real outputs in the browser, and only then expand to other sites.

## Primary references

- [ASF Earthaccess and authentication](https://nisar-docs.asf.alaska.edu/earthaccess/)
- [ASF GCOV: gamma0, dataset names and posting](https://nisar-docs.asf.alaska.edu/gcov/)
- [ASF GUNW: phase, components and unapplied corrections](https://nisar-docs.asf.alaska.edu/gunw/)

The catalogue normalization helper currently reads local raw CMR snapshots from
`data/catalog/`. The exact queries needed to recreate those snapshots are in the
manifest. Raw snapshots are excluded from Git; stable normalized records are included.
