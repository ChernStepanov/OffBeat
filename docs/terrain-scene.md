# Real 3D terrain and window controls

The former Canvas signal-height cloud has been replaced with WebGL terrain.
Geographic elevation comes from a DEM; NISAR backscatter changes dot colour.
The sample's height therefore stays fixed when its HH/HV signal changes.

## Continuous global terrain

`js/terrain-tiles.js` addresses the full Web Mercator world, wraps longitude at
the antimeridian, and streams zoom-0–14 Terrarium DEM tiles. Display navigation
supports zoom 0–19 and latitude ±85.05112878°. Zooming further does not create
additional source resolution. The camera is independent of every NISAR bbox.

The renderer computes tile coverage from the camera frustum and adjusts LOD to
stay within 64 visible tiles. Tile meshes have 64 or 128 subdivisions depending
on the visible tile budget. Surface coordinates and NISAR overlays use the same
Mercator frame, including the latitude-dependent conversion of elevation metres.
Surface and dense terrain point cloud share real DEM elevations. There are no
extruded study-area walls or fixed rectangular terrain extents.

The loader allows five concurrent requests and a cache of at most 96 decoded
tiles. It cancels obsolete requests, ignores obsolete views, and handles a return
to a just-aborted viewport. Nearby lower-LOD parents and the bundled measured
global tile fill coverage while detail loads. Download failures remain explicit
and a Retry button retries them; missing heights are not replaced with fictional
measurements. Mesh generation is spread across frames rather than blocking the UI.

The bundled `data/terrain/world-0.png` is the provider's real zoom-0 ETOPO1 tile.
Its URL, retrieval timestamp, source and SHA-256 are in `world-0.json`. It provides
coarse global coverage without provider access; finer detail requires internet.
Source attributions are linked from the viewport and below.

World, Study area and Map centre navigation, direct coordinate/place search,
and clickable prepared-area labels allow browsing outside measured coverage.
At low zoom the dense radar dots are replaced by study-area labels. The HUD
explicitly reports when there is no prepared NISAR series at the map centre;
the selected sample card still belongs to its named study series. New or expanded
radar bboxes do not require a new fixed terrain rectangle.

## Optional prepared elevation context

| Site | Nodes | Elevation range (m) |
|---|---:|---:|
| Itupiranga | 257 × 257 | 69.54–188.79 |
| Mexico City | 257 × 257 | 2183.04–2296.44 |
| Caracas | 257 × 257 | 839.01–2202.84 |

Each context bbox is three times the width and height of the original NISAR AOI.
The historical DEM does not establish a present-day terrain surface or a current
NISAR height product. Source resolution and vertical datum depend on the upstream
tile blend. Output node count is a rendering/sample count, not independent
ground observations or demonstrated spatial accuracy.

`python3 scripts/prepare_terrain.py` downloads zoom-13 Terrarium RGB tiles from
Mapzen's AWS Open Data archive. The standard-library PNG decoder verifies chunk
CRCs and decodes the PNG row filters; elevation is `R*256 + G + B/256 - 32768`.
The script bilinearly samples at source pixel centres in Web Mercator, then saves
a north-to-south regular WGS84 grid. Cached original PNGs are excluded from Git.
Prepared JSON files preserve source URLs, byte counts, SHA-256 hashes, numeric
array checksum, bbox, sampling method, attribution and limitations.

These optional contexts preserve the original extraction receipts and support
height fallback before streamed DEM data is available. They do not bound the map.
NISAR lat/lon and HH/HV arrays are unchanged. Each dot's elevation is sampled from the DEM;
a small constant clearance avoids z-fighting. There are still only 1,024 sparse
NISAR locations per site. No interpolated radar points, classifications or areas
are generated. Height exaggeration defaults to 4x and can be set to 1x.

The surface uses elevation colours, illumination and optional contour lines.
A separate depth-tested DEM point cloud and NISAR overlay can be shown together
or separately. Picking selects the nearest visible dot in screen space and
checks the terrain ray intersection to reject a sample hidden behind a ridge.
The static CRT effect is optional and reduced for reduced-motion preference.

## Windows and validation

The shared window manager handles large floating windows, maximization to the
browser content area and native browser fullscreen. It moves the existing panel
and restores it at a placeholder; it does not re-create maps, charts or inputs.
Resize events update Leaflet and the WebGL projection. Escape restores a promoted
panel before it exits the scene; open selector popups consume their first Escape.

`node scripts/test_point_cloud.mjs` verifies all three numeric DEM receipts,
finite grids, source references, coordinate registration on every prepared date
and channel, interpolation on a known plane, physical elevation under vertical
exaggeration, missing values and preservation of original NISAR data.

`node scripts/test_terrain_tiles.mjs` verifies global coordinate roundtrips,
antimeridian addressing, polar bounds, visible tile budgets, Terrarium decoding,
the bundled PNG checksum, download/cache bounds, aborted-request races and retry.

Chrome browser checks cover terrain rendering without shader/runtime errors,
precise picking, HH/HV and acquisition controls, all study areas, orbit/pan/zoom,
render modes, contour/CRT toggles, independent map enlargement, 3D maximization,
native fullscreen and restoration, input/selection retention, Russian controls,
and 390 px layouts. Physical mobile devices and other browsers were not tested.

Streaming checks additionally cover a region outside all prepared data (the
Himalayas), movement beyond the old rectangles, the date line, rapid region
changes, bounded caches, stale geocoder results, global overview, retained
fullscreen/series controls and explicit provider failure with the bundled
measured world fallback. Existing NISAR data and numerical receipts are unchanged.

## Primary sources

- [Mapzen Terrain Tiles on AWS](https://registry.opendata.aws/terrain-tiles/)
- [Terrarium format and source-pixel units](https://github.com/tilezen/joerd/blob/master/docs/formats.md)
- [Upstream attribution and terms](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)
- [Three.js](https://threejs.org/), vendored r160.1 with MIT notice

Visual direction uses muted olive, bone and amber, faceted shading, grain and
scanlines inspired by the field-terminal atmosphere of
[Buckshot Roulette](https://mikeklubnika.itch.io/buckshot-roulette).
No game assets are copied; the existing Windows-style window furniture is retained.
