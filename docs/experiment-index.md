# Experiment index

This index groups the research materials in this branch. These are exploratory
analyses, not evidence of validated event detection or a measured detection
accuracy. See each protocol and report for methods, provenance and limitations.

| Work | Results and protocol | Data | Code and presentation |
|---|---|---|---|
| Amazon cross-sensor matching and spatial robustness | [Summary](research-summary.md), [protocol](research-protocol.md), [cross-sensor](research-cross-sensor.md), [spatial robustness](research-spatial-robustness.md) | `data/research/` | `scripts/research_*.py`, [research page](../research.html) |
| Map candidates and independent context | [Summary](investigation-summary.md), [protocol](investigation-protocol.md), [map candidates](investigation-map-candidates.md), [external maps](investigation-external-maps.md) | `data/investigation/` | `scripts/investigate_*.py`, [candidates page](../candidates.html) |
| Regional events, weather and hydrology | [Regional events](investigation-regional-events.md), [weather](investigation-weather.md), [hydrology](investigation-hydrology.md) | `data/investigation/regional/`, `regional-raw/`, `weather-raw/`, `hydrology-raw/` | `scripts/investigate_*.py`, `scripts/*regional*.py` |
| Amazon ranking benchmark | [Project README](../README.md) and `pipeline/amazon_benchmark.py` | `data/benchmark/amazon-v1/` | `scripts/verify_amazon_benchmark.py` |
| Historical GLAD/RGB audit | [Archive README](../archive/preview-2026-11-14/README.md) | See archive README | See archive README |

Prepared results and source receipts are versioned; ignored raw downloads and
credentials are not included. Some reproduction steps require external data,
network access or Earthdata credentials. Run the static pages as described in
the [project README](../README.md); individual scripts and reports document
their additional dependencies and assumptions.
