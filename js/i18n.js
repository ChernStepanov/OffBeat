// Interface translations. Data, coordinates, source identifiers and place names are kept intact.
(() => {
  const translations = {
    'Welcome to OffBeat':'Добро пожаловать в OffBeat',
    'Measured HH/HV on 2 dates; exploratory peer deviations only. Too few dates for curve-shape classification. No GUNW displacement samples passed quality checks.':'Измерения HH/HV за две даты; отклонения от соседей требуют проверки. Для определения формы кривой дат недостаточно. Ни одно измерение смещения GUNW не прошло проверку качества.',
    'Measured HH/HV on 2 dates; exploratory peer deviations only. Too few dates for curve-shape classification. GUNW has quality-filtered samples on a separate date axis.':'Измерения HH/HV за две даты; отклонения от соседей требуют проверки. Для определения формы кривой дат недостаточно. Прошедшие проверку точки GUNW показаны на отдельной временной шкале.',
    'No prepared measurements at this location. Choose a marked site to see its data and listen to a sample.':'Для этого места нет подготовленных измерений. Выберите отмеченный участок, чтобы увидеть данные и прослушать точку.',
    'Choose a prepared measurement site':'Выбрать участок с измерениями',
    'Measured data could not be loaded. Check your connection and reload the page.':'Не удалось загрузить измерения. Проверьте соединение и обновите страницу.',
    'Amazon change experiment':'Эксперимент по изменениям в Амазонии',
    'Explore the fixed-window analysis':'Посмотреть анализ за выбранный период',
    'Polarization':'Поляризация', 'Neighborhood':'Окрестность', 'Show experiment on map':'Показать эксперимент на карте',
    'Radar sees through cloud and at night, but almost nobody can read it.':'Радар видит сквозь облака и ночью, но читать его почти никто не умеет.',
    'OffBeat compares every NISAR sample with its neighbours of the same land cover, flags the ones that fall out of step, and lets you hear them.':'OffBeat сравнивает каждую точку NISAR с соседями того же класса покрова, отмечает выбившиеся из ритма и даёт их услышать.',
    'The tour takes about two minutes and uses real NISAR measurements.':'Тур занимает около двух минут и идёт по настоящим измерениям NISAR.',
    'Take the tour':'Пройти тур',
    'Explore the map':'Открыть карту',
    'NISAR measurements are available at the marked demo sites. Search the archive at the map centre for source acquisitions elsewhere.':'Измерения NISAR доступны на отмеченных демоучастках. Для других мест можно найти исходные съёмки через поиск архива в центре карты.',
    'No prepared NISAR series at this location. Select a marked demo site; the basemap and optical mosaic provide geographic context.':'В этой точке нет подготовленного ряда NISAR. Выберите отмеченный демоучасток; фон карты и оптическая мозаика служат географическим контекстом.',
    'Peer deviations and curve shapes are candidates for investigation, not confirmed events. Sparse samples do not define event areas. The light map shows NISAR sample locations; the optical map shows Esri context or a selected Sentinel-2 image with cloud and missing-data masks. Measured HH/HV are shown in the charts. Missing and quality-rejected measurements remain unavailable.':'Отклонения от соседей и формы кривых — кандидаты для проверки, а не подтверждённые события. Разреженные точки измерений не задают площадь события. Светлая карта показывает расположение образцов NISAR; оптическая карта — контекст Esri или выбранный снимок Sentinel-2 с масками облаков и пропусков. Измеренные HH/HV показаны на графиках. Отсутствующие и отклонённые по качеству измерения остаются недоступными.',
    'HV drop':'Снижение HV', 'HH jump':'Рост HH', 'Slow drift':'Плавный дрейф', 'Step':'Скачок',
    'Downward HV shift. Cause requires independent checks.':'Снижение HV. Причина требует независимой проверки.', 'Upward HH shift with limited HV change. Flooding unverified.':'Рост HH при небольшом изменении HV. Затопление не подтверждено.', 'Displacement trend. Ground motion requires validated time series.':'Тенденция смещения. Движение грунта требует проверки по временному ряду.', 'Displacement step. Event attribution unverified.':'Скачок смещения. Причина не подтверждена.',
    'Peers keep the beat, the pixel plays its HV curve.':'Соседние точки задают ритм, а пиксель воспроизводит кривую HV.', 'Water labels unavailable.':'Подписи водных объектов недоступны.', 'Unavailable':'Недоступно',
    'Sentinel-1 OPERA DISP-S1, short-wavelength relative LOS, cm; + toward satellite (':'Sentinel-1 OPERA DISP-S1, относительное смещение по линии визирования, см; + к спутнику (',
    'source and quality':'источник и качество',
    'Common reference date; locally filtered. Uncorrected atmosphere; not vertical motion or a validated subsidence rate.':'Общая опорная дата; данные локально отфильтрованы. Влияние атмосферы не устранено; это не вертикальное смещение и не подтверждённая скорость оседания.',
    'Suggested places to investigate':'Предлагаем изучить',
    "Strongest measured deviations from same-class neighbours in prepared sites, on each site's latest date. Candidates require verification; the cause is unknown.":'Самые сильные измеренные отклонения от соседей того же класса на подготовленных участках, на последнюю дату каждого участка. Это кандидаты для проверки; причина неизвестна.',
    'No prepared samples exceed the threshold, or valid peer data are unavailable.':'Нет подготовленных точек выше порога или нет пригодных данных для сравнения.',
    'Dense HV peer deviation · 2026-09-28':'Плотное отклонение HV от соседей · 2026-09-28',
    '20 m measured samples, fixed 2026-09-28. Full 1 km peer radius required; missing edges are transparent. WorldCover 2021.':'Измерения 20 м за 28.09.2026. Нужна полная окрестность 1 км; края без данных прозрачны. WorldCover 2021.',
    'Source and limitations':'Источник и ограничения',
    'GUNW quality and sources':'Качество и источники GUNW',
    'First three GUNW pairs: ascending 0/1024, descending 0/1024 points pass all three pair masks. A continuous rate cannot be estimated from these pairs.':'Первые три пары GUNW: в восходящем и нисходящем направлениях все фильтры проходят 0 из 1024 точек. По этим парам нельзя оценить непрерывную скорость.',
    'Later-pair quality and sources':'Качество и источники последующих пар',
    'Later segments: 275 ascending and 68 descending points pass their respective pair masks. Dates differ; reference stability and velocity remain unverified.':'В последующих отрезках маски всех пар проходят 275 восходящих и 68 нисходящих точек. Даты различаются; устойчивость опоры и скорость не проверены.',
    'Inspect nearby GNSS station MMX1':'Открыть ближайшую станцию GNSS MMX1',
    'GNSS MMX1 vertical position change, cm, since 2025-12-17 (IGS20)':'Изменение вертикального положения GNSS MMX1, см, с 17.12.2025 (IGS20)',
    'Independent daily GNSS, not NISAR line of sight. Nearest sampled radar point is about 21 m away and fails some GUNW quality checks; no direct validation or stable reference is established.':'Независимые ежедневные измерения GNSS, не линия визирования NISAR. Ближайшая радарная точка находится примерно в 21 м и не проходит часть проверок GUNW; прямое подтверждение и стабильная опора не установлены.',
    'GNSS source and quality':'Источник и качество GNSS',
    'Skip to the map':'Перейти к карте', 'OffBeat - NISAR change finder':'OffBeat — поиск изменений NISAR',
    'Take the tour':'Обзор', 'Map':'Карта', 'Pixel card':'Карточка пикселя', 'Top anomalies':'Основные аномалии', 'How it works':'Как это работает', 'NISAR data guide':'Справка по данным NISAR',
    'Location search':'Поиск места', 'Search':'Найти', 'Name in any language or coordinates':'Название на любом языке или координаты',
    'Search names in any language. Coordinates: latitude, longitude. Names are sent to Open-Meteo, with Photon / Komoot as fallback.':'Ищите названия на любом языке или введите координаты: широта, долгота. Запрос отправляется в Open-Meteo; при необходимости используются Photon / Komoot.',
    'Explore the world':'Исследовать мир', 'World':'Мир', 'Europe':'Европа', 'Africa':'Африка', 'Asia':'Азия', 'Oceania':'Океания', 'Americas':'Америка',
    'NASA NISAR imagery where available. Coverage gaps remain transparent. Search anywhere for source acquisitions.':'Снимки NASA NISAR показаны там, где доступны. Пропуски покрытия прозрачны. Поиск исходных снимков доступен для любой точки.',
    'Prepared measurement series:':'Подготовленные ряды измерений:', 'Layers':'Слои', 'Local measured HV overlay (optional)':'Локальный слой измерений HV', 'Measured NISAR samples':'Измерения NISAR', 'WorldCover classes':'Классы WorldCover', 'Map labels':'Подписи на карте', 'This site':'Этот участок', 'Threshold':'Порог', 'Show pixels with |z| >=':'Показать пиксели с |z| ≥', 'Change styles':'Типы изменений',
    'Loading measured data...':'Загрузка измерений...', 'NISAR sources and granule IDs':'Источники NISAR и идентификаторы гранул', 'Processing and limitations':'Обработка и ограничения',
    'OffBeat Tour -':'Обзор OffBeat —', 'Play the pixel':'Прослушать пиксель', '< Back':'< Назад', 'Next >':'Далее >', 'Close':'Закрыть',
    'Off-Beat map -':'Карта OffBeat —', 'Optical observation:':'Оптический снимок:', 'Context mosaic (date varies)':'Обзорная мозаика (даты различаются)',
    'Context imagery is not date-matched validation.':'Обзорные снимки не являются проверкой на соответствующую дату.', 'Esri context mosaic: dates vary, not date-matched validation.':'Обзорная мозаика Esri: даты различаются; это не проверка на соответствующую дату.',
    'Measured samples: grey in step, blue below and red above their same-class neighbours':'Измерения: серый — как у соседей того же класса, синий — ниже, красный — выше',
    'Measured samples: grey in step, blue below and red above their same-class neighbours (|z| over the threshold)':'Измерения: серый — как у соседей того же класса, синий — ниже, красный — выше (|z| выше порога)',
    'NISAR archive':'Архив NISAR', 'Search at map centre':'Искать в центре карты', 'Find ASF acquisitions and source files for the point at the centre of the map.':'Найти снимки ASF и исходные файлы для точки в центре карты.', 'Load more':'Показать ещё',
    'Pixel card -':'Карточка пикселя —', 'click the map':'нажмите на карту', 'WorldCover class':'Класс WorldCover', 'Peers':'Соседи', 'Style':'Тип', 'Since':'С', 'Location':'Координаты', 'GUNW quality':'Качество GUNW',
    'Backscatter, dB - HH':'Обратное рассеяние, дБ — HH', 'peers':'соседи', 'Apparent relative LOS change, cm (GUNW); + toward sensor':'Видимое относительное изменение по линии визирования, см (GUNW); + к спутнику',
    'Stop':'Остановить', 'Ranked curve-shape candidates':'Предполагаемые изменения формы кривой', 'Most off-beat samples':'Самые выбившиеся точки', 'Departure':'Отклонение', 'Sample':'Точка', 'Below neighbours':'Ниже соседей', 'Above neighbours':'Выше соседей', 'Shape':'Форма', 'Samples / area':'Измерения / площадь', 'Latest |z|':'Последний |z|', 'Latest z':'Последний z', 'Shift date':'Дата сдвига', 'How OffBeat finds a pixel out of step':'Как OffBeat находит отклоняющийся пиксель',
    'No classified shape':'Форма не определена', 'No prepared measurement series here':'Для этой точки нет подготовленного ряда измерений', 'No classified shape passes |z| >= 2.5.':'Нет определённых форм с |z| ≥ 2,5.', 'Sound on':'Звук включён', 'Sound off':'Звук выключен', 'Loading…':'Загрузка…', 'Source: no measurements loaded':'Источник: измерения не загружены',
    'These cases show measured NISAR HH/HV at sparse sample locations. Each GUNW result uses one actual acquisition pair; rejected samples remain unavailable. Backscatter peers are sampled locations of the same historical WorldCover 2021 class within 1 km; the band is median ± 2 × 1.4826 MAD, with at least 10 valid peers.':'Здесь показаны измерения NISAR HH/HV в отдельных точках. Каждый результат GUNW получен по одной реальной паре снимков; отбракованные измерения недоступны. Соседние точки обратного рассеяния относятся к тому же историческому классу WorldCover 2021 и находятся в радиусе 1 км; полоса — медиана ± 2 × 1,4826 MAD при наличии не менее 10 пригодных соседних измерений.',
    'GUNW is referenced to one coherent location in the same connected component. Ionospheric phase is removed; troposphere and tides remain. The reference is not proven stable. This apparent LOS change is not a subsidence rate or vertical displacement. The first epoch is zero by definition.':'GUNW отсчитывается от одной когерентной точки в той же связной области. Ионосферная фаза удалена; влияние тропосферы и приливов сохраняется. Стабильность опорной точки не подтверждена. Видимое изменение по линии визирования не является скоростью оседания или вертикальным смещением. Первой эпохе по определению присвоен ноль.',
    'Peer deviations and curve shapes are exploratory candidates, not confirmed events. Sparse sample points do not define event areas. The global NASA browse mosaic has its own dates and brightness scale, separate from calibrated HH/HV charts. The optical selector offers dated Sentinel-2 observations with cloud and nodata masks; the Esri mosaic remains geographic context. Missing and rejected measurements remain unavailable.':'Отклонения от соседних точек и формы кривых указывают на возможные, но не подтверждённые события. Редкие точки измерений не определяют площадь события. Глобальная обзорная мозаика NASA имеет собственные даты и шкалу яркости, отдельные от калиброванных графиков HH/HV. В списке оптических наблюдений доступны снимки Sentinel-2 с масками облаков и отсутствующих данных; мозаика Esri служит географическим фоном. Отсутствующие и отбракованные измерения недоступны.'
  };
  // Match the punctuation normalization performed by text98, including text inserted later.
  const punctuation={'–':'-','—':'-','−':'-','·':',','≤':'<=','≥':'>=','±':'+/-','×':'x','²':'2','…':'...','©':'(c)','°':' deg','µ':'u','σ':'sd','Δ':'d','→':'->','←':'<-','≈':'~','′':"'",'″':'"','«':'"','»':'"','▶':'>','■':''};
  const normalize=value=>value.replace(/[\s\u00a0]*·[\s\u00a0]*/g, ', ').replace(/[–—−·≤≥±×²…©°µσΔ→←≈′″«»▶■]/g, c=>punctuation[c]);
  const normalizedTranslations=Object.fromEntries(Object.entries(translations).map(([en,ru])=>[normalize(en),normalize(ru)]));
  const key='offbeat.language.v1', originals=new WeakMap();
  let lang='en';
  try { if (localStorage.getItem(key)==='ru') lang='ru'; } catch (_) {}
  const button=document.getElementById('language-switch');
  function translate(value) {
    const match=value.match(/^(\s*)([\s\S]*?)(\s*)$/), core=match[2];
    let translated=normalizedTranslations[normalize(core)];
    if (!translated) translated=core.replace(/^Measured HH\/HV on (\d+) dates; exploratory peer deviations and curve shapes\. Event cause unverified; GUNW remains separate\.$/, 'Измерения HH/HV за $1 дат; отклонения от соседей и формы кривых требуют проверки. Причина не подтверждена; GUNW рассматривается отдельно.')
      .replace(/^Scale: (.+) m\/px \| Approx\. viewing altitude: (.+)$/, 'Масштаб: $1 м/пикс. | Примерная высота обзора: $2')
      .replace(/^(\d+) valid HV samples at latest date; same class, ≤1 km$/, '$1 пригодных измерений HV на последнюю дату; тот же класс, ≤1 км');
    return match[1]+translated+match[3];
  }
  function text(node) {
    if (!node.parentElement || node.parentElement.closest('script, style, .leaflet-container, #place-results, #archive-results')) return;
    let original=originals.get(node);
    if (!original || (node.nodeValue!==original.en && node.nodeValue!==original.ru)) {
      original={en:normalize(node.nodeValue),ru:normalize(translate(node.nodeValue))}; originals.set(node,original);
    }
    const next=original[lang]; if (node.nodeValue!==next) node.nodeValue=next;
  }
  function walk(root) {
    if (root.nodeType===Node.TEXT_NODE) { text(root); return; }
    if (root.nodeType!==Node.ELEMENT_NODE && root.nodeType!==Node.DOCUMENT_NODE) return;
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT); while (walker.nextNode()) text(walker.currentNode);
  }
  function render() {
    document.documentElement.lang=lang; walk(document.body);
    button.textContent=lang==='en'?'Русский':'English';
    const query=document.getElementById('place-query');
    query.placeholder=lang==='ru'?translations['Name in any language or coordinates']:'Name in any language or coordinates';
    query.setAttribute('aria-label',lang==='ru'?translations['Location search']:'Location search');
  }
  button.addEventListener('click',()=>{lang=lang==='en'?'ru':'en';try{localStorage.setItem(key,lang);}catch(_){} render();});
  new MutationObserver(records=>{for(const record of records){if(record.type==='characterData') text(record.target); else for(const node of record.addedNodes) walk(node);}}).observe(document.body,{subtree:true,childList:true,characterData:true});
  render();
})();
