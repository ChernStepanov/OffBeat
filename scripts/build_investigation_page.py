#!/usr/bin/env python3
"""Build the map-page UI payload from published investigation source JSON.

This is a presentation adapter only: it does not recalculate scientific analyses.
Run `python scripts/build_investigation_page.py` to write the payload, or add
`--check` to fail if the committed/generated payload is stale.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/investigation/results.json"
INPUTS = {
    "map_candidates": "data/investigation/map-candidates.json",
    "weather": "data/investigation/weather.json",
    "external_maps": "data/investigation/external-maps.json",
    "regional_events": "data/investigation/regional-events.json",
    "hydrology": "data/investigation/hydrology.json",
}


def read_json(path: str) -> dict[str, Any] | None:
    file = ROOT / path
    if not file.is_file():
        return None
    value = json.loads(file.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def sha256(path: str) -> str | None:
    file = ROOT / path
    if not file.is_file():
        return None
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_asset(path: Any) -> str | None:
    """Return a safe repository-relative asset path only for an existing file."""
    if not isinstance(path, str) or not path.strip() or "\\" in path:
        return None
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or ":" in path:
        return None
    resolved = (ROOT / Path(*candidate.parts)).resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        return None
    return path if resolved.is_file() else None


def _utm22s_to_lonlat(easting: float, northing: float) -> tuple[float, float]:
    """WGS84 inverse UTM zone 22S, used only to draw the documented grid bounds."""
    a = 6378137.0
    ecc_sq = 0.0066943799901413165
    k0 = 0.9996
    x = easting - 500000.0
    y = northing - 10000000.0
    ecc_prime_sq = ecc_sq / (1.0 - ecc_sq)
    m = y / k0
    mu = m / (a * (1 - ecc_sq / 4 - 3 * ecc_sq**2 / 64 - 5 * ecc_sq**3 / 256))
    e1 = (1 - math.sqrt(1 - ecc_sq)) / (1 + math.sqrt(1 - ecc_sq))
    j1 = 3 * e1 / 2 - 27 * e1**3 / 32
    j2 = 21 * e1**2 / 16 - 55 * e1**4 / 32
    j3 = 151 * e1**3 / 96
    j4 = 1097 * e1**4 / 512
    fp = mu + j1 * math.sin(2 * mu) + j2 * math.sin(4 * mu) + j3 * math.sin(6 * mu) + j4 * math.sin(8 * mu)
    sin_fp, cos_fp = math.sin(fp), math.cos(fp)
    c1 = ecc_prime_sq * cos_fp**2
    t1 = math.tan(fp) ** 2
    n1 = a / math.sqrt(1 - ecc_sq * sin_fp**2)
    r1 = a * (1 - ecc_sq) / (1 - ecc_sq * sin_fp**2) ** 1.5
    d = x / (n1 * k0)
    lat = fp - (n1 * math.tan(fp) / r1) * (
        d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ecc_prime_sq) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ecc_prime_sq - 3 * c1**2) * d**6 / 720
    )
    lon = (d - (1 + 2 * t1 + c1) * d**3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ecc_prime_sq + 24 * t1**2) * d**5 / 120) / cos_fp
    lon0 = math.radians(-51.0)
    return math.degrees(lon0 + lon), math.degrees(lat)


def prepared_bounds(external: dict[str, Any] | None) -> list[float] | None:
    grid = (external or {}).get("native_grid") or {}
    shape = grid.get("shape")
    x0, y0, dx, dy = (grid.get(key) for key in ("x_first", "y_first", "x_step", "y_step"))
    if not (isinstance(shape, list) and len(shape) == 2 and all(isinstance(v, (int, float)) for v in [x0, y0, dx, dy])):
        return None
    rows, cols = shape
    x_last = x0 + (cols - 1) * dx
    y_last = y0 + (rows - 1) * dy
    xs = [min(x0, x_last) - abs(dx) / 2, max(x0, x_last) + abs(dx) / 2]
    ys = [min(y0, y_last) - abs(dy) / 2, max(y0, y_last) + abs(dy) / 2]
    corners = [_utm22s_to_lonlat(x, y) for x in xs for y in ys]
    lons, lats = zip(*corners)
    return [min(lats), min(lons), max(lats), max(lons)]


WORLD_COVER = {
    10: {"ru": "Древесный покров", "en": "Tree cover"},
    20: {"ru": "Кустарники", "en": "Shrubland"},
    30: {"ru": "Травянистый покров", "en": "Grassland"},
    40: {"ru": "Пахотные земли", "en": "Cropland"},
    50: {"ru": "Застроенная территория", "en": "Built-up"},
    60: {"ru": "Редкая растительность", "en": "Bare / sparse vegetation"},
    70: {"ru": "Снег и лёд", "en": "Snow and ice"},
    80: {"ru": "Постоянная вода", "en": "Permanent water bodies"},
    90: {"ru": "Водно-болотная растительность", "en": "Herbaceous wetland"},
    95: {"ru": "Мангровый покров", "en": "Mangroves"},
    100: {"ru": "Мхи и лишайники", "en": "Moss and lichen"},
}


def bbox_from_geojson(geometry: Any) -> list[float] | None:
    coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
    found: list[tuple[float, float]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            if len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
                found.append((float(value[0]), float(value[1])))
            else:
                for child in value:
                    walk(child)

    walk(coords)
    if not found:
        return None
    lons, lats = zip(*found)
    return [min(lons), min(lats), max(lons), max(lats)]


def intersects(a: list[float] | None, b: list[float] | None) -> bool | None:
    if not a or not b:
        return None
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def source_catalogue(sources: dict[str, dict[str, Any] | None]) -> list[dict[str, Any]]:
    maps = sources.get("map_candidates") or {}
    weather = sources.get("weather") or {}
    external = sources.get("external_maps") or {}
    regional = sources.get("regional_events") or {}
    hydro = sources.get("hydrology")
    catalog = [
        {"id": "nisar", "name": {"ru": "NISAR GCOV HH/HV", "en": "NISAR GCOV HH/HV"}, "status": "obtained" if maps else "unavailable", "years": _scene_years(maps.get("maps", [])), "scale": {"ru": "Нативная сетка 20 м; 6 дат", "en": "Native 20 m grid; 6 dates"}, "purpose": {"ru": "HV-only скрининг и ряды HH/HV для выбранных точек", "en": "HV-only screen and HH/HV series for selected points"}},
        {"id": "sentinel2", "name": {"ru": "Sentinel-2 L2A", "en": "Sentinel-2 L2A"}, "status": "obtained" if maps.get("optical_scenes") else "unavailable", "years": _scene_years(maps.get("optical_scenes", []) + _new_scenes(maps)), "scale": {"ru": "RGB-превью; локальные окна B04/B08/B11/SCL и индексы — по датам в metadata", "en": "RGB previews; local B04/B08/B11/SCL windows and indices as dated in metadata"}, "purpose": {"ru": "Визуальный контекст и локальная cloud fraction; не подтверждение по одному индексу", "en": "Visual context and local cloud fraction; an index alone is not confirmation"}},
        {"id": "worldcover", "name": {"ru": "ESA WorldCover", "en": "ESA WorldCover"}, "status": "obtained" if maps and any("worldcover2021_code" in m for m in maps.get("maps", [])) else "unavailable", "years": [2021], "scale": {"ru": "Класс покрова 2021; prior, не текущее ground truth", "en": "2021 land-cover class; prior, not current ground truth"}, "purpose": {"ru": "Описательный prior-контекст", "en": "Descriptive prior context"}},
        {"id": "weather", "name": {"ru": "ERA5 / ERA5-Land", "en": "ERA5 / ERA5-Land"}, "status": "obtained" if weather else "unavailable", "years": _weather_years(weather), "scale": _weather_scale(weather), "purpose": {"ru": "Общий погодный контекст по датам для всех Amazon-точек; корреляции не причинны", "en": "Shared date-level weather context for all Amazon points; correlations are not causal"}},
    ]
    if external:
        forest = external.get("forest_change") or {}
        catalog.extend([
            {"id": "hansen", "name": forest.get("product", "Hansen Global Forest Change"), "status": "obtained" if forest else "unavailable", "years": [2000, forest.get("lossyear", {}).get("source_year", 2024)] if forest else [], "scale": forest.get("lossyear", {}).get("resolution", {"ru": "Приблизительно 30 м", "en": "Approximately 30 m"}), "purpose": {"ru": "Исторический canopy/loss context; не свидетельство события после последнего года продукта", "en": "Historical canopy/loss context; not evidence for events after the product's last year"}},
        {"id": "dem", "name": {"ru": "DEM (AWS Terrain / Mapzen mixed-source)", "en": "DEM (AWS Terrain / Mapzen mixed-source)"}, "status": "obtained" if external.get("derived") else "unavailable", "years": [], "scale": (external.get("derived") or {}).get("method", ""), "purpose": {"ru": "Рельефный контекст; не вывод о воде/затоплении и не hydrologically conditioned", "en": "Terrain context; does not establish water/flooding and is not hydrologically conditioned"}},
        ])
        for item in external.get("not_acquired", []):
            catalog.append({"id": "not-acquired-" + str(len(catalog)), "name": item.get("source"), "status": "not_acquired", "reason": item.get("reason"), "years": [], "scale": None, "purpose": {"ru": "Не использовать как измерение или подтверждение события", "en": "Do not treat as a measurement or event confirmation"}})
    catalog.append({"id": "inpe-deter", "name": (regional.get("source") or {}).get("name", "INPE DETER"), "status": "obtained" if regional.get("selected_leads") and regional.get("selected_geometry") else "unavailable", "years": _event_years(regional), "scale": {"ru": "Три dated DETER polygons 2026 с парными окнами Sentinel-2; regional context, вне подготовленного SAR окна", "en": "Three dated DETER polygons from 2026 with paired Sentinel-2 windows; regional context, outside prepared SAR bounds"}, "purpose": {"ru": "Реестровый alert с оптическим изменением; не NISAR detection, причина и точный onset неизвестны", "en": "Registry alert with optical change; not a NISAR detection; cause and exact onset are unknown"}})
    if not hydro:
        catalog.append({"id": "hydrology", "name": {"ru": "Гидрология Тукуруи", "en": "Tucuruí hydrology"}, "status": "unavailable", "years": [], "scale": None, "purpose": {"ru": "Проверенный источник/координаты пока не опубликованы; значения и положение не подставляются", "en": "No verified source/coordinates published yet; values and location are not inferred"}})
    else:
        feasibility = hydro.get("geospatial_feasibility") or {}
        products = hydro.get("product_metadata", {}).get("products", [])
        availability = hydro.get("availability", {})
        years = []
        for detail in availability.values():
            for key in ("first_date", "last_date"):
                year = str(detail.get(key, ""))[:4]
                if year.isdigit(): years.append(int(year))
        catalog.append({"id": "hydrology", "name": {"ru": "NASA LDOPE — водохранилище Тукуруи", "en": "NASA LDOPE — Tucuruí reservoir"}, "status": "obtained", "years": [min(years), max(years)] if years else [], "scale": {"ru": "Площадь спутниковой классификации, композиты с шагом 8 дней; elevation/storage — производные от площади", "en": "Satellite-classified area, 8-day composites; elevation/storage are derived from area"}, "purpose": {"ru": f"Отдельный региональный контекст водохранилища (опорная точка примерно в {feasibility.get('study_to_ldope_site_center_km')} км); не локальное измерение и не причинное объяснение SAR", "en": f"Separate regional reservoir context (reference point about {feasibility.get('study_to_ldope_site_center_km')} km away); not a local measurement or causal explanation of SAR"}, "products": products, "availability": availability, "other_provider_status": (hydro.get("status") or {}).get("grealm")})
    return catalog


def _scene_years(items: list[dict[str, Any]]) -> list[int]:
    years = {int(str(x.get("date", ""))[:4]) for x in items if str(x.get("date", ""))[:4].isdigit()}
    return sorted(years)


def _new_scenes(maps: dict[str, Any]) -> list[dict[str, Any]]:
    return list((maps.get("new_optical_evidence") or {}).get("selected_scenes", []))


def _weather_years(weather: dict[str, Any]) -> list[int]:
    years = set()
    for site in (weather.get("sites") or {}).values():
        years |= set(_scene_years(site.get("dates", [])))
    return sorted(years)


def _weather_scale(weather: dict[str, Any]) -> dict[str, str]:
    prov = weather.get("provenance", [])
    resolutions = sorted({str(p.get("nominal_resolution_degrees")) + "°" for p in prov if p.get("requested_center_lat_lon", [None])[0] is not None})
    suffix = "; ".join(resolutions)
    return {"ru": f"Одна coarse cell на участок ({suffix}); не 20 м пиксель" if suffix else "Грубая ячейка; не 20 м пиксель", "en": f"One coarse cell per site ({suffix}); not 20 m pixels" if suffix else "Coarse cell; not 20 m pixels"}


def _event_years(regional: dict[str, Any]) -> list[int]:
    years = set()
    for event in regional.get("selected_leads", []):
        date = str((event.get("properties") or {}).get("view_date", ""))
        if date[:4].isdigit():
            years.add(int(date[:4]))
    return sorted(years)


def make_optical_evidence(record: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = []
    sheet = record.get("new_optical_contact_sheet")
    if isinstance(sheet, dict):
        path = local_asset(sheet.get("path"))
        if path:
            evidence.append({"kind": "contact_sheet", "label": {"ru": "Контактный лист новых оптических дат", "en": "New optical dates contact sheet"}, "date": ", ".join(sheet.get("dates", [])), "image": path, "sha256": sheet.get("sha256")})
    old_sheet = local_asset(record.get("optical_contact_sheet"))
    if old_sheet:
        evidence.append({"kind": "contact_sheet", "label": {"ru": "Исходный оптический контактный лист", "en": "Original optical contact sheet"}, "image": old_sheet})
    for item in record.get("new_optical", []):
        metrics = item.get("metrics") or {}
        evidence.append({
            "kind": "dated_optical", "date": item.get("date"), "scene_id": item.get("scene_id"),
            "context_status": item.get("context_status"), "local_clear_fraction": item.get("local_scl_clear_fraction"),
            "index_support": {"ru": "NDVI/NDMI — медианы отдельных 1 км окон, рассчитанные на 20 м сетке; не значение одного 20 м пикселя в координате.", "en": "NDVI/NDMI are medians over separate 1 km windows computed on a 20 m grid; not a single 20 m pixel value at the coordinate."},
            "rgb_image": local_asset(metrics.get("rgb_path")),
            "ndvi_image": local_asset((metrics.get("ndvi_map") or {}).get("path")),
            "ndmi_image": local_asset((metrics.get("ndmi_map") or {}).get("path")),
            "ndvi": metrics.get("ndvi"), "ndmi": metrics.get("ndmi"),
            "sha256": {"rgb": metrics.get("rgb_sha256"), "ndvi": (metrics.get("ndvi_map") or {}).get("sha256"), "ndmi": (metrics.get("ndmi_map") or {}).get("sha256")},
        })
    return evidence


def make_weather(weather: dict[str, Any] | None) -> dict[str, Any]:
    if not weather or not isinstance(weather.get("sites"), dict):
        return {"status": "unavailable", "dates": [], "mexico_context": None, "amazon_method": None}
    amazon = weather["sites"].get("amazon") or {}
    mexico = weather["sites"].get("mexico") or {}
    return {
        "status": "obtained" if amazon.get("dates") else "unavailable",
        "site": "amazon",
        "shared_cell": True,
        "scale_note": {"ru": "Все Amazon-точки используют одну coarse weather cell; погодные даты не являются пиксельными измерениями и не доказывают причину SAR-сдвига.", "en": "All Amazon points share one coarse weather cell; dates are not pixel-level measurements and do not establish the cause of SAR change."},
        "sources": amazon.get("weather_sources"),
        "method": amazon.get("method"),
        "dates": amazon.get("dates", []),
        "correlations": amazon.get("common_mode_removed_weather_correlations", {}),
        "targeted_temperature": amazon.get("temperature_hv_targeted_falsification"),
        "mexico_context": {
            "site": "mexico", "n_dates": len(mexico.get("dates", [])), "dates": mexico.get("dates", []),
            "targeted_temperature": mexico.get("temperature_hv_targeted_falsification"),
            "method": mexico.get("method"), "sources": mexico.get("weather_sources"),
            "note": {"ru": "Отдельный 29-date context другого участка; значения не назначены ни одной Amazon-точке. Сильная raw-level связь температуры с HV не причинная и должна читаться вместе с differenced/season-adjusted и future-window control.", "en": "Separate 29-date context from another site; values are not assigned to Amazon points. The strong raw-level temperature–HV association is not causal and must be read alongside differenced/season-adjusted results and the future-window control."},
        },
    }


def make_hydrology(hydro: dict[str, Any] | None) -> dict[str, Any]:
    if not hydro:
        return {"status": "unavailable", "source": None, "reference_site": None, "nearest_measurements_to_nisar_dates": [], "note": {"ru": "Нет проверенного источника/координат; значения не подставлены.", "en": "No verified source/coordinates; no values inferred."}}
    geo = hydro.get("geospatial_feasibility") or {}
    product = hydro.get("product_metadata") or {}
    series = hydro.get("series") or {}
    viirs = [row for row in series.get("SNPPJ1_area", []) if str(row.get("date", "")).startswith("2026-")]
    nearest = hydro.get("nearest_measurements_to_nisar_dates", [])
    return {
        "status": "obtained", "site_name": geo.get("ldope_site_name"), "site_id": geo.get("ldope_site_id"),
        "reference_coordinates": geo.get("ldope_site_center_lat_lon"), "distance_from_study_km": geo.get("study_to_ldope_site_center_km"),
        "area_series_2026": viirs, "nearest_date_context": [
            {"nisar_date": row.get("nisar_date"), "prior_composite": row.get("viirs_area_conservative_prior_8day"),
             "nearest_composite": row.get("viirs_area"), "elevation_prior": row.get("viirs_elevation_conservative_prior_8day")}
            for row in nearest
        ],
        "temporal_support": product.get("temporal_support"), "variable_source_classification": product.get("variable_source_classification"),
        "quality_note": product.get("quality_note"), "provider_status": hydro.get("status"),
        "availability": hydro.get("availability"), "products": product.get("products"),
        "geospatial_caveat": {"ru": "Опорная точка около 113 км от AOI. Расстояние до точки не является расстоянием до берега; береговая геометрия отсутствует. Совместимость вертикальных датумов неизвестна, DEM не hydrologically conditioned; это не исключает и не подтверждает затопление или гидрологическую связь.", "en": "Reference point is about 113 km from the AOI. Distance to the point is not shoreline distance; shoreline geometry is unavailable. Vertical-datum compatibility is unknown and the DEM is not hydrologically conditioned; this neither rules out nor establishes flooding or hydrologic connection."},
        "limitations": hydro.get("limitations", []),
        "note": {"ru": "Отдельный региональный контекст резервуара. Площадь — спутниковая классификация водной поверхности в 8-дневном продукте; смысл даты композита неизвестен. Для conservative prior используется соглашение label + 8 дней ≤ дата NISAR, это допущение, не подтверждённая семантика поставщика. Elevation/storage производны от площади по кривым area-volume-elevation и не являются независимым альтиметрическим свидетельством. Не назначать значения региональным событиям или SAR-точкам; причинность/аномалия не установлены.", "en": "Separate regional reservoir context. Area is satellite water-surface classification in an 8-day product; date-label semantics are unknown. Conservative prior uses the convention label + 8 days ≤ NISAR date, an assumption rather than provider-confirmed semantics. Elevation/storage are derived from area using area-volume-elevation curves and are not independent altimetry evidence. Do not assign these values to regional events or SAR points; no anomaly/causality is established."},
    }


def make_raster_overlays(external: dict[str, Any] | None, sar_bounds: list[float] | None) -> list[dict[str, Any]]:
    """Consume only explicitly published, local, bounded rasters; no inferred layers."""
    result = []
    layers = (external or {}).get("overlays", [])
    if isinstance(layers, dict):
        layers = [dict(value, id=key) for key, value in layers.items() if isinstance(value, dict)]
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        path = local_asset(layer.get("path"))
        raw = layer.get("bounds_wgs84")
        supplied_hash = layer.get("sha256")
        legend = layer.get("legend")
        period = layer.get("period") or layer.get("year")
        if (not path or not isinstance(supplied_hash, str) or len(supplied_hash) != 64
                or sha256(path) != supplied_hash or not isinstance(legend, (list, dict)) or not legend
                or period is None or not isinstance(raw, list) or len(raw) != 4
                or not all(isinstance(v, (int, float)) for v in raw)):
            continue
        west, south, east, north = raw
        if west >= east or south >= north or not sar_bounds:
            continue
        # Keep the original georeferencing and clip the visible image to this
        # intersection in the renderer; never extrapolate a raster beyond the SAR AOI.
        s, w, n, e = sar_bounds
        epsilon = 1e-7
        if east < w or west > e or north < s or south > n:
            continue
        visible = [max(s, south), max(w, west), min(n, north), min(e, east)]
        if visible[0] >= visible[2] or visible[1] >= visible[3]:
            continue
        if isinstance(legend, dict):
            legend_title = legend.get("title") or layer.get("id")
            legend_items = legend.get("items") or legend.get("palette_stops") or []
            legend = [{"value": item.get("value"), "label": item.get("label", str(item.get("value", ""))), "color": item.get("color")} for item in legend_items if isinstance(item, dict)]
        else:
            legend_title = layer.get("id")
        translated_names = {
            "hansen_lossyear": {"ru": "Hansen GFC · исторический год потери", "en": "Hansen GFC · historical loss year"},
            "hansen_treecover2000": {"ru": "Hansen GFC · древесный покров около 2000 г.", "en": "Hansen GFC · tree cover circa 2000"},
            "dem_elevation": {"ru": "DEM · высота рельефа", "en": "DEM · terrain elevation"},
        }
        result.append({
            "id": layer.get("id"), "name": layer.get("name") or translated_names.get(layer.get("id"), {"ru": legend_title, "en": legend_title}), "path": path,
            "sha256": supplied_hash, "bounds": [south, west, north, east], "clip_bounds": visible,
            "year": period, "resolution": layer.get("resolution"),
            "legend": legend, "nodata": layer.get("nodata") or (layer.get("legend", {}).get("nodata") if isinstance(layer.get("legend"), dict) else None),
            "caveats": layer.get("warnings") or layer.get("caveats") or layer.get("resolution_qualification") or layer.get("period"),
            "source": layer.get("source"),
        })
    return result


def make_optical_overlays(maps: dict[str, Any] | None, sar_bounds: list[float] | None) -> list[dict[str, Any]]:
    overlays = (maps or {}).get("new_optical_overlays", [])
    if not sar_bounds or not isinstance(overlays, list):
        return []
    south, west, north, east = sar_bounds
    result = []
    for item in overlays:
        if not isinstance(item, dict):
            continue
        path, date, expected_hash = local_asset(item.get("path")), item.get("date"), item.get("sha256")
        raw = item.get("bounds_wgs84")
        if (not path or not date or not isinstance(expected_hash, str) or sha256(path) != expected_hash
                or not isinstance(raw, list) or len(raw) != 4 or not all(isinstance(v, (int, float)) for v in raw)):
            continue
        layer_west, layer_south, layer_east, layer_north = raw
        if (layer_west >= layer_east or layer_south >= layer_north or layer_east <= west
                or layer_west >= east or layer_north <= south or layer_south >= north):
            continue
        legend = item.get("legend") or {}
        result.append({
            "id": f"sentinel2-{date}", "kind": "dated_optical", "date": date,
            "name": {"ru": f"Sentinel-2 RGB · {date}", "en": f"Sentinel-2 RGB · {date}"},
            "path": path, "sha256": expected_hash,
            "bounds": [layer_south, layer_west, layer_north, layer_east],
            "clip_bounds": [max(south, layer_south), max(west, layer_west), min(north, layer_north), min(east, layer_east)],
            "legend": [{"label": {"ru": "Истинный цвет RGB (качественный визуальный контекст)", "en": "True-color RGB (qualitative visual context)"}}],
            "caveats": item.get("resolution_qualification") or legend.get("display"),
            "valid_fraction": (item.get("alpha") or {}).get("valid_fraction"),
            "valid_mask_policy": item.get("valid_mask_policy"), "source_scene": item.get("source_scene"),
            "source_item_url": item.get("source_item_url"),
        })
    return result


def make_local_map_overlay(product: dict[str, Any]) -> dict[str, Any] | None:
    """Pass through only an exported, local, georeferenced overlay with a verified digest."""
    metadata = product.get("map_overlay")
    if not isinstance(metadata, dict):
        return None
    path = local_asset(metadata.get("path"))
    declared_sha = metadata.get("sha256")
    actual_sha = sha256(path) if path else None
    bounds = metadata.get("bounds_wgs84")
    if not path or not isinstance(declared_sha, str) or actual_sha != declared_sha.lower():
        return None
    if not isinstance(bounds, list) or len(bounds) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bounds):
        return None
    west, south, east, north = bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        return None
    date = str(metadata.get("date") or product.get("datetime") or "")[:10]
    scene = metadata.get("source_scene") or product.get("scene_id")
    if len(date) != 10 or not isinstance(scene, str) or not scene:
        return None
    return {
        "path": path, "sha256": actual_sha, "bounds_wgs84": list(bounds),
        "date": date, "source_scene": scene,
        "mask_policy": metadata.get("mask_policy"),
        "resolution_qualification": metadata.get("resolution_qualification"),
    }


def make_events(regional: dict[str, Any] | None, bounds: list[float] | None, geometry_file: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not regional:
        return [], {"status": "unavailable", "events": [], "source": None}
    geojson = None
    geometry_hash = sha256(geometry_file)
    geometry_path = local_asset((regional.get("selected_geometry") or {}).get("path"))
    if geometry_path:
        geojson = read_json(geometry_path)
    features = (geojson or {}).get("features", []) if isinstance(geojson, dict) else []
    by_id = {}
    for feature in features:
        props = feature.get("properties") or {}
        raw_id = str(props.get("gid") or props.get("id") or "")
        by_id[raw_id] = feature
    optical_by_id = {str(item.get("event_id")): item for item in regional.get("optical_catalogue_checks", []) if item.get("event_id")}
    falsification = regional.get("targeted_falsification") or {}
    falsification_by_id = {str(item.get("event_id")): item for item in falsification.get("events", []) if item.get("event_id")}
    events = []
    for lead in regional.get("selected_leads", []):
        props = lead.get("properties") or {}
        gid = str(props.get("gid") or "")
        feature = by_id.get(gid)
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        bbox = bbox_from_geojson(geometry)
        optical_record = optical_by_id.get(str(lead.get("id")), {})
        falsification_record = falsification_by_id.get(str(lead.get("id")))
        products = []
        for product in optical_record.get("products", []):
            rgb = local_asset(product.get("rgb_preview"))
            if not rgb or (product.get("rgb_preview_sha256") and sha256(rgb) != product.get("rgb_preview_sha256")):
                continue
            presented_product = {
                "phase": product.get("phase"), "date": str(product.get("datetime", ""))[:10] or None,
                "scene_id": product.get("scene_id"), "days_from_event_observation": product.get("days_from_view_date"),
                "image": rgb, "image_sha256": product.get("rgb_preview_sha256"),
                "local_valid_fraction": product.get("valid_fraction"), "polygon_clear_fraction": product.get("event_polygon_clear_fraction"),
                "polygon_clear_pixels": product.get("event_polygon_clear_pixels"),
                "polygon_ndvi_median": product.get("event_polygon_ndvi_median"),
                "polygon_ndmi_median": product.get("event_polygon_ndmi_median"),
                "window_ndvi_median": product.get("ndvi_median"), "window_ndmi_median": product.get("ndmi_median"),
                "data_sha256": product.get("sha256"), "timestamp_note": product.get("timestamp_note"),
            }
            map_overlay = make_local_map_overlay(product)
            if map_overlay:
                presented_product["map_overlay"] = map_overlay
            products.append(presented_product)
        products.sort(key=lambda p: (0 if p.get("phase") == "before" else 1, p.get("date") or ""))
        event = {
            "id": lead.get("id"), "kind": "regional_event", "evidence_status": "supported" if ((falsification_record or {}).get("evidence_observations") or {}).get("calibrated_assessment", {}).get("status") == "supported_localized_optical_decrease" else "unresolved", "name": {"ru": f"INPE DETER · {props.get('view_date', '')} · {props.get('municipality', '')}", "en": f"INPE DETER · {props.get('view_date', '')} · {props.get('municipality', '')}"},
            "event_date": props.get("view_date"), "published_month": props.get("publish_month"),
            "source": (regional.get("source") or {}).get("name"), "source_url": (regional.get("source") or {}).get("documentation"),
            "class_name": props.get("classname"), "municipality": props.get("municipality"), "state": props.get("uf"),
            "registry_area_km2": props.get("areamunkm"), "geometry_area_ha": lead.get("area_geometry_ha"),
            "distance_center_m": lead.get("distance_center_m"), "area_ha": lead.get("area_geometry_ha"),
            "geometry": geometry, "bounds_wgs84": bbox, "overlaps_prepared_sar": intersects(bounds, [bbox[1], bbox[0], bbox[3], bbox[2]]) if bbox else None,
            "sar_coverage": "inside_prepared_window" if bbox and intersects(bounds, [bbox[1], bbox[0], bbox[3], bbox[2]]) else "outside_or_unknown",
            "optical_products": products,
            "optical_status": "paired_local_pre_post" if {p.get("phase") for p in products} >= {"before", "after"} else "partial_or_unavailable",
            "falsification": falsification_record,
            "visual_interpretation": ((falsification_record or {}).get("evidence_observations") or {}).get("calibrated_assessment", {}).get("statement"),
            "interpretation": {"ru": "Официальный класс DETER сохранён как метка источника. Observation date каталога не равна точной дате начала изменения. Это региональный lead вне компактного подготовленного NISAR-окна; SAR detection для этих объектов не заявляется. Региональным событиям не назначается Amazon coarse-cell weather.", "en": "The official DETER class is retained as a source label. Catalog observation date is not the exact onset date. This regional lead is outside the compact prepared NISAR window; no SAR detection is claimed for these objects. Amazon coarse-cell weather is not assigned to regional events."},
        }
        events.append(event)
    outcomes = [((item.get("evidence_observations") or {}).get("calibrated_assessment") or {}).get("status") for item in falsification_by_id.values()]
    supported = sum(status == "supported_localized_optical_decrease" for status in outcomes)
    registry_only = sum(status == "registry_only_background_similar" for status in outcomes)
    assessment_summary = {"supported_localized_optical_change": supported, "registry_only_background_similar": registry_only, "total_assessed": len(outcomes), "text": {"ru": f"Оптическое отличие от фона поддержано: {supported}; alert без локального отличия: {registry_only}. Это не {len(outcomes)} подтверждённых вырубок.", "en": f"Localized optical change supported relative to background: {supported}; alerts without localized difference: {registry_only}. These are not {len(outcomes)} confirmed clearings."}}
    return events, {"status": "obtained" if events else "obtained_no_selected_leads", "search_radius_m": regional.get("search_radius_m"), "study_center": regional.get("study_center"), "source": regional.get("source"), "events": events, "assessment_summary": assessment_summary, "targeted_falsification_method": falsification.get("method"), "selected_geometry_path": geometry_path, "selected_geometry_sha256": geometry_hash, "nisar_note": {"ru": f"Все {len(events)} выбранных DETER-полигона находятся вне компактного подготовленного NISAR AOI: это региональные alerts, не SAR-detections. Общая Amazon weather cell этим точкам не назначается.", "en": (regional.get("interpretation") or {}).get("nisar", "Regional alerts are not SAR detections; Amazon weather-cell data are not assigned to these points.")}, "interpretation": regional.get("interpretation")}


def build_payload() -> dict[str, Any]:
    sources = {key: read_json(path) for key, path in INPUTS.items()}
    maps = sources.get("map_candidates") or {}
    weather_source = sources.get("weather")
    external = sources.get("external_maps")
    regional = sources.get("regional_events")
    bounds = prepared_bounds(external)
    regional_path = (regional or {}).get("selected_geometry", {}).get("path", "")
    source_hashes = {path: sha256(path) for path in INPUTS.values()}
    if regional_path:
        source_hashes[regional_path] = sha256(regional_path)

    external_matches = {str(x.get("id")): x for x in (external or {}).get("candidate_matches", []) if x.get("id")}
    weather = make_weather(weather_source)
    records = []
    for item in maps.get("maps", []):
        if not isinstance(item, dict) or not isinstance(item.get("lat"), (int, float)) or not isinstance(item.get("lon"), (int, float)):
            continue
        code = item.get("worldcover2021_code")
        external_item = external_matches.get(str(item.get("id")))
        new_images = item.get("visual_annotation_key", {}).get("new_source_images", [])
        cloud_by_date = {x.get("date"): x.get("local_scl_clear_fraction") for x in item.get("new_optical", [])}
        records.append({
            "id": item.get("id"), "name": item.get("id"), "kind": "control" if item.get("role") == "control" else "candidate", "role": item.get("role"),
            "coordinates": {"lat": item["lat"], "lon": item["lon"]}, "evidence_status": "unknown",
            "hv_shift_db": item.get("hv_shift_db"), "hh_companion_shift_db": item.get("hh_companion_shift_db"), "joint3dbflag": item.get("joint3dbflag"),
            "joint3dbflag_rule": item.get("joint3dbflag_rule"),
            "sar_series": item.get("sar_series_db"), "worldcover": {"year": 2021, "code": code, "class": WORLD_COVER.get(code), "ground_truth": False, "note": {"ru": "Исторический prior-класс WorldCover 2021, не проверка текущего состояния на земле.", "en": "Historical WorldCover 2021 prior class, not a current ground-truth check."}},
            "visual_observation": item.get("observation"), "interpretation": item.get("interpretation"), "status_label": item.get("status"), "limitations": item.get("limitations"),
            "optical_evidence": make_optical_evidence(item), "optical_scenes": item.get("new_optical", []), "local_cloud_fraction_by_date": {date: (None if fraction is None else 1 - fraction) for date, fraction in cloud_by_date.items()},
            "external_features": ({**external_item, "lossyear_source_year": (external or {}).get("forest_change", {}).get("lossyear", {}).get("source_year")} if external_item else None), "weather_dates": weather.get("dates", []), "weather_cell_id": "amazon_shared_coarse_cell" if weather.get("dates") else None,
        })

    regional_events, regional_payload = make_events(regional, bounds, regional_path) if regional else ([], {"status": "unavailable", "events": [], "source": None})
    if regional_events:
        regional_payload["nisar_note"] = {
            "ru": "Региональные полигоны вне подготовленного SAR-окна: это оптические и реестровые находки, не NISAR-обнаружения.",
            "en": "Regional polygons lie outside the prepared SAR window: these are optical and registry leads, not NISAR detections.",
        }
    hydrology_payload = make_hydrology(sources.get("hydrology"))

    payload = {
        "schema_version": 1,
        "title": {"ru": "Кандидаты и находки на карте", "en": "Candidates and findings on the map"},
        "summary": ({
            "ru": f"Локальное оптическое изменение относительно окрестности поддержано у {regional_payload['assessment_summary']['supported_localized_optical_change']} региональных участков. SAR-кандидаты и alerts без локального отличия показаны отдельно.",
            "en": f"Localized optical change relative to the surroundings is supported at {regional_payload['assessment_summary']['supported_localized_optical_change']} regional sites. SAR candidates and alerts without localized contrast are shown separately.",
        } if regional_events else maps.get("summary")), "selection": maps.get("selection"), "coordinate_mapping": maps.get("coordinate_mapping"),
        "prepared_sar": {"bounds": bounds, "crs": (external or {}).get("native_grid", {}).get("epsg"), "resolution_m": (external or {}).get("native_grid", {}).get("x_step"), "coverage_note": {"ru": "Окно отражает подготовленную сетку SAR; вне него SAR-измерений в этом наборе нет.", "en": "This bounds the prepared SAR grid; outside it there are no SAR measurements in this dataset."}},
        "selection_note": {"ru": "Скрининг HV-only по сетке; это не выборка по forest class. Контроли не являются проверенными отрицательными случаями и не class-matched.", "en": "HV-only grid screen; not selected by forest class. Controls are neither verified negatives nor class-matched."},
        "candidates": records, "regional_events": regional_payload, "weather": weather,
        "external_context": {"status": "obtained" if external else "unavailable", "study": (external or {}).get("study"), "interpretation": (external or {}).get("interpretation"), "source": (external or {}).get("source"), "forest_change": (external or {}).get("forest_change"), "derived_terrain": (external or {}).get("derived"), "not_acquired": (external or {}).get("not_acquired", [])},
        "hydrology": hydrology_payload, "source_catalogue": source_catalogue(sources), "source_hashes": source_hashes,
        "optical_provenance": maps.get("new_optical_evidence"),
        "events": regional_events, "raster_layers": make_raster_overlays(external, bounds) + make_optical_overlays(maps, bounds),
    }
    # Include hashes for local imagery/rasters actually referenced by the adapter
    # as well as the upstream JSON receipts. This is provenance, not new analysis.
    def add_asset_hashes(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values(): add_asset_hashes(child)
        elif isinstance(value, list):
            for child in value: add_asset_hashes(child)
        elif isinstance(value, str) and value.startswith("data/") and local_asset(value):
            payload["source_hashes"].setdefault(value, sha256(value))
    add_asset_hashes(payload)
    return payload


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if results.json differs from a fresh build")
    args = parser.parse_args()
    content = render_json(build_payload())
    if args.check:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != content:
            print(f"STALE: run python {Path(__file__).relative_to(ROOT)}", file=sys.stderr)
            return 1
        print(f"OK: {OUT.relative_to(ROOT)} is up to date")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(content)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
