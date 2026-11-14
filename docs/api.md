# OffBeat HTTP API v1

Read-only JSON API over the same prepared data as the interface. It requires Python 3
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

## Endpoints

All paths below start with `/api/v1`. JSON errors have the shape
`{"error":{"status":404,"message":"..."}}`.

| GET | Description |
| --- | --- |
| `/` | API entry point |
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

Sites are `mexico`, `amazon`, `venezuela`, `delhi`, `tokyo`, `khimki`, `nairobi`, `sydney`. Index is zero-based row-major,
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
