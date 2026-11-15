# Non-urban change research leads

Research collected 2026-11-15. These are independently documented events and leads for future analysis, not events detected by OffBeat. Satellite image pairs cited below are not NISAR unless explicitly stated. Image footprints, licensing, coordinates, NISAR coverage, matching tracks, quality masks and detector output still require verification before adding any event marker or claiming a detection. No new measurements have been generated for these leads.

## Cottonwood fire, Utah, United States

- **Event:** fire in a rural, mountainous area with forest and shrubland, June 2026.
- **Imagery:** NASA presents HLS L30 natural-colour and NBR before/after images acquired 2026-06-05 and 2026-06-29, together with downloadable versions. NBR colours are thematic, not natural colour.
- **Independent event context:** NOAA and the National Interagency Fire Center document the incident.
- **Sources:** [NASA image comparison and explanation](https://science.nasa.gov/mission/landsat/hls-vegetation-indices/), [NOAA incident context](https://www.nesdis.noaa.gov/news/noaa-satellites-monitor-western-wildfire-outbreak), [NIFC report, 2026-06-28](https://www.nifc.gov/sites/default/files/NICC/1-Incident%20Information/IMSR/2026/June/IMSR_CY26_06282026.pdf).
- **Next:** identify an area of interest using georeferenced scene data and a fire perimeter, then check NISAR GCOV before and after the fire and select comparable observations. Do not assign geographic coordinates to NASA's rendered JPEGs without source georeferencing.

## Morrill fire, Nebraska, United States

- **Event:** grassland fire began 2026-03-12 in Morrill County and spread across rural prairie.
- **Imagery:** NASA's NOAA-21 VIIRS false-colour comparison is dated 2026-02-28 and 2026-03-29; the post-event image also includes areas affected by other fires. It is a regional context product, not a field-scale NISAR image.
- **Source:** [NASA Earth Observatory](https://science.nasa.gov/earth/earth-observatory/fires-tear-through-nebraska-grasslands/).
- **Next:** obtain a dated perimeter and higher-resolution imagery; search for compatible pre/post NISAR acquisitions.

## Gandak/Narayani floodplain, Nepal and India

- **Event:** late September 2026 floods affected farmland and settlements along the Gandak following heavy rain.
- **Imagery:** NASA compares MODIS false-colour images from 2026-09-20 and 2026-09-29; blue indicates water in this composition.
- **Source:** [NASA Earth Observatory](https://science.nasa.gov/earth/earth-observatory/rains-swamp-the-gandak-river/).
- **Next:** choose a non-urban floodplain with a verified georeferenced flood extent and check NISAR coverage; account for seasonal inundation, clouds, and acquisition timing.

## Limpopo and Incomati floodplains, Mozambique

- **Event:** January 2026 flooding affected agricultural areas along both rivers.
- **Imagery:** NASA compares MODIS false-colour imagery from 2025-12-17 and 2026-01-25.
- **Source:** [NASA Earth Observatory](https://science.nasa.gov/earth/earth-observatory/floods-inundate-southern-mozambique/).
- **Next:** select a rural area from georeferenced flood mapping, inspect seasonal controls, and find compatible NISAR acquisitions. NASA's regional images alone do not establish change at an individual NISAR cell.

## Northern Venezuela earthquake sequence

- **Event:** magnitude 7.2 and 7.5 earthquakes on 2026-06-24; USGS reports associated landslide hazards west of Caracas.
- **Imagery and independent deformation:** USGS released preliminary Sentinel-1 interferograms and Sentinel-2 displacement fields; the optical comparison uses images from 2026-05-05 to 2026-05-09 and 2026-06-24 to 2026-06-29. USGS states its release is provisional and has not been ground checked.
- **Sources:** [USGS earthquake-triggered landslides](https://www.usgs.gov/programs/landslide-hazards/science/2026-venezuela-sequence-earthquake-triggered-landslide-hazards), [USGS remote deformation data](https://www.usgs.gov/data/remote-observations-surface-deformation-m72-and-m75-2026-venezuela-earthquakes), [NASA NISAR line-of-sight displacement layer](https://gis.earthdata.nasa.gov/portal/home/item.html?id=1d972eab2bbd4098af71c0c61db083fc).
- **Existing OffBeat limitation:** the prepared Venezuela candidate pair is 2025-11-09 to 2025-11-21, before these earthquakes, and cannot be used as their before/after comparison.
- **Next:** obtain a verified NISAR GUNW pair straddling the event, inspect coverage, coherence, connected components and reference stability, then compare its line-of-sight displacement to an appropriately aligned independent product. Do not equate a single LOS measurement with plate velocity or 3D motion.

## Existing forest clearing example

The prepared `amazon-visible-clearing` case has a reviewed optical clearing. Its dossier explicitly says radar history is insufficient to validate detection; it is a worked example, not an independent detector benchmark. See `data/cases/amazon-v1.json` and its linked sources.
