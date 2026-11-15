# OffBeat: Space Apps project page (copy into the Project tab)

Fields follow the Space Apps project form. Replace the demonstration link with the public YouTube
or Google Drive link once uploaded; the site link below already works without login.

---

## Project name

OffBeat

## Summary

OffBeat lets anyone see and hear where NASA-ISRO NISAR radar finds the ground falling out of step with its neighbours. We processed real NISAR L-band GCOV (HH and HV) and GUNW data for 7 places on 4 continents: Mexico City (29 dates), the Amazon frontier at Itupiranga, Caracas, New Delhi, Tokyo, Nairobi and Sydney, 6,879 measured points in total. Each point is compared with points of the same land cover within 1 km, so city-wide or seasonal shifts cancel out and only local departures stand out. A Windows 98-style app shows them on a map that steps through the dates, plays each point's history as music, and opens with statistically tested findings, such as 114 Mexico City points that drift steadily from their neighbours under a 5% false-discovery rate. Independent data sit beside the radar: dated Sentinel-2 images, Sentinel-1 radar, a GNSS station and deforestation alerts. Every result is a candidate to check, not a confirmed event, and the app says why each might happen.

## Project Demonstration

https://offbeat.chern.su/docs/submission/offbeat-video.mp4 (29.6 s; replace with the YouTube link once uploaded)

## Project

https://offbeat.chern.su

Code (Apache-2.0): https://github.com/ChernStepanov/OffBeat

## Project Details

### What it does

OffBeat turns NISAR radar into a question anyone can ask of a place: which spots are changing differently from everything like them around them? A visitor can:

- open a site from the world map, where NASA GIBS shows where NISAR looked, coloured by date;
- move a date slider or press **Play**: the map steps through every acquisition while the selected point is played as sound. Its neighbours keep the beat, and the point drifts late and out of tune when it leaves them;
- open a point's card: its HH and HV history against the neighbours' band, its land-cover class, interferometric quality and, where available, Sentinel-1 C-band and GNSS curves;
- read **What the data says**: findings with a strength badge, the test behind each one (**How we know**) and labelled hypotheses about physical drivers (**Why might this happen?**);
- follow guided investigations with dated optical evidence, explore the samples on 3D terrain, and watch a 30-second video;
- use it in English or Russian, on desktop or phone.

### How it works

- **Data:** NISAR L2 GCOV (provisional) HH/HV at 1,024 native sample locations per site, missing and rejected values kept as missing. GUNW pairs are used only where they pass coherence, connected-component and ionosphere checks (for example 357 of 1,024 Mexico City points).
- **Neighbour comparison:** for every point and date, the median and 1.4826 x MAD of at least 10 points of the same ESA WorldCover 2021 class within 1 km, excluding the point itself. The departure is a robust z-score. Because neighbours share weather, season and processing, scene-wide shifts cancel: Mexico City darkened by about 5 dB on 22 January 2026 in every class, and the comparison removes it.
- **Statistics (`scripts/findings.py`):** join-count permutation tests for spatial clustering, Kendall trend tests on each point with Benjamini-Hochberg false-discovery control, persistence of departures, a 12-day noise floor, a calibration check of the neighbour band, and a physical plausibility gate on every site.
- **Context:** Sentinel-2 L2A images within +/-15 days of each radar date with cloud masks, NASA OPERA RTC-S1 (Sentinel-1 C-band) at the same Amazon points, NASA OPERA DISP-S1 and Nevada Geodetic Laboratory GNSS station MMX1 in Mexico City, and NASA FIRMS, INPE DETER and UMD GLAD records in the Amazon.
- **App:** a static site with no server or login: Leaflet maps, Three.js terrain, Web Audio sonification, all data as small JSON files with SHA-256 receipts.

### What we found

- **Mexico City is changing in patches.** 114 of 1,003 points drift steadily away from their neighbours over 29 dates (63 trends in HH, 57 in HV) under a 5% false-discovery rate. Off-beat points sit next to each other more often than chance allows (join-count test, p = 0.007). At the other sites, departures scatter like noise, and we say so.
- **The two polarisations see different changes.** Only 5-28% of off-beat points depart in both HH and HV, consistent with HH reacting to buildings, water and soil moisture and HV to vegetation volume. Using both finds more candidates than either alone.
- **L-band separates forest from pasture far better than C-band.** At the same Amazon points, the forest-minus-grassland contrast is 6.1 dB in NISAR HV against 1.2 dB in Sentinel-1 VH.
- **Mexico City is sinking fast.** GNSS station MMX1 drops 28.9 +/- 1.0 cm/year. Anchored at that station, OPERA suggests 15-20 cm/year along the radar line across the sampled area, with 95% of points sinking. This is an estimate with stated assumptions. The raw OPERA value next to the station (-4.8 cm/year, relative line of sight) uses a different reference and geometry, so the two are not directly comparable.
- **The method is honest about noise.** 92-94% of measurements fall inside the neighbour band, close to the 95% it is designed for. A typical point moves 1.2-1.9 dB between 12-day passes, so smaller single-pair changes are not called change.

### Benefits

Radar works through cloud and at night, but its images are hard to read. OffBeat answers a plain question, "is this spot behaving like everything similar around it?", without asking users to understand speckle, polarisation or interferometry first. Students and the public can explore it in minutes. Researchers and planners get reproducible candidates with their tests, sources and granule IDs, and NASA data is free, so anyone can rerun it.

### Intended impact

We want NISAR's 12-day rhythm to become something people can follow for their own city or forest: where land is sinking, where buildings or canopies change, which signals are just weather. The same neighbour comparison works for any site and grows with every new NISAR pass, and results are ready to hand to people who can check them on the ground.

### Creativity

Most radar tools show a change map between two dates. OffBeat asks a different question, "who is out of step with their neighbours?", and lets you hear the answer: each point is a voice against a steady beat. The interface is a working Windows 98 desktop, so a serious data tool feels familiar and playful. The page opens with tested conclusions rather than a blank map.

### Factors we considered

- **Honesty:** results are candidates, not detections. Every finding carries its strength, its test and its limits, and hypotheses about causes are labelled as hypotheses.
- **Real data only:** no interpolation or simulated values; the loader rejects synthetic data. We removed one site (Khimki, near Moscow) after its values failed physical plausibility checks, for example HV above HH and above 0 dB.
- **Validation where we could:** Amazon candidates were checked against dated alerts and fires. None of 575 tree-cover points matched the 65 local alert records in the window, which we report rather than hide. Weather correction and an independent labelled test set are still open.
- **Limits:** NISAR products are provisional and the public record is short (2 dates at four sites). Sites are windows of a few kilometres sampled at 1,024 points, not wall-to-wall maps. Thresholds were never relaxed to make a picture.
- **Reliability and openness:** the measured data ship with the site, so the demo needs no NASA login or server (basemaps and imagery still load from the internet); asset files are content-hashed against stale caches. 103 Python and 20 JavaScript tests cover data, statistics, maps, search and the tour. Licence: Apache-2.0.

### Tools, languages, hardware and software

- **Frontend:** HTML, CSS and JavaScript without a framework; Leaflet 1.9, MapLibre GL, Three.js r160, Web Audio API; W95FA and Ark Pixel fonts (OFL).
- **Data and analysis:** Python (earthaccess, h5py, NumPy, SciPy, pyproj, rasterio, shapely, Pillow, requests), GDAL.
- **Testing and hosting:** pytest, Node.js test scripts, GitHub Pages with a custom domain.
- **Video:** recorded from the running app with headless Chromium (Puppeteer) and ffmpeg; music synthesised in Python.
- **Hardware:** team laptops.

### Use of AI

OffBeat is the work of seven team members: the idea, data choices, design, analysis direction, reviews and every decision are theirs. Team members used OpenAI Codex and Anthropic Claude (Claude Code) as coding assistants on their own tasks: implementation, tests, statistics code, documentation drafts and the scripts that render the video. No image, video or music generation model was used. No measurement or statistic was produced by AI. People checked AI output and corrected an overstated claim after their own audit. Details: https://github.com/ChernStepanov/OffBeat/blob/master/docs/ai-use.md

## NASA Data

- [NISAR L2 GCOV and GUNW, NASA-ISRO via ASF DAAC](https://nisar-docs.asf.alaska.edu/)
- [NASA Earthdata Search](https://search.earthdata.nasa.gov/search)
- [ASF Data Search Vertex](https://search.asf.alaska.edu/)
- [NASA OPERA RTC-S1 and DISP-S1, via ASF DAAC](https://www.jpl.nasa.gov/go/opera/)
- [NASA GIBS, NISAR browse coverage](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api)
- [NASA FIRMS active fires](https://firms.modaps.eosdis.nasa.gov/)

## Space Agency Partner & Other Data

- [ESA WorldCover 2021 (CC BY 4.0)](https://esa-worldcover.org/)
- [Copernicus Sentinel-2 L2A via Earth Search (Element 84)](https://earth-search.aws.element84.com/v1)
- [Copernicus ERA5 reanalysis](https://cds.climate.copernicus.eu/)
- [Nevada Geodetic Laboratory GNSS, station MMX1](https://geodesy.unr.edu/NGLStationPages/stations/MMX1.sta)
- [INPE DETER deforestation alerts](http://terrabrasilis.dpi.inpe.br/)
- [UMD GLAD alerts](https://glad.umd.edu/)
- [Mapzen Terrain Tiles on AWS](https://registry.opendata.aws/terrain-tiles/)
- [Esri World Imagery and reference layers](https://www.esri.com/)
- [Open-Meteo / GeoNames and Photon (OpenStreetMap) geocoding](https://open-meteo.com/)
