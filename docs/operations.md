# Operations and data update foundation

The public UI is static. The Python API is a separate, optional read-only service;
it does not currently power the UI. Prepared JSON is still the source of truth.

## Inventory and checks

Run `python -m scripts.operations inventory > inventory.json` to build an offline
index of the eight prepared sites, their bounding boxes, dates, sample counts and
SHA-256 hashes. It exits nonzero if a dataset is missing or violates basic checks.
Bounding boxes describe sparse samples, not complete raster coverage. This index
is a portable inventory, not a spatial database or a replacement for provenance.

Run `python -m scripts.operations probe https://offbeat.chern.su/` from a machine
with network access; add `https://your-api.example/api/v1/health` only if an API
has actually been deployed. The command exits nonzero for a failed check. Schedule
it in an external monitoring system and configure notifications there. The included
GitHub Actions workflow checks the public site every six hours and can be run
manually; configure GitHub Actions failure notifications for the repository. It
does not collect browser errors, monitor map providers or guarantee immediate
alerts. Scheduled Actions can be delayed or disabled by GitHub. Avoid URLs
containing tokens, personal data or sensitive query parameters: URLs are printed.

## Discovering updates

`python -m scripts.discover_updates amazon > candidates.json` queries the public
NASA CMR catalogue after the most recent prepared date. Output includes the query,
time, IDs and dates; it flags truncation. Catalogue intersection does not prove
valid coverage or compatible track, polarization or quality. This discovery is
read-only: it does not download, validate, process or publish any measurement.
Existing extraction scripts are site-specific; assess candidates and masks, run
the relevant extraction and scientific checks in an isolated checkout, verify
provenance and hashes, then publish only after review. Preserve the previous
dataset and deployment for rollback. Earthdata credentials must remain local and
never appear in reports, source control, command arguments or logs.

## API exposure

`GET /api/v1/health` returns 200 only if all prepared site files pass basic API
loading checks; otherwise it returns 503. It does not test external data providers
or scientific validity. The built-in server is intended for local use. Before any
public deployment, put it behind an HTTPS reverse proxy with rate limits, request
size/time limits, access controls appropriate to the use case, and monitoring.
Do not expose it directly on an untrusted network. See `docs/api.md`.
