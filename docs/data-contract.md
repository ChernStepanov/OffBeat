# Runtime data contract (schema version 2)

`js/data.js` fetches `data/mexico.json`. Network errors and invalid input stop
loading with an explicit message; the legacy mock generator is never loaded.

The JSON has site `id`, `name`, `region`, `center`, `zoom`, `source`, `status`,
`message`, `event`, `dates`, `displacement_dates`, `grid`, `pixels`, `provenance`.
The grid contains `n` and geographic `bbox: {w,s,e,n}`. `pixels` has exactly `n*n`
entries, row-major from northwest; locations represent sparse preview samples,
not native raster pixels or area averages. `cellM` is null for this sparse grid.

Each pixel has `id`, `lat`, `lon`, `cover`, `peers`, `z`, `style`, `since`, `hh`,
`hv`, `peer`, `disp`, `peer_disp`. `peer` contains `hh_med`, `hh_sd`, `hv_med`,
`hv_sd`. Each backscatter and peer array has exactly `dates.length` entries.
HH/HV are gamma0 power converted to dB. Missing entries are JSON null.
With no WorldCover, `cover`, `peers`, `z`, `style`, `since` are null and peer
arrays contain only nulls. Do not infer land cover or a normal/in-step result.

`disp` contains [0, apparent_relative_LOS_cm] for the accepted GUNW pair and is
null for rejected samples. `peer_disp` is null: no deformation peer band is estimated.
`coherence`, `component`, `ionosphere_interpolated`, `ionosphere_sd_rad` retain
per-sample quality information. First epoch zero is a reference definition.
Displacement arrays use `displacement_dates`, independently of GCOV dates;
each result must name its pair/reference, units, sign convention, connected
component, masks, corrections and reference location in provenance. A missing
measurement is never represented as zero or carried across a gap. An optional
`peer_disp_sd` must contain measured robust spread; the plot supplies no fixed band.

`provenance` records input producer and CMR IDs, dates, URLs, SHA-256 of saved subsets,
processing steps, creation time and limitations. The checked-in file contains real
measurements and points to the public CMR manifest and reproducible numeric subsets.

The earlier pipeline design described irregular pixel samples, but the running
map actually required square arrays plus a `series(x,y)` function. The loader
adapts this square JSON to those arrays. Future native geospatial rasters need
their own CRS/geotransform-aware rendering rather than assuming a geographic grid.
