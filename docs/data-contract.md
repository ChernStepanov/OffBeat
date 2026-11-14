# Data contract: pipeline → front end

The front end reads one JSON file per demo site. Today `js/mock.js` builds these objects in the browser;
the NISAR pipeline should write the same shape to `data/<site>.json`, and `app.js` switches to `fetch`.

```jsonc
{
  "id": "mexico",                       // url hash, lowercase
  "name": "Mexico City",
  "region": "Subsidence of the lake-bed clays",   // one line under the name
  "center": [19.40, -99.06],            // lat, lon
  "zoom": 11,
  "source": "NISAR L2 GCOV + GUNW",     // "synthetic" for mock data; shown in the status bar
  "event": { "index": 16, "label": "Main shock" },  // or null; index into dates
  "dates": ["2025-11-07", "..."],       // acquisition dates, ISO, ascending, shared by every pixel

  "pixels": [{
    "id": "MEX-0281",
    "lat": 19.5095, "lon": -99.0965,
    "cover": 50,                        // ESA WorldCover v200 class code
    "peers": 43,                        // how many same-class pixels in the neighbourhood
    "z": -4.1,                          // signed z-score vs. peers at the last date, in the style's channel
    "style": "drift",                   // "drop" | "flood" | "drift" | "step" | null (in step)
    "since": "2025-12-01",              // first date the pixel left the peer band, or null

    "hh": [-3.1, "..."],                // dB, gamma0, one value per date (null where missing)
    "hv": [-11.2, "..."],
    "peer": {
      "hh_med": [], "hh_sd": [],        // peer median and std per date, dB
      "hv_med": [], "hv_sd": []
    },
    "disp": [0, -0.4, "..."],           // cm, line of sight, relative to dates[0]; null if no GUNW
    "peer_disp": [0, -0.15, "..."]      // peer median displacement, cm; null if no GUNW
  }]
}
```

## Rules the front end relies on

- Every array has `dates.length` entries.
- `z` is computed on the channel the style lives in: HV for `drop`, HH for `flood`, displacement for
  `drift` and `step`. Pixels with no style still carry `z` (the heat map shows them at low thresholds).
- Peers: same WorldCover class, inside a fixed radius (start with 3 km), excluding the pixel itself.
  Use median and a robust spread (1.4826 × MAD) rather than mean and std.
- Ship only what the map needs: all pixels above |z| 1.5 plus a thin random sample of the rest.
  A site file should stay under 5 MB.
