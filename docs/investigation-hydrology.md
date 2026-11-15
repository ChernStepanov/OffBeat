# Tucuruí reservoir context for the Amazon SAR dates

## Краткий итог

Нашёлся реальный спутниковый продукт (не reanalysis) с рядом Tucuruí за 2026 год: публичный NASA LDOPE Water Reservoir Time Series, объект `TucuruiReservoir`, site 13, Suomi-NPP VIIRS `Vxx28C2` (8-day L3 composite). Но это не набор мгновенных наблюдений: предоставленные даты — composite labels, а точная семантика label (начало/центр/конец) в просмотренных provider docs и chart response **не подтверждена**; в JSON она явно записана как `unknown`. Area — спутниковая оценка площади по классификации NIR reflectance. Elevation и storage выводятся из area через заранее заданные reservoir AVE curves, поэтому это **не независимые altimetry/gauge measurements** и не три независимых источника. USDA G-REALM на дату проверки данных не предоставил: web-fetch получил HTTP 503; отдельный Python запрос завершился TLS EOF. DAHITI не запрашивал и регистрацию/auth не обходил.

На доступных VIIRS labels площадь в поздней части серии в целом снижалась: например, от label **13 августа (2511 km²)** к **14 сентября (2162 km²)** и далее к label **22 сентября (2162 km²)**. Из-за композитной поддержки нельзя утверждать, что Sep 22 строго предшествует NISAR Sep 28: если label означает начало 8-дневного окна, предполагаемое окно Sep 22…Sep 29 пересекало SAR-сцену. Поэтому это общий drawdown по доступным composite windows, а не точно измеренное предшествующее состояние на Sep 28. Он не устанавливает причину SAR rebound и не исключает эффекты обнажения/увлажнения береговой зоны.

## Доступность, vintage, качество

| Сервис/продукт | Проверка и фактический охват | Качество и ограничения |
|---|---|---|
| NASA MODIS LDOPE Lake TS, Terra/Aqua `MxD28C2`, AS7 | HTTP 200; 8-day серия 2000-02-26…2025-12-27. Area/elevation не дают данных для 2026; последний ряд более чем за 200 дней до первой NISAR даты. | 1189 дат, 1154 значения, 35 отсутствуют. Для match 2026 старый ряд не подставлялся как актуальный уровень. |
| NASA MODIS LDOPE Lake TS, Suomi-NPP VIIRS `Vxx28C2`, AS5200 | HTTP 200; 8-day серия 2012-01-25…2026-10-16; area и elevation доступны в 2026. Идентификаторы и выбор dataset проверены публичными menu endpoints. | 678 дат, 663 значения, 15 отсутствуют. Chart endpoint отдаёт только `date`, `mean`, `clim`; per-observation quality flag и processing metadata/version отдельно не предоставлены. Пропуски сохранены как null; доступность значения не равна подтверждённому QA pass или наземному gauge. |
| USDA FAS G-REALM | `https://ipad.fas.usda.gov/cropexplorer/global_reservoir/`: web-fetch HTTP 503; Python HTTPS попытка — TLS EOF. Сырой HTTP 503 body сохранён. | Реальные 2026 values из G-REALM получить не удалось. Исторический MEASURES id 785 не использовался как современный endpoint или как данные 2026. |
| DAHITI Tucurui 1065 | Не запрашивал. | Пользователь указал обязательную регистрацию; auth не обходился. |

LDOPE веб-интерфейс показывает software version `0.40`, site id 13, reference area capacity 2606 km², storage capacity 45.5 km³ и elevation capacity 75.4 m. Суффикс C2 означает 8-day продукт в каталоге; endpoint не сообщает per-observation processing build/version. MODIS `MxD28C2` и VIIRS `Vxx28C2` методологически используют area classification по отражению (MODIS product guide/ATBD и NASA VIIRS GWR page); elevation/storage рассчитываются по area-elevation/AVE curves. Источники: [NASA VIIRS GWR](https://viirsland.gsfc.nasa.gov/Products/NASA/GWR.html), [NASA MODIS GWR](https://modis-land.gsfc.nasa.gov/modgwr.html), [MODIS MOD28 User Guide](https://modis-land.gsfc.nasa.gov/pdf/MODIS_MOD28_User_Guide_1.1_20210702_zero_storage.pdf). Эти методы означают зависимые производные переменные, а не независимые высотомерные/гидрометрические измерения. Все исходные ответы, точные URLs/params, время получения UTC, статус, размер и SHA-256 лежат в `data/investigation/hydrology.json` и `data/investigation/hydrology-raw/`. Общий размер сохранённых raw responses около **178 kB**, существенно меньше лимита 10 MB.

## Сопоставление по датам

В исходных JSON-полях сохранены прежние nearest-date и label-only prior matches для backward compatibility; они не должны трактоваться как точные acquisition times или гарантированно antecedent composite observations. Для VIIRS 8-day продукта label semantics остаётся `unknown`. Новые поля `viirs_*_conservative_prior_8day` используют **явное консервативное допущение**: label является первым днём окна, и label + 8 дней ≤ NISAR date. Это screening rule для гарантированно не пересекающегося окна только при данном допущении, а не подтверждённая provider date convention. Стандартный lag в таблице — `label date − NISAR date`; положительный означает label позже NISAR. Интерполяции нет.

| NISAR date | Ближайший VIIRS composite label (lag) | Area km²* | Elevation estimate m* | Conservative prior: label + 8d ≤ NISAR (assumption) | Area km²* / elevation estimate m* |
|---|---:|---:|---:|---|---:|
| 2026-07-18 | Jul 20 (+2 d) | 2389.2 | 72.53 | Jul 4 (−14 d) | 2504.2 / 74.05 |
| 2026-08-11 | Aug 13 (+2 d) | 2511.4 | 74.15 | Jul 28 (−14 d) | 2461.5 / 73.49 |
| 2026-08-23 | Aug 21 (−2 d) | 2352.8 | 72.05 | Aug 13 (−10 d) | 2511.4 / 74.15 |
| 2026-09-04 | Sep 6 (+2 d) | 2226.2 | 70.38 | Aug 21 (−14 d) | 2352.8 / 72.05 |
| 2026-09-16 | Sep 14 (−2 d) | 2162.0 | 69.53 | Sep 6 (−10 d) | 2226.2 / 70.38 |
| 2026-09-28 | Sep 30 (+2 d) | 2042.7 | 67.95 | Sep 14 (−14 d) | 2162.0 / 69.53 |

Для NISAR **28 сентября** нельзя называть Sep 22 строго предшествующим наблюдением: label-only lag −6 дней не предотвращает overlap, поскольку label Sep 22 при 8-дневной поддержке может включать дни после SAR. По явно оговорённому условию `label + 8 days <= NISAR date` последнее консервативное prior label — **Sep 14** (−14 дней); Sep 14 + 8 = Sep 22. Это не доказывает, что provider фактически маркирует начало окна — это выбранное консервативное допущение при неизвестной семантике label. По доступным labels площадь от Aug 13 до Sep 14 снизилась на ~349 km² (−13,9%); этот drawdown характеризует временные composite windows, не точный уровень непосредственно перед сценой. Sep 30 — post-scene label и также composite, так что не точное пост-сценовое мгновенное измерение.

*Area — классификационная спутниковая оценка; elevation — оценка, выведенная из area по AVE curve. Они имеют общую методическую основу и не являются независимыми измерениями. Storage в выбранном ответе не извлекался, но в продуктовой методике он также curve-derived.

## Географическая правдоподобность и что проверить

Amazon study center — −4.775°, −49.275°; координата LDOPE Tucuruí — −3.83°, −49.65°. По прямой между study center и **reference point сайта**, не берегом, около **113 km**. Это оставляет географическую связь с протяжённым водохранилищем возможной, но сам LDOPE endpoint возвращает точку объекта, не shoreline polygon, и ближайшее расстояние до берега неизвестно.

Существующая локальная 141×141 DEM-derived поверхность study area — **AWS Terrain Tiles / Mapzen mixed-source terrain compilation**, а не Copernicus DEM. Источник tile: `data/investigation/layers/aws-terrain-z12-1487-2102.tif` (SHA-256 `671b6b7107e86f7caf570cfec5b62c827004bb005530bc92fca7d0002b050c2e`); derived grid: `data/investigation/layers/amazon-dem-native.npz` (SHA-256 `40fdd141768b524ab42a86752985d15998b8b3a8aeadb5e829f3e48c7f2e93af`). Эти provenance подтверждаются `docs/investigation-external-maps.md` и `data/investigation/external-maps.json`. Min/median/max **76.00 / 90.87 / 126.81 m**; minimum всего на **0.6 m** выше LDOPE site-page capacity elevation 75.4 m. Это небольшая разница, не исключающая flooding: terrain error и datum mismatch существенны, а вертикальный datum Mapzen provider не подтверждён и сопоставимость с LDOPE неизвестна. Геометрия берега/затопления также не установлена.

Полезные визуальные проверки (без новой атрибуции):

1. На независимой карте гидрографии/воды проверить, лежит ли study AOI на береговом рукаве Tucuruí, сколько до фактической береговой линии и есть ли непрерывное гидрологическое соединение с основным водоёмом.
2. Сопоставить локальные candidate clusters с береговой кромкой и water extent по composite windows позднего сезона; labels не точные даты наблюдения.
3. Для Amazon Sep 28 использовать как осторожный prior только Sep 14 при указанном `label + 8 days <= scene date` допущении; Sep 22 может перекрываться со сценой. Не переносить coarse reservoir series на локальные пиксели без карты берега.

**Вывод:** спутниковая площадь показывает drawdown по доступным 8-day composite windows позднего сезона, но точную preceding value на Sep 28 из labels установить нельзя; наиболее консервативный prior — Sep 14 при явно принятом 8-дневном правиле. Elevation/storage производны от classified area и не независимые измерения. Никакой причинной связи с SAR rebound не установлено. Дополнительно, точное расстояние до берега неизвестно, а отличие локальной Mapzen DEM от reference elevation всего 0.6 m не является аргументом против inundation при неизвестных errors/datums. Воспроизведение: `/tmp/opencode/nasa-venv/bin/python scripts/investigate_hydrology.py`; тесты: `PYTHONPATH=scripts /tmp/opencode/nasa-venv/bin/python -m unittest scripts.test_investigate_hydrology -v`.
