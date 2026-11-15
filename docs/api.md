# OffBeat HTTP API v1

JSON API over the same prepared data as the interface. It requires Python 3
and no additional dependencies. Run from the project root:

```sh
python3 -m api.server --host 127.0.0.1 --port 8766
curl http://127.0.0.1:8766/api/v1/sites
```

This is a separate service; the existing static UI still runs independently. For
remote access, deploy behind a reverse proxy with TLS, authentication, rate limits
and appropriate network access controls. Binding to `0.0.0.0` exposes an
**unauthenticated** read-only service; do not do so on an untrusted network without
those protections. No browser CORS access is enabled by default. This is HTTP API,
not MCP.

## Shared candidate reviews

The public site uses the separate persistent D1-backed review service at
`https://offbeat-shared-reviews.glazedbream.chatgpt.site/api/v1/reviews`.
Its `/health` endpoint checks the database. Browser access is restricted by CORS
to `https://offbeat.chern.su`. The Worker validates catalogue fingerprints,
candidate IDs and image coverage, hashes anonymous browser tokens, limits write
requests per anonymized network/hour bucket, and exposes aggregate verdict counts.
Comments and browser tokens are not exposed through the read API. Clearing a
review requires its original browser token. This is anonymous community feedback,
not an independently validated label set. The Python service below remains a
local development alternative. Worker source is in the separate Sites source
repository for project `appgprj_6af9cf16c13c8191add5ba9ffc84a1d1`.

The optional `GET /api/v1/reviews?site=…&marker=…&dataset=…` returns aggregate
counts. `POST /api/v1/reviews` accepts a candidate, dataset fingerprint, random
browser token, verdict and image basis. A token may update or remove its own
review. Comments are browser-local and are not sent. Counts are unverified and
do not establish detector accuracy. Browser tokens do not prevent deliberate
multiple votes; production needs rate limiting, moderation and backups.

Storage is disabled until `OFFBEAT_REVIEWS_DB` is set to a writable SQLite file
outside any publicly served directory. Serve the API under the same HTTPS origin
as the site using a reverse proxy. GitHub Pages alone cannot run the API. The
production endpoint must be deployed separately; adding these files does not
make reviews public. For local testing only, `python -m api.dev_server` serves
the UI and a SQLite database on `127.0.0.1:8873`.

## Endpoints

All paths below start with `/api/v1`. JSON errors have the shape
`{"error":{"status":404,"message":"..."}}`.

| GET | Description |
| --- | --- |
| `/` | API entry point |
| `/health` | Basic prepared dataset readiness; returns 503 if any site cannot load |
| `/help` | Endpoint discovery |
| `/sites` | Available sites and per-site loading errors |
| `/sites/{site}` | Site metadata, grid, dates, status and limitations |
| `/sites/{site}/provenance` | Full measurement provenance |
| `/sites/{site}/acquisitions` | GCOV and displacement dates and per-date HV availability |
| `/sites/{site}/pixels` | Paginated sample summaries |
| `/sites/{site}/pixels/{index}` | Full sample and peer series, quality fields and corresponding dates |
| `/sites/{site}/signals` | Classified samples with z scores, ordered by descending absolute z |
| `/sites/{site}/patches` | Classified samples or connected patches, depending on dataset type |
| `/sites/amazon/context/fires` | NASA FIRMS fire context |
| `/sites/amazon/context/alerts` | Alert GeoJSON |
| `/sites/amazon/context/ranking` | Experimental sampled-point ranking data, metadata and limitations |

Sites are `mexico`, `amazon`, `venezuela`, `delhi`, `tokyo`, `nairobi`, `sydney`. Index is zero-based row-major,
from northwest; `row` and `col` are also zero-based. Pixel detail contains full
HH/HV, peer and displacement arrays, with the date axes supplied separately.

`pixels`, `signals`, and `patches` support `limit` (1–1000, default 100) and
`offset` (default 0); responses include `total`, `limit`, `offset`, `items`.
`pixels` and `signals` support `style=drop|flood|drift|step`, `min_abs_z` (nonnegative),
and `date=YYYY-MM-DD` (must be an actual GCOV acquisition). The date adds HH and
HV for that acquisition, including nulls; it does not change classification.
`patches` accepts `min_abs_z` (default 2). For sparse samples, it returns individual
classified samples ordered by absolute z; they do not represent area. For dense grids,
it uses four-neighbor connectivity, at least three cells, and size × mean absolute z ordering.

```sh
curl 'http://127.0.0.1:8766/api/v1/sites/mexico/pixels?limit=2&date=2025-10-30'
curl 'http://127.0.0.1:8766/api/v1/sites/mexico/pixels/0'
curl 'http://127.0.0.1:8766/api/v1/sites/amazon/signals?min_abs_z=2'
curl 'http://127.0.0.1:8766/api/v1/sites/amazon/patches?min_abs_z=2'
```

These are sparse preview samples, not native raster pixels or area estimates.
Null means unavailable, not zero or normal. Empty signals/patches do not imply
nothing happened: datasets without validated anomaly classification cannot produce
classified signals. The optional Amazon ranking is an experiment, not a probability
or proof of cause. See [data contract](data-contract.md) and site provenance for
units, reference frames and scientific limitations. Context and ranking endpoints
return their source documents unmodified. The API does not control another user's
browser, play audio, or proxy place-name search.

Test with `python3 -m unittest api.test_server`.


## Shared investigation queue

`GET /api/v1/review-queue` returns the current source-versioned candidates and
published-reference comparisons, aggregate verdict counts, and `pending`,
`visible` or `rejected` status. No voter tokens, voter hashes or comments are
returned. A negative `no_visible_change` vote excludes a card from the shared
rotation and the reviewed map; it takes priority over conflicting positive votes.
A voter can undo their own decision with `clear`. `uncertain` keeps a card pending
for other browsers; that browser skips cards it has already reviewed or passed.
This is browser-token identity, not a registered-user account or consensus test.
Open pages refresh shared status every 30 seconds and before choosing a new card.

Positive radar reviews create green points on the map, labelled as user reviews,
not verified events. Published reference JPEGs have no verified detection
coordinates, so they do not create fabricated map points. Their votes stay separate
from detector evaluation. The public worker source is versioned in Sites project
`appgprj_6af9cf16c13c8191add5ba9ffc84a1d1`; `scripts/update-catalog.mjs` in that
source exports identifiers, input-image fingerprints and real radar coordinates
from an OffBeat checkout. Rebuild it whenever the image set changes.
